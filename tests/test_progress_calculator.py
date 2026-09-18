# tests/test_progress_calculator.py
# Pure math, no network/DB calls - stride resolution, steps -> meters,
# empirical pace/ETA, exact position on the route (interpolated between
# real OSRM vertices, not snapped to the nearest one), and workout
# distance/calibration. See travel_logic/progress_calculator.py.

import pytest
from travel_logic.progress_calculator import (
    resolve_stride_m,
    steps_to_meters,
    meters_remaining,
    average_daily_meters,
    estimate_days_remaining,
    locate_on_route,
    workout_distance_m,
    calibrate_from_workout,
    interval_duration_hours,
    interval_within_any,
    milestones_just_crossed,
    MALE_STRIDE_M,
    FEMALE_STRIDE_M,
    DEFAULT_STRIDE_M,
    DEFAULT_STRIDE_M_BY_TYPE,
)
from travel_logic.route_service import Route, RoutePoint
from travel_logic.coordinates import Coordinates


# --- resolve_stride_m ---

def test_resolve_stride_m_prefers_google_health_value_over_everything():
    assert resolve_stride_m(google_health_stride_m=0.9, age=30, height_cm=170, weight_kg=70, gender="female") == 0.9


def test_resolve_stride_m_uses_the_age_height_weight_sex_formula_for_a_man():
    stride = resolve_stride_m(age=30, height_cm=170, weight_kg=70, gender="male")
    full_stride_cm = 34.70 - (0.30 * 30) + (0.76 * 170) - (0.15 * 70) - (3.33 * 0)
    assert stride == pytest.approx(full_stride_cm / 2 / 100)


def test_resolve_stride_m_uses_the_age_height_weight_sex_formula_for_a_woman():
    stride = resolve_stride_m(age=30, height_cm=170, weight_kg=70, gender="female")
    full_stride_cm = 34.70 - (0.30 * 30) + (0.76 * 170) - (0.15 * 70) - (3.33 * 1)
    assert stride == pytest.approx(full_stride_cm / 2 / 100)


def test_resolve_stride_m_falls_back_to_gender_average_when_formula_inputs_incomplete():
    assert resolve_stride_m(gender="male") == MALE_STRIDE_M
    assert resolve_stride_m(gender="female") == FEMALE_STRIDE_M
    # Missing weight - can't run the formula, so it falls all the way to
    # the gender average, not a partial/guessed calculation.
    assert resolve_stride_m(age=30, height_cm=170, gender="male") == MALE_STRIDE_M


def test_resolve_stride_m_falls_back_to_unisex_default_with_nothing_to_go_on():
    assert resolve_stride_m() == DEFAULT_STRIDE_M
    assert resolve_stride_m(gender="unspecified") == DEFAULT_STRIDE_M


def test_resolve_stride_m_formula_needs_a_real_male_or_female_gender():
    # age/height/weight alone aren't enough - the formula's sex term needs
    # gender to be exactly "male" or "female".
    assert resolve_stride_m(age=30, height_cm=170, weight_kg=70) == DEFAULT_STRIDE_M


# --- steps_to_meters / meters_remaining ---

def test_steps_to_meters_multiplies_by_the_given_stride():
    assert steps_to_meters(4000, DEFAULT_STRIDE_M) == pytest.approx(4000 * DEFAULT_STRIDE_M)


def test_steps_to_meters_zero_steps_is_zero_meters():
    assert steps_to_meters(0, DEFAULT_STRIDE_M) == 0.0


def test_meters_remaining_subtracts_covered_from_total():
    assert meters_remaining(100_000.0, 40_000.0) == 60_000.0


def test_meters_remaining_never_goes_negative():
    assert meters_remaining(100_000.0, 150_000.0) == 0.0


# --- average_daily_meters / estimate_days_remaining ---

def test_average_daily_meters_computes_empirical_pace():
    assert average_daily_meters(10_000.0, 2.0) == 5_000.0


def test_average_daily_meters_none_until_real_progress_exists():
    # No guessed fallback - None means "unknown," not a made-up pace.
    assert average_daily_meters(0.0, 2.0) is None
    assert average_daily_meters(-1.0, 2.0) is None
    assert average_daily_meters(5_000.0, 0.0) is None
    assert average_daily_meters(5_000.0, -1.0) is None


def test_estimate_days_remaining_computes_eta():
    assert estimate_days_remaining(10_000.0, 5_000.0) == 2.0


def test_estimate_days_remaining_none_without_a_real_pace():
    assert estimate_days_remaining(10_000.0, None) is None
    assert estimate_days_remaining(10_000.0, 0.0) is None
    assert estimate_days_remaining(10_000.0, -3.0) is None


# --- locate_on_route ---

def _sample_route():
    return Route(
        points=[
            RoutePoint(Coordinates(41.80, -87.65), point_number=1, distance_from_start=0.0,
                       distance_to_destination=1300.0, distance_to_previous=0.0, distance_to_next=500.0),
            RoutePoint(Coordinates(41.81, -87.64), point_number=2, distance_from_start=500.0,
                       distance_to_destination=800.0, distance_to_previous=500.0, distance_to_next=800.0),
            RoutePoint(Coordinates(41.83, -87.60), point_number=3, distance_from_start=1300.0,
                       distance_to_destination=0.0, distance_to_previous=800.0, distance_to_next=0.0),
        ],
        total_distance=1300.0,
        point_count=3,
    )


def test_locate_on_route_interpolates_between_bracketing_points():
    progress = locate_on_route(_sample_route(), 650.0)
    assert progress.coords.lat == pytest.approx(41.81375)
    assert progress.coords.lng == pytest.approx(-87.6325)
    assert progress.distance_walked_m == 650.0
    assert progress.distance_remaining_m == pytest.approx(650.0)
    assert progress.percent_complete == pytest.approx(50.0)


def test_locate_on_route_exact_vertex_hit_matches_that_vertex():
    progress = locate_on_route(_sample_route(), 500.0)
    assert progress.coords.lat == pytest.approx(41.81)
    assert progress.coords.lng == pytest.approx(-87.64)


def test_locate_on_route_at_the_very_start():
    progress = locate_on_route(_sample_route(), 0.0)
    assert progress.coords == Coordinates(41.80, -87.65)
    assert progress.distance_walked_m == 0.0
    assert progress.percent_complete == 0.0


def test_locate_on_route_clamps_past_the_end():
    progress = locate_on_route(_sample_route(), 999_999.0)
    assert progress.coords == Coordinates(41.83, -87.60)
    assert progress.distance_walked_m == 1300.0
    assert progress.distance_remaining_m == 0.0
    assert progress.percent_complete == 100.0


def test_locate_on_route_clamps_negative_distance_to_the_start():
    progress = locate_on_route(_sample_route(), -500.0)
    assert progress.coords == Coordinates(41.80, -87.65)
    assert progress.distance_walked_m == 0.0


def test_locate_on_route_empty_route_raises_value_error():
    with pytest.raises(ValueError):
        locate_on_route(Route(points=[], total_distance=0.0, point_count=0), 500.0)


# --- workout_distance_m ---

def test_workout_distance_m_non_foot_type_never_counts():
    assert workout_distance_m(
        "BIKING", duration_hours=1.0, distance_mm=5_000_000, steps=1000
    ) is None


def test_workout_distance_m_prefers_direct_measured_distance():
    meters = workout_distance_m("WALKING", duration_hours=0.75, distance_mm=3_200_000)
    assert meters == pytest.approx(3200.0)


def test_workout_distance_m_uses_reported_speed_when_no_distance():
    meters = workout_distance_m("RUNNING", duration_hours=0.5, avg_speed_mm_per_s=2000)
    assert meters == pytest.approx(2.0 * 0.5 * 3600)


def test_workout_distance_m_uses_reported_pace_when_no_speed_or_distance():
    # 0.5 s/m == 2 m/s, same as the speed test above, for one hour.
    meters = workout_distance_m("RUNNING", duration_hours=1.0, avg_pace_s_per_m=0.5)
    assert meters == pytest.approx(2.0 * 1.0 * 3600)


def test_workout_distance_m_uses_calibrated_stride_for_the_activity_type():
    meters = workout_distance_m(
        "RUNNING", duration_hours=0.5, steps=5000, stride_by_type={"RUNNING": 1.2}
    )
    assert meters == pytest.approx(5000 * 1.2)


def test_workout_distance_m_uses_type_default_stride_when_uncalibrated():
    meters = workout_distance_m("RUNNING", duration_hours=0.5, steps=5000)
    assert meters == pytest.approx(5000 * DEFAULT_STRIDE_M_BY_TYPE["RUNNING"])


def test_workout_distance_m_walking_type_falls_through_to_generic_default():
    meters = workout_distance_m("WALKING", duration_hours=0.5, steps=5000)
    assert meters == pytest.approx(5000 * DEFAULT_STRIDE_M)


def test_workout_distance_m_uses_calibrated_speed_when_only_duration_known():
    meters = workout_distance_m(
        "RUNNING", duration_hours=0.5, speed_by_type_m_per_s={"RUNNING": 3.0}
    )
    assert meters == pytest.approx(3.0 * 0.5 * 3600)


def test_workout_distance_m_none_when_nothing_usable_is_given():
    assert workout_distance_m("WALKING", duration_hours=0.5) is None


# --- calibrate_from_workout ---

def test_calibrate_from_workout_derives_stride_from_distance_and_steps():
    calibration = calibrate_from_workout("WALKING", duration_hours=0.75, distance_mm=3_200_000, steps=4200)
    assert calibration.stride_m == pytest.approx(3200 / 4200)


def test_calibrate_from_workout_prefers_reported_speed_over_derived_speed():
    calibration = calibrate_from_workout(
        "RUNNING", duration_hours=1.0, distance_mm=1_600_000, avg_speed_mm_per_s=2500
    )
    assert calibration.speed_m_per_s == pytest.approx(2.5)


def test_calibrate_from_workout_derives_speed_from_distance_and_duration_as_a_fallback():
    calibration = calibrate_from_workout("RUNNING", duration_hours=0.5, distance_mm=3_600_000)
    assert calibration.speed_m_per_s == pytest.approx(2.0)  # 3600m in half an hour = 2 m/s


def test_calibrate_from_workout_non_foot_type_yields_nothing():
    calibration = calibrate_from_workout(
        "BIKING", duration_hours=1.0, distance_mm=8_000_000, steps=6000, avg_speed_mm_per_s=2500
    )
    assert calibration.stride_m is None
    assert calibration.speed_m_per_s is None


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
