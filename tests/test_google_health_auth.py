# tests/test_google_health_auth.py
# OAuth token exchange/refresh, with the real HTTP call mocked out
# (pytest-httpx) and credentials/token files redirected to a tmp_path.

import json

from auth_setup import google_health_auth

FAKE_CREDENTIALS = {"web": {
    "client_id": "cid",
    "client_secret": "secret",
    "redirect_uris": ["https://www.google.com"],
}}


def _point_paths_at(tmp_path, monkeypatch, existing_tokens=None):
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps(FAKE_CREDENTIALS))
    tokens_path = tmp_path / ".tokens.json"
    if existing_tokens is not None:
        tokens_path.write_text(json.dumps(existing_tokens))
    monkeypatch.setattr(google_health_auth, "CREDENTIALS_PATH", creds_path)
    monkeypatch.setattr(google_health_auth, "TOKENS_PATH", tokens_path)
    return tokens_path


def test_exchange_code_saves_tokens(tmp_path, monkeypatch, httpx_mock):
    tokens_path = _point_paths_at(tmp_path, monkeypatch)
    httpx_mock.add_response(json={"access_token": "AT", "refresh_token": "RT"})

    tokens = google_health_auth.exchange_code("some-code")

    assert tokens["access_token"] == "AT"
    assert json.loads(tokens_path.read_text())["refresh_token"] == "RT"


def test_refresh_access_token_updates_access_token(tmp_path, monkeypatch, httpx_mock):
    tokens_path = _point_paths_at(tmp_path, monkeypatch, existing_tokens={"access_token": "OLD", "refresh_token": "RT"})
    httpx_mock.add_response(json={"access_token": "NEW"})

    google_health_auth.refresh_access_token()

    assert json.loads(tokens_path.read_text())["access_token"] == "NEW"


def test_get_access_token_reads_saved_token(tmp_path, monkeypatch):
    _point_paths_at(tmp_path, monkeypatch, existing_tokens={"access_token": "AT", "refresh_token": "RT"})
    assert google_health_auth.get_access_token() == "AT"
