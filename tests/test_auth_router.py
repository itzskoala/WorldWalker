# tests/test_auth_router.py
# The OAuth callback route: must validate the CSRF `state` param before
# ever exchanging a code, and must save a connection before reporting
# success. Tested against its own minimal FastAPI app (not
# services.fitbit_service.app) - the auth module shouldn't need Gradio or
# the webhook secret pulled in just to test the callback.
#
# Persistence (auth/connections.py, database/session.py) is mocked out
# here rather than hitting a real database - this file tests the
# callback's HTTP-level orchestration (validate state -> exchange code ->
# save connection -> respond), not upsert_connection_from_tokens' actual
# find-or-create logic, which tests/test_connections.py already proves
# against real Postgres.

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import connections, google_health_auth
from auth import router as router_module
from auth.router import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


class _FakeSession:
    def commit(self):
        pass


class _FakeSessionLocal:
    def __enter__(self):
        return _FakeSession()

    def __exit__(self, *args):
        return False


def _mock_successful_db_write(monkeypatch):
    """The success path (state valid, code exchanged) also needs to save
    a connection before returning 200 - fake both SessionLocal (so no
    real DB connection is attempted) and the save itself."""
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(connections, "upsert_connection_from_tokens", lambda session, tokens: None)


def test_callback_rejects_missing_state(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", set())
    calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: calls.append(code))

    response = client.get("/auth/google/callback", params={"code": "abc"})

    assert response.status_code == 400
    assert calls == []


def test_callback_rejects_mismatched_state(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})
    calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: calls.append(code))

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "wrong-state"})

    assert response.status_code == 400
    assert calls == []


def test_callback_rejects_missing_code(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})

    response = client.get("/auth/google/callback", params={"state": "real-state"})

    assert response.status_code == 400


def test_callback_success_page_redirects_home_after_a_delay(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})
    _mock_successful_db_write(monkeypatch)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    # A plain meta-refresh - no JS framework needed for a one-shot delayed
    # redirect back to "/" (the Gradio-mounted home page).
    assert '<meta http-equiv="refresh" content="3;url=/">' in response.text


def test_callback_exchanges_code_and_saves_the_connection_for_a_valid_state(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})
    exchange_calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: exchange_calls.append(code) or {"access_token": "AT"})
    save_calls = []
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(
        connections,
        "upsert_connection_from_tokens",
        lambda session, tokens: save_calls.append(tokens),
    )

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 200
    assert exchange_calls == ["abc"]
    assert save_calls == [{"access_token": "AT"}]


def test_callback_state_is_single_use(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})
    _mock_successful_db_write(monkeypatch)

    first = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})
    second = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert first.status_code == 200
    assert second.status_code == 400


def test_callback_surfaces_google_error_without_exchanging(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", set())
    calls = []
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: calls.append(code))

    response = client.get("/auth/google/callback", params={"error": "access_denied"})

    assert response.status_code == 400
    assert calls == []


def test_callback_returns_error_when_exchange_fails(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})

    def failing_exchange(code):
        raise RuntimeError("token endpoint said no")

    monkeypatch.setattr(google_health_auth, "exchange_code", failing_exchange)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 502


def test_callback_returns_error_when_saving_the_connection_fails(monkeypatch):
    monkeypatch.setattr(google_health_auth, "_pending_states", {"real-state"})
    monkeypatch.setattr(google_health_auth, "exchange_code", lambda code: {})
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    def failing_save(session, tokens):
        raise RuntimeError("could not reach the database")

    monkeypatch.setattr(connections, "upsert_connection_from_tokens", failing_save)

    response = client.get("/auth/google/callback", params={"code": "abc", "state": "real-state"})

    assert response.status_code == 502


def test_disconnect_returns_404_when_not_connected(monkeypatch):
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    def no_active_connection(session):
        raise RuntimeError("no active connection")

    monkeypatch.setattr(connections, "get_active_connection", no_active_connection)

    response = client.post("/auth/google/disconnect")

    assert response.status_code == 404


def test_disconnect_calls_disconnect_on_the_active_connection(monkeypatch):
    fake_connection = object()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(connections, "get_active_connection", lambda session: fake_connection)
    calls = []
    monkeypatch.setattr(connections, "disconnect", lambda session, connection: calls.append(connection))

    response = client.post("/auth/google/disconnect")

    assert response.status_code == 200
    assert calls == [fake_connection]
