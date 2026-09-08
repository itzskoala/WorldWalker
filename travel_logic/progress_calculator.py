#progress_calculator.py
# Steps -> miles -> where that lands on the route.

import bisect
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint

METERS_PER_MILE = 1609.344
MM_PER_MILE = METERS_PER_MILE * 1000  # 1_609_344.0
SECONDS_PER_HOUR = 3600.0

# Stride = distance per step. Priority: a real per-user value (e.g. pulled
# from Fitbit/Google Health) > gender average (from intake) > unisex default.
MALE_STRIDE_M = 0.78
FEMALE_STRIDE_M = 0.70
DEFAULT_STRIDE_M = 0.762  # ~2.5 ft, used when neither a user stride nor gender is on file


def resolve_stride_m(user_stride_m: Optional[float] = None, gender: Optional[str] = None) -> float:
    if user_stride_m:
        return user_stride_m
    if gender == "male":
        return MALE_STRIDE_M
    if gender == "female":
        return FEMALE_STRIDE_M
    return DEFAULT_STRIDE_M


def steps_to_miles(steps: int, user_stride_m: Optional[float] = None, gender: Optional[str] = None) -> float:
    return (steps * resolve_stride_m(user_stride_m, gender)) / METERS_PER_MILE


# --- Workouts (exercise events) ---
#
# Foot-based exercise types only - a bike ride or swim doesn't move you
# along a walking route. From developers.google.com/health's exercise type
# enum (200+ values total); this is the on-foot subset as of this pass -
# revisit if a new foot-based type shows up there.
FOOT_EXERCISE_TYPES = {
    "WALKING", "POWER_WALKING", "INCLINE_WALK", "TREADMILL_WALK", "STROLLER_WALK",
    "RUNNING", "TRAIL_RUN", "INCLINE_RUN", "HIKING", "NORDIC_WALKING",
}

# Generic per-type pace/stride defaults, used only until a user has a real
# calibrated value for that activity - same role as MALE_STRIDE_M/
# FEMALE_STRIDE_M above, just bucketed by activity instead of gender.
# Running covers far more ground per step than walking; one flat constant
# across both would badly under/over-count distance. Types not listed here
# (the WALKING variants) fall through to DEFAULT_STRIDE_M.
DEFAULT_STRIDE_M_BY_TYPE = {
    "RUNNING": 1.10,
    "TRAIL_RUN": 1.05,
    "INCLINE_RUN": 1.00,
    "HIKING": 0.75,
    "NORDIC_WALKING": 0.80,
}


@dataclass(frozen=True)
class WorkoutCalibration:
    """What one workout teaches us about this user's real stride/pace for
    its activity type, to use on a FUTURE workout of the same type that's
    missing data this one has. Only ever populated from data this workout
    actually reported - never invented."""
    stride_m: Optional[float] = None
    pace_mph: Optional[float] = None


def _speed_mph_from_mm_per_s(speed_mm_per_s: float) -> float:
    return (speed_mm_per_s / MM_PER_MILE) * SECONDS_PER_HOUR


def _speed_mph_from_pace_s_per_m(pace_s_per_m: float) -> Optional[float]:
    if not pace_s_per_m or pace_s_per_m <= 0:
        return None
    meters_per_second = 1.0 / pace_s_per_m
    return (meters_per_second / METERS_PER_MILE) * SECONDS_PER_HOUR


def _reported_speed_mph(avg_speed_mm_per_s: Optional[float], avg_pace_s_per_m: Optional[float]) -> Optional[float]:
    """The device's own average speed/pace for this workout, converted to
    mph - prefer the direct speed field, fall back to pace (its inverse)."""
    if avg_speed_mm_per_s:
        return _speed_mph_from_mm_per_s(avg_speed_mm_per_s)
    if avg_pace_s_per_m:
        return _speed_mph_from_pace_s_per_m(avg_pace_s_per_m)
    return None


def _parse_iso(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def interval_duration_hours(start_time: str, end_time: str) -> float:
    delta = _parse_iso(end_time) - _parse_iso(start_time)
    return max(delta.total_seconds(), 0.0) / SECONDS_PER_HOUR


def interval_within_any(start_time: str, end_time: str, covering_intervals: list) -> bool:
    """True if [start_time, end_time] falls entirely inside one of the
    (start, end) ISO-timestamp pairs in covering_intervals. Used to skip a
    "steps" sync that a foot-based workout already accounted for, so the
    same real walk doesn't add distance twice."""
    start, end = _parse_iso(start_time), _parse_iso(end_time)
    for cov_start, cov_end in covering_intervals:
        if _parse_iso(cov_start) <= start and end <= _parse_iso(cov_end):
            return True
    return False


def workout_distance_miles(
    exercise_type: str,
    duration_hours: float,
    distance_mm: Optional[float] = None,
    steps: Optional[int] = None,
    avg_speed_mm_per_s: Optional[float] = None,
    avg_pace_s_per_m: Optional[float] = None,
    stride_by_type: Optional[dict] = None,
    pace_by_type_mph: Optional[dict] = None,
) -> Optional[float]:
    """Distance covered by one completed workout, in miles. None if this
    exercise_type doesn't count toward route progress (not foot-based), or
    if there isn't enough data to compute anything - never guesses beyond
    what's actually given.

    Priority, most direct first:
    1. distance_mm - a real measured distance, nothing to compute.
    2. average_speed/average_pace as reported by the device for THIS
       workout - real measured pace, distance = speed x time.
    3. steps - converted using this activity type's real calibrated stride
       if we have one (from a past workout of the same type), else a
       generic per-type default.
    4. Neither steps, distance, nor a reported pace - fall back to a real
       calibrated pace from a past workout of the same type, applied to
       this workout's duration. Otherwise: None, this workout contributes
       nothing (not a guess).
    """
    if exercise_type not in FOOT_EXERCISE_TYPES:
        return None

    if distance_mm:
        return distance_mm / MM_PER_MILE

    speed_mph = _reported_speed_mph(avg_speed_mm_per_s, avg_pace_s_per_m)
    if speed_mph and duration_hours > 0:
        return speed_mph * duration_hours

    if steps:
        stride_m = (stride_by_type or {}).get(exercise_type) or DEFAULT_STRIDE_M_BY_TYPE.get(exercise_type, DEFAULT_STRIDE_M)
        return (steps * stride_m) / METERS_PER_MILE

    calibrated_pace_mph = (pace_by_type_mph or {}).get(exercise_type)
    if calibrated_pace_mph and duration_hours > 0:
        return calibrated_pace_mph * duration_hours

    return None


def calibrate_from_workout(
    exercise_type: str,
    duration_hours: float,
    distance_mm: Optional[float] = None,
    steps: Optional[int] = None,
    avg_speed_mm_per_s: Optional[float] = None,
    avg_pace_s_per_m: Optional[float] = None,
) -> WorkoutCalibration:
    if exercise_type not in FOOT_EXERCISE_TYPES:
        return WorkoutCalibration()

    stride_m = (distance_mm / 1000.0) / steps if (distance_mm and steps) else None

    pace_mph = _reported_speed_mph(avg_speed_mm_per_s, avg_pace_s_per_m)
    if pace_mph is None and distance_mm and duration_hours > 0:
        pace_mph = (distance_mm / MM_PER_MILE) / duration_hours

    return WorkoutCalibration(stride_m=stride_m, pace_mph=pace_mph)


def average_daily_miles(total_miles_walked: float, days_elapsed: float) -> Optional[float]:
    """The user's own empirical pace (miles walked / days since journey
    start). None if they haven't actually walked yet - no progress means
    no pace to report, not a guessed one."""
    if total_miles_walked <= 0 or days_elapsed <= 0:
        return None
    return total_miles_walked / days_elapsed


def estimate_days_remaining(miles_remaining: float, daily_miles: Optional[float]) -> Optional[float]:
    """None (unknown) until a real pace exists."""
    if not daily_miles or daily_miles <= 0:
        return None
    return miles_remaining / daily_miles


@dataclass(frozen=True)
class Progress:
    position: RoutePoint
    miles_walked: float
    miles_remaining: float
    percent_complete: float


def locate_on_route(route: Route, miles_walked: float) -> Progress:
    """Total miles walked so far (cumulative) -> exact position on the route.

    route.points are OSRM polyline vertices - real points on the actual
    path, placed wherever its direction changes, so a straight line between
    two consecutive ones IS the real path there (that's why no vertex was
    needed in between). So we don't snap to the nearest existing vertex;
    we interpolate along the segment miles_walked actually falls on, which
    reconstructs the exact point on the path, not an estimate of it.
    """
    if not route.points:
        raise ValueError("Route has no points - cannot locate a position on it")

    miles_walked = max(0.0, min(miles_walked, route.total_miles))
    mileages = [p.miles_from_start for p in route.points]
    idx = bisect.bisect_left(mileages, miles_walked)

    if idx == 0:
        position = route.points[0]
    elif idx >= len(route.points):
        position = route.points[-1]
    else:
        before, after = route.points[idx - 1], route.points[idx]
        span = after.miles_from_start - before.miles_from_start
        frac = (miles_walked - before.miles_from_start) / span if span else 0.0
        position = RoutePoint(
            coords=Coordinates(
                lat=before.coords.lat + frac * (after.coords.lat - before.coords.lat),
                lng=before.coords.lng + frac * (after.coords.lng - before.coords.lng),
            ),
            miles_from_start=miles_walked,
        )

    remaining = route.total_miles - miles_walked
    percent = (miles_walked / route.total_miles * 100) if route.total_miles else 100.0
    return Progress(position=position, miles_walked=miles_walked, miles_remaining=remaining, percent_complete=percent)


HALFWAY_PERCENT = 50.0
FINISHED_PERCENT = 100.0


def milestones_just_crossed(percent_complete: float, already_notified: set) -> set:
    """Which of {"halfway", "finished"} just became true and haven't fired
    yet, given the current percent_complete. >= rather than == so a sync
    that jumps straight past 50% (e.g. a big workout) still fires it.
    Pure - the caller (TravelFacade) is responsible for updating
    already_notified once it's actually notified for each one."""
    crossed = set()
    if percent_complete >= HALFWAY_PERCENT and "halfway" not in already_notified:
        crossed.add("halfway")
    if percent_complete >= FINISHED_PERCENT and "finished" not in already_notified:
        crossed.add("finished")
    return crossed
