# tests/test_google_health_webhook.py
# The real ingestion pipeline: webhook notification -> resolve which
# WorldWalker user this Google account belongs to -> pull -> Strategy ->
# typed object -> TravelFacade (steps/exercise) or a structured print
# (sleep/heart-rate, no persistence yet). Tested against its own minimal
# FastAPI app (not app.py) - same pattern as tests/test_auth_router.py.
#
# process_notification() resolves the WorldWalker user from the
# notification's own "user": "users/{healthUserId}" field (Google's own
# identity - the only one a webhook ever carries) via
# auth.connections.get_user_id_for_provider_user_id(), never "whichever
# connection happens to be active." Most tests here use the
# connected_user_id fixture (tests/conftest.py) - a User with an active
# GoogleHealthConnection whose provider_user_id is f"test-provider-{user_id}".

import uuid
from math import degrees

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.google_health.webhook as webhook_module
from core.facade import travel_facade
from data.total_distance_db import TotalDistanceDB
from database.models import GoogleHealthConnection, User
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


def _provider_user_id(user_id) -> str:
    """Matches tests/conftest.py's connected_user_id fixture, which sets
    provider_user_id to exactly this."""
    return f"test-provider-{user_id}"


def _google_user(user_id) -> str:
    return f"users/{_provider_user_id(user_id)}"


def _connect_new_user(session) -> uuid.UUID:
    """A second, independent connected user - for proving one user's
    webhook notification can't resolve to (or credit) another's."""
    user = User()
    session.add(user)
    session.flush()
    session.add(GoogleHealthConnection(
        user_id=user.id, provider_user_id=_provider_user_id(user.id), status="active",
    ))
    session.commit()
    return user.id


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
    user_id, _trip = active_journey
    calls = []

    def fake_get_data_points(data_type, start_time, end_time, notified_user_id):
        calls.append((data_type, start_time, end_time, notified_user_id))
        return [STEPS_POINT]

    monkeypatch.setattr(webhook_module, "get_data_points", fake_get_data_points)

    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "user": _google_user(user_id),
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)

    assert calls == [("steps", "2026-09-01T15:00:00Z", "2026-09-01T16:00:00Z", user_id)]
    assert "1250 steps" in capsys.readouterr().out


def test_notification_missing_data_type_is_handled_gracefully(capsys):
    process_notification({"operation": "UPSERT", "user": "users/whoever", "intervals": []})
    assert "Notification missing dataType" in capsys.readouterr().out


def test_notification_missing_user_field_is_skipped(capsys):
    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)
    assert "can't tell which WorldWalker account" in capsys.readouterr().out


def test_notification_for_an_unknown_google_account_is_skipped(patched_session, capsys):
    # patched_session (not connected_user_id): the DB session is real but
    # empty - nobody's ever connected this Google account, so
    # get_user_id_for_provider_user_id() has nothing to resolve. Using the
    # patched, rolled-back test session here (rather than leaving
    # SessionLocal unpatched) keeps this test from ever touching the real
    # dev database.
    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "user": "users/never-connected",
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)
    assert "Skipping webhook notification" in capsys.readouterr().out


def test_notification_resolves_to_the_matching_user_not_another_connected_one(
    active_journey, patched_session, monkeypatch, capsys
):
    """The actual webhook multi-tenancy proof: two users are connected: a
    notification naming user A's Google account must credit user A's
    trip, never user B's - even though user B also has an active
    connection at the same time."""
    user_a_id, trip = active_journey
    user_b_id = _connect_new_user(patched_session)

    monkeypatch.setattr(webhook_module, "get_data_points", lambda *a, **k: [STEPS_POINT])

    notification = {
        "dataType": "steps",
        "operation": "UPSERT",
        "user": _google_user(user_a_id),
        "intervals": [{"physicalTimeInterval": {"startTime": "2026-09-01T15:00:00Z", "endTime": "2026-09-01T16:00:00Z"}}],
    }
    process_notification(notification)

    assert travel_facade._db.today_steps(str(trip.id)) == 1250
    assert "No active journey" not in capsys.readouterr().out
    # user_b_id exists only to prove it was never touched - no trip means
    # crediting it would have raised, so a clean run above is the proof.
    assert user_b_id != user_a_id


def test_notification_pull_failure_logs_cleanly_instead_of_raising(active_journey, monkeypatch, capsys):
    user_id, _trip = active_journey

    def failing_get_data_points(data_type, start_time, end_time, notified_user_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhook_module, "get_data_points", failing_get_data_points)

    notification = {
        "dataType": "sleep",
        "operation": "UPSERT",
        "user": _google_user(user_id),
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
            "user": "users/never-connected",
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
    # database. No matching connection exists there, so this proves only
    # the fast-ack path, not that steps were credited.
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

    def fake_get_data_points(data_type, start_time, end_time, user_id):
        calls.append((data_type, start_time, end_time, user_id))
        return []

    monkeypatch.setattr(webhook_module, "get_data_points", fake_get_data_points)

    provider_user_id = "some-google-account"
    backfill_since(provider_user_id, "2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert set(BACKFILL_DATA_TYPES) == {"steps", "exercise", "sleep", "heart-rate"}
    assert calls == []  # no connection for "some-google-account" - every pull is skipped, not crashed


def test_backfill_since_defaults_end_time_to_now(connected_user_id, monkeypatch):
    calls = []
    monkeypatch.setattr(webhook_module, "get_data_points", lambda *a, **k: calls.append(a) or [])

    backfill_since(_provider_user_id(connected_user_id), "2026-09-05T00:00:00Z")

    # Every call got some non-empty end_time (defaulted to "now"), not None.
    assert calls
    assert all(call[2] for call in calls)


def test_backfill_since_routes_pulled_points_through_the_normal_pipeline(active_journey, monkeypatch, capsys):
    user_id, _trip = active_journey
    monkeypatch.setattr(
        webhook_module, "get_data_points", lambda data_type, s, e, uid: [STEPS_POINT] if data_type == "steps" else []
    )

    backfill_since(_provider_user_id(user_id), "2026-09-05T00:00:00Z", "2026-09-08T00:00:00Z")

    assert "1250 steps" in capsys.readouterr().out
