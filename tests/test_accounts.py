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
from accounts.google_oauth import GoogleTokenError
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


# --- signup (POST /auth/signup) ---
# One call: accounts/service.py's signup() creates the User row and this
# route issues tokens from it immediately - no separate verification
# step. skip_mx_lookup stands in for accounts/email_validation.py's real
# MX check.

@pytest.fixture
def skip_mx_lookup(monkeypatch):
    monkeypatch.setattr("accounts.email_validation.has_mx_record", lambda domain: True)


def test_signup_creates_the_user_and_returns_tokens(patched_session, client, skip_mx_lookup):
    response = client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies
    assert patched_session.query(User).count() == 1


def test_signup_rejects_a_duplicate_email(patched_session, client, skip_mx_lookup):
    create_user(patched_session, "walker@example.com", "correct-horse")

    response = client.post("/auth/signup", json={"email": "walker@example.com", "password": "another-password"})

    assert response.status_code == 400
    assert patched_session.query(User).count() == 1


def test_signup_rejects_an_invalid_email(patched_session, client):
    response = client.post("/auth/signup", json={"email": "not-an-email", "password": "correct-horse"})
    assert response.status_code == 400
    assert patched_session.query(User).count() == 0


# --- email validation (GET /auth/validate-email) ---

def test_validate_email_accepts_a_real_looking_address(skip_mx_lookup, client):
    response = client.get("/auth/validate-email", params={"email": "walker@example.com"})
    assert response.status_code == 200
    assert response.json() == {"valid": True}


def test_validate_email_rejects_bad_syntax(client):
    response = client.get("/auth/validate-email", params={"email": "not-an-email"})
    assert response.status_code == 200
    assert response.json() == {"valid": False}


def test_validate_email_rejects_a_domain_with_no_mx_record(client, monkeypatch):
    monkeypatch.setattr("accounts.email_validation.has_mx_record", lambda domain: False)
    response = client.get("/auth/validate-email", params={"email": "walker@nowhere-really.invalid"})
    assert response.status_code == 200
    assert response.json() == {"valid": False}


# --- login ---

def test_login_with_correct_credentials_returns_an_access_token(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")

    response = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies


def test_login_rejects_the_wrong_password(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")

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


def test_login_defaults_to_remembered_with_a_long_lived_refresh_cookie(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")

    response = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})

    cookie = next(c for c in response.cookies.jar if c.name == "refresh_token")
    assert cookie.expires is not None  # a persistent cookie, not a session cookie
    payload = security.decode_token(response.cookies["refresh_token"])
    assert payload["exp"] - payload["iat"] == security.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def test_login_with_remember_me_false_issues_a_short_session_cookie(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")

    response = client.post(
        "/auth/login", json={"email": "walker@example.com", "password": "correct-horse", "remember_me": False}
    )

    cookie = next(c for c in response.cookies.jar if c.name == "refresh_token")
    assert cookie.expires is None  # a session cookie - gone when the browser closes
    payload = security.decode_token(response.cookies["refresh_token"])
    assert payload["exp"] - payload["iat"] == security.SESSION_REFRESH_TOKEN_EXPIRE_HOURS * 60 * 60


# --- protected routes ---

def test_me_requires_a_token(patched_session, client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_the_logged_in_user(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")
    login = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    access_token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "walker@example.com"
    assert response.json()["created_at"]  # frontend/src/pages/ProfilePage.tsx's "Member since"


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
    create_user(patched_session, "walker@example.com", "correct-horse")
    login = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    assert "refresh_token" in login.cookies

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


# --- Google sign-in ---
# accounts/router.py's POST /auth/google calls
# accounts.google_oauth.verify_google_id_token() before ever touching the
# database - these tests stand in for Google by monkeypatching that one
# function (it's imported by name into accounts/router.py, so patching it
# there is what the route actually calls), never a real network call.

def _stub_google_claims(monkeypatch, **claims):
    monkeypatch.setattr("accounts.router.verify_google_id_token", lambda credential: claims)


def _stub_google_error(monkeypatch, message="Invalid or expired Google credential"):
    def _raise(credential):
        raise GoogleTokenError(message)

    monkeypatch.setattr("accounts.router.verify_google_id_token", _raise)


def test_google_auth_creates_a_new_user_on_first_sign_in(patched_session, client, monkeypatch):
    _stub_google_claims(monkeypatch, sub="google-sub-1", email="walker@example.com", email_verified=True)

    response = client.post("/auth/google", json={"credential": "fake-id-token"})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies


def test_google_auth_does_not_create_a_duplicate_user_on_a_returning_sign_in(patched_session, client, monkeypatch):
    _stub_google_claims(monkeypatch, sub="google-sub-1", email="walker@example.com", email_verified=True)
    client.post("/auth/google", json={"credential": "fake-id-token"})

    response = client.post("/auth/google", json={"credential": "fake-id-token"})
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"})

    assert response.status_code == 200
    assert patched_session.query(User).count() == 1
    assert me.json()["email"] == "walker@example.com"


def test_google_auth_links_to_an_existing_email_password_account(patched_session, client, monkeypatch):
    create_user(patched_session, "walker@example.com", "correct-horse")
    _stub_google_claims(monkeypatch, sub="google-sub-1", email="walker@example.com", email_verified=True)

    response = client.post("/auth/google", json={"credential": "fake-id-token"})

    assert response.status_code == 200
    assert patched_session.query(User).count() == 1
    # The same account is now reachable either way - password login still
    # works after the Google link.
    login = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    assert login.status_code == 200


def test_google_auth_rejects_an_unverified_email(patched_session, client, monkeypatch):
    _stub_google_claims(monkeypatch, sub="google-sub-1", email="walker@example.com", email_verified=False)

    response = client.post("/auth/google", json={"credential": "fake-id-token"})

    assert response.status_code == 400
    assert patched_session.query(User).count() == 0


def test_google_auth_rejects_an_invalid_or_expired_credential(patched_session, client, monkeypatch):
    _stub_google_error(monkeypatch)

    response = client.post("/auth/google", json={"credential": "garbage"})

    assert response.status_code == 401


def test_google_auth_rejects_a_deactivated_users_google_account(patched_session, client, monkeypatch):
    user = create_user(patched_session, "walker@example.com", "correct-horse")
    user.google_sub = "google-sub-1"
    user.is_active = False
    patched_session.commit()
    _stub_google_claims(monkeypatch, sub="google-sub-1", email="walker@example.com", email_verified=True)

    response = client.post("/auth/google", json={"credential": "fake-id-token"})

    assert response.status_code == 401


# --- logout ---

def test_logout_clears_the_refresh_cookie(patched_session, client):
    create_user(patched_session, "walker@example.com", "correct-horse")
    client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert "refresh_token" not in response.cookies


# --- existing accounts (regression coverage for the Clerk revert) ---
# These lock in Step 4's data-preservation requirements: an account that
# already has a hashed_password (every production user does - see the
# migration audit) must log in as itself, not get duplicated or re-keyed,
# and anything foreign-keyed to its user.id (trips, Google Health
# connections) must stay attached to the exact same row.

def test_existing_user_with_a_password_hash_logs_in_without_creating_a_duplicate(patched_session, client):
    """Simulates a real pre-Clerk production row: created directly (not
    through signup()) with a real bcrypt hash already on it, the same
    shape every existing account has."""
    existing = User(email="returning@example.com", hashed_password=security.hash_password("correct-horse"))
    patched_session.add(existing)
    patched_session.commit()

    response = client.post("/auth/login", json={"email": "returning@example.com", "password": "correct-horse"})

    assert response.status_code == 200
    assert patched_session.query(User).count() == 1


def test_existing_users_trips_and_google_health_connection_stay_attached_after_login(
    patched_session, client, connected_user_id, seed_trip
):
    """connected_user_id (tests/conftest.py) is a bare User with a real
    GoogleHealthConnection already on it - gives it a password, logs in,
    and confirms /auth/me resolves back to that exact row, with the
    connection and a seeded trip both still foreign-keyed to it."""
    from travel_logic.route_service import Route, RoutePoint
    from travel_logic.dataclasses.coordinates import Coordinates

    user = patched_session.get(User, connected_user_id)
    user.email = "connected@example.com"
    user.hashed_password = security.hash_password("correct-horse")
    patched_session.commit()

    route = Route(
        points=[
            RoutePoint(Coordinates(0.0, 0.0), 1, 0.0, 1000.0, 0.0, 1000.0),
            RoutePoint(Coordinates(0.0, 0.01), 2, 1000.0, 0.0, 1000.0, 0.0),
        ],
        total_distance=1000.0,
        point_count=2,
    )
    seed_trip(connected_user_id, route)

    login = client.post("/auth/login", json={"email": "connected@example.com", "password": "correct-horse"})
    assert login.status_code == 200

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert me.json()["id"] == str(connected_user_id)

    patched_session.refresh(user)
    assert user.google_health_connection is not None
    assert len(user.trips) == 1
