# auth_setup/google_health_auth.py
# OAuth for the Google Health API: https://developers.google.com/health/setup
#
# credentials.json -> the OAuth *client* (already set up, holds client_id/secret)
# .tokens.json     -> the access/refresh tokens for YOUR account, created by
#                      exchange_code() the first time you run auth_setup/authorize.py

import json
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"
TOKENS_PATH = ROOT / ".tokens.json"

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# Read-only scopes for the 4 metrics WorldWalker tracks, plus .profile to
# call users.getIdentity (needed for healthUserId - required to create a
# MANUAL subscription for "sleep", see auth_setup/register_webhook_subscription.py).
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.profile.readonly",
]


def _load_client() -> tuple[str, str, str]:
    creds = json.loads(CREDENTIALS_PATH.read_text())["web"]
    return creds["client_id"], creds["client_secret"], creds["redirect_uris"][0]


def build_auth_url() -> str:
    """URL to open in a browser to grant consent (step 1 of auth_setup/authorize.py)."""
    client_id, _, redirect_uri = _load_client()
    scope = " ".join(SCOPES)
    return (
        f"{AUTH_URL}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&access_type=offline&scope={scope}"
    )


def exchange_code(code: str) -> dict:
    """Trade the one-time authorization code for access + refresh tokens.
    code is URL-decoded defensively - the browser address bar shows it
    URL-encoded (e.g. "%2F" for "/"), which is easy to paste as-is."""
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
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    return tokens


def refresh_access_token() -> dict:
    """Use the saved refresh_token to get a new access_token."""
    client_id, client_secret, _ = _load_client()
    tokens = json.loads(TOKENS_PATH.read_text())
    response = httpx.post(TOKEN_URL, data={
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    })
    response.raise_for_status()
    tokens["access_token"] = response.json()["access_token"]
    tokens["obtained_at"] = time.time()
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_access_token() -> str:
    return json.loads(TOKENS_PATH.read_text())["access_token"]
