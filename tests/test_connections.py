# tests/test_connections.py
# auth/connections.py's find-or-create, token-refresh, and disconnect
# logic - proven against real Postgres (see tests/test_database_models.py
# for why real Postgres, not SQLite - the constraints being relied on
# here don't behave identically on SQLite).
#
# connections.py's google_health_auth dependency is monkeypatched via
# connections.google_health_auth (module-attribute access, not a name
# import) - same convention as auth/router.py's tests.

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from auth import connections
from database.models import GoogleHealthConnection, User

FAKE_TOKENS = {
    "access_token": "fresh-access-token",
    "refresh_token": "fresh-refresh-token",
    "expires_in": 3600,
    "scope": "https://www.googleapis.com/auth/googlehealth.profile.readonly",
    "obtained_at": datetime(2026, 9, 17, tzinfo=timezone.utc).timestamp(),
}


def test_new_provider_user_id_creates_a_user_and_connection(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "new-google-user")

    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)

    assert connection.provider_user_id == "new-google-user"
    assert connection.access_token == "fresh-access-token"
    assert connection.refresh_token == "fresh-refresh-token"
    assert connection.status == "active"
    assert db_session.get(User, connection.user_id) is not None


def test_existing_provider_user_id_updates_the_same_connection_not_a_new_one(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "returning-google-user")
    first = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)
    first_id, first_user_id = first.id, first.user_id

    newer_tokens = {**FAKE_TOKENS, "access_token": "rotated-access-token"}
    second = connections.upsert_connection_from_tokens(db_session, newer_tokens)

    assert second.id == first_id
    assert second.user_id == first_user_id
    assert second.access_token == "rotated-access-token"

    count = (
        db_session.query(GoogleHealthConnection)
        .filter_by(provider_user_id="returning-google-user")
        .count()
    )
    assert count == 1


def test_reconnecting_clears_disconnected_state(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "was-disconnected-user")
    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)
    connection.status = "disconnected"
    connection.access_token = None
    connection.refresh_token = None
    connection.disconnected_at = datetime.now(timezone.utc)
    db_session.flush()

    reconnected = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)

    assert reconnected.status == "active"
    assert reconnected.disconnected_at is None
    assert reconnected.access_token == "fresh-access-token"


def test_token_expiry_is_computed_as_an_absolute_timestamp(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "expiry-check-user")

    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)

    expected = datetime.fromtimestamp(FAKE_TOKENS["obtained_at"] + FAKE_TOKENS["expires_in"], tz=timezone.utc)
    assert connection.token_expires_at == expected


def _create_connection_with_expiry(db_session, monkeypatch, provider_user_id, obtained_at):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: provider_user_id)
    tokens = {**FAKE_TOKENS, "obtained_at": obtained_at.timestamp()}
    return connections.upsert_connection_from_tokens(db_session, tokens)


def test_get_valid_access_token_returns_the_stored_token_when_not_expired(db_session, monkeypatch):
    _create_connection_with_expiry(db_session, monkeypatch, "valid-token-user", datetime.now(timezone.utc))
    calls = []
    monkeypatch.setattr(connections.google_health_auth, "refresh_access_token", lambda rt: calls.append(rt))

    token = connections.get_valid_access_token(db_session)

    assert token == "fresh-access-token"
    assert calls == []  # still valid - refreshing it would be wasteful


def test_get_valid_access_token_refreshes_when_expired(db_session, monkeypatch):
    _create_connection_with_expiry(
        db_session, monkeypatch, "expired-token-user", datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(
        connections.google_health_auth,
        "refresh_access_token",
        lambda rt: {
            "access_token": "rotated-access-token",
            "expires_in": 3600,
            "obtained_at": datetime.now(timezone.utc).timestamp(),
        },
    )

    token = connections.get_valid_access_token(db_session)

    assert token == "rotated-access-token"


def test_get_valid_access_token_persists_the_refreshed_token(db_session, monkeypatch):
    connection = _create_connection_with_expiry(
        db_session, monkeypatch, "persist-check-user", datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(
        connections.google_health_auth,
        "refresh_access_token",
        lambda rt: {
            "access_token": "rotated-access-token",
            "expires_in": 3600,
            "obtained_at": datetime.now(timezone.utc).timestamp(),
        },
    )

    connections.get_valid_access_token(db_session)
    db_session.expire_all()

    reloaded = db_session.get(GoogleHealthConnection, connection.id)
    assert reloaded.access_token == "rotated-access-token"
    assert reloaded.token_expires_at > datetime.now(timezone.utc)


def test_get_valid_access_token_forces_refresh_when_asked(db_session, monkeypatch):
    _create_connection_with_expiry(db_session, monkeypatch, "force-refresh-user", datetime.now(timezone.utc))
    calls = []
    monkeypatch.setattr(
        connections.google_health_auth,
        "refresh_access_token",
        lambda rt: calls.append(rt)
        or {"access_token": "forced-new-token", "expires_in": 3600, "obtained_at": datetime.now(timezone.utc).timestamp()},
    )

    token = connections.get_valid_access_token(db_session, force_refresh=True)

    assert token == "forced-new-token"
    assert calls == ["fresh-refresh-token"]


def test_get_valid_access_token_raises_when_no_active_connection(db_session):
    with pytest.raises(RuntimeError):
        connections.get_valid_access_token(db_session)


def test_get_valid_access_token_disconnects_when_refresh_token_is_rejected(db_session, monkeypatch):
    connection = _create_connection_with_expiry(
        db_session, monkeypatch, "dead-refresh-user", datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    monkeypatch.setattr(connections.google_health_auth, "revoke_token", lambda token: None)

    def rejected_refresh(refresh_token):
        request = httpx.Request("POST", "https://oauth2.googleapis.com/token")
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError("invalid_grant", request=request, response=response)

    monkeypatch.setattr(connections.google_health_auth, "refresh_access_token", rejected_refresh)

    with pytest.raises(httpx.HTTPStatusError):
        connections.get_valid_access_token(db_session)

    db_session.expire_all()
    reloaded = db_session.get(GoogleHealthConnection, connection.id)
    assert reloaded.status == "disconnected"
    assert reloaded.access_token is None
    assert reloaded.refresh_token is None


def test_disconnect_flips_status_and_nulls_tokens(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "disconnect-test-user")
    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)
    monkeypatch.setattr(connections.google_health_auth, "revoke_token", lambda token: None)

    connections.disconnect(db_session, connection)

    assert connection.status == "disconnected"
    assert connection.access_token is None
    assert connection.refresh_token is None
    assert connection.disconnected_at is not None


def test_disconnect_calls_revoke_with_the_refresh_token(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "revoke-call-user")
    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)
    calls = []
    monkeypatch.setattr(connections.google_health_auth, "revoke_token", lambda token: calls.append(token))

    connections.disconnect(db_session, connection)

    assert calls == ["fresh-refresh-token"]


def test_disconnect_proceeds_locally_even_if_revoke_call_fails(db_session, monkeypatch):
    monkeypatch.setattr(connections, "get_health_user_id", lambda access_token: "revoke-fails-user")
    connection = connections.upsert_connection_from_tokens(db_session, FAKE_TOKENS)

    def failing_revoke(token):
        raise RuntimeError("network error")

    monkeypatch.setattr(connections.google_health_auth, "revoke_token", failing_revoke)

    connections.disconnect(db_session, connection)  # must not raise

    assert connection.status == "disconnected"
