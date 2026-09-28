# auth/connections.py
# Everything that reads or writes a GoogleHealthConnection row: creating
# one from a fresh OAuth exchange, keeping its access token valid, and
# disconnecting it. auth/google_health_auth.py stays pure OAuth-HTTP -
# this module is what decides *when* to call it and what to do with the
# result.
#
# upsert_connection_from_tokens() takes an already-open session and
# doesn't commit it - it's called from inside auth/router.py's callback,
# which owns the transaction for that whole request. get_valid_access_token()
# and disconnect() commit their own changes - both are always used
# standalone (not as part of a larger multi-step request), so there's no
# outer transaction for them to defer to.

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from auth import google_health_auth
from database.models import GoogleHealthConnection
from services.google_health.client import get_health_user_id

# Refresh a bit before the token actually expires, not exactly at the
# deadline - a token valid for 5 more seconds could expire mid-flight
# between this check and the API call that's about to use it.
_EXPIRY_SAFETY_MARGIN = timedelta(seconds=60)


def upsert_connection_from_tokens(session: Session, user_id, tokens: dict) -> GoogleHealthConnection:
    """tokens: exchange_code()'s return value. user_id: the WorldWalker
    user this OAuth flow was started for - recovered from the OAuth state
    by the caller (auth/router.py's callback), never from anything Google
    tells us. WorldWalker identity is always the source of truth here:
    this links Google's account to an EXISTING WorldWalker user, it never
    creates one.

    Looks up the Google account's stable identity (healthUserId) using
    the access token we just got, not get_valid_access_token() below -
    at this exact moment the row we're about to find or create doesn't
    exist yet to read a token back out of.

    user_id is the find-or-create key: an existing row for this user
    means this is a reconnect (tokens/status/provider_user_id updated in
    place, not a new row) - possibly with a different Google account than
    last time, which is fine. Raises ValueError if that Google account is
    already linked to a *different* WorldWalker user - one Google account
    can never back two WorldWalker accounts.
    """
    provider_user_id = get_health_user_id(access_token=tokens["access_token"])
    expires_at = datetime.fromtimestamp(tokens["obtained_at"] + tokens["expires_in"], tz=timezone.utc)

    other_owner = (
        session.query(GoogleHealthConnection)
        .filter(GoogleHealthConnection.provider_user_id == provider_user_id)
        .filter(GoogleHealthConnection.user_id != user_id)
        .one_or_none()
    )
    if other_owner is not None:
        raise ValueError("This Google account is already connected to a different WorldWalker account.")

    connection = session.query(GoogleHealthConnection).filter_by(user_id=user_id).one_or_none()

    if connection is None:
        connection = GoogleHealthConnection(user_id=user_id, provider_user_id=provider_user_id)
        session.add(connection)
        print(f"🔐 auth: new Google Health connection for user {user_id} (provider_user_id={provider_user_id})")
    else:
        connection.provider_user_id = provider_user_id
        print(f"🔐 auth: reconnecting Google Health for user {user_id} (provider_user_id={provider_user_id})")

    connection.access_token = tokens["access_token"]
    connection.refresh_token = tokens["refresh_token"]
    connection.token_expires_at = expires_at
    connection.scopes = tokens.get("scope")
    connection.status = "active"
    connection.disconnected_at = None

    session.flush()
    return connection


def get_active_connection(session: Session, user_id, for_update: bool = False) -> GoogleHealthConnection:
    """This user's own active connection, and only this user's - every
    caller that acts on a specific user's behalf (accessing, refreshing,
    or disconnecting it) must go through here, never a query that could
    return another user's row.

    for_update: SELECT ... FOR UPDATE, so the row is locked for the rest
    of this transaction - see get_valid_access_token() below, the one
    caller that actually needs it."""
    query = session.query(GoogleHealthConnection).filter_by(user_id=user_id, status="active")
    if for_update:
        query = query.with_for_update()
    connection = query.one_or_none()
    if connection is None:
        raise RuntimeError("No active Google Health connection for this user - they need to click Connect first.")
    return connection


def _any_active_connection(session: Session) -> GoogleHealthConnection:
    """The sole active connection, whoever it belongs to - only for the
    handful of callers with no specific logged-in user to scope to yet
    (the incoming webhook, the pre-login connect banner). Never use this
    to act on a connection on a particular user's behalf - that's
    get_active_connection()."""
    connection = session.query(GoogleHealthConnection).filter_by(status="active").one_or_none()
    if connection is None:
        raise RuntimeError("No active Google Health connection - the user needs to click Connect first.")
    return connection


def get_active_user_id(session: Session):
    """The real WorldWalker User.id (UUID) behind *some* active Google
    Health connection - single-tenant fallback for callers with no
    specific logged-in user yet, see _any_active_connection(). Raises the
    same RuntimeError when nobody's connected yet."""
    return _any_active_connection(session).user_id


def get_user_id_for_provider_user_id(session: Session, provider_user_id: str):
    """The WorldWalker user_id behind a specific Google account
    (healthUserId) - how an incoming webhook notification, which only
    ever carries Google's own identity, is mapped back to the one
    WorldWalker user it belongs to. Never "whichever connection happens
    to be active" - see services/google_health/webhook.py."""
    connection = (
        session.query(GoogleHealthConnection)
        .filter_by(provider_user_id=provider_user_id, status="active")
        .one_or_none()
    )
    if connection is None:
        raise RuntimeError(f"No active WorldWalker connection for Google account {provider_user_id!r}.")
    return connection.user_id


def get_valid_access_token(session: Session, user_id, force_refresh: bool = False) -> str:
    """A currently-usable access token for this user's own active
    connection, refreshing and persisting a new one first if the stored
    one is expired (or force_refresh=True forces it regardless - used
    after a 401 despite this function saying the token looked fine, e.g.
    the user revoked access out-of-band since our last check).

    Google's webhook can fire several notifications for the same user
    within milliseconds of each other (see services/google_health/
    webhook.py - each one becomes its own concurrent background task), so
    more than one request can land here for the same connection at once.
    Without a lock, two concurrent "expired, refresh it" requests both go
    to Google's token endpoint at the same time - a real race that was
    producing intermittent 401 CREDENTIALS_MISSING responses from
    health.googleapis.com even though the connection's tokens were fine.
    with_for_update() (see get_active_connection) makes the check-then-
    refresh below atomic across concurrent transactions: the second
    request blocks until the first commits, then re-checks and simply
    reuses the token the first request just refreshed, instead of racing
    Google's token endpoint a second time.

    If Google rejects the refresh itself (the refresh_token is dead -
    revoked, or expired from 6 months of inactivity), the connection is
    disconnected here rather than left silently broken for every future
    call to keep failing against."""
    connection = get_active_connection(session, user_id, for_update=True)

    still_valid = (
        not force_refresh
        and connection.token_expires_at is not None
        and connection.token_expires_at > datetime.now(timezone.utc) + _EXPIRY_SAFETY_MARGIN
    )
    if still_valid:
        return connection.access_token

    try:
        new_tokens = google_health_auth.refresh_access_token(connection.refresh_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            disconnect(session, connection, reason="refresh_token_rejected_by_google")
        raise

    connection.access_token = new_tokens["access_token"]
    connection.token_expires_at = datetime.fromtimestamp(
        new_tokens["obtained_at"] + new_tokens["expires_in"], tz=timezone.utc
    )
    session.commit()
    print(f"🔐 auth: access token refreshed and persisted for connection {connection.id}")

    if not connection.access_token:
        # Should be unreachable - Google's token endpoint always returns
        # an access_token on 200, and raise_for_status() above already
        # catches a non-200. Fail loudly here rather than let a blank
        # Authorization header reach Google as a confusing CREDENTIALS_MISSING.
        raise RuntimeError(f"Refreshed token for connection {connection.id} came back empty")
    return connection.access_token


def disconnect(session: Session, connection: GoogleHealthConnection, reason: str = "user_requested") -> None:
    """Revokes the connection with Google (best-effort - Google returns
    200 even for an already-dead token, so failures here are almost
    always something else, e.g. a network blip) and always nulls the
    stored tokens locally regardless of whether that call succeeded: the
    point is that this credential must stop being usable, and a null
    value can't be misused even if some other code path forgets to check
    status first.

    reason is log-only, not persisted - both a user-initiated disconnect
    and an auto-disconnect from a dead refresh token end up with the same
    status, since the remedy is identical either way (reconnect). A
    queryable disconnect_reason column is easy to add later if that
    signal ever needs to be more than a log line.
    """
    if connection.refresh_token:
        try:
            google_health_auth.revoke_token(connection.refresh_token)
        except Exception as e:
            print(f"🔐 auth: revoke call to Google failed, disconnecting locally anyway: {e}")

    connection.status = "disconnected"
    connection.access_token = None
    connection.refresh_token = None
    connection.disconnected_at = datetime.now(timezone.utc)
    session.commit()
    print(f"🔐 auth: connection {connection.id} disconnected (reason={reason})")
