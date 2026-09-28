#!/usr/bin/env python3
# auth/register_webhook_subscription.py
# Re-runnable: run once you have service-account.json (see plan doc for
# the manual Cloud Console steps) and a public webhook URL (e.g. ngrok).
# Safe to re-run every time that URL changes (ngrok rotates it on restart).
#   venv/bin/python3 auth/register_webhook_subscription.py <public-https-url> <gcp-project-id>
#
# Auth: uses the broad "cloud-platform" scope, same pattern as the Cloud
# Healthcare API (same family of Google Cloud API - project-scoped
# resources + IAM roles controlling actual access, rather than a
# per-API OAuth scope). Confirmed by trial: requesting
# "auth/health" as a scope isn't recognized, so Google's token endpoint
# falls back to minting an id_token instead of an access_token.
#
# "sleep" needs its own handling: subscriptionCreatePolicy=AUTOMATIC 409s
# for it (SLEEP_ALREADY_EXISTS). Google's own docs pair "sleep" with
# MANUAL policy (unlike steps/weight, shown as AUTOMATIC), which needs:
#   1. The subscriber's own subscriberConfigs to declare "sleep" under
#      MANUAL (a separate list entry, alongside the AUTOMATIC one) -
#      without this, creating the per-user subscription 400s as
#      FAILED_PRECONDITION.
#   2. A per-user Subscription resource, keyed by healthUserId - one per
#      connected WorldWalker user, read from our own GoogleHealthConnection
#      rows (each was resolved via the .profile.readonly scope at connect
#      time - see auth/connections.py - so this script never has to call
#      Google's identity API itself).
#
# Re-running: an earlier version of this script deleted the subscriber
# before recreating it, which 400s (FAILED_PRECONDITION) once a manual
# sleep subscription is attached as a child - Google won't delete a
# subscriber with active child subscriptions. PATCH-if-exists avoids that
# entirely.

import os
import sys
import json
from pathlib import Path

import httpx
import google.auth.transport.requests
from dotenv import load_dotenv
from google.oauth2 import service_account

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `database` is importable
from database.models import GoogleHealthConnection
from database.session import SessionLocal

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SERVICE_ACCOUNT_PATH = ROOT / "service-account.json"
SUBSCRIBER_ID = "worldwalker"
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]  # must match services/google_health/webhook.py
AUTOMATIC_DATA_TYPES = ["steps", "exercise", "heart-rate"]
MANUAL_DATA_TYPES = ["sleep"]


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


def _sleep_subscription_exists(base: str, health_user_id: str) -> bool:
    list_response = _request("GET", f"{base}/{SUBSCRIBER_ID}/subscriptions")
    _raise_with_body(list_response)
    subscriptions = list_response.json().get("subscriptions", [])
    return any(sub.get("user") == f"users/{health_user_id}" for sub in subscriptions)


def _connected_provider_user_ids() -> list[str]:
    """provider_user_id (healthUserId) for every WorldWalker user with an
    active Google Health connection - read straight from our own DB, not
    Google's identity API, since we already stored each one the moment
    that user connected (see auth/connections.py::upsert_connection_from_tokens).
    A manual "sleep" subscription is per-Google-account, so every
    connected account needs its own, not just whichever one happened to
    be active when this script last ran."""
    with SessionLocal() as session:
        connections = session.query(GoogleHealthConnection).filter_by(status="active").all()
        return [connection.provider_user_id for connection in connections]


def register(public_url: str, project_id: str):
    base = f"https://health.googleapis.com/v4/projects/{project_id}/subscribers"

    subscriber = _upsert_subscriber(base, {
        "endpointUri": f"{public_url}/api/webhook/google-health",
        "subscriberConfigs": [
            {"dataTypes": AUTOMATIC_DATA_TYPES, "subscriptionCreatePolicy": "AUTOMATIC"},
            {"dataTypes": MANUAL_DATA_TYPES, "subscriptionCreatePolicy": "MANUAL"},
        ],
        "endpointAuthorization": {"secret": WEBHOOK_SECRET},
    })
    print("Subscriber (steps/exercise/heart-rate/sleep):")
    print(json.dumps(subscriber, indent=2))

    provider_user_ids = _connected_provider_user_ids()
    if not provider_user_ids:
        print("\nManual subscription (sleep): no connected users yet, nothing to subscribe.")
        return

    for health_user_id in provider_user_ids:
        if _sleep_subscription_exists(base, health_user_id):
            print(f"\nManual subscription (sleep) for {health_user_id}: already exists, skipping.")
            continue

        create_response = _request("POST", f"{base}/{SUBSCRIBER_ID}/subscriptions", {
            "user": f"users/{health_user_id}",
            "dataTypes": MANUAL_DATA_TYPES,
        })
        _raise_with_body(create_response)
        print(f"\nManual subscription (sleep) for {health_user_id}:")
        print(json.dumps(create_response.json(), indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 auth/register_webhook_subscription.py <public-https-url> <gcp-project-id>")
        sys.exit(1)
    register(sys.argv[1], sys.argv[2])
