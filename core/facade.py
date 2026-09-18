#facade.py
# Single entry point for the web app: intake (from/to, step counts) in,
# map-ready state out. Hides travel_logic's geocode -> route -> progress
# pipeline from callers (app.py, fitbit_service.py).

from datetime import datetime, timezone
from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import NominatimGeocoder
from travel_logic.route_service import OSRMWalkingRouteService
from travel_logic.progress_calculator import (
    steps_to_miles,
    locate_on_route,
    average_daily_miles,
    estimate_days_remaining,
    workout_distance_miles,
    calibrate_from_workout,
    interval_duration_hours,
    interval_within_any,
    milestones_just_crossed,
)
from travel_logic.checkpoints import pick_checkpoints
from data.total_distance_db import TotalDistanceDB
from data.landmarks_db import LandmarksDB
from core.observer_decorator.event_manager import EventManager
from core.observer_decorator.console_alert_listener import ConsoleAlertListener


class TravelFacade:
    def __init__(self):
        self._geocoder = NominatimGeocoder()
        self._router = OSRMWalkingRouteService()
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
        self._sessions[user_id] = {
            "route": route,
            "miles_walked": 0.0,
            "gender": gender,  # asked at intake, used only as a stride/pace fallback
            "stride_length_m": stride_length_m,  # real per-user value, e.g. from Fitbit, if we have one
            "started_at": datetime.now(timezone.utc),
            "stride_by_type": {},  # exercise_type -> real calibrated meters/step, from past workouts
            "pace_by_type_mph": {},  # exercise_type -> real calibrated mph, from past workouts
            "workout_intervals": [],  # (start_time, end_time) already credited by record_workout
            "destination": to_place,  # for the "finished" event's message
            "milestones_notified": set(),  # {"halfway", "finished"} once each has fired - never re-fires
            # Captured from the UI's trip-type toggle; not acted on yet -
            # the route below is still a single one-way leg. A real
            # "walk back" pipeline (doubling the route once the
            # destination is reached) is a flagged fast-follow, not built
            # this pass.
            "round_trip": round_trip,
        }
        # Landmarks are found once here and persisted - LandmarksDB is the
        # single source of truth for them from here on, not the session dict.
        self._landmarks_db.save_landmarks(user_id, pick_checkpoints(route, self._geocoder))
        return self.get_map_state(user_id)

    def record_steps(self, user_id: str, steps: int, interval=None) -> dict:
        """interval: the steps event's TimeInterval, if known. Used to check
        whether a foot-based workout (record_workout) already credited this
        exact window - if so, this whole event is Google reporting the same
        real walk twice (once via the general steps stream, once via the
        exercise stream), so it's skipped entirely: not just its distance,
        but its step count too, since record_workout already logged that
        step count via its own DB row. Windows a workout hasn't covered
        still always add distance and log steps normally."""
        if user_id not in self._sessions:
            raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

        session = self._sessions[user_id]
        if interval is not None and interval_within_any(
            interval.start_time, interval.end_time, session["workout_intervals"]
        ):
            state = self.get_map_state(user_id)
            state["newly_passed_landmarks"] = []
            return state

        session["miles_walked"] += steps_to_miles(steps, session["stride_length_m"], session["gender"])

        progress = self._locate(session)
        self._db.record_sync(
            user_id=user_id,
            steps=steps,
            distance_walked_miles=progress.miles_walked,
            distance_remaining_miles=progress.miles_remaining,
            percent_complete=progress.percent_complete,
            synced_at=datetime.now(timezone.utc),
        )

        newly_passed = self._notify_progress(user_id, session, progress)

        state = self.get_map_state(user_id)
        state["newly_passed_landmarks"] = newly_passed
        return state

    def record_workout(self, user_id: str, exercise) -> dict:
        """exercise: the ExerciseData Pydantic object from the webhook.
        Foot-based activity types (walking/running/hiking/...) move the
        user along the route, using the workout's own measured distance or
        pace when available - more accurate than the generic step-stride
        guess, and aware that running covers more ground than walking.
        Non-foot types (biking, swimming, ...) never add distance."""
        if user_id not in self._sessions:
            raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

        session = self._sessions[user_id]
        summary = exercise.metrics_summary
        duration_hours = interval_duration_hours(exercise.interval.start_time, exercise.interval.end_time)

        distance_miles = workout_distance_miles(
            exercise_type=exercise.exercise_type,
            duration_hours=duration_hours,
            distance_mm=summary.distance_millimeters,
            steps=summary.steps,
            avg_speed_mm_per_s=summary.average_speed_mm_per_s,
            avg_pace_s_per_m=summary.average_pace_s_per_m,
            stride_by_type=session["stride_by_type"],
            pace_by_type_mph=session["pace_by_type_mph"],
        )

        # Whatever this workout teaches us about the user's real
        # stride/pace for this activity type - saved for a future workout
        # of the same type that's missing data this one has.
        calibration = calibrate_from_workout(
            exercise_type=exercise.exercise_type,
            duration_hours=duration_hours,
            distance_mm=summary.distance_millimeters,
            steps=summary.steps,
            avg_speed_mm_per_s=summary.average_speed_mm_per_s,
            avg_pace_s_per_m=summary.average_pace_s_per_m,
        )
        if calibration.stride_m:
            session["stride_by_type"][exercise.exercise_type] = calibration.stride_m
        if calibration.pace_mph:
            session["pace_by_type_mph"][exercise.exercise_type] = calibration.pace_mph

        if distance_miles:
            session["miles_walked"] += distance_miles
            # Only mark this window covered if we actually credited real
            # distance for it - otherwise a later "steps" event for the
            # same minutes is the only source of distance we have, and
            # suppressing it would lose real activity instead of just
            # avoiding a double-count.
            session["workout_intervals"].append((exercise.interval.start_time, exercise.interval.end_time))

        progress = self._locate(session)
        self._db.record_sync(
            user_id=user_id,
            steps=summary.steps or 0,
            distance_walked_miles=progress.miles_walked,
            distance_remaining_miles=progress.miles_remaining,
            percent_complete=progress.percent_complete,
            synced_at=datetime.now(timezone.utc),
        )

        newly_passed = self._notify_progress(user_id, session, progress)

        state = self.get_map_state(user_id)
        state["newly_passed_landmarks"] = newly_passed
        return state

    def _notify_progress(self, user_id: str, session: dict, progress) -> list:
        """Landmark-passed and halfway/finished checks, in one place so
        record_steps and record_workout don't each repeat this. Fires
        self.events.notify() per event type; returns the newly-passed
        landmarks (callers still need that list for their own return dict)."""
        newly_passed = self._landmarks_db.landmarks_just_passed(user_id, session["miles_walked"])
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
        daily_miles = average_daily_miles(session["miles_walked"], days_elapsed)

        landmarks = self._landmarks_db.all_landmarks(user_id)
        for landmark in landmarks:
            landmark["miles_until"] = max(0.0, landmark["miles_from_start"] - session["miles_walked"])

        return {
            "current_position": progress.position.coords,
            "miles_walked": progress.miles_walked,
            "miles_remaining": progress.miles_remaining,
            "percent_complete": progress.percent_complete,
            "estimated_days_remaining": estimate_days_remaining(progress.miles_remaining, daily_miles),
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
        return locate_on_route(session["route"], session["miles_walked"])

# One shared instance for the whole process - fitbit_service.py's webhook
# and app.py's routes both need the same in-memory session state/db handle.
travel_facade = TravelFacade()
