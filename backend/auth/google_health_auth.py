# auth/google_health_auth.py

'''
Handles the Google OAuth 2.0 connection for Google Health
'''

import json
import os
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.profile.readonly",
]


def _load_client() -> tuple[str, str, str]:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")
    if client_id and client_secret and redirect_uri:
        return client_id, client_secret, redirect_uri

    creds = json.loads(CREDENTIALS_PATH.read_text())["web"]
    return creds["client_id"], creds["client_secret"], creds["redirect_uris"][0]


def build_auth_url(state: str) -> str:
    client_id, _, redirect_uri = _load_client()
    scope = " ".join(SCOPES)
    return (
        f"{AUTH_URL}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&access_type=offline&prompt=consent&scope={scope}&state={state}"
    )


def exchange_code(code: str) -> dict:
    client_id, client_secret, redirect_uri = _load_client()
    response = httpx.post(TOKEN_URL, data={
        "code": unquote(code),
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    response.raise_for_status()
    tokens = response.json()
    tokens["obtained_at"] = time.time()
    print(f"🔐 auth: code exchanged (scopes: {tokens.get('scope', 'unknown')})")
    return tokens


def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret, _ = _load_client()
    response = httpx.post(TOKEN_URL, data={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    })
    response.raise_for_status()
    tokens = response.json()
    tokens["obtained_at"] = time.time()
    print("🔐 auth: access token refreshed")
    return tokens


def revoke_token(token: str) -> None:
    response = httpx.post(REVOKE_URL, data={"token": token})
    response.raise_for_status()
    print("🔐 auth: token revoked with Google")
