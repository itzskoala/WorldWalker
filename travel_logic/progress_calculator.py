#progress_calculator.py
# Pure math, no network/DB calls: turns real-world activity (steps,
# workouts) into distance along a route, in meters. Unit conversion for
# display (miles/km) belongs to the presentation layer, not here.

import bisect
import random
from dataclasses import dataclass
from datetime import datetime
from travel_logic.coordinates import Coordinates

# Population-average per-step distance, CDC anthropometric reference
# values: 0.76m for men, 0.66m for women. DEFAULT_STRIDE_M (gender
# unknown) is the midpoint of the two - the honest "no information at
# all" fallback, not a separately-sourced number.
MALE_STRIDE_M = random.uniform(0.76,0.78)
FEMALE_STRIDE_M = 0.66
DEFAULT_STRIDE_M = (MALE_STRIDE_M + FEMALE_STRIDE_M) / 2

# Running covers meaningfully more ground per step than walking (a real
# flight phase lengthens each step) - used only when no real per-user
# calibrated stride exists yet for that activity type (see
# calibrate_from_workout). Every other foot-based type (walking
# variants, hiking, nordic walking) falls through to DEFAULT_STRIDE_M -
# there's no verified separate figure for those worth a special case.
RUNNING_STRIDE_M = 1.15
DEFAULT_STRIDE_M_BY_TYPE = {
    "RUNNING": RUNNING_STRIDE_M,
    "TRAIL_RUN": RUNNING_STRIDE_M,
    "INCLINE_RUN": RUNNING_STRIDE_M,
}

# The on-foot subset of Google Health's exercise type enum - anything
# else (biking, swimming, ...) never counts toward route progress.
FOOT_EXERCISE_TYPES = frozenset({
    "WALKING", "POWER_WALKING", "INCLINE_WALK", "TREADMILL_WALK",
    "STROLLER_WALK", "RUNNING", "TRAIL_RUN", "INCLINE_RUN", "HIKING",
    "NORDIC_WALKING",
})

HALFWAY_PERCENT = 50.0
FINISHED_PERCENT = 100.0


def resolve_stride_m(google_health_stride_m: float = None, age: int = None, height_cm: float = None,
                      weight_kg: float = None, gender: str = None):
    """Priority: a real, device-calibrated value from Google Health >
    calculated from age/height/weight/gender > population average by
    gender > unisex population average. Never a global - always resolved
    fresh from whatever this particular user's data actually is."""
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
    """User-supplied regression: full stride length (both feet) in cm,
    given age, height, weight, and sex (male=0, female=1). Halved here -
    the rest of this app (steps x stride length = distance) works in
    single-step distance, not two-foot stride length, so a raw un-halved
    result would double every distance calculation. Returns None (not a
    guess) unless all four inputs are real and the result is physically
    sensible."""
    if age is None or height_cm is None or weight_kg is None or gender not in ("male", "female"):
        return None

    sex = 1 if gender == "female" else 0
    full_stride_cm = 34.70 - (0.30 * age) + (0.76 * height_cm) - (0.15 * weight_kg) - (3.33 * sex)
    step_m = (full_stride_cm / 2) / 100
    return step_m if step_m > 0 else None


def steps_to_meters(steps: int, stride_m: float):
    return steps * stride_m


def meters_remaining(total_distance_m: float, distance_covered_m: float):
    return max(0.0, total_distance_m - distance_covered_m)


def average_daily_meters(distance_covered_m: float, days_elapsed: float):
    """Empirical pace only - None ("unknown") until real progress and
    real elapsed time both exist, never a guessed number."""
    if distance_covered_m <= 0 or days_elapsed <= 0:
        return None
    return distance_covered_m / days_elapsed


def estimate_days_remaining(distance_remaining_m: float, daily_meters: float):
    if not daily_meters or daily_meters <= 0:
        return None
    return distance_remaining_m / daily_meters


@dataclass(frozen=True)
class Progress:
    coords: Coordinates
    distance_walked_m: float
    distance_remaining_m: float
    percent_complete: float


def locate_on_route(route, distance_walked_m: float):
    """Exact position at distance_walked_m along the route's real
    geometry - a polyline is straight segments between its vertices, so
    linear interpolation between the two bracketing points *is* the
    exact location at that distance, not an approximation of one."""
    if not route.points:
        raise ValueError("Route has no points")

    total = route.total_distance
    distance_walked_m = max(0.0, min(distance_walked_m, total))

    distances = [p.distance_from_start for p in route.points]
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


def workout_distance_m(exercise_type: str, duration_hours: float, distance_mm: float = None, steps: int = None,
                        avg_speed_mm_per_s: float = None, avg_pace_s_per_m: float = None,
                        stride_by_type: dict = None, speed_by_type_m_per_s: dict = None):
    """A completed workout's distance, in priority order: recorded
    distance > device-reported speed/pace x duration > steps x
    calibrated-or-default per-type stride > calibrated per-type speed x
    duration. None (not a guess) if the type isn't foot-based or nothing
    usable was given."""
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


@dataclass(frozen=True)
class WorkoutCalibration:
    stride_m: float
    speed_m_per_s: float


def calibrate_from_workout(exercise_type: str, duration_hours: float, distance_mm: float = None, steps: int = None,
                            avg_speed_mm_per_s: float = None, avg_pace_s_per_m: float = None):
    """What one workout teaches us about this user's real stride/speed
    for this activity type, to reuse on a future workout of the same
    type that's missing data this one has."""
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


def interval_duration_hours(start_time: str, end_time: str):
    return (_parse_iso(end_time) - _parse_iso(start_time)).total_seconds() / 3600


def interval_within_any(start_time: str, end_time: str, covering_intervals: list):
    """Is [start_time, end_time) fully inside one of the given
    (start, end) intervals already credited elsewhere - the double-count
    guard between a "steps" event and a workout covering the same real
    walk."""
    start, end = _parse_iso(start_time), _parse_iso(end_time)
    for covering_start, covering_end in covering_intervals:
        if _parse_iso(covering_start) <= start and end <= _parse_iso(covering_end):
            return True
    return False


def _parse_iso(timestamp: str):
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def milestones_just_crossed(percent_complete: float, already_notified: set):
    crossed = set()
    if percent_complete >= HALFWAY_PERCENT and "halfway" not in already_notified:
        crossed.add("halfway")
    if percent_complete >= FINISHED_PERCENT and "finished" not in already_notified:
        crossed.add("finished")
    return crossed
