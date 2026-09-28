# tests/test_google_oauth.py
# accounts/google_oauth.py in isolation - never makes a real call to
# Google (google.oauth2.id_token.verify_oauth2_token is monkeypatched),
# since these are unit tests for the wrapper's own logic: missing
# configuration and "anything the verifier raises becomes GoogleTokenError".

import pytest

from accounts import google_oauth


def test_verify_google_id_token_requires_google_signin_client_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_SIGNIN_CLIENT_ID", raising=False)

    with pytest.raises(google_oauth.GoogleTokenError):
        google_oauth.verify_google_id_token("some-credential")


def test_verify_google_id_token_returns_claims_on_success(monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(
        google_oauth.id_token,
        "verify_oauth2_token",
        lambda credential, request, audience: {"sub": "123", "email": "walker@example.com", "email_verified": True},
    )

    claims = google_oauth.verify_google_id_token("real-looking-jwt")

    assert claims["sub"] == "123"
    assert claims["email"] == "walker@example.com"


def test_verify_google_id_token_wraps_a_bad_token_as_google_token_error(monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "test-client-id")

    def _raise(credential, request, audience):
        raise ValueError("Token expired")

    monkeypatch.setattr(google_oauth.id_token, "verify_oauth2_token", _raise)

    with pytest.raises(google_oauth.GoogleTokenError):
        google_oauth.verify_google_id_token("expired-jwt")


def test_verify_google_id_token_passes_the_configured_client_id_as_audience(monkeypatch):
    monkeypatch.setenv("GOOGLE_SIGNIN_CLIENT_ID", "test-client-id")
    seen = {}

    def _capture(credential, request, audience):
        seen["audience"] = audience
        return {"sub": "123"}

    monkeypatch.setattr(google_oauth.id_token, "verify_oauth2_token", _capture)

    google_oauth.verify_google_id_token("real-looking-jwt")

    assert seen["audience"] == "test-client-id"
