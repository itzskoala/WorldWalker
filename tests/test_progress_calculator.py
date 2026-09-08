# tests/test_progress_calculator.py
# Pure math, no network calls - steps -> miles, empirical pace/ETA, and
# exact position on the route (interpolated between real OSRM vertices,
# not snapped to the nearest one - see travel_logic/progress_calculator.py).

import pytest
from travel_logic.progress_calculator import (
    resolve_stride_m,
    steps_to_miles,
    average_daily_miles,
    estimate_days_remaining,
    locate_on_route,
    workout_distance_miles,
    calibrate_from_workout,
    interval_duration_hours,
    interval_within_any,
    milestones_just_crossed,
    MALE_STRIDE_M,
    FEMALE_STRIDE_M,
    DEFAULT_STRIDE_M,
    DEFAULT_STRIDE_M_BY_TYPE,
    METERS_PER_MILE,
)
from travel_logic.route_service import Route, RoutePoint
from travel_logic.coordinates import Coordinates


# --- resolve_stride_m / steps_to_miles ---

def test_resolve_stride_m_prefers_real_user_value_over_gender():
    assert resolve_stride_m(user_stride_m=0.9, gender="female") == 0.9


def test_resolve_stride_m_falls_back_to_gender_average():
    assert resolve_stride_m(gender="male") == MALE_STRIDE_M
    assert resolve_stride_m(gender="female") == FEMALE_STRIDE_M


def test_resolve_stride_m_falls_back_to_unisex_default():
    assert resolve_stride_m() == DEFAULT_STRIDE_M
    assert resolve_stride_m(gender="unspecified") == DEFAULT_STRIDE_M


def test_steps_to_miles_uses_the_resolved_stride():
    miles = steps_to_miles(4000, gender=None)
    assert miles == pytest.approx((4000 * DEFAULT_STRIDE_M) / METERS_PER_MILE)


def test_steps_to_miles_zero_steps_is_zero_miles():
    assert steps_to_miles(0) == 0.0


# --- average_daily_miles / estimate_days_remaining ---

def test_average_daily_miles_computes_empirical_pace():
    assert average_daily_miles(10.0, 2.0) == 5.0


def test_average_daily_miles_none_until_real_progress_exists():
    # No guessed fallback - None means "unknown," not a made-up pace.
    assert average_daily_miles(0.0, 2.0) is None
    assert average_daily_miles(-1.0, 2.0) is None
    assert average_daily_miles(5.0, 0.0) is None
    assert average_daily_miles(5.0, -1.0) is None


def test_estimate_days_remaining_computes_eta():
    assert estimate_days_remaining(10.0, 5.0) == 2.0


def test_estimate_days_remaining_none_without_a_real_pace():
    assert estimate_days_remaining(10.0, None) is None
    assert estimate_days_remaining(10.0, 0.0) is None
    assert estimate_days_remaining(10.0, -3.0) is None


# --- locate_on_route ---

def _sample_route():
    return Route(
        points=[
            RoutePoint(Coordinates(41.80, -87.65), 12.00),
            RoutePoint(Coordinates(41.81, -87.64), 12.50),
            RoutePoint(Coordinates(41.83, -87.60), 13.00),
        ],
        total_miles=13.00,
    )


def test_locate_on_route_interpolates_between_bracketing_points():
    # The exact worked example from the design discussion.
    progress = locate_on_route(_sample_route(), 12.34)
    assert progress.position.coords.lat == pytest.approx(41.8068, abs=1e-4)
    assert progress.position.coords.lng == pytest.approx(-87.6432, abs=1e-4)
    assert progress.miles_walked == 12.34
    assert progress.miles_remaining == pytest.approx(0.66)
    assert progress.percent_complete == pytest.approx(12.34 / 13.00 * 100)


def test_locate_on_route_exact_vertex_hit_matches_that_vertex():
    progress = locate_on_route(_sample_route(), 12.50)
    assert progress.position.coords.lat == pytest.approx(41.81)
    assert progress.position.coords.lng == pytest.approx(-87.64)


def test_locate_on_route_at_the_very_start():
    progress = locate_on_route(_sample_route(), 0.0)
    assert progress.position.coords == Coordinates(41.80, -87.65)
    assert progress.miles_walked == 0.0
    assert progress.percent_complete == 0.0


def test_locate_on_route_clamps_past_the_end():
    progress = locate_on_route(_sample_route(), 999.0)
    assert progress.position.coords == Coordinates(41.83, -87.60)
    assert progress.miles_walked == 13.00
    assert progress.miles_remaining == 0.0
    assert progress.percent_complete == 100.0


def test_locate_on_route_clamps_negative_miles_to_the_start():
    progress = locate_on_route(_sample_route(), -5.0)
    assert progress.position.coords == Coordinates(41.80, -87.65)
    assert progress.miles_walked == 0.0


def test_locate_on_route_empty_route_raises_value_error():
    with pytest.raises(ValueError):
        locate_on_route(Route(points=[], total_miles=0.0), 5.0)


# --- workout_distance_miles ---

def test_workout_distance_miles_non_foot_type_never_counts():
    assert workout_distance_miles(
        "BIKING", duration_hours=1.0, distance_mm=5_000_000, steps=1000
    ) is None


def test_workout_distance_miles_prefers_direct_measured_distance():
    miles = workout_distance_miles("WALKING", duration_hours=0.75, distance_mm=3_200_000)
    assert miles == pytest.approx(3_200_000 / (METERS_PER_MILE * 1000))


def test_workout_distance_miles_uses_reported_speed_when_no_distance():
    # 2 m/s (2000 mm/s) for half an hour.
    miles = workout_distance_miles("RUNNING", duration_hours=0.5, avg_speed_mm_per_s=2000)
    expected_mph = (2000 / (METERS_PER_MILE * 1000)) * 3600
    assert miles == pytest.approx(expected_mph * 0.5)


def test_workout_distance_miles_uses_reported_pace_when_no_speed_or_distance():
    # 0.5 s/m == 2 m/s, same as the speed test above, for one hour.
    miles = workout_distance_miles("RUNNING", duration_hours=1.0, avg_pace_s_per_m=0.5)
    expected_mph = ((1 / 0.5) / METERS_PER_MILE) * 3600
    assert miles == pytest.approx(expected_mph)


def test_workout_distance_miles_uses_calibrated_stride_for_the_activity_type():
    miles = workout_distance_miles(
        "RUNNING", duration_hours=0.5, steps=5000, stride_by_type={"RUNNING": 1.2}
    )
    assert miles == pytest.approx((5000 * 1.2) / METERS_PER_MILE)


def test_workout_distance_miles_uses_type_default_stride_when_uncalibrated():
    miles = workout_distance_miles("RUNNING", duration_hours=0.5, steps=5000)
    assert miles == pytest.approx((5000 * DEFAULT_STRIDE_M_BY_TYPE["RUNNING"]) / METERS_PER_MILE)


def test_workout_distance_miles_walking_type_falls_through_to_generic_default():
    miles = workout_distance_miles("WALKING", duration_hours=0.5, steps=5000)
    assert miles == pytest.approx((5000 * DEFAULT_STRIDE_M) / METERS_PER_MILE)


def test_workout_distance_miles_uses_calibrated_pace_when_only_duration_known():
    miles = workout_distance_miles(
        "RUNNING", duration_hours=0.5, pace_by_type_mph={"RUNNING": 6.0}
    )
    assert miles == pytest.approx(3.0)


def test_workout_distance_miles_none_when_nothing_usable_is_given():
    assert workout_distance_miles("WALKING", duration_hours=0.5) is None


# --- calibrate_from_workout ---

def test_calibrate_from_workout_derives_stride_from_distance_and_steps():
    calibration = calibrate_from_workout("WALKING", duration_hours=0.75, distance_mm=3_200_000, steps=4200)
    assert calibration.stride_m == pytest.approx(3200 / 4200)


def test_calibrate_from_workout_prefers_reported_speed_over_derived_pace():
    calibration = calibrate_from_workout(
        "RUNNING", duration_hours=1.0, distance_mm=1_609_344, avg_speed_mm_per_s=2500
    )
    expected_mph = (2500 / (METERS_PER_MILE * 1000)) * 3600
    assert calibration.pace_mph == pytest.approx(expected_mph)


def test_calibrate_from_workout_derives_pace_from_distance_and_duration_as_a_fallback():
    calibration = calibrate_from_workout("RUNNING", duration_hours=0.5, distance_mm=1_609_344)
    assert calibration.pace_mph == pytest.approx(2.0)  # 1 mile in half an hour


def test_calibrate_from_workout_non_foot_type_yields_nothing():
    calibration = calibrate_from_workout(
        "BIKING", duration_hours=1.0, distance_mm=8_000_000, steps=6000, avg_speed_mm_per_s=2500
    )
    assert calibration.stride_m is None
    assert calibration.pace_mph is None


# --- interval helpers ---

def test_interval_duration_hours_computes_the_gap():
    hours = interval_duration_hours("2026-08-11T18:00:00Z", "2026-08-11T18:30:00Z")
    assert hours == pytest.approx(0.5)


def test_interval_within_any_true_when_fully_contained():
    covering = [("2026-08-11T18:00:00Z", "2026-08-11T18:45:00Z")]
    assert interval_within_any("2026-08-11T18:10:00Z", "2026-08-11T18:20:00Z", covering) is True


def test_interval_within_any_false_when_only_partially_overlapping():
    covering = [("2026-08-11T18:00:00Z", "2026-08-11T18:45:00Z")]
    assert interval_within_any("2026-08-11T18:30:00Z", "2026-08-11T19:00:00Z", covering) is False


def test_interval_within_any_false_when_no_overlap():
    covering = [("2026-08-11T18:00:00Z", "2026-08-11T18:45:00Z")]
    assert interval_within_any("2026-08-11T20:00:00Z", "2026-08-11T20:10:00Z", covering) is False


# --- milestones_just_crossed ---

def test_milestones_just_crossed_fires_halfway_at_50_percent():
    assert milestones_just_crossed(50.0, set()) == {"halfway"}


def test_milestones_just_crossed_fires_both_when_a_sync_jumps_straight_to_100():
    assert milestones_just_crossed(100.0, set()) == {"halfway", "finished"}


def test_milestones_just_crossed_never_refires_an_already_notified_one():
    assert milestones_just_crossed(75.0, {"halfway"}) == set()
    assert milestones_just_crossed(100.0, {"halfway", "finished"}) == set()


def test_milestones_just_crossed_nothing_below_halfway():
    assert milestones_just_crossed(49.9, set()) == set()
