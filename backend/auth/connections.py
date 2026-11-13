# auth/connections.py

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from backend.auth import google_health_auth
from backend.database.models import GoogleHealthConnection
from backend.services.google_health.client import get_health_user_id

_EXPIRY_SAFETY_MARGIN = timedelta(seconds=60)

def upsert_connection_from_tokens(session: Session, user_id, tokens: dict) -> GoogleHealthConnection:
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
    if connection is None or connection.access_token is None or connection.refresh_token is None:
        raise RuntimeError("No active Google Health connection for this user - they need to click Connect first.")
    return connection


def _any_active_connection(session: Session) -> GoogleHealthConnection:
    connection = session.query(GoogleHealthConnection).filter_by(status="active").one_or_none()
    if connection is None:
        raise RuntimeError("No active Google Health connection - user needs to click Connect first.")
    return connection


def get_active_user_id(session: Session):
    return _any_active_connection(session).user_id


def get_user_id_for_provider_user_id(session: Session, provider_user_id: str):
    connection = (
        session.query(GoogleHealthConnection)
        .filter_by(provider_user_id=provider_user_id, status="active")
        .one_or_none()
    )
    if connection is None:
        raise RuntimeError(f"No active WorldWalker connection for Google account {provider_user_id!r}.")
    return connection.user_id


def get_valid_access_token(session: Session, user_id, force_refresh: bool = False) -> str:
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
        raise RuntimeError(f"Refreshed token for connection {connection.id} came back empty")
    return connection.access_token


def mark_synced(session: Session, user_id, until: datetime) -> None:
    connection = get_active_connection(session, user_id)
    connection.last_synced_at = until
    session.commit()


def disconnect(session: Session, connection: GoogleHealthConnection, reason: str = "user_requested") -> None:
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
