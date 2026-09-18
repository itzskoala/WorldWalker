# auth/google_health_auth.py
# Pure OAuth HTTP mechanics for the Google Health API - talks to Google,
# never touches a file or the database. credentials.json is the OAuth
# *client* (client_id/secret); the access/refresh tokens this module
# hands back are persisted by auth/connections.py, in Postgres, not here
# (that split - see Step 7 in docs/prompt_log/ - replaced an earlier
# .tokens.json file that lived at this module's level).

import json
import secrets
import time
from pathlib import Path
from urllib.parse import unquote

import httpx

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = ROOT / "credentials.json"

TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# CSRF protection for the OAuth redirect: build_auth_url() issues a random
# state and remembers it here; auth/router.py's callback must present that
# exact state back (and only once) before exchange_code() ever runs.
# In-memory/single-process, matching the rest of this MVP's session state
# (see core/facade.py's TravelFacade._sessions) - a real multi-worker
# deployment would need this shared (e.g. in the database), not local to
# one process.
_pending_states: set[str] = set()


def _issue_state() -> str:
    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    return state


def consume_state(state: str) -> bool:
    """True and removes it if state was actually pending; False otherwise.
    Removing it makes each state single-use - replaying an old callback
    URL (or a guessed/leaked state) fails the second time."""
    if state in _pending_states:
        _pending_states.remove(state)
        return True
    return False

# Read-only scopes for the 4 metrics WorldWalker tracks, plus .profile to
# call users.getIdentity (needed for healthUserId - required to create a
# MANUAL subscription for "sleep", see auth/register_webhook_subscription.py).
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
    """URL for the Connect button to send the user to. Issues a fresh CSRF
    state (see _issue_state) that auth/router.py's callback must see come
    back before it will exchange a code.

    prompt=consent forces Google to re-show the consent screen and issue a
    fresh refresh_token even if this client was already authorized before -
    without it, Google only returns a refresh_token on a user's very first
    consent grant, and silently omits it on every re-authorization after
    that (this bit us: an earlier .tokens.json had no refresh_token at
    all, so the access token became a dead end the moment it expired)."""
    client_id, _, redirect_uri = _load_client()
    scope = " ".join(SCOPES)
    state = _issue_state()
    print(f"🔐 auth: issued state {state[:8]}... for a new consent request")
    return (
        f"{AUTH_URL}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&access_type=offline&prompt=consent&scope={scope}&state={state}"
    )


def exchange_code(code: str) -> dict:
    """Trade the one-time authorization code for access + refresh tokens.
    code is URL-decoded defensively - the browser address bar shows it
    URL-encoded (e.g. "%2F" for "/"), which is easy to paste as-is.

    Returns the tokens dict; doesn't persist it anywhere itself -
    auth/router.py's callback hands this straight to
    auth/connections.py::upsert_connection_from_tokens()."""
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
    """Trade a refresh_token for a new access_token. Pure function - no
    file, no database; auth/connections.py::get_valid_access_token() is
    what actually calls this and persists the result, since it's the one
    that knows which connection row to update."""
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
    """Revoke a token with Google - either the access_token or
    refresh_token works and revokes the *entire* grant (confirmed against
    developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke),
    so revoking just one is enough. Google returns 200 even for an
    already-dead token, so there's nothing to distinguish here - a
    non-200 means something else went wrong (network, Google's own
    outage), which the caller (auth/connections.py::disconnect) treats as
    non-fatal: the local disconnect proceeds regardless."""
    response = httpx.post(REVOKE_URL, data={"token": token})
    response.raise_for_status()
    print("🔐 auth: token revoked with Google")
