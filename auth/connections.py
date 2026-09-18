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
from database.models import GoogleHealthConnection, User
from services.google_health.client import get_health_user_id

# Refresh a bit before the token actually expires, not exactly at the
# deadline - a token valid for 5 more seconds could expire mid-flight
# between this check and the API call that's about to use it.
_EXPIRY_SAFETY_MARGIN = timedelta(seconds=60)


def upsert_connection_from_tokens(session: Session, tokens: dict) -> GoogleHealthConnection:
    """tokens: exchange_code()'s return value.

    Looks up the Google account's stable identity (healthUserId) using
    the access token we just got, not get_valid_access_token() below -
    at this exact moment the row we're about to find or create doesn't
    exist yet to read a token back out of.

    provider_user_id is the find-or-create key: an existing row means
    this is a reconnect (tokens/status updated in place, not a new row);
    no existing row means a brand new WorldWalker user, created together
    with their first connection.
    """
    provider_user_id = get_health_user_id(access_token=tokens["access_token"])
    expires_at = datetime.fromtimestamp(tokens["obtained_at"] + tokens["expires_in"], tz=timezone.utc)

    connection = (
        session.query(GoogleHealthConnection).filter_by(provider_user_id=provider_user_id).one_or_none()
    )

    if connection is None:
        user = User()
        session.add(user)
        session.flush()  # assigns user.id before the connection references it
        connection = GoogleHealthConnection(user_id=user.id, provider_user_id=provider_user_id)
        session.add(connection)
        print(f"🔐 auth: new WorldWalker user created (provider_user_id={provider_user_id})")
    else:
        print(f"🔐 auth: existing connection found, reconnecting (provider_user_id={provider_user_id})")

    connection.access_token = tokens["access_token"]
    connection.refresh_token = tokens["refresh_token"]
    connection.token_expires_at = expires_at
    connection.scopes = tokens.get("scope")
    connection.status = "active"
    connection.disconnected_at = None

    session.flush()
    return connection


def get_active_connection(session: Session) -> GoogleHealthConnection:
    connection = session.query(GoogleHealthConnection).filter_by(status="active").one_or_none()
    if connection is None:
        raise RuntimeError("No active Google Health connection - the user needs to click Connect first.")
    return connection


def get_valid_access_token(session: Session, force_refresh: bool = False) -> str:
    """A currently-usable access token for the (sole) active connection,
    refreshing and persisting a new one first if the stored one is
    expired (or force_refresh=True forces it regardless - used after a
    401 despite this function saying the token looked fine, e.g. the
    user revoked access out-of-band since our last check).

    If Google rejects the refresh itself (the refresh_token is dead -
    revoked, or expired from 6 months of inactivity), the connection is
    disconnected here rather than left silently broken for every future
    call to keep failing against."""
    connection = get_active_connection(session)

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
