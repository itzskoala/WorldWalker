#!/usr/bin/env python3
# auth/register_webhook_subscription.py
# Re-runnable: run once you have service-account.json (see plan doc for
# the manual Cloud Console steps) and a public URL Google can reach -
# your real deployment's URL for production, or a tunnel (e.g. ngrok)
# for local dev testing only. Either way, this is the base URL that
# services/google_health/webhook.py's router is actually served from -
# the exact endpoint registered is always {base_url}/api/webhook/google-health.
#
#   venv/bin/python3 auth/register_webhook_subscription.py [public-https-url] [gcp-project-id]
#
# Both arguments are optional - each falls back to an env var
# (WEBHOOK_PUBLIC_URL, GCP_PROJECT_ID) if omitted, so a real deployment
# can just set those once in its environment and re-run this script with
# no arguments any time the deployment's own webhook config needs
# re-registering (e.g. after rotating WEBHOOK_SECRET). A CLI argument
# always overrides the env var, for one-off dev testing against a
# tunnel without touching the real deployment's configured URL. Safe to
# re-run whenever the URL changes (a tunnel rotates it on restart; a
# real deployment shouldn't, but nothing stops you from re-registering).
#
# Never hardcode a tunnel URL here - it's temporary by nature (ngrok
# rotates it on every restart) and would silently stop delivering real
# push notifications the moment it changes, with no error from Google.
#
# Auth: uses the broad "cloud-platform" scope, same pattern as the Cloud
# Healthcare API (same family of Google Cloud API - project-scoped
# resources + IAM roles controlling actual access, rather than a
# per-API OAuth scope). Confirmed by trial: requesting
# "auth/health" as a scope isn't recognized, so Google's token endpoint
# falls back to minting an id_token instead of an access_token.
#
# Only "steps"/"exercise" are subscribed - not "sleep"/"heart-rate":
# auth/google_health_auth.py's SCOPES doesn't request those (Google
# Health's sleep/heart-rate scopes are Restricted and nothing in
# WorldWalker uses that data yet - see docs/google_oauth_verification.md).
# A no-longer-granted scope's data type can't be subscribed to anyway.
# Note for whoever re-adds sleep later: it needs its own handling
# (subscriptionCreatePolicy=MANUAL, not AUTOMATIC - Google's own docs
# pair "sleep" with MANUAL, unlike steps/weight) - see this file's git
# history for the working implementation this once had.
#
# Re-running: PATCH-if-exists (_upsert_subscriber below), not
# delete-then-recreate - deleting a subscriber with any active child
# subscription 400s (FAILED_PRECONDITION).

import os
import sys
import json
from pathlib import Path

import httpx
import google.auth.transport.requests
from dotenv import load_dotenv
from google.oauth2 import service_account

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SERVICE_ACCOUNT_PATH = ROOT / "service-account.json"
SUBSCRIBER_ID = "worldwalker"
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]  # must match services/google_health/webhook.py
AUTOMATIC_DATA_TYPES = ["steps", "exercise"]


def _service_account_token() -> str:
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_PATH),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def _request(method: str, url: str, body: dict | None = None) -> httpx.Response:
    return httpx.request(method, url, json=body, headers={"Authorization": f"Bearer {_service_account_token()}"})


def _raise_with_body(response: httpx.Response):
    if response.status_code >= 400:
        print(f"{response.status_code} error:\n{response.text}")
        response.raise_for_status()


def _upsert_subscriber(base: str, body: dict) -> dict:
    """PATCH if the subscriber already exists, POST (create) if not."""
    update_mask = ",".join(body.keys())
    patch_response = _request("PATCH", f"{base}/{SUBSCRIBER_ID}?updateMask={update_mask}", body)
    if patch_response.status_code == 404:
        create_response = _request("POST", f"{base}?subscriberId={SUBSCRIBER_ID}", body)
        _raise_with_body(create_response)
        return create_response.json()
    _raise_with_body(patch_response)
    return patch_response.json()


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")


def _resolve_public_url(cli_arg: str | None) -> str:
    """CLI argument wins; otherwise WEBHOOK_PUBLIC_URL from the
    environment - never a value baked into this file. Rejects anything
    Google's servers could never reach, so a mistake here fails loudly
    now instead of registering a subscription that will silently never
    deliver anything (confirmed the hard way - see progress/day6.md)."""
    url = (cli_arg or os.environ.get("WEBHOOK_PUBLIC_URL") or "").strip().rstrip("/")
    if not url:
        raise SystemExit(
            "No public URL given. Pass one as the first argument, or set "
            "WEBHOOK_PUBLIC_URL in .env to your real deployment's URL "
            "(see .env.example) - never a temporary tunnel URL committed "
            "anywhere."
        )
    if not url.startswith("https://"):
        raise SystemExit(f"WEBHOOK_PUBLIC_URL must be a real https:// URL, got: {url!r}")
    if any(host in url for host in _LOCAL_HOSTS):
        raise SystemExit(
            f"{url!r} is a local address - Google's servers can never reach it, "
            "so registering it would silently never deliver anything. Use your "
            "real deployment's public URL, or a tunnel's public https URL for "
            "local dev testing (not the localhost URL itself)."
        )
    return url


def _resolve_project_id(cli_arg: str | None) -> str:
    """This must be the GCP project NUMBER (e.g. 580356155767), not the
    project ID string (e.g. coral-core-506316-d1) - the Health Connect
    Partner API 403s as PERMISSION_DENIED on the ID string even with
    correct IAM roles granted, since it resolves that as a different
    identifier entirely. See .env.example."""
    project_id = cli_arg or os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise SystemExit(
            "No GCP project number given. Pass one as the second argument, or set "
            "GCP_PROJECT_ID in .env - must be the project NUMBER, not the project ID string."
        )
    return project_id


def register(public_url: str | None, project_id: str | None):
    public_url = _resolve_public_url(public_url)
    project_id = _resolve_project_id(project_id)
    endpoint_uri = f"{public_url}/api/webhook/google-health"
    base = f"https://health.googleapis.com/v4/projects/{project_id}/subscribers"

    print(f"Registering webhook endpoint: {endpoint_uri}")
    subscriber = _upsert_subscriber(base, {
        "endpointUri": endpoint_uri,
        "subscriberConfigs": [
            {"dataTypes": AUTOMATIC_DATA_TYPES, "subscriptionCreatePolicy": "AUTOMATIC"},
        ],
        "endpointAuthorization": {"secret": WEBHOOK_SECRET},
    })
    print("Subscriber (steps/exercise):")
    print(json.dumps(subscriber, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 3:
        print(
            "Usage: python3 auth/register_webhook_subscription.py [public-https-url] [gcp-project-id]\n"
            "Both are optional - each falls back to WEBHOOK_PUBLIC_URL / GCP_PROJECT_ID in .env."
        )
        sys.exit(1)
    cli_public_url = sys.argv[1] if len(sys.argv) > 1 else None
    cli_project_id = sys.argv[2] if len(sys.argv) > 2 else None
    register(cli_public_url, cli_project_id)
