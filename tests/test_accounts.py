# tests/test_accounts.py
# Signup, login, protected routes, refresh, and token validation for the
# accounts/ login system. Runs against the real app (app.py includes
# accounts.router), with SessionLocal patched (see tests/conftest.py's
# patched_session fixture) so every DB write stays inside this test's own
# rolled-back transaction.

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from accounts import security
from accounts.service import signup as create_user
from app import app
from database.models import User


@pytest.fixture
def client():
    return TestClient(app)


def _expired_token(user_id: str, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "type": token_type, "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1)}
    return jwt.encode(payload, security.SECRET_KEY, algorithm=security.ALGORITHM)


def _tampered_token(user_id: str) -> str:
    real_token = security.create_access_token(user_id)
    return real_token[:-1] + ("A" if real_token[-1] != "A" else "B")


# --- signup ---

def test_signup_creates_a_user_and_returns_an_access_token(patched_session, client):
    response = client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies


def test_signup_rejects_a_duplicate_email(patched_session, client):
    client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    response = client.post("/auth/signup", json={"email": "walker@example.com", "password": "another-password"})

    assert response.status_code == 400


def test_signup_rejects_an_invalid_email(patched_session, client):
    response = client.post("/auth/signup", json={"email": "not-an-email", "password": "correct-horse"})
    assert response.status_code == 400


# --- login ---

def test_login_with_correct_credentials_returns_an_access_token(patched_session, client):
    client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    response = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies


def test_login_rejects_the_wrong_password(patched_session, client):
    client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    response = client.post("/auth/login", json={"email": "walker@example.com", "password": "wrong-password"})

    assert response.status_code == 401


def test_login_rejects_an_unknown_email(patched_session, client):
    response = client.post("/auth/login", json={"email": "nobody@example.com", "password": "correct-horse"})
    assert response.status_code == 401


def test_login_rejects_a_deactivated_user(patched_session, client, user_id):
    user = create_user(patched_session, "walker@example.com", "correct-horse")
    user.is_active = False
    patched_session.commit()

    response = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    assert response.status_code == 401


# --- protected routes ---

def test_me_requires_a_token(patched_session, client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_the_logged_in_user(patched_session, client):
    signup = client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})
    access_token = signup.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "walker@example.com"


def test_me_rejects_an_expired_token(patched_session, client, user_id):
    token = _expired_token(str(user_id), security.ACCESS_TOKEN_TYPE)
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_a_tampered_token(patched_session, client, user_id):
    token = _tampered_token(str(user_id))
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_rejects_a_refresh_token_used_as_an_access_token(patched_session, client, user_id):
    refresh_token = security.create_refresh_token(str(user_id))
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401


def test_me_rejects_a_deleted_users_token(patched_session, client, user_id):
    token = security.create_access_token(str(user_id))

    user = patched_session.get(User, user_id)
    patched_session.delete(user)
    patched_session.commit()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# --- refresh ---

def test_refresh_requires_a_refresh_cookie(patched_session, client):
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_refresh_issues_a_new_access_token(patched_session, client):
    signup = client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})
    assert "refresh_token" in signup.cookies

    response = client.post("/auth/refresh")

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_refresh_rejects_an_access_token_used_as_a_refresh_token(patched_session, client, user_id):
    access_token = security.create_access_token(str(user_id))
    client.cookies.set("refresh_token", access_token)

    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_refresh_rejects_an_expired_refresh_token(patched_session, client, user_id):
    token = _expired_token(str(user_id), security.REFRESH_TOKEN_TYPE)
    client.cookies.set("refresh_token", token)

    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_refresh_rejects_a_deactivated_user(patched_session, client, user_id):
    refresh_token = security.create_refresh_token(str(user_id))
    client.cookies.set("refresh_token", refresh_token)

    user = patched_session.get(User, user_id)
    user.is_active = False
    patched_session.commit()

    response = client.post("/auth/refresh")
    assert response.status_code == 401


# --- logout ---

def test_logout_clears_the_refresh_cookie(patched_session, client):
    client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert "refresh_token" not in response.cookies
