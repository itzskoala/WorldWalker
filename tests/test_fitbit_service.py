# tests/test_fitbit_service.py

from fastapi.testclient import TestClient

import services.fitbit_service as fitbit_service
from services.fitbit_service import app, process_health_data, process_notification, backfill_since, BACKFILL_DATA_TYPES

client = TestClient(app)

STEPS_POINT = {
    "interval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"},
    "count": "1250",
}


def test_steps_routes_and_prints_summary(capsys):
    process_health_data("steps", STEPS_POINT)
    out = capsys.readouterr().out
    assert "1250 steps" in out


def test_unknown_data_type_is_handled_gracefully(capsys):
    process_health_data("sneeze", {})
    out = capsys.readouterr().out
    assert "Unknown or unhandled dataType: sneeze" in out


def test_notification_pulls_data_for_each_interval_and_routes_it(monkeypatch, capsys):
    calls = []

    def fake_get_data_points(data_type, start_time, end_time):
        calls.append((data_type, start_time, end_time))
        return [STEPS_POINT]

    monkeypatch.setattr(fitbit_service, "get_data_points", fake_get_data_points)

    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)

    assert calls == [("steps", "2026-09-01T15:00:00Z", "2026-09-01T16:00:00Z")]
    assert "1250 steps" in capsys.readouterr().out


def test_notification_missing_data_type_is_handled_gracefully(capsys):
    process_notification({"operation": "UPSERT", "intervals": []})
    assert "Notification missing dataType" in capsys.readouterr().out


def test_notification_pull_failure_logs_cleanly_instead_of_raising(monkeypatch, capsys):
    def failing_get_data_points(data_type, start_time, end_time):
        raise RuntimeError("boom")

    monkeypatch.setattr(fitbit_service, "get_data_points", failing_get_data_points)

    notification = {
        "dataType": "sleep",
        "operation": "UPSERT",
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T05:00:00Z", "endTime": "2026-09-01T13:00:00Z"}}],
    }
    process_notification(notification)  # must not raise

    assert "Failed to pull sleep" in capsys.readouterr().out


def test_webhook_requires_auth_header():
    response = client.post("/api/webhook/google-health", json=[])
    assert response.status_code == 401


def test_webhook_acks_204_and_schedules_background_pull(monkeypatch, capsys):
    monkeypatch.setattr(fitbit_service, "get_data_points", lambda *a, **k: [STEPS_POINT])

    payload = [{
        "data": {
            "dataType": "steps",
            "operation": "UPSERT",
            "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
        }
    }]
    response = client.post(
        "/api/webhook/google-health",
        json=payload,
        headers={"Authorization": "Bearer MySuperSecureSecretToken"},
    )

    assert response.status_code == 204
    assert "1250 steps" in capsys.readouterr().out


def test_backfill_since_pulls_every_tracked_data_type_for_the_given_range(monkeypatch):
    calls = []

    def fake_get_data_points(data_type, start_time, end_time):
        calls.append((data_type, start_time, end_time))
        return []

    monkeypatch.setattr(fitbit_service, "get_data_points", fake_get_data_points)

    backfill_since("2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert set(BACKFILL_DATA_TYPES) == {"steps", "exercise", "sleep", "heart-rate"}
    assert calls == [
        (data_type, "2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z") for data_type in BACKFILL_DATA_TYPES
    ]


def test_backfill_since_defaults_end_time_to_now(monkeypatch):
    calls = []
    monkeypatch.setattr(fitbit_service, "get_data_points", lambda *a, **k: calls.append(a) or [])

    backfill_since("2026-09-05T00:00:00Z")

    # Every call got some non-empty end_time (defaulted to "now"), not None.
    assert all(call[2] for call in calls)


def test_backfill_since_routes_pulled_points_through_the_normal_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(fitbit_service, "get_data_points", lambda data_type, s, e: [STEPS_POINT] if data_type == "steps" else [])

    backfill_since("2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert "1250 steps" in capsys.readouterr().out


def test_auth_callback_is_reachable_through_the_fully_mounted_app():
    # Regression guard: gr.mount_gradio_app(app, ..., path="/") is a
    # catch-all Mount added at the bottom of this module. A route included
    # *after* that Mount would silently 404/fall through to Gradio instead
    # of reaching FastAPI - confirms auth_router really is registered
    # before that mount, not just reachable in auth/router.py's own
    # isolated test app (see tests/test_auth_router.py).
    response = client.get("/auth/google/callback", params={"error": "access_denied"})
    assert response.status_code == 400


def test_webhook_verification_ping_is_accepted():
    # Google's verification handshake: {"type": "verification"}, no "data" key.
    response = client.post(
        "/api/webhook/google-health",
        json={"type": "verification"},
        headers={"Authorization": "Bearer MySuperSecureSecretToken"},
    )
    assert response.status_code == 200
