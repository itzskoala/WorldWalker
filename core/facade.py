#facade.py
# Single entry point for the web app: intake (from/to, step counts) in,
# map-ready state out. Hides travel_logic's geocode -> route -> progress
# pipeline from callers (app.py, services/google_health/webhook.py).

from datetime import datetime, timezone
from dotenv import load_dotenv
from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import NominatimGeocoder
from travel_logic.route_service import OSRMWalkingRouteService
from travel_logic.progress_calculator import (
    resolve_stride_m,
    steps_to_meters,
    locate_on_route,
    average_daily_meters,
    estimate_days_remaining,
    workout_distance_m,
    interval_duration_hours,
    interval_within_any,
    milestones_just_crossed,
)
from travel_logic.checkpoints import generate_checkpoints
from travel_logic.description_generator import AIDescriptionGenerator
from data.total_distance_db import TotalDistanceDB
from data.landmarks_db import LandmarksDB
from core.observer_decorator.event_manager import EventManager
from core.observer_decorator.console_alert_listener import ConsoleAlertListener
from services.google_health.client import get_profile
from services.fitbitMetrics.fitbit_user_data import UserMetric

load_dotenv()

METERS_PER_MILE = 1609.344
DEFAULT_USER_ID = "me"


class TravelFacade:
    def __init__(self):
        self._geocoder = NominatimGeocoder()
        self._router = OSRMWalkingRouteService()
        self._describer = AIDescriptionGenerator()
        self._db = TotalDistanceDB()
        self._landmarks_db = LandmarksDB()
        self._sessions = {}  # user_id -> journey state. In-memory for MVP; swap for data/models.py once that exists.

        # Publisher (Observer pattern - https://refactoring.guru/design-patterns/observer):
        # TravelFacade plays the "Editor" role from that page's example -
        # it owns the EventManager and calls notify() when something
        # worth telling subscribers about happens. Three event types
        # today; only the terminal listener is wired up for now.
        self.events = EventManager()
        console_listener = ConsoleAlertListener()
        for event_type in ("landmark", "halfway", "finished"):
            self.events.subscribe(event_type, console_listener)

    def start_journey(self, user_id: str, from_place: str, to_place: str, gender: str = None, stride_length_m: float = None, round_trip: bool = False) -> dict:
        start = self._geocoder.geocode(from_place)
        end = self._geocoder.geocode(to_place)
        route = self._router.get_walking_route(start, end)

        stride_by_type = _real_stride_by_type()
        if stride_length_m is None:
            stride_length_m = stride_by_type.get("WALKING")

        self._sessions[user_id] = {
            "route": route,
            "meters_walked": 0.0,
            "gender": gender,  # asked at intake, used only as a stride fallback
            "stride_length_m": stride_length_m,  # real per-user value, from Google Health if we have one
            "started_at": datetime.now(timezone.utc),
            "stride_by_type": stride_by_type,  # exercise_type -> real per-user meters/step, from Google Health
            "speed_by_type_m_per_s": {},  # exercise_type -> not populated today (no calibration); kept for workout_distance_m's device-speed fallback
            "workout_intervals": [],  # (start_time, end_time) already credited by record_workout
            "destination": to_place,  # for the "finished" event's message
            "milestones_notified": set(),  # {"halfway", "finished"} once each has fired - never re-fires
            # Captured from the UI's trip-type toggle; not acted on yet -
            # the route below is still a single one-way leg.
            "round_trip": round_trip,
        }
        # Landmarks are found once here and persisted - LandmarksDB is the
        # single source of truth for them from here on, not the session dict.
        checkpoints = generate_checkpoints(route, self._geocoder, self._describer)
        self._landmarks_db.save_landmarks(user_id, [_checkpoint_to_landmark(c, route) for c in checkpoints])
        return self.get_map_state(user_id)

    def record_steps(self, user_id: str, steps: int, interval=None) -> dict:
        """interval: the steps event's TimeInterval, if known. Used to check
        whether a foot-based workout (record_workout) already credited this
        exact window - if so, this whole event is skipped, since
        record_workout already logged that step count via its own DB row."""
        if user_id not in self._sessions:
            raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

        session = self._sessions[user_id]
        if interval is not None and interval_within_any(
            interval.start_time, interval.end_time, session["workout_intervals"]
        ):
            state = self.get_map_state(user_id)
            state["newly_passed_landmarks"] = []
            return state

        stride_m = resolve_stride_m(google_health_stride_m=session["stride_length_m"], gender=session["gender"])
        session["meters_walked"] += steps_to_meters(steps, stride_m)

        progress = self._locate(session)
        self._record_sync(user_id, steps, progress)

        newly_passed = self._notify_progress(user_id, session, progress)

        state = self.get_map_state(user_id)
        state["newly_passed_landmarks"] = newly_passed
        return state

    def record_workout(self, user_id: str, exercise) -> dict:
        """exercise: the ExerciseData Pydantic object from the webhook.
        Foot-based activity types move the user along the route, using the
        workout's own measured distance or pace when available. Non-foot
        types (biking, swimming, ...) never add distance."""
        if user_id not in self._sessions:
            raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

        session = self._sessions[user_id]
        summary = exercise.metrics_summary
        duration_hours = interval_duration_hours(exercise.interval.start_time, exercise.interval.end_time)

        distance_m = workout_distance_m(
            exercise_type=exercise.exercise_type,
            duration_hours=duration_hours,
            distance_mm=summary.distance_millimeters,
            steps=summary.steps,
            avg_speed_mm_per_s=summary.average_speed_mm_per_s,
            avg_pace_s_per_m=summary.average_pace_s_per_m,
            stride_by_type=session["stride_by_type"],
            speed_by_type_m_per_s=session["speed_by_type_m_per_s"],
        )

        # No calibration-from-a-past-workout: pace is dictated by the
        # user's real Google Health stride (seeded once in start_journey)
        # if we have one, else workout_distance_m's own standard fallback.

        if distance_m:
            session["meters_walked"] += distance_m
            # Only mark this window covered if we actually credited real
            # distance for it - otherwise a later "steps" event for the
            # same minutes is the only source of distance we have.
            session["workout_intervals"].append((exercise.interval.start_time, exercise.interval.end_time))

        progress = self._locate(session)
        self._record_sync(user_id, summary.steps or 0, progress)

        newly_passed = self._notify_progress(user_id, session, progress)

        state = self.get_map_state(user_id)
        state["newly_passed_landmarks"] = newly_passed
        return state

    def _record_sync(self, user_id: str, steps: int, progress) -> None:
        self._db.record_sync(
            user_id=user_id,
            steps=steps,
            distance_walked_miles=progress.distance_walked_m / METERS_PER_MILE,
            distance_remaining_miles=progress.distance_remaining_m / METERS_PER_MILE,
            percent_complete=progress.percent_complete,
            synced_at=datetime.now(timezone.utc),
        )

    def _notify_progress(self, user_id: str, session: dict, progress) -> list:
        """Landmark-passed and halfway/finished checks, in one place so
        record_steps and record_workout don't each repeat this. Fires
        self.events.notify() per event type; returns the newly-passed
        landmarks (callers still need that list for their own return dict)."""
        miles_walked = progress.distance_walked_m / METERS_PER_MILE
        newly_passed = self._landmarks_db.landmarks_just_passed(user_id, miles_walked)
        for landmark in newly_passed:
            self.events.notify("landmark", f"🏁 Landmark reached: {landmark['name']} ({landmark['percent']}% of the way there!)")

        for milestone in milestones_just_crossed(progress.percent_complete, session["milestones_notified"]):
            session["milestones_notified"].add(milestone)
            if milestone == "halfway":
                self.events.notify("halfway", "🎉 Halfway to your goal - 50%!")
            elif milestone == "finished":
                total_steps = self._db.total_steps(user_id)
                self.events.notify("finished", f"🏆 You reached {session['destination']} in {total_steps} steps! Congrats!")

        return newly_passed

    def get_map_state(self, user_id: str) -> dict:
        session = self._sessions[user_id]
        progress = self._locate(session)

        days_elapsed = (datetime.now(timezone.utc) - session["started_at"]).total_seconds() / 86400
        daily_meters = average_daily_meters(progress.distance_walked_m, days_elapsed)

        landmarks = self._landmarks_db.all_landmarks(user_id)
        miles_walked = progress.distance_walked_m / METERS_PER_MILE
        for landmark in landmarks:
            landmark["miles_until"] = max(0.0, landmark["miles_from_start"] - miles_walked)

        days_remaining = estimate_days_remaining(progress.distance_remaining_m, daily_meters)

        return {
            "current_position": progress.coords,
            "miles_walked": miles_walked,
            "miles_remaining": progress.distance_remaining_m / METERS_PER_MILE,
            "percent_complete": progress.percent_complete,
            "estimated_days_remaining": days_remaining,
            "total_steps": self._db.total_steps(user_id),
            "today_steps": self._db.today_steps(user_id),
            "landmarks": landmarks,
        }

    def search_places(self, query: str, limit: int = 5) -> list:
        """Autocomplete candidates for app.py's Where From/Where To
        dropdowns. Thin passthrough to the geocoder - kept here (not
        called directly by app.py) so the UI only ever talks to the
        facade, matching this module's "single entry point" role."""
        return self._geocoder.search_places(query, limit)

    def current_location_place(self, lat: float, lng: float) -> str:
        """Browser-geolocation coordinates -> a place name app.py can drop
        straight into the Where From field."""
        return self._geocoder.reverse_geocode(Coordinates(lat=lat, lng=lng))

    @staticmethod
    def _locate(session: dict):
        return locate_on_route(session["route"], session["meters_walked"])


def _real_stride_by_type() -> dict:
    """Real per-user stride from Google Health's profile (Profile >
    Google Health settings > Activity > Stride Length), confirmed live -
    empty if there's no connection yet or the pull fails, not a crash."""
    try:
        profile = UserMetric(get_profile()).metric_obj()
    except Exception:
        return {}

    stride_by_type = {}
    if profile.walking_stride_length_mm:
        stride_by_type["WALKING"] = profile.walking_stride_length_mm / 1000
    if profile.running_stride_length_mm:
        stride_by_type["RUNNING"] = profile.running_stride_length_mm / 1000
    return stride_by_type


def _checkpoint_to_landmark(checkpoint, route) -> dict:
    percent = (checkpoint.distance_from_start_m / route.total_distance * 100) if route.total_distance else 0.0
    return {
        "name": checkpoint.name,
        "coords": {"lat": checkpoint.coordinates.lat, "lng": checkpoint.coordinates.lng},
        "miles_from_start": checkpoint.distance_from_start_m / METERS_PER_MILE,
        "percent": percent,
    }


# One shared instance for the whole process - the webhook
# (services/google_health/webhook.py) and app.py's routes both need the
# same in-memory session state/db handle.
travel_facade = TravelFacade()
