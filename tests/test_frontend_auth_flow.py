# tests/test_frontend_auth_flow.py
# Verifies the exact request sequence frontend/src/api/httpClient.ts and
# frontend/src/auth/AuthContext.tsx rely on: signup/login hand back an
# access_token the frontend attaches as "Authorization: Bearer <token>"
# on /api/* calls, and an expired access token can be silently recovered
# with one /auth/refresh call (using the refresh cookie the browser sends
# automatically) followed by a retry - the "401 -> refresh -> retry once"
# logic in auth.js's apiFetch(). accounts/router.py and app.py's routes
# already have their own focused unit tests (tests/test_accounts.py,
# tests/test_app_journey_routes.py) - this file proves the two work
# together the way the browser actually calls them, end to end.

from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from accounts import security
from accounts.service import signup as create_user
from app import app

client = TestClient(app)


def _expired_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "type": security.ACCESS_TOKEN_TYPE, "iat": now - timedelta(hours=1), "exp": now - timedelta(minutes=1)}
    return jwt.encode(payload, security.SECRET_KEY, algorithm=security.ALGORITHM)


def test_signup_then_authenticated_request_succeeds(patched_session, monkeypatch):
    """POST /auth/signup (tests/test_accounts.py covers its own behavior
    in isolation) end to end: no real DNS lookup, same as those tests.

    TODO(otp): this used to be the two-call start/verify flow - see
    tests/test_accounts.py's commented-out OTP tests for that version."""
    monkeypatch.setattr("accounts.email_validation.has_mx_record", lambda domain: True)

    signup = client.post("/auth/signup", json={"email": "walker@example.com", "password": "correct-horse"})
    assert signup.status_code == 200
    access_token = signup.json()["access_token"]

    response = client.get("/api/journey/list", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json() == {"trips": []}


def test_login_then_authenticated_request_succeeds(patched_session):
    create_user(patched_session, "walker@example.com", "correct-horse")

    login = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    access_token = login.json()["access_token"]

    response = client.get("/api/journey/list", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200


def test_missing_bearer_token_is_rejected(patched_session):
    response = client.get("/api/journey/list")
    assert response.status_code == 401


def test_expired_access_token_can_be_refreshed_and_the_request_retried(patched_session):
    """Mirrors frontend/src/api/httpClient.ts's apiFetch(): a stale access token
    401s, /auth/refresh (using the refresh cookie the login response just
    set) hands back a fresh one, and the same request succeeds when
    retried with it - the exact sequence the frontend performs
    automatically instead of bouncing the user to the login page."""
    create_user(patched_session, "walker@example.com", "correct-horse")
    login = client.post("/auth/login", json={"email": "walker@example.com", "password": "correct-horse"})
    user_id = jwt.decode(login.json()["access_token"], security.SECRET_KEY, algorithms=[security.ALGORITHM])["sub"]

    stale_token = _expired_access_token(user_id)
    first_attempt = client.get("/api/journey/list", headers={"Authorization": f"Bearer {stale_token}"})
    assert first_attempt.status_code == 401

    refreshed = client.post("/auth/refresh")
    assert refreshed.status_code == 200
    new_token = refreshed.json()["access_token"]

    retry = client.get("/api/journey/list", headers={"Authorization": f"Bearer {new_token}"})
    assert retry.status_code == 200


def test_google_health_disconnect_requires_authentication(patched_session):
    """The Connect button becomes a disconnect action once connected (see
    frontend/src/components/Topbar.tsx) - it's a same-origin POST, not a redirect, so it
    must carry the bearer token like any other authenticated action."""
    response = client.post("/auth/google/disconnect")
    assert response.status_code == 401
