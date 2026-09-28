# tests/test_notifications_router.py
# notifications/router.py's three JWT-protected routes. Tested against a
# minimal FastAPI app (not app.py), with notifications/email_config.py's
# functions monkeypatched out rather than hitting a real database - same
# "HTTP-level orchestration only" approach as tests/test_auth_router.py;
# notifications/email_config.py's own logic is proven for real against
# Postgres in tests/test_email_config.py.
#
# The main thing every test here guards: a response never carries back
# smtp_host/smtp_username/smtp_password, only configured: true/false.

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts.dependencies import get_current_user
from database.models import User
from notifications import email_config
from notifications import router as router_module
from notifications.router import router

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


def _login_as(user_id: uuid.UUID | None = None) -> uuid.UUID:
    user_id = user_id or uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: _fake_current_user(user_id)
    return user_id


# --- PUT /notifications/email-config ---

def test_put_requires_authentication():
    response = client.put("/notifications/email-config", json={
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "smtp_username": "walker@example.com", "smtp_password": "app-password",
    })
    assert response.status_code == 401


def test_put_saves_config_for_the_logged_in_user_only(monkeypatch):
    user_id = _login_as()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    seen = {}

    def fake_upsert(session, uid, smtp_host, smtp_port, smtp_username, smtp_password):
        seen["user_id"] = uid
        seen["smtp_host"] = smtp_host
        seen["smtp_port"] = smtp_port
        seen["smtp_username"] = smtp_username
        seen["smtp_password"] = smtp_password

    monkeypatch.setattr(email_config, "upsert_config", fake_upsert)

    response = client.put("/notifications/email-config", json={
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "smtp_username": "walker@example.com", "smtp_password": "app-password",
    })

    assert response.status_code == 200
    assert response.json() == {"configured": True}
    assert seen["user_id"] == user_id
    assert seen["smtp_host"] == "smtp.gmail.com"
    assert seen["smtp_username"] == "walker@example.com"
    assert seen["smtp_password"] == "app-password"


def test_put_response_never_echoes_back_the_credentials(monkeypatch):
    _login_as()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(email_config, "upsert_config", lambda *a, **k: None)

    response = client.put("/notifications/email-config", json={
        "smtp_host": "smtp.gmail.com", "smtp_port": 587,
        "smtp_username": "walker@example.com", "smtp_password": "super-secret-password",
    })

    assert "super-secret-password" not in response.text
    assert "walker@example.com" not in response.text


# --- GET /notifications/email-config ---

def test_get_requires_authentication():
    response = client.get("/notifications/email-config")
    assert response.status_code == 401


def test_get_reports_configured_true_when_a_config_exists(monkeypatch):
    _login_as()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(email_config, "get_config", lambda session, user_id: object())

    response = client.get("/notifications/email-config")

    assert response.status_code == 200
    assert response.json() == {"configured": True}


def test_get_reports_configured_false_when_no_config_exists(monkeypatch):
    _login_as()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())
    monkeypatch.setattr(email_config, "get_config", lambda session, user_id: None)

    response = client.get("/notifications/email-config")

    assert response.status_code == 200
    assert response.json() == {"configured": False}


# --- DELETE /notifications/email-config ---

def test_delete_requires_authentication():
    response = client.delete("/notifications/email-config")
    assert response.status_code == 401


def test_delete_removes_this_users_config(monkeypatch):
    user_id = _login_as()
    monkeypatch.setattr(router_module, "SessionLocal", lambda: _FakeSessionLocal())

    seen = {}
    monkeypatch.setattr(email_config, "delete_config", lambda session, uid: seen.setdefault("user_id", uid) or True)

    response = client.delete("/notifications/email-config")

    assert response.status_code == 200
    assert response.json() == {"configured": False}
    assert seen["user_id"] == user_id
