# tests/test_google_health_webhook.py
# The real ingestion pipeline: webhook notification -> pull -> Strategy ->
# typed object -> TravelFacade (steps/exercise) or a structured print
# (sleep/heart-rate, no persistence yet). Tested against its own minimal
# FastAPI app (not app.py) - same pattern as tests/test_auth_router.py.

import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.google_health.webhook as webhook_module
from core.facade import travel_facade
from data.landmarks_db import LandmarksDB
from data.total_distance_db import TotalDistanceDB
from services.google_health.webhook import (
    router,
    process_health_data,
    process_notification,
    backfill_since,
    BACKFILL_DATA_TYPES,
    WEBHOOK_SECRET,
)
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint

app = FastAPI()
app.include_router(router)
client = TestClient(app)

STEPS_POINT = {
    "interval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"},
    "count": "1250",
}


@pytest.fixture
def active_journey(tmp_path, monkeypatch):
    """A real (non-mocked) TravelFacade session + temp DBs, so a test can
    prove data actually lands in the database, not just that a function
    was called."""
    monkeypatch.setattr(travel_facade, "_db", TotalDistanceDB(str(tmp_path / "steps.db")))
    monkeypatch.setattr(travel_facade, "_landmarks_db", LandmarksDB(str(tmp_path / "steps.db")))
    travel_facade._sessions["me"] = {
        "route": Route(
            points=[
                RoutePoint(Coordinates(0, 0), point_number=1, distance_from_start=0.0,
                           distance_to_destination=100_000.0, distance_to_previous=0.0, distance_to_next=100_000.0),
                RoutePoint(Coordinates(1, 1), point_number=2, distance_from_start=100_000.0,
                           distance_to_destination=0.0, distance_to_previous=100_000.0, distance_to_next=0.0),
            ],
            total_distance=100_000.0,
            point_count=2,
        ),
        "meters_walked": 0.0,
        "gender": None,
        "stride_length_m": 0.7,
        "started_at": datetime.datetime.now(datetime.timezone.utc),
        "stride_by_type": {},
        "speed_by_type_m_per_s": {},
        "workout_intervals": [],
        "destination": "Somewhere",
        "milestones_notified": set(),
    }
    yield
    del travel_facade._sessions["me"]


def test_steps_routes_and_prints_summary(capsys):
    process_health_data("steps", STEPS_POINT)
    assert "1250 steps" in capsys.readouterr().out


def test_steps_data_point_is_actually_recorded_in_the_database(active_journey):
    process_health_data("steps", STEPS_POINT)
    assert travel_facade._db.today_steps("me") == 1250


def test_unknown_data_type_is_handled_gracefully(capsys):
    process_health_data("sneeze", {})
    assert "Unknown or unhandled dataType: sneeze" in capsys.readouterr().out


def test_steps_with_no_active_journey_fails_soft(capsys):
    process_health_data("steps", STEPS_POINT)  # no active_journey fixture here
    assert "No active journey" in capsys.readouterr().out


def test_notification_pulls_data_for_each_interval_and_routes_it(monkeypatch, capsys):
    calls = []

    def fake_get_data_points(data_type, start_time, end_time):
        calls.append((data_type, start_time, end_time))
        return [STEPS_POINT]

    monkeypatch.setattr(webhook_module, "get_data_points", fake_get_data_points)

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

    monkeypatch.setattr(webhook_module, "get_data_points", failing_get_data_points)

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
    monkeypatch.setattr(webhook_module, "get_data_points", lambda *a, **k: [STEPS_POINT])

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
        headers={"Authorization": WEBHOOK_SECRET},
    )

    assert response.status_code == 204
    assert "1250 steps" in capsys.readouterr().out


def test_webhook_verification_ping_is_accepted():
    response = client.post(
        "/api/webhook/google-health",
        json={"type": "verification"},
        headers={"Authorization": WEBHOOK_SECRET},
    )
    assert response.status_code == 200


def test_backfill_since_pulls_every_tracked_data_type_for_the_given_range(monkeypatch):
    calls = []

    def fake_get_data_points(data_type, start_time, end_time):
        calls.append((data_type, start_time, end_time))
        return []

    monkeypatch.setattr(webhook_module, "get_data_points", fake_get_data_points)

    backfill_since("2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert set(BACKFILL_DATA_TYPES) == {"steps", "exercise", "sleep", "heart-rate"}
    assert calls == [
        (data_type, "2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z") for data_type in BACKFILL_DATA_TYPES
    ]


def test_backfill_since_defaults_end_time_to_now(monkeypatch):
    calls = []
    monkeypatch.setattr(webhook_module, "get_data_points", lambda *a, **k: calls.append(a) or [])

    backfill_since("2026-09-05T00:00:00Z")

    # Every call got some non-empty end_time (defaulted to "now"), not None.
    assert all(call[2] for call in calls)


def test_backfill_since_routes_pulled_points_through_the_normal_pipeline(monkeypatch, capsys):
    monkeypatch.setattr(webhook_module, "get_data_points", lambda data_type, s, e: [STEPS_POINT] if data_type == "steps" else [])

    backfill_since("2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert "1250 steps" in capsys.readouterr().out
