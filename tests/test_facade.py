# tests/test_facade.py
# TravelFacade wiring: record_workout crediting distance + calibrating
# stride/speed, and record_steps not double-counting a window a foot-based
# workout already covered. No network calls (route/session seeded
# directly, same pattern as the smoke test in progress/day3.md); DBs point
# at a temp file so tests never touch the real data/total_distance.db.

import datetime
import pytest
from core.facade import TravelFacade, METERS_PER_MILE
from core.observer_decorator.event_listener import EventListener
from data.total_distance_db import TotalDistanceDB
from data.landmarks_db import LandmarksDB
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint
from services.fitbit_pydantic_schema import ExerciseData, TimeInterval, ExerciseMetricsSummary

MM_PER_MILE = 1_609_344
TOTAL_DISTANCE_M = 100 * METERS_PER_MILE  # a round 100-mile route


class _RecordingListener(EventListener):
    """Test double for a Concrete Subscriber - just remembers every
    message it was notified with, in order."""

    def __init__(self):
        self.received = []

    def update(self, message) -> None:
        self.received.append(message)


def _route(total_distance_m):
    return Route(
        points=[
            RoutePoint(Coordinates(25.7, -80.2), point_number=1, distance_from_start=0.0,
                       distance_to_destination=total_distance_m, distance_to_previous=0.0, distance_to_next=total_distance_m),
            RoutePoint(Coordinates(41.8, -87.6), point_number=2, distance_from_start=total_distance_m,
                       distance_to_destination=0.0, distance_to_previous=total_distance_m, distance_to_next=0.0),
        ],
        total_distance=total_distance_m,
        point_count=2,
    )


@pytest.fixture
def facade(tmp_path):
    f = TravelFacade()
    db_path = str(tmp_path / "test_total_distance.db")
    f._db = TotalDistanceDB(db_path)
    f._landmarks_db = LandmarksDB(db_path)

    f._sessions["me"] = {
        "route": _route(TOTAL_DISTANCE_M),
        "meters_walked": 0.0,
        "gender": None,
        "stride_length_m": None,
        "started_at": datetime.datetime.now(datetime.timezone.utc),
        "stride_by_type": {},
        "speed_by_type_m_per_s": {},
        "workout_intervals": [],
        "destination": "Chicago, Illinois",
        "milestones_notified": set(),
    }
    return f


def _exercise(exercise_type, start, end, distance_mm=None, steps=None, avg_speed=None, avg_pace=None):
    return ExerciseData(
        interval=TimeInterval(startTime=start, endTime=end),
        exerciseType=exercise_type,
        metricsSummary=ExerciseMetricsSummary(
            distanceMillimeters=distance_mm,
            steps=steps,
            averageSpeedMillimetersPerSecond=avg_speed,
            averagePaceSecondsPerMeter=avg_pace,
        ),
    )


def test_record_workout_adds_measured_distance_and_does_not_touch_stride_by_type(facade):
    # A real per-user stride (as if seeded from Google Health's profile at
    # start_journey) must survive a workout untouched - no calibration
    # overwriting it with a value derived from this one workout.
    facade._sessions["me"]["stride_by_type"]["WALKING"] = 0.7

    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    state = facade.record_workout("me", exercise)

    assert state["miles_walked"] == pytest.approx(3_200_000 / MM_PER_MILE)
    assert facade._sessions["me"]["workout_intervals"] == [("2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z")]
    assert facade._sessions["me"]["stride_by_type"]["WALKING"] == 0.7


def test_record_steps_skips_distance_already_covered_by_a_workout(facade):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout("me", exercise)
    meters_after_workout = facade._sessions["me"]["meters_walked"]

    interval = TimeInterval(startTime="2026-09-08T18:00:00Z", endTime="2026-09-08T18:45:00Z")
    facade.record_steps("me", 4200, interval)

    assert facade._sessions["me"]["meters_walked"] == pytest.approx(meters_after_workout)  # not double-counted
    # The workout's own record_sync already logged these 4200 steps -
    # logging them again here would double the step total too.
    assert facade._db.today_steps("me") == 4200


def test_record_steps_outside_any_workout_window_still_adds_distance(facade):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout("me", exercise)
    meters_after_workout = facade._sessions["me"]["meters_walked"]

    # A different time window - not covered by the workout above.
    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps("me", 3000, interval)

    assert facade._sessions["me"]["meters_walked"] > meters_after_workout


def test_non_foot_exercise_adds_no_distance_and_does_not_block_steps(facade):
    exercise = _exercise("BIKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=8_000_000, steps=6000)
    facade.record_workout("me", exercise)

    assert facade._sessions["me"]["meters_walked"] == 0.0
    assert facade._sessions["me"]["workout_intervals"] == []

    # Steps during the same window as the bike ride still count normally -
    # biking isn't tracked as a covered interval.
    interval = TimeInterval(startTime="2026-09-08T18:10:00Z", endTime="2026-09-08T18:20:00Z")
    state = facade.record_steps("me", 1000, interval)
    assert state["miles_walked"] > 0.0


def test_record_workout_with_only_steps_uses_the_real_per_user_stride(facade):
    # As if seeded from Google Health's profile at start_journey - not
    # derived from any past workout (no calibration).
    facade._sessions["me"]["stride_by_type"]["RUNNING"] = 0.9

    exercise = _exercise("RUNNING", "2026-09-08T07:00:00Z", "2026-09-08T07:30:00Z", steps=1000)
    facade.record_workout("me", exercise)

    assert facade._sessions["me"]["meters_walked"] == pytest.approx(1000 * 0.9)


# --- Observer pattern wiring (landmark / halfway / finished events) ---

def test_landmark_event_notifies_with_name_and_percent(facade):
    facade._landmarks_db.save_landmarks("me", [
        {"name": "TownA", "coords": {"lat": 30, "lng": -81}, "miles_from_start": 10.0, "percent": 10.0},
    ])
    listener = _RecordingListener()
    facade.events.subscribe("landmark", listener)

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps("me", 100_000, interval)  # far past mile 10 with the default stride

    assert listener.received == ["🏁 Landmark reached: TownA (10.0% of the way there!)"]


def test_halfway_event_notifies_once_and_never_again(facade):
    listener = _RecordingListener()
    facade.events.subscribe("halfway", listener)
    facade._sessions["me"]["meters_walked"] = 49.99 * METERS_PER_MILE

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps("me", 100, interval)  # small nudge past the 50% line
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]

    facade.record_steps("me", 100, interval)  # still well past 50% - must not refire
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]


# --- app.py's UI-facing helpers ---

def _start_journey_facade(monkeypatch, profile: dict):
    f = TravelFacade()
    monkeypatch.setattr(f._geocoder, "geocode", lambda place: Coordinates(0, 0))
    monkeypatch.setattr(f._router, "get_walking_route", lambda start, end: _route(10.0))
    monkeypatch.setattr(f._landmarks_db, "save_landmarks", lambda user_id, landmarks: None)
    monkeypatch.setattr("core.facade.get_profile", lambda: profile)
    return f


def test_start_journey_stores_round_trip_but_route_stays_one_way(monkeypatch):
    f = _start_journey_facade(monkeypatch, {})

    f.start_journey("me", "A", "B", round_trip=True)

    assert f._sessions["me"]["round_trip"] is True
    assert f._sessions["me"]["route"].total_distance == 10.0  # not doubled - flagged, not built this pass


def test_start_journey_seeds_stride_from_the_real_google_health_profile(monkeypatch):
    f = _start_journey_facade(monkeypatch, {
        "userConfiguredWalkingStrideLengthMm": 693,
        "userConfiguredRunningStrideLengthMm": 1150,
    })

    f.start_journey("me", "A", "B")

    assert f._sessions["me"]["stride_by_type"]["WALKING"] == pytest.approx(0.693)
    assert f._sessions["me"]["stride_by_type"]["RUNNING"] == pytest.approx(1.150)
    assert f._sessions["me"]["stride_length_m"] == pytest.approx(0.693)  # walking - the general steps-to-distance default


def test_start_journey_falls_back_cleanly_with_no_connection(monkeypatch):
    f = TravelFacade()
    monkeypatch.setattr(f._geocoder, "geocode", lambda place: Coordinates(0, 0))
    monkeypatch.setattr(f._router, "get_walking_route", lambda start, end: _route(10.0))
    monkeypatch.setattr(f._landmarks_db, "save_landmarks", lambda user_id, landmarks: None)

    def _raise():
        raise RuntimeError("no active Google Health connection")
    monkeypatch.setattr("core.facade.get_profile", _raise)

    f.start_journey("me", "A", "B")

    assert f._sessions["me"]["stride_by_type"] == {}
    assert f._sessions["me"]["stride_length_m"] is None


def test_search_places_delegates_to_the_geocoder(facade, monkeypatch):
    monkeypatch.setattr(facade._geocoder, "search_places", lambda query, limit=5: [f"{query} match"])
    assert facade.search_places("ariz") == ["ariz match"]


def test_current_location_place_delegates_to_reverse_geocode(facade, monkeypatch):
    monkeypatch.setattr(facade._geocoder, "reverse_geocode", lambda coords: f"place at {coords.lat},{coords.lng}")
    assert facade.current_location_place(44.9, -93.2) == "place at 44.9,-93.2"


def test_finished_event_includes_destination_and_total_steps(facade):
    listener = _RecordingListener()
    facade.events.subscribe("finished", listener)
    facade._sessions["me"]["meters_walked"] = 99.999 * METERS_PER_MILE

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    state = facade.record_steps("me", 100, interval)

    assert state["percent_complete"] == 100.0
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]

    facade.record_steps("me", 50, interval)  # already finished - must not refire
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]
