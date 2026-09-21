# tests/test_google_health_webhook.py
# The real ingestion pipeline: webhook notification -> pull -> Strategy ->
# typed object -> TravelFacade (steps/exercise) or a structured print
# (sleep/heart-rate, no persistence yet). Tested against its own minimal
# FastAPI app (not app.py) - same pattern as tests/test_auth_router.py.
#
# process_notification() now resolves the connected user itself
# (auth.connections.get_active_user_id(), the same lookup app.py's
# endpoints use) before doing anything else, so most tests here need the
# connected_user_id fixture (tests/conftest.py) - a User with an active
# GoogleHealthConnection - not just a bare user_id.

import uuid
from math import degrees

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.google_health.webhook as webhook_module
from core.facade import travel_facade
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
from travel_logic.route_service import EARTH_RADIUS_METERS, Route, RoutePoint

app = FastAPI()
app.include_router(router)
client = TestClient(app)

STEPS_POINT = {
    "interval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"},
    "count": "1250",
}

TOTAL_DISTANCE_M = 100_000.0


def _route() -> Route:
    """Two points on the equator, exactly TOTAL_DISTANCE_M apart by real
    haversine distance - see tests/test_facade.py's _route() for why this
    has to be exact now that core.facade rebuilds a Route from stored
    {lat, lng} points instead of trusting an explicit distance field."""
    end_lng = degrees(TOTAL_DISTANCE_M / EARTH_RADIUS_METERS)
    start, end = Coordinates(0.0, 0.0), Coordinates(0.0, end_lng)
    return Route(
        points=[
            RoutePoint(start, point_number=1, distance_from_start=0.0,
                       distance_to_destination=TOTAL_DISTANCE_M, distance_to_previous=0.0, distance_to_next=TOTAL_DISTANCE_M),
            RoutePoint(end, point_number=2, distance_from_start=TOTAL_DISTANCE_M,
                       distance_to_destination=0.0, distance_to_previous=TOTAL_DISTANCE_M, distance_to_next=0.0),
        ],
        total_distance=TOTAL_DISTANCE_M,
        point_count=2,
    )


@pytest.fixture
def active_journey(connected_user_id, seed_trip, tmp_path, monkeypatch):
    """A real (non-mocked) TravelFacade trip + a temp step-sync DB, so a
    test can prove data actually lands in the database, not just that a
    function was called. Route points are ~100km apart on the same
    meridian - close enough to 100_000.0m real haversine that record_steps'
    default stride can't overshoot the route in one call.

    Returns (user_id, trip) - today_steps/total_steps are keyed by trip_id
    now (data/total_distance_db.py), not user_id, so callers need both."""
    monkeypatch.setattr(travel_facade, "_db", TotalDistanceDB(str(tmp_path / "steps.db")))
    trip = seed_trip(connected_user_id, _route())
    return connected_user_id, trip


def test_steps_routes_and_prints_summary(connected_user_id, capsys):
    process_health_data("steps", STEPS_POINT, connected_user_id)
    assert "1250 steps" in capsys.readouterr().out


def test_steps_data_point_is_actually_recorded_in_the_database(active_journey, capsys):
    user_id, trip = active_journey
    process_health_data("steps", STEPS_POINT, user_id)
    assert travel_facade._db.today_steps(str(trip.id)) == 1250


def test_unknown_data_type_is_handled_gracefully(capsys):
    process_health_data("sneeze", {}, uuid.uuid4())
    assert "Unknown or unhandled dataType: sneeze" in capsys.readouterr().out


def test_steps_with_no_active_journey_fails_soft(connected_user_id, capsys):
    process_health_data("steps", STEPS_POINT, connected_user_id)  # no active_journey fixture here
    assert "No active journey" in capsys.readouterr().out


def test_notification_pulls_data_for_each_interval_and_routes_it(active_journey, monkeypatch, capsys):
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


def test_notification_with_no_connected_user_is_skipped(patched_session, capsys):
    # patched_session (not connected_user_id): the DB session is real but
    # empty - nobody's clicked Connect yet, so get_active_user_id() has
    # nothing to resolve. Using the patched, rolled-back test session here
    # (rather than leaving SessionLocal unpatched) keeps this test from
    # ever touching the real dev database.
    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)
    assert "Skipping webhook notification" in capsys.readouterr().out


def test_notification_pull_failure_logs_cleanly_instead_of_raising(active_journey, monkeypatch, capsys):
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


def test_webhook_acks_204_and_schedules_background_pull(patched_session, monkeypatch, capsys):
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

    # patched_session keeps the background task's own SessionLocal() call
    # inside this test's rolled-back transaction instead of the real dev
    # database. No connected user exists there, so this proves only the
    # fast-ack path, not that steps were credited.
    assert response.status_code == 204


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


def test_backfill_since_routes_pulled_points_through_the_normal_pipeline(active_journey, monkeypatch, capsys):
    monkeypatch.setattr(webhook_module, "get_data_points", lambda data_type, s, e: [STEPS_POINT] if data_type == "steps" else [])

    backfill_since("2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert "1250 steps" in capsys.readouterr().out
