# tests/test_auth_router.py
# The Google OAuth flow's two HTTP endpoints:
#   - POST /auth/google/start: JWT-protected, issues a state bound to the
#     logged-in user.
#   - GET /auth/google/callback: NOT JWT-protected (Google's redirect
#     can't carry a bearer token) - must recover the WorldWalker user_id
#     from that state before it will exchange a code or save anything.
# Tested against a minimal FastAPI app (not app.py) - the auth module
# shouldn't need the webhook secret pulled in just to test these routes.
#
# Persistence (auth/connections.py, auth/oauth_state.py, database/session.py)
# is mocked out here rather than hitting a real database - this file tests
# the HTTP-level orchestration (validate state -> exchange code -> save
# connection -> respond), not upsert_connection_from_tokens' or
# oauth_state's own logic, which tests/test_connections.py and
# tests/test_oauth_state.py already prove against real Postgres.
#
# get_current_user is faked via FastAPI's dependency_overrides instead of
# a real JWT/DB user, to keep this file's "no real database" approach.

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts.dependencies import get_current_user
from auth import connections, google_health_auth, oauth_state
from auth import router as router_module
from auth.router import router
from database.models import User

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _fake_current_user(user_id: uuid.UUID) -> User:
    user = User()
    user.id = user_id
    user.is_active = True
    return user


class _FakeSession:
    def commit(self):
        pass


class _FakeSessionLocal:
    def __enter__(self):
        return _FakeSession()

    def __exit__(self, *args):
        return False


def _mock_valid_state(monkeypatch, user_id: uuid.UUID | None = None) -> uuid.UUID:
    """The callback's state was valid and belonged to user_id (a fresh
    one if not given)."""
    user_id = user_id or uuid.uuid4()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(oauth_state, "consume_state", lambda session, state: user_id)
    return user_id


def _mock_successful_db_write(monkeypatch):
    """The success path also needs to save a connection before returning
    200 - fake the save itself (SessionLocal is already faked by
    _mock_valid_state)."""
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(connections, "upsert_connection_from_tokens", lambda session, user_id, tokens: None)


# --- POST /auth/google/start ---

def test_start_requires_authentication():
    response = client.post("/auth/google/start")
    assert response.status_code == 401


def test_start_issues_a_state_bound_to_the_logged_in_user(monkeypatch):
    user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(user_id)
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    seen_user_ids = []
    monkeypatch.setattr(
        oauth_state, "issue_state", lambda session, uid: seen_user_ids.append(uid) or "the-issued-state"
    )
    monkeypatch.setattr(google_health_auth, "_load_client", lambda: ("cid", "secret", "https://redirect.example"))

    response = client.post("/auth/google/start")

    assert response.status_code == 200
    assert "state=the-issued-state" in response.json()["auth_url"]
    assert seen_user_ids == [user_id]


def test_start_calls_issue_state_fresh_each_time(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(google_health_auth, "_load_client", lambda: ("cid", "secret", "https://redirect.example"))
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(uuid.uuid4())

    issued = iter(["state-1", "state-2"])
    monkeypatch.setattr(oauth_state, "issue_state", lambda session, uid: next(issued))

    first = client.post("/auth/google/start").json()["auth_url"]
    second = client.post("/auth/google/start").json()["auth_url"]

    assert "state=state-1" in first
    assert "state=state-2" in second


# --- GET /auth/google/callback ---

def test_callback_rejects_missing_state():
    response = client.get("/auth/google/callback", params={"code": "abc"})
    assert response.status_code == 400


def test_callback_rejects_an_invalid_or_expired_state(monkeypatch):
    # oauth_state.consume_state() already collapses "unknown", "expired",
    # and "already used" into the same None - see tests/test_oauth_state.py
    # for that distinction proven at the source. The callback just needs
    # to treat None as a rejection, whatever the reason.
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(oauth_state, "consume_state", lambda session, state: None)
    calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: calls.append(code))

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "bad-state"})

    assert response.status_code == 400
    assert calls == []


def test_callback_rejects_missing_code(monkeypatch):
    _mock_valid_state(monkeypatch)
    response = client.get("/auth/google/callback", params={"state": "real-state"})
    assert response.status_code == 400


def test_callback_success_page_redirects_home_after_a_delay(monkeypatch):
    _mock_valid_state(monkeypatch)
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})
    _mock_successful_db_write(monkeypatch)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    # A plain meta-refresh - no JS framework needed for a one-shot delayed
    # redirect back to "/".
    assert '<meta http-equiv="refresh" content="3;url=/">' in response.text


def test_callback_recovers_the_user_id_from_state_and_saves_that_users_connection(monkeypatch):
    user_id = _mock_valid_state(monkeypatch)
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {"access_token": "AT"})
    save_calls = []
    monkeypatch.setattr(
        connections,
        "upsert_connection_from_tokens",
        lambda session, uid, tokens: save_calls.append((uid, tokens)),
    )

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 200
    assert save_calls == [(user_id, {"access_token": "AT"})]


def test_callback_consumes_the_state_it_was_given(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    seen_states = []
    monkeypatch.setattr(
        oauth_state, "consume_state", lambda session, state: seen_states.append(state) or uuid.uuid4()
    )
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})
    monkeypatch.setattr(connections, "upsert_connection_from_tokens", lambda session, user_id, tokens: None)

    client.get("/auth/google/callback", params={"code": "abc", "state": "the-real-state"})

    assert seen_states == ["the-real-state"]


def test_callback_surfaces_google_error_without_exchanging(monkeypatch):
    calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: calls.append(code))

    response = client.get("/auth/google/callback", params={"error": "access_denied"})

    assert response.status_code == 400
    assert calls == []


def test_callback_returns_error_when_exchange_fails(monkeypatch):
    _mock_valid_state(monkeypatch)

    def failing_exchange(code):
        raise RuntimeError("token endpoint said no")

    monkeypatch.setattr(google_health_auth, "exchange_code", failing_exchange)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 502


def test_callback_returns_409_when_the_google_account_is_linked_elsewhere(monkeypatch):
    _mock_valid_state(monkeypatch)
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})

    def rejected_save(session, user_id, tokens):
        raise ValueError("This Google account is already connected to a different WorldWalker account.")

    monkeypatch.setattr(connections, "upsert_connection_from_tokens", rejected_save)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 409


def test_callback_returns_error_when_saving_the_connection_fails(monkeypatch):
    _mock_valid_state(monkeypatch)
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})

    def failing_save(session, user_id, tokens):
        raise RuntimeError("could not reach the database")

    monkeypatch.setattr(connections, "upsert_connection_from_tokens", failing_save)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 502


# --- GET /auth/google/status ---

def test_status_requires_authentication():
    response = client.get("/auth/google/status")
    assert response.status_code == 401


def test_status_reports_connected_true_when_the_user_has_an_active_connection(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(uuid.uuid4())
    monkeypatch.setattr(connections, "get_active_connection", lambda session, user_id: object())

    response = client.get("/auth/google/status")

    assert response.status_code == 200
    assert response.json() == {"connected": True}


def test_status_reports_connected_false_when_there_is_no_active_connection(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(uuid.uuid4())

    def no_active_connection(session, user_id):
        raise RuntimeError("no active connection")

    monkeypatch.setattr(connections, "get_active_connection", no_active_connection)

    response = client.get("/auth/google/status")

    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_status_checks_the_logged_in_users_own_connection(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    user_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(user_id)

    seen_user_ids = []

    def get_active_connection_for(session, uid):
        seen_user_ids.append(uid)
        return object()

    monkeypatch.setattr(connections, "get_active_connection", get_active_connection_for)

    client.get("/auth/google/status")

    assert seen_user_ids == [user_id]


# --- POST /auth/google/disconnect ---

def test_disconnect_requires_authentication():
    response = client.post("/auth/google/disconnect")
    assert response.status_code == 401


def test_disconnect_returns_404_when_not_connected(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    current_user = _fake_current_user(uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: current_user

    def no_active_connection(session, user_id):
        raise RuntimeError("no active connection")

    monkeypatch.setattr(connections, "get_active_connection", no_active_connection)

    response = client.post("/auth/google/disconnect")

    assert response.status_code == 404


def test_disconnect_calls_disconnect_on_the_current_users_own_connection(monkeypatch):
    fake_connection = object()
    current_user = _fake_current_user(uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: current_user
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    seen_user_ids = []

    def get_active_connection_for(session, user_id):
        seen_user_ids.append(user_id)
        return fake_connection

    monkeypatch.setattr(connections, "get_active_connection", get_active_connection_for)
    calls = []
    monkeypatch.setattr(connections, "disconnect", lambda session, connection: calls.append(connection))

    response = client.post("/auth/google/disconnect")

    assert response.status_code == 200
    assert calls == [fake_connection]
    assert seen_user_ids == [current_user.id]


def test_disconnect_never_touches_another_users_connection(monkeypatch):
    """The actual per-user scoping proof: two different logged-in users
    each hitting /auth/google/disconnect only ever reach their own
    connection - never the other's."""
    user_a_id, user_b_id = uuid.uuid4(), uuid.uuid4()
    connection_by_user = {user_a_id: "connection-a", user_b_id: "connection-b"}

    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(connections, "get_active_connection", lambda session, user_id: connection_by_user[user_id])
    disconnected = []
    monkeypatch.setattr(connections, "disconnect", lambda session, connection: disconnected.append(connection))

    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(user_a_id)
    client.post("/auth/google/disconnect")

    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(user_b_id)
    client.post("/auth/google/disconnect")

    assert disconnected == ["connection-a", "connection-b"]
