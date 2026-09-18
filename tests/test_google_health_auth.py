# tests/test_google_health_auth.py
# OAuth HTTP mechanics only - no file I/O left here since Step 7 (see
# auth/connections.py for where tokens actually get persisted,
# database-side). Real HTTP calls mocked out via pytest-httpx; the OAuth
# client's credentials.json is redirected to a tmp_path.

import json

from auth import google_health_auth

FAKE_CREDENTIALS = {"web": {
    "client_id": "cid",
    "client_secret": "secret",
    "redirect_uris": ["https://www.google.com"],
}}


def _point_credentials_at(tmp_path, monkeypatch):
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps(FAKE_CREDENTIALS))
    monkeypatch.setattr(google_health_auth, "CREDENTIALS_PATH", creds_path)


def test_exchange_code_returns_the_tokens(tmp_path, monkeypatch, httpx_mock):
    _point_credentials_at(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})

    tokens = google_health_auth.exchange_code("some-code")

    assert tokens["access_token"] == "AT"
    assert tokens["refresh_token"] == "RT"
    assert "obtained_at" in tokens  # stamped locally, not part of Google's response


def test_refresh_access_token_returns_a_new_access_token(tmp_path, monkeypatch, httpx_mock):
    _point_credentials_at(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"access_token": "NEW", "expires_in": 3600})

    tokens = google_health_auth.refresh_access_token("some-refresh-token")

    assert tokens["access_token"] == "NEW"
    assert tokens["expires_in"] == 3600
    assert "obtained_at" in tokens


def test_refresh_access_token_sends_the_given_refresh_token(tmp_path, monkeypatch, httpx_mock):
    _point_credentials_at(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"access_token": "NEW", "expires_in": 3600})

    google_health_auth.refresh_access_token("the-real-refresh-token")

    request = httpx_mock.get_requests()[0]
    assert "refresh_token=the-real-refresh-token" in request.content.decode()


def test_revoke_token_posts_to_googles_revoke_endpoint(tmp_path, monkeypatch, httpx_mock):
    _point_credentials_at(tmp_path, monkeypatch)
    httpx_mock.add_response()  # Google returns 200 with an empty body, even for a dead token

    google_health_auth.revoke_token("some-token")

    request = httpx_mock.get_requests()[0]
    assert str(request.url) == "https://oauth2.googleapis.com/revoke"
    assert "token=some-token" in request.content.decode()


def test_build_auth_url_includes_a_unique_pending_state(tmp_path, monkeypatch):
    _point_credentials_at(tmp_path, monkeypatch)
    monkeypatch.setattr(google_health_auth, "_pending_states", set())

    url1 = google_health_auth.build_auth_url()
    url2 = google_health_auth.build_auth_url()

    state1 = url1.split("state=")[1].split("&")[0]
    state2 = url2.split("state=")[1].split("&")[0]

    assert state1 != state2
    assert google_health_auth._pending_states == {state1, state2}
