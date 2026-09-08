# tests/test_facade.py
# TravelFacade wiring: record_workout crediting distance + calibrating
# stride/pace, and record_steps not double-counting a window a foot-based
# workout already covered. No network calls (route/session seeded
# directly, same pattern as the smoke test in progress/day3.md); DBs point
# at a temp file so tests never touch the real data/total_distance.db.

import datetime
import pytest
from core.facade import TravelFacade
from core.observer_decorator.event_listener import EventListener
from data.total_distance_db import TotalDistanceDB
from data.landmarks_db import LandmarksDB
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint
from travel_logic.checkpoints import Checkpoint
from services.fitbit_pydantic_schema import ExerciseData, TimeInterval, ExerciseMetricsSummary

MM_PER_MILE = 1_609_344


class _RecordingListener(EventListener):
    """Test double for a Concrete Subscriber - just remembers every
    message it was notified with, in order."""

    def __init__(self):
        self.received = []

    def update(self, message) -> None:
        self.received.append(message)


@pytest.fixture
def facade(tmp_path):
    f = TravelFacade()
    db_path = str(tmp_path / "test_total_distance.db")
    f._db = TotalDistanceDB(db_path)
    f._landmarks_db = LandmarksDB(db_path)

    route = Route(
        points=[RoutePoint(Coordinates(25.7, -80.2), 0.0), RoutePoint(Coordinates(41.8, -87.6), 100.0)],
        total_miles=100.0,
    )
    f._sessions["me"] = {
        "route": route,
        "miles_walked": 0.0,
        "gender": None,
        "stride_length_m": None,
        "started_at": datetime.datetime.now(datetime.timezone.utc),
        "stride_by_type": {},
        "pace_by_type_mph": {},
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


def test_record_workout_adds_measured_distance_and_calibrates_stride(facade):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    state = facade.record_workout("me", exercise)

    assert state["miles_walked"] == pytest.approx(3_200_000 / MM_PER_MILE)
    assert facade._sessions["me"]["workout_intervals"] == [("2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z")]
    assert facade._sessions["me"]["stride_by_type"]["WALKING"] == pytest.approx(3200 / 4200)


def test_record_steps_skips_distance_already_covered_by_a_workout(facade):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout("me", exercise)
    miles_after_workout = facade._sessions["me"]["miles_walked"]

    interval = TimeInterval(startTime="2026-09-08T18:00:00Z", endTime="2026-09-08T18:45:00Z")
    state = facade.record_steps("me", 4200, interval)

    assert state["miles_walked"] == pytest.approx(miles_after_workout)  # not double-counted
    # The workout's own record_sync already logged these 4200 steps -
    # logging them again here would double the step total too.
    assert facade._db.today_steps("me") == 4200


def test_record_steps_outside_any_workout_window_still_adds_distance(facade):
    exercise = _exercise("WALKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=3_200_000, steps=4200)
    facade.record_workout("me", exercise)
    miles_after_workout = facade._sessions["me"]["miles_walked"]

    # A different time window - not covered by the workout above.
    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    state = facade.record_steps("me", 3000, interval)

    assert state["miles_walked"] > miles_after_workout


def test_non_foot_exercise_adds_no_distance_and_does_not_block_steps(facade):
    exercise = _exercise("BIKING", "2026-09-08T18:00:00Z", "2026-09-08T18:45:00Z", distance_mm=8_000_000, steps=6000)
    facade.record_workout("me", exercise)

    assert facade._sessions["me"]["miles_walked"] == 0.0
    assert facade._sessions["me"]["workout_intervals"] == []

    # Steps during the same window as the bike ride still count normally -
    # biking isn't tracked as a covered interval.
    interval = TimeInterval(startTime="2026-09-08T18:10:00Z", endTime="2026-09-08T18:20:00Z")
    state = facade.record_steps("me", 1000, interval)
    assert state["miles_walked"] > 0.0


def test_record_workout_without_distance_or_steps_uses_calibrated_pace_from_a_prior_run(facade):
    # First run: reports a real average speed - calibrates RUNNING's pace.
    first = _exercise("RUNNING", "2026-09-08T07:00:00Z", "2026-09-08T07:30:00Z", avg_speed=2500)
    facade.record_workout("me", first)
    miles_after_first = facade._sessions["me"]["miles_walked"]
    calibrated_pace = facade._sessions["me"]["pace_by_type_mph"]["RUNNING"]
    assert calibrated_pace == pytest.approx((2500 / MM_PER_MILE) * 3600)

    # Second run: no distance, no steps, no reported speed - just a
    # duration. Falls back to the pace calibrated above.
    second = _exercise("RUNNING", "2026-09-09T07:00:00Z", "2026-09-09T07:30:00Z")
    state = facade.record_workout("me", second)
    assert state["miles_walked"] == pytest.approx(miles_after_first + calibrated_pace * 0.5)


# --- Observer pattern wiring (landmark / halfway / finished events) ---

def test_landmark_event_notifies_with_name_and_percent(facade):
    facade._landmarks_db.save_landmarks("me", [
        Checkpoint(name="TownA", coords=Coordinates(30, -81), miles_from_start=10.0, percent=10.0),
    ])
    listener = _RecordingListener()
    facade.events.subscribe("landmark", listener)

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps("me", 100_000, interval)  # far past mile 10 with the default stride

    assert listener.received == ["🏁 Landmark reached: TownA (10.0% of the way there!)"]


def test_halfway_event_notifies_once_and_never_again(facade):
    listener = _RecordingListener()
    facade.events.subscribe("halfway", listener)
    facade._sessions["me"]["miles_walked"] = 49.99

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    facade.record_steps("me", 100, interval)  # small nudge past the 50% line
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]

    facade.record_steps("me", 100, interval)  # still well past 50% - must not refire
    assert listener.received == ["🎉 Halfway to your goal - 50%!"]


def test_finished_event_includes_destination_and_total_steps(facade):
    listener = _RecordingListener()
    facade.events.subscribe("finished", listener)
    facade._sessions["me"]["miles_walked"] = 99.999

    interval = TimeInterval(startTime="2026-09-08T09:00:00Z", endTime="2026-09-08T09:30:00Z")
    state = facade.record_steps("me", 100, interval)

    assert state["percent_complete"] == 100.0
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]

    facade.record_steps("me", 50, interval)  # already finished - must not refire
    assert listener.received == ["🏆 You reached Chicago, Illinois in 100 steps! Congrats!"]
