#facade.py
# Single entry point for the web app: intake (from/to, step counts) in,
# map-ready state out. Hides travel_logic's geocode -> route -> progress
# pipeline from callers (app.py, services/google_health/webhook.py).
#
# A journey's state lives in Postgres now (database/trips.py's
# active_trips/trip_checkpoints tables), not in a process-local dict - see
# database/trips.py's module docstring for why. Every public method here
# that touches a trip opens its own short-lived SQLAlchemy session
# (database/session.py's SessionLocal), does its reads/writes through
# database/trips.py, and closes it - this class still owns no SQL itself.

import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import trips
from database.models import ActiveTrip, TripCheckpoint
from database.session import SessionLocal
from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import NominatimGeocoder
from travel_logic.route_service import OSRMWalkingRouteService, Route, build_route
from travel_logic.progress_calculator import (
    Progress,
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
from core.observer_decorator.event_manager import EventManager
from core.observer_decorator.console_alert_listener import ConsoleAlertListener
from services.google_health.client import get_profile
from services.fitbitMetrics.fitbit_user_data import UserMetric

load_dotenv()

METERS_PER_MILE = 1609.344


class TravelFacade:
    def __init__(self):
        self._geocoder = NominatimGeocoder()
        self._router = OSRMWalkingRouteService()
        self._describer = AIDescriptionGenerator()
        self._db = TotalDistanceDB()

        # Publisher (Observer pattern - https://refactoring.guru/design-patterns/observer):
        # TravelFacade plays the "Editor" role from that page's example -
        # it owns the EventManager and calls notify() when something
        # worth telling subscribers about happens. Three event types
        # today; only the terminal listener is wired up for now.
        self.events = EventManager()
        console_listener = ConsoleAlertListener()
        for event_type in ("landmark", "halfway", "finished"):
            self.events.subscribe(event_type, console_listener)

    def start_journey(
        self,
        user_id: uuid.UUID,
        from_place: str,
        to_place: str,
        gender: str | None = None,
        stride_length_m: float | None = None,
        round_trip: bool = False,
    ) -> dict:
        """Builds the route and checkpoints (network calls - geocoding,
        OSRM, Nominatim), then persists the whole trip in one go. The
        network work happens before any database session is opened, so a
        slow external call never holds a DB connection idle."""
        start = self._geocoder.geocode(from_place)
        end = self._geocoder.geocode(to_place)
        route = self._router.get_walking_route(start, end)

        stride_by_type = _real_stride_by_type()
        if stride_length_m is None:
            stride_length_m = stride_by_type.get("WALKING")

        checkpoints = generate_checkpoints(route, self._geocoder, self._describer)

        with SessionLocal() as session:
            trip = trips.create_trip(
                session=session,
                user_id=user_id,
                from_place=from_place,
                to_place=to_place,
                route=route,
                checkpoints=checkpoints,
                gender=gender,
                stride_length_m=stride_length_m,
                stride_by_type=stride_by_type,
                round_trip=round_trip,
            )
            return self._build_map_state(trip)

    def record_steps(self, user_id: uuid.UUID, steps: int, interval=None) -> list[dict]:
        """Real steps happen once but can count toward several trips at
        once - every trip the user currently has status="active" (not
        paused, not finished) gets credited the same step count, each
        logged as its own sync row (data/total_distance_db.py is keyed by
        trip_id) so one trip's steps never bleed into another's "today's
        steps"/"total steps". Returns one map-state dict per trip, newest-
        started first.

        interval: the steps event's TimeInterval, if known. Used per-trip to
        check whether a foot-based workout (record_workout) already
        credited this exact window for that trip - if so, that trip's event
        is skipped, since record_workout already logged that step count via
        its own DB row."""
        with SessionLocal() as session:
            active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
            if not active_trips:
                raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

            states = []
            for trip in active_trips:
                if interval is not None and interval_within_any(
                    interval.start_time, interval.end_time, trip.workout_intervals
                ):
                    # This trip's own workout_intervals already cover this
                    # window (record_workout beat us to it) - skip it
                    # exactly as the single-trip version did, without
                    # touching progress, sync history, or notify_progress
                    # for it.
                    state = self._build_map_state(trip)
                    state["newly_hit_checkpoints"] = []
                    states.append(state)
                    continue

                stride_m = resolve_stride_m(google_health_stride_m=trip.stride_length_m, gender=trip.gender)
                meters_delta = steps_to_meters(steps, stride_m)
                trips.add_progress(session, trip, meters_delta)

                # Before _notify_progress: a "finished" milestone reads this
                # trip's total steps back out of the same log.
                self._record_sync(user_id, steps, trip)

                newly_hit_checkpoints = self._notify_progress(session, trip)
                state = self._build_map_state(trip)
                state["newly_hit_checkpoints"] = [_checkpoint_state(c) for c in newly_hit_checkpoints]
                states.append(state)

            return states

    def record_workout(self, user_id: uuid.UUID, exercise) -> list[dict]:
        """exercise: the ExerciseData Pydantic object from the webhook.
        Foot-based activity types move the user along every currently
        status="active" trip, using the workout's own measured distance or
        pace when available (recomputed per trip, since each trip can have
        its own stride profile). Non-foot types (biking, swimming, ...)
        never add distance. Each trip logs its own sync row regardless (see
        record_steps's docstring on why this is trip-scoped, not just
        user-scoped). Returns one map-state dict per trip credited."""
        with SessionLocal() as session:
            active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
            if not active_trips:
                raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

            summary = exercise.metrics_summary
            duration_hours = interval_duration_hours(exercise.interval.start_time, exercise.interval.end_time)

            states = []
            for trip in active_trips:
                distance_m = workout_distance_m(
                    exercise_type=exercise.exercise_type,
                    duration_hours=duration_hours,
                    distance_mm=summary.distance_millimeters,
                    steps=summary.steps,
                    avg_speed_mm_per_s=summary.average_speed_mm_per_s,
                    avg_pace_s_per_m=summary.average_pace_s_per_m,
                    stride_by_type=trip.stride_by_type,
                    speed_by_type_m_per_s={},  # not populated today (no calibration); kept for workout_distance_m's device-speed fallback
                )

                # No calibration-from-a-past-workout: pace is dictated by the
                # user's real Google Health stride (seeded once in
                # start_journey) if we have one, else workout_distance_m's own
                # standard fallback.

                if distance_m:
                    workout_interval = (exercise.interval.start_time, exercise.interval.end_time)
                    # Only mark this window covered if we actually credited real
                    # distance for it - otherwise a later "steps" event for the
                    # same minutes is the only source of distance we have.
                    trips.add_progress(session, trip, distance_m, workout_interval=workout_interval)

                # Before _notify_progress: a "finished" milestone reads this
                # trip's total steps back out of the same log.
                self._record_sync(user_id, summary.steps or 0, trip)

                newly_hit_checkpoints = self._notify_progress(session, trip)
                state = self._build_map_state(trip)
                state["newly_hit_checkpoints"] = [_checkpoint_state(c) for c in newly_hit_checkpoints]
                states.append(state)

            return states

    def get_map_state(self, user_id: uuid.UUID, trip_id: uuid.UUID) -> dict:
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            return self._build_map_state(trip)

    def list_trips(self, user_id: uuid.UUID) -> list[dict]:
        """Every trip belonging to this user (in progress or finished),
        summarized for the trips list UI - no per-trip network calls, just
        what's already on the row plus a lightweight thumbnail polyline."""
        with SessionLocal() as session:
            return [_trip_summary(trip) for trip in trips.list_trips(session, user_id)]

    def pause_journey(self, user_id: uuid.UUID, trip_id: uuid.UUID) -> dict:
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            trips.pause_trip(session, trip)
            return self._build_map_state(trip)

    def resume_journey(self, user_id: uuid.UUID, trip_id: uuid.UUID) -> dict:
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            trips.resume_trip(session, trip)
            return self._build_map_state(trip)

    def delete_journey(self, user_id: uuid.UUID, trip_id: uuid.UUID) -> None:
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            trips.delete_trip(session, trip)

    def delete_journeys(self, user_id: uuid.UUID, trip_ids: list[uuid.UUID]) -> int:
        """Deletes whichever of trip_ids actually belong to this user and
        ignores the rest (already gone, or someone else's id) - returns how
        many rows were actually deleted."""
        with SessionLocal() as session:
            owned = [trips.get_trip(session, trip_id, user_id) for trip_id in trip_ids]
            owned = [trip for trip in owned if trip is not None]
            trips.delete_trips(session, owned)
            return len(owned)

    def _record_sync(self, user_id: uuid.UUID, steps: int, trip: ActiveTrip) -> None:
        _route, progress = _locate(trip)
        self._db.record_sync(
            user_id=str(user_id),
            trip_id=str(trip.id),
            steps=steps,
            distance_walked_miles=progress.distance_walked_m / METERS_PER_MILE,
            distance_remaining_miles=progress.distance_remaining_m / METERS_PER_MILE,
            percent_complete=progress.percent_complete,
            synced_at=datetime.now(timezone.utc),
        )

    def _notify_progress(self, session: Session, trip: ActiveTrip) -> list[TripCheckpoint]:
        """Checkpoint-hit and halfway/finished checks, in one place so
        record_steps and record_workout don't each repeat this. Fires
        self.events.notify() per event type; returns the newly-hit
        checkpoints (callers still need that list for their own return
        dict)."""
        _route, progress = _locate(trip)

        newly_hit_checkpoints = trips.mark_checkpoints_hit(session, trip, progress.distance_walked_m)
        for checkpoint in newly_hit_checkpoints:
            percent = (checkpoint.distance_from_start_m / trip.total_distance_m * 100) if trip.total_distance_m else 0.0
            self.events.notify(
                "landmark", f"🏁 Landmark reached: {checkpoint.name} ({percent}% of the way there!)"
            )

        for milestone in milestones_just_crossed(progress.percent_complete, set(trip.milestones_notified)):
            trips.mark_milestone_notified(session, trip, milestone)
            if milestone == "halfway":
                self.events.notify("halfway", "🎉 Halfway to your goal - 50%!")
            elif milestone == "finished":
                trips.complete_trip(session, trip)
                total_steps = self._db.total_steps(str(trip.id))
                self.events.notify("finished", f"🏆 You reached {trip.to_place} in {total_steps} steps! Congrats!")

        return newly_hit_checkpoints

    def _build_map_state(self, trip: ActiveTrip) -> dict:
        """Everything the frontend map/metrics need for this trip, built
        straight from an already-loaded ActiveTrip (no extra query) -
        used by every public method above so they all return the exact
        same shape."""
        route, progress = _locate(trip)

        now = datetime.now(timezone.utc)
        elapsed_seconds = _elapsed_seconds(trip, now)
        days_elapsed = elapsed_seconds / 86400
        daily_meters = average_daily_meters(progress.distance_walked_m, days_elapsed)
        days_remaining = estimate_days_remaining(progress.distance_remaining_m, daily_meters)

        trip_id_str = str(trip.id)

        return {
            "trip_id": trip_id_str,
            "status": trip.status,
            "from_place": trip.from_place,
            "to_place": trip.to_place,
            "round_trip": trip.round_trip,
            "start": {"lat": trip.start_lat, "lng": trip.start_lng},
            "end": {"lat": trip.end_lat, "lng": trip.end_lng},
            "route_geometry": trip.route_geometry,
            "walked_geometry": _walked_geometry(route, progress),
            "current_position": {"lat": progress.coords.lat, "lng": progress.coords.lng},
            "total_distance_m": trip.total_distance_m,
            "distance_walked_m": progress.distance_walked_m,
            "distance_remaining_m": progress.distance_remaining_m,
            "miles_walked": progress.distance_walked_m / METERS_PER_MILE,
            "miles_remaining": progress.distance_remaining_m / METERS_PER_MILE,
            "percent_complete": progress.percent_complete,
            "estimated_days_remaining": days_remaining,
            "total_steps": self._db.total_steps(trip_id_str),
            "today_steps": self._db.today_steps(trip_id_str),
            "started_at": trip.started_at.isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "checkpoints": [_checkpoint_state(c) for c in trip.checkpoints],
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


def _elapsed_seconds(trip: ActiveTrip, now: datetime) -> float:
    """Wall-clock time since started_at, minus every second the trip has
    spent paused (finished pauses, in total_paused_seconds, plus however
    long the current pause has run so far, if it's paused right now) - so
    this stays "time actually walking," matching the "Time walking"
    metrics-strip label, instead of drifting while a trip just sits
    paused."""
    ongoing_pause_seconds = (now - trip.paused_at).total_seconds() if trip.paused_at is not None else 0.0
    return (now - trip.started_at).total_seconds() - trip.total_paused_seconds - ongoing_pause_seconds


def _trip_summary(trip: ActiveTrip) -> dict:
    """The trips-list UI's per-card shape: enough to render a thumbnail,
    the from -> to line, and progress, without pulling in checkpoints or
    re-deriving current position the way _build_map_state() does for the
    live map."""
    return {
        "trip_id": str(trip.id),
        "status": trip.status,
        "from_place": trip.from_place,
        "to_place": trip.to_place,
        "round_trip": trip.round_trip,
        "total_distance_m": trip.total_distance_m,
        "distance_walked_m": min(trip.meters_walked, trip.total_distance_m),
        "miles_total": trip.total_distance_m / METERS_PER_MILE,
        "miles_walked": min(trip.meters_walked, trip.total_distance_m) / METERS_PER_MILE,
        "percent_complete": min(100.0, (trip.meters_walked / trip.total_distance_m * 100) if trip.total_distance_m else 0.0),
        "started_at": trip.started_at.isoformat(),
        "thumbnail_route": _thumbnail_route(trip.route_geometry),
    }


def _thumbnail_route(route_geometry: list[dict], max_points: int = 24) -> list[dict]:
    """route_geometry, downsampled to a small handful of points - plenty
    to draw a recognizable sparkline-style thumbnail on a trip card, at a
    fraction of the full polyline's size."""
    if len(route_geometry) <= max_points:
        return route_geometry
    step = len(route_geometry) / max_points
    indices = sorted({round(i * step) for i in range(max_points)} | {len(route_geometry) - 1})
    return [route_geometry[min(i, len(route_geometry) - 1)] for i in indices]


def _locate(trip: ActiveTrip) -> tuple[Route, Progress]:
    route = _route_from_geometry(trip.route_geometry)
    progress = locate_on_route(route, trip.meters_walked)
    return route, progress


def _route_from_geometry(route_geometry: list[dict]) -> Route:
    """Rebuilds the same Route shape OSRM originally returned, from the
    trip's stored polyline - no network call back to OSRM needed just to
    locate where the user currently is."""
    coords = [Coordinates(lat=point["lat"], lng=point["lng"]) for point in route_geometry]
    return build_route(coords)


def _walked_geometry(route: Route, progress: Progress) -> list[dict]:
    """The polyline from the start up to exactly where the user is now -
    every real route point the user has already passed, plus the precise
    interpolated current position as the final vertex, so this line's tip
    always lines up with the "you are here" marker on the map. Computed
    here (not in the browser) so the frontend never has to re-derive
    distance-along-a-polyline math that travel_logic/progress_calculator.py
    already owns."""
    passed_points = [
        {"lat": point.coords.lat, "lng": point.coords.lng}
        for point in route.points
        if point.distance_from_start <= progress.distance_walked_m
    ]
    passed_points.append({"lat": progress.coords.lat, "lng": progress.coords.lng})
    return passed_points


def _checkpoint_state(checkpoint: TripCheckpoint) -> dict:
    return {
        "checkpoint_number": checkpoint.checkpoint_number,
        "name": checkpoint.name,
        "coords": {"lat": checkpoint.lat, "lng": checkpoint.lng},
        "distance_from_start_m": checkpoint.distance_from_start_m,
        "description": checkpoint.description,
        "hit": checkpoint.hit_at is not None,
        "hit_at": checkpoint.hit_at.isoformat() if checkpoint.hit_at is not None else None,
    }


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


# One shared instance for the whole process - the webhook
# (services/google_health/webhook.py) and app.py's routes both need the
# same facade (it holds no per-user state itself anymore, just the shared
# geocoder/router/describer/db handles and the Observer event bus).
travel_facade = TravelFacade()
