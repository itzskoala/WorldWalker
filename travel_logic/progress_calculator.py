#progress_calculator.py

# Pure math, no network/DB calls: turns real-world activity (steps,
# workouts) into distance along a route, in meters.

import bisect
from datetime import datetime

from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.dataclasses.progress import Progress
from travel_logic.dataclasses.workout_calibration import WorkoutCalibration

# Population-average per-step distance, CDC reference: 0.76m for men,
# 0.66m for women. DEFAULT_STRIDE_M is the midpoint - the "no information
# at all" fallback.
MALE_STRIDE_M = 0.76
FEMALE_STRIDE_M = 0.66
DEFAULT_STRIDE_M = (MALE_STRIDE_M + FEMALE_STRIDE_M) / 2

# Running covers more ground per step than walking - used only when no
# real per-user calibrated stride exists yet for that activity type.
RUNNING_STRIDE_M = 1.15
DEFAULT_STRIDE_M_BY_TYPE = {
    "RUNNING": RUNNING_STRIDE_M,
    "TRAIL_RUN": RUNNING_STRIDE_M,
    "INCLINE_RUN": RUNNING_STRIDE_M,
}

# The on-foot subset of Google Health's exercise type enum.
FOOT_EXERCISE_TYPES = frozenset({
    "WALKING", "POWER_WALKING", "INCLINE_WALK", "TREADMILL_WALK",
    "STROLLER_WALK", "RUNNING", "TRAIL_RUN", "INCLINE_RUN", "HIKING",
    "NORDIC_WALKING",
})

HALFWAY_PERCENT = 50.0
FINISHED_PERCENT = 100.0


def resolve_stride_m(google_health_stride_m=None, age=None, height_cm=None, weight_kg=None, gender=None):
    """Priority: real device-calibrated value > age/height/weight/gender
    formula > population average by gender > unisex population average."""
    if google_health_stride_m:
        return google_health_stride_m

    calculated = _calculated_stride_m(age, height_cm, weight_kg, gender)
    if calculated is not None:
        return calculated

    if gender == "male":
        return MALE_STRIDE_M
    if gender == "female":
        return FEMALE_STRIDE_M
    return DEFAULT_STRIDE_M


def _calculated_stride_m(age, height_cm, weight_kg, gender):
    """Regression for full stride length in cm, halved into a single-step
    distance. None unless all four inputs are real and sensible."""
    if age is None or height_cm is None or weight_kg is None or gender not in ("male", "female"):
        return None

    sex = 1 if gender == "female" else 0
    full_stride_cm = 34.70 - (0.30 * age) + (0.76 * height_cm) - (0.15 * weight_kg) - (3.33 * sex)
    step_m = (full_stride_cm / 2) / 100
    return step_m if step_m > 0 else None


def steps_to_meters(steps, stride_m):
    return steps * stride_m


def meters_remaining(total_distance_m, distance_covered_m):
    return max(0.0, total_distance_m - distance_covered_m)


def average_daily_meters(distance_covered_m, days_elapsed):
    """Empirical pace only - None until real progress and elapsed time exist."""
    if distance_covered_m <= 0 or days_elapsed <= 0:
        return None
    return distance_covered_m / days_elapsed


def estimate_days_remaining(distance_remaining_m, daily_meters):
    if not daily_meters or daily_meters <= 0:
        return None
    return distance_remaining_m / daily_meters


def locate_on_route(route, distance_walked_m):
    """Exact position at distance_walked_m along the route - linear interpolation between the two bracketing points."""
    if not route.points:
        raise ValueError("Route has no points")

    total = route.total_distance
    # Clamp against the route's own last point, not total_distance - the
    # two can disagree by a tiny float epsilon.
    distance_walked_m = max(0.0, min(distance_walked_m, route.points[-1].distance_from_start))

    distances = []
    for point in route.points:
        distances.append(point.distance_from_start)
    idx = bisect.bisect_left(distances, distance_walked_m)

    if idx < len(distances) and distances[idx] == distance_walked_m:
        coords = route.points[idx].coords
    else:
        before, after = route.points[idx - 1], route.points[idx]
        span = after.distance_from_start - before.distance_from_start
        fraction = (distance_walked_m - before.distance_from_start) / span
        coords = Coordinates(
            lat=before.coords.lat + fraction * (after.coords.lat - before.coords.lat),
            lng=before.coords.lng + fraction * (after.coords.lng - before.coords.lng),
        )

    percent_complete = FINISHED_PERCENT if total == 0 else (distance_walked_m / total) * 100

    return Progress(
        coords=coords,
        distance_walked_m=distance_walked_m,
        distance_remaining_m=meters_remaining(total, distance_walked_m),
        percent_complete=percent_complete,
    )


def workout_distance_m(exercise_type, duration_hours, distance_mm=None, steps=None,
                        avg_speed_mm_per_s=None, avg_pace_s_per_m=None,
                        stride_by_type=None, speed_by_type_m_per_s=None):
    """A completed workout's distance, priority order: recorded distance >
    device speed/pace x duration > steps x stride > calibrated speed x
    duration. None if the type isn't foot-based or nothing usable is given."""
    if exercise_type not in FOOT_EXERCISE_TYPES:
        return None

    if distance_mm:
        return distance_mm / 1000

    if avg_speed_mm_per_s:
        return (avg_speed_mm_per_s / 1000) * duration_hours * 3600

    if avg_pace_s_per_m:
        return (1 / avg_pace_s_per_m) * duration_hours * 3600

    if steps:
        stride_m = (stride_by_type or {}).get(exercise_type) or DEFAULT_STRIDE_M_BY_TYPE.get(exercise_type, DEFAULT_STRIDE_M)
        return steps * stride_m

    calibrated_speed = (speed_by_type_m_per_s or {}).get(exercise_type)
    if calibrated_speed:
        return calibrated_speed * duration_hours * 3600

    return None


def calibrate_from_workout(exercise_type, duration_hours, distance_mm=None, steps=None,
                            avg_speed_mm_per_s=None, avg_pace_s_per_m=None):
    """What one workout teaches us about this user's real stride/speed,
    to reuse on a future workout missing that data."""
    if exercise_type not in FOOT_EXERCISE_TYPES:
        return WorkoutCalibration(stride_m=None, speed_m_per_s=None)

    distance_m = distance_mm / 1000 if distance_mm else None
    stride_m = distance_m / steps if (distance_m and steps) else None

    if avg_speed_mm_per_s:
        speed_m_per_s = avg_speed_mm_per_s / 1000
    elif avg_pace_s_per_m:
        speed_m_per_s = 1 / avg_pace_s_per_m
    elif distance_m and duration_hours:
        speed_m_per_s = distance_m / (duration_hours * 3600)
    else:
        speed_m_per_s = None

    return WorkoutCalibration(stride_m=stride_m, speed_m_per_s=speed_m_per_s)

def get_user_current_position(route, distance_walked_m):
    """Coordinates only, for placing the map marker - thin wrapper around
    locate_on_route for callers that don't need the rest of Progress."""
    return locate_on_route(route, distance_walked_m).coords


def interval_duration_hours(start_time, end_time):
    return (_parse_iso(end_time) - _parse_iso(start_time)).total_seconds() / 3600


def interval_within_any(start_time, end_time, covering_intervals):
    """Is [start_time, end_time) fully inside one of the given intervals -
    the double-count guard between a steps event and a workout."""
    start, end = _parse_iso(start_time), _parse_iso(end_time)
    for covering_start, covering_end in covering_intervals:
        if _parse_iso(covering_start) <= start and end <= _parse_iso(covering_end):
            return True
    return False


def _parse_iso(timestamp):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def milestones_just_crossed(percent_complete, already_notified):
    crossed = set()
    if percent_complete >= HALFWAY_PERCENT and "halfway" not in already_notified:
        crossed.add("halfway")
    if percent_complete >= FINISHED_PERCENT and "finished" not in already_notified:
        crossed.add("finished")
    return crossed
