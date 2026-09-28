# tests/test_facade.py
# TravelFacade wiring: record_workout crediting distance + calibrating
# stride/speed, record_steps not double-counting a window a foot-based
# workout already covered, and the Observer events firing at the right
# moments. Journey state lives in Postgres now (database/trips.py), not an
# in-memory dict - these tests seed an ActiveTrip row directly via
# tests/conftest.py's seed_trip fixture, on the same transactional
# db_session the patched_session fixture makes core.facade.SessionLocal
# reuse, so every assertion here reads back real database state.

from math import degrees

import pytest

from core.facade import TravelFacade, METERS_PER_MILE
from core.observer_decorator.event_listener import EventListener
from database import trips
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import EARTH_RADIUS_METERS, Route, RoutePoint
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


def _route(total_distance_m: float) -> Route:
    """Two points on the equator, exactly total_distance_m apart by real
    haversine distance. This matters now: core.facade rebuilds a Route
    from a trip's stored {lat, lng} points via
    travel_logic.route_service.build_route(), which recomputes distance
    from real haversine between consecutive points - unlike the old
    in-memory Route, a route whose points aren't actually that far apart
    would silently disagree with the total_distance_m a test expects."""
    end_lng = degrees(total_distance_m / EARTH_RADIUS_METERS)
    start, end = Coordinates(0.0, 0.0), Coordinates(0.0, end_lng)
    return Route(
        points=[
            RoutePoint(start, point_number=1, distance_from_start=0.0,
                       distance_to_destination=total_distance_m, distance_to_previous=0.0, distance_to_next=total_distance_m),
            RoutePoint(end, point_number=2, distance_from_start=total_distance_m,
                       distance_to_destination=0.0, distance_to_previous=total_distance_m, distance_to_next=0.0),
        ],
        total_distance=total_distance_m,
        point_count=2,
    )


def _the_active_trip(session, user_id):
    """These tests each seed exactly one trip (via the facade fixture's
    seed_trip call below), so "the" active trip is always
    get_active_trips()[0] now that a user can have several at once."""
    return trips.get_active_trips(session, user_id)[0]


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


@pytest.fixture
def facade(patched_session, user_id, seed_trip) -> TravelFacade:
    f = TravelFacade()
    seed_trip(user_id, _route(TOTAL_DISTANCE_M))
    return f


def test_record_workout_adds_measured_distance_and_does_not_touch_stride_by_type(facade, user_id, patched_session):
    # A real per-user stride (as if seeded from Google Health's profile at
    # start_journey) must survive a workout untouched - no calibration
    # overwriting it with a value derived from this one workout.
    trip = _the_active_trip(patched_session, user_id)
    trip.stride_by_type = {"WALKING": 0.7}
    patched_session.commit()

    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    # record_workout() fans out over every active trip and returns one
    # state dict per trip - this fixture seeds exactly one.
    state = facade.record_workout(user_id, exercise)[0]

    assert state["miles_walked"] == pytest.approx(3_200_000 / MM_PER_MILE)
    assert trip.workout_intervals == [["2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z"]]
    assert trip.stride_by_type["WALKING"] == 0.7


def test_record_steps_skips_distance_already_covered_by_a_workout(facade, user_id, patched_session):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout(user_id, exercise)
    trip = _the_active_trip(patched_session, user_id)
    meters_after_workout = trip.meters_walked

    interval = TimeInterval(startTime="2026-09-08T18:00:00Z", endTime="2026-09-08T18:45:00Z")
    facade.record_steps(user_id, 4200, interval)

    assert trip.meters_walked == pytest.approx(meters_after_workout)  # not double-counted
    # The workout's own record_sync already logged these 4200 steps -
    # logging them again here would double the step total too.
    assert facade._db.today_steps(str(trip.id)) == 4200


def test_record_steps_outside_any_workout_window_still_adds_distance(facade, user_id, patched_session):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout(user_id, exercise)
    trip = _the_active_trip(patched_session, user_id)
    meters_after_workout = trip.meters_walked

    # A different time window - not covered by the workout above.
    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps(user_id, 3000, interval)

    assert trip.meters_walked > meters_after_workout


def test_each_trip_tracks_its_own_step_totals_independently(user_id, patched_session, seed_trip):
    # Multi-trip fan-out (record_steps credits every active trip with the
    # same real step count) must never make one trip's "today's steps" /
    # "total steps" bleed into another's - each trip logs its own row in
    # data/total_distance_db.py, keyed by trip_id.
    f = TravelFacade()
    trip_a = seed_trip(user_id, _route(TOTAL_DISTANCE_M), to_place="Trip A")
    trip_b = seed_trip(user_id, _route(TOTAL_DISTANCE_M), to_place="Trip B")

    f.record_steps(user_id, 1000)  # both trips are active - both get credited

    assert f._db.today_steps(str(trip_a.id)) == 1000
    assert f._db.today_steps(str(trip_b.id)) == 1000

    # Pausing trip B opts it out - later steps only add to trip A's total.
    trips.pause_trip(patched_session, trip_b)
    f.record_steps(user_id, 500)

    assert f._db.today_steps(str(trip_a.id)) == 1500
    assert f._db.today_steps(str(trip_b.id)) == 1000
    assert f._db.total_steps(str(trip_a.id)) == 1500
    assert f._db.total_steps(str(trip_b.id)) == 1000


def test_lifetime_steps_sums_across_every_trip_this_user_has_ever_run(user_id, patched_session, seed_trip):
    # Profile screen's one stat (frontend/src/pages/ProfilePage.tsx) - unlike
    # today_steps/total_steps above, this is keyed by user_id, not one
    # trip_id, so it should keep growing across trips instead of
    # resetting per trip.
    f = TravelFacade()
    trip_a = seed_trip(user_id, _route(TOTAL_DISTANCE_M), to_place="Trip A")
    f.record_steps(user_id, 1000)

    trips.complete_trip(patched_session, trip_a)
    trip_b = seed_trip(user_id, _route(TOTAL_DISTANCE_M), to_place="Trip B")
    f.record_steps(user_id, 750)

    assert f.lifetime_steps(user_id) == 1750


def test_non_foot_exercise_adds_no_distance_and_does_not_block_steps(facade, user_id, patched_session):
    exercise = _exercise("BIKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=8_000_000, steps=6000)
    facade.record_workout(user_id, exercise)

    trip = _the_active_trip(patched_session, user_id)
    assert trip.meters_walked == 0.0
    assert trip.workout_intervals == []

    # Steps during the same window as the bike ride still count normally -
    # biking isn't tracked as a covered interval.
    interval = TimeInterval(startTime="2026-09-08T18:10:00Z", endTime="2026-09-08T18:20:00Z")
    state = facade.record_steps(user_id, 1000, interval)[0]
    assert state["miles_walked"] > 0.0


def test_record_workout_with_only_steps_uses_the_real_per_user_stride(facade, user_id, patched_session):
    # As if seeded from Google Health's profile at start_journey - not
    # derived from any past workout (no calibration).
    trip = _the_active_trip(patched_session, user_id)
    trip.stride_by_type = {"RUNNING": 0.9}
    patched_session.commit()

    exercise = _exercise("RUNNING", "2026-09-08T07:00:00Z", "2026-09-08T07:30:00Z", steps=1000)
    facade.record_workout(user_id, exercise)

    assert trip.meters_walked == pytest.approx(1000 * 0.9)


# --- Observer pattern wiring (landmark / halfway / finished events) ---

def test_landmark_event_notifies_with_name_and_percent(facade, user_id, patched_session, seed_checkpoint):
    trip = _the_active_trip(patched_session, user_id)
    seed_checkpoint(trip, "TownA", distance_from_start_m=10.0 * METERS_PER_MILE)

    listener = _RecordingListener()
    facade.events.subscribe("landmark", listener)

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps(user_id, 100_000, interval)  # far past mile 10 with the default stride

    assert listener.received == ["🏁 Landmark reached: TownA (10.0% of the way there!)"]


def test_checkpoint_reached_event_carries_user_and_checkpoint_details(
    facade, user_id, patched_session, seed_checkpoint
):
    trip = _the_active_trip(patched_session, user_id)
    trip.user.email = "walker@example.com"
    seed_checkpoint(
        trip, "TownA", distance_from_start_m=10.0 * METERS_PER_MILE,
        checkpoint_number=1, description="A stop along the way in TownA.",
    )
    patched_session.commit()

    listener = _RecordingListener()
    facade.events.subscribe("checkpoint_reached", listener)

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps(user_id, 100_000, interval)  # far past mile 10 with the default stride

    assert len(listener.received) == 1
    event = listener.received[0]
    assert event.user_id == user_id
    assert event.user_name == "walker@example.com"
    assert event.checkpoint_name == "TownA"
    assert event.checkpoint_number == 1
    assert event.description == "A stop along the way in TownA."


def test_halfway_event_notifies_once_and_never_again(facade, user_id, patched_session):
    listener = _RecordingListener()
    facade.events.subscribe("halfway", listener)

    trip = _the_active_trip(patched_session, user_id)
    trip.meters_walked = 49.99 * METERS_PER_MILE
    patched_session.commit()

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps(user_id, 100, interval)  # small nudge past the 50% line
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]

    facade.record_steps(user_id, 100, interval)  # still well past 50% - must not refire
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]


# --- app.py's UI-facing helpers ---

def _start_journey_facade(monkeypatch, profile: dict) -> TravelFacade:
    f = TravelFacade()
    monkeypatch.setattr(f._geocoder, "geocode", lambda place: Coordinates(0, 0))
    monkeypatch.setattr(f._router, "get_walking_route", lambda start, end: _route(10.0))
    monkeypatch.setattr("core.facade.get_profile", lambda user_id: profile)
    return f


def test_start_journey_stores_round_trip_but_route_stays_one_way(patched_session, user_id, monkeypatch):
    f = _start_journey_facade(monkeypatch, {})

    f.start_journey(user_id, "A", "B", round_trip=True)

    trip = _the_active_trip(patched_session, user_id)
    assert trip.round_trip is True
    assert trip.total_distance_m == 10.0  # not doubled - flagged, not built this pass


def test_start_journey_seeds_stride_from_the_real_google_health_profile(patched_session, user_id, monkeypatch):
    f = _start_journey_facade(monkeypatch, {
        "userConfiguredWalkingStrideLengthMm": 693,
        "userConfiguredRunningStrideLengthMm": 1150,
    })

    f.start_journey(user_id, "A", "B")

    trip = _the_active_trip(patched_session, user_id)
    assert trip.stride_by_type["WALKING"] == pytest.approx(0.693)
    assert trip.stride_by_type["RUNNING"] == pytest.approx(1.150)
    assert trip.stride_length_m == pytest.approx(0.693)  # walking - the general steps-to-distance default


def test_start_journey_falls_back_cleanly_with_no_connection(patched_session, user_id, monkeypatch):
    f = TravelFacade()
    monkeypatch.setattr(f._geocoder, "geocode", lambda place: Coordinates(0, 0))
    monkeypatch.setattr(f._router, "get_walking_route", lambda start, end: _route(10.0))

    def _raise(user_id):
        raise RuntimeError("no active Google Health connection")
    monkeypatch.setattr("core.facade.get_profile", _raise)

    f.start_journey(user_id, "A", "B")

    trip = _the_active_trip(patched_session, user_id)
    assert trip.stride_by_type == {}
    assert trip.stride_length_m is None


def test_search_places_delegates_to_the_geocoder(facade, monkeypatch):
    monkeypatch.setattr(facade._geocoder, "search_places", lambda query, limit=5: [f"{query} match"])
    assert facade.search_places("ariz") == ["ariz match"]


def test_current_location_place_delegates_to_reverse_geocode(facade, monkeypatch):
    monkeypatch.setattr(facade._geocoder, "reverse_geocode", lambda coords: f"place at {coords.lat},{coords.lng}")
    assert facade.current_location_place(44.9, -93.2) == "place at 44.9,-93.2"


def test_finished_event_includes_destination_and_total_steps(facade, user_id, patched_session):
    listener = _RecordingListener()
    facade.events.subscribe("finished", listener)

    trip = _the_active_trip(patched_session, user_id)
    trip.meters_walked = 99.999 * METERS_PER_MILE
    patched_session.commit()

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    state = facade.record_steps(user_id, 100, interval)[0]

    assert state["percent_complete"] == 100.0
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]

    # The trip is completed now - trips.complete_trip() flipped its status,
    # so there's no active trip left to credit. Same ValueError the real
    # webhook path already handles (services/google_health/webhook.py
    # catches it and logs, rather than crashing).
    with pytest.raises(ValueError):
        facade.record_steps(user_id, 50, interval)
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]
