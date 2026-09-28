# tests/test_register_webhook_subscription.py
# The public-URL/project-id resolution logic in
# auth/register_webhook_subscription.py - CLI argument vs. env var
# fallback, and the guardrails that stop a mistake (localhost, a
# non-https URL, nothing given at all) from silently registering a
# subscription that can never actually deliver anything. Doesn't call
# Google or touch the database - _service_account_token()/_request() are
# never exercised here.

import pytest

from auth import register_webhook_subscription as rws


# --- _resolve_public_url ---

def test_resolve_public_url_prefers_the_cli_argument(monkeypatch):
    monkeypatch.setenv("WEBHOOK_PUBLIC_URL", "https://from-env.example.com")
    assert rws._resolve_public_url("https://from-cli.example.com") == "https://from-cli.example.com"


def test_resolve_public_url_falls_back_to_the_env_var(monkeypatch):
    monkeypatch.setenv("WEBHOOK_PUBLIC_URL", "https://from-env.example.com")
    assert rws._resolve_public_url(None) == "https://from-env.example.com"


def test_resolve_public_url_strips_a_trailing_slash(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    assert rws._resolve_public_url("https://example.com/") == "https://example.com"


def test_resolve_public_url_raises_when_nothing_is_given(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    with pytest.raises(SystemExit):
        rws._resolve_public_url(None)


def test_resolve_public_url_rejects_a_non_https_url(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    with pytest.raises(SystemExit):
        rws._resolve_public_url("http://example.com")


@pytest.mark.parametrize("local_url", [
    "https://localhost:8010",
    "https://127.0.0.1:8010",
    "https://0.0.0.0:8010",
])
def test_resolve_public_url_rejects_local_addresses(monkeypatch, local_url):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    with pytest.raises(SystemExit):
        rws._resolve_public_url(local_url)


def test_resolve_public_url_accepts_a_real_deployment_url(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    assert rws._resolve_public_url("https://worldwalker.example.com") == "https://worldwalker.example.com"


def test_resolve_public_url_accepts_a_tunnel_url_passed_explicitly(monkeypatch):
    # A tunnel is fine for local dev testing as long as it's passed
    # explicitly, not baked into any default - the guardrail is against
    # unreachable addresses (localhost), not against tunnels themselves.
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    assert rws._resolve_public_url("https://abc123.ngrok-free.app") == "https://abc123.ngrok-free.app"


# --- _resolve_project_id ---

def test_resolve_project_id_prefers_the_cli_argument(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "from-env")
    assert rws._resolve_project_id("from-cli") == "from-cli"


def test_resolve_project_id_falls_back_to_the_env_var(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "from-env")
    assert rws._resolve_project_id(None) == "from-env"


def test_resolve_project_id_raises_when_nothing_is_given(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(SystemExit):
        rws._resolve_project_id(None)


# --- register(): the resolved endpoint URL Google is actually told about ---

def test_register_points_at_the_real_webhook_route(monkeypatch):
    monkeypatch.delenv("WEBHOOK_PUBLIC_URL", raising=False)
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)

    seen = {}

    def fake_upsert_subscriber(base, body):
        seen["base"] = base
        seen["endpointUri"] = body["endpointUri"]
        return {}

    monkeypatch.setattr(rws, "_upsert_subscriber", fake_upsert_subscriber)
    monkeypatch.setattr(rws, "_connected_provider_user_ids", lambda: [])

    rws.register("https://worldwalker.example.com", "my-project")

    assert seen["endpointUri"] == "https://worldwalker.example.com/api/webhook/google-health"
    assert seen["base"] == "https://health.googleapis.com/v4/projects/my-project/subscribers"


def test_register_rejects_a_local_url_before_calling_google(monkeypatch):
    calls = []
    monkeypatch.setattr(rws, "_upsert_subscriber", lambda base, body: calls.append(body))

    with pytest.raises(SystemExit):
        rws.register("https://127.0.0.1:8010", "my-project")

    assert calls == []
