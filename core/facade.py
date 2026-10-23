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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from database import trips
from database.models import ActiveTrip, TripCheckpoint
from database.session import SessionLocal
from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.geocoder import Place, create_geocoder
from travel_logic.route_service import OSRMWalkingRouteService, Route, RoutePoint, build_route
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
from travel_logic.checkpoints import resolve_checkpoint_name
from travel_logic.description_generator import generate_checkpoint_description
from data.total_distance_db import TotalDistanceDB
from core.observer_decorator.event_manager import EventManager
from core.observer_decorator.console_alert_listener import ConsoleAlertListener
from core.observer_decorator.email_alerts_listener import EmailAlertsListener
from core.observer_decorator.events import CheckpointReachedEvent
from services.google_health.client import get_profile
from services.fitbitMetrics.fitbit_user_data import UserMetric

load_dotenv()

METERS_PER_MILE = 1609.344

# How many checkpoints (by checkpoint_number, from the start) get their
# name/description resolved right away, as soon as a trip exists - so the
# walker's very first view of the map already shows real place names
# instead of every pin reading blank, without waiting on the *whole*
# route's worth of Nominatim/AI calls before the trip can even open.
INITIAL_METADATA_BATCH = 4

# How many checkpoints beyond the furthest currently-revealed one stay
# pre-resolved at all times - small enough that a long route's checkpoints
# mostly sit "pending" until the walker is actually near them (the whole
# point of resolving metadata lazily), large enough that a walker moving
# at a normal clip never outpaces the background resolution and sees a
# checkpoint's name still blank right as it reveals.
METADATA_LOOKAHEAD = 2

# One process-wide, bounded pool for every checkpoint's name/description
# resolution - shared across every trip and every call site (the initial
# bootstrap right after a trip is created, and every proximity-triggered
# lookahead afterward), not one pool per call. Nominatim's own rate limit
# is still the real bottleneck (travel_logic/geocoder.py's NominatimGeocoder
# throttles every request from any instance, process-wide, to its own
# policy) - this pool just bounds how many resolutions can be in flight
# waiting on that at once.
_checkpoint_metadata_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="checkpoint-metadata")


class TravelFacade:
    def __init__(self):
        self._geocoder = create_geocoder()
        self._router = OSRMWalkingRouteService()
        self._db = TotalDistanceDB()

        # Publisher (Observer pattern - https://refactoring.guru/design-patterns/observer):
        # TravelFacade plays the "Editor" role from that page's example -
        # it owns the EventManager and calls notify() when something
        # worth telling subscribers about happens.
        self.events = EventManager()
        console_listener = ConsoleAlertListener()
        for event_type in ("landmark", "halfway", "finished"):
            self.events.subscribe(event_type, console_listener)

        # checkpoint_reached carries structured data (see
        # core/observer_decorator/events.py), not a ready-to-print string
        # like the three above - Email is the only subscriber today, but
        # any future listener (UI, push notifications, ...) subscribes the
        # same way, via self.events.subscribe("checkpoint_reached", ...).
        self.events.subscribe("checkpoint_reached", EmailAlertsListener())

    def start_journey(
        self,
        user_id: uuid.UUID,
        from_place: str,
        to_place: str,
        gender: str | None = None,
        stride_length_m: float | None = None,
        round_trip: bool = False,
        from_coords: Coordinates | None = None,
        to_coords: Coordinates | None = None,
    ) -> dict:
        """Builds the route (network calls - geocoding, OSRM) and persists
        the trip immediately - every checkpoint's position for the whole
        route is generated and persisted right along with it
        (database/trips.py's create_trip(), via travel_logic/checkpoints.py's
        generate_checkpoint_positions() - pure geometry, no network calls,
        so it never slows this down), but every checkpoint's name/
        description starts blank. Resolving those is the genuinely slow,
        per-checkpoint part (Nominatim's ~1 req/sec policy, plus an AI
        call each) - app.py kicks bootstrap_checkpoint_metadata() off as a
        background task right after this returns to resolve just the
        first few, and the rest resolve lazily as the walker actually
        approaches them (see _ensure_checkpoint_metadata()). The trip
        appears on screen - map, route, distance, ETA, every checkpoint's
        position - in roughly the time two geocodes and one OSRM call
        take, not however long the full route's worth of metadata
        resolution would take. The network work here still happens before
        any database session is opened, so a slow external call never
        holds a DB connection idle.

        from_coords/to_coords: pass these when the caller already
        resolved real coordinates for from_place/to_place (the normal
        case now - CreatePage.tsx's autocomplete always resolves a
        selection to real lat/lng before Start Walking is even
        clickable, see app.py's JourneyStartRequest). Geocoding a place
        the caller already has coordinates for isn't just wasted work -
        it can genuinely fail for text a real selection produced but
        Nominatim's plain /search can't parse back (confirmed live: an
        airport-style or already-shortened label like "Chile Chico
        Airport (CCH), Chile Chico, CL" 400s as "No match", even though
        the user picked a real, valid place). geocode() is still the
        fallback for a caller with only place-name text and no
        coordinates of its own to offer."""
        start = from_coords or self._geocoder.geocode(from_place)
        end = to_coords or self._geocoder.geocode(to_place)
        route = self._router.get_walking_route(start, end)

        stride_by_type = _real_stride_by_type(user_id)
        if stride_length_m is None:
            stride_length_m = stride_by_type.get("WALKING")

        with SessionLocal() as session:
            trip = trips.create_trip(
                session=session,
                user_id=user_id,
                from_place=from_place,
                to_place=to_place,
                route=route,
                gender=gender,
                stride_length_m=stride_length_m,
                stride_by_type=stride_by_type,
                round_trip=round_trip,
            )
            # A checkpoint can land within the trip's own reveal radius of
            # the starting point itself (a short route, or just an
            # unlucky draw of the radius) - without this, it would only
            # reveal on the walker's first real progress sync instead of
            # showing up the instant the map first loads.
            trips.mark_checkpoints_revealed(session, trip, distance_walked_m=0.0)
            return self._build_map_state(trip)

    def bootstrap_checkpoint_metadata(self, trip_id: uuid.UUID) -> None:
        """Resolves name/description for just the first INITIAL_METADATA_
        BATCH checkpoints, split out of start_journey() above so it can
        run after the trip (map/route, every checkpoint's position) is
        already on screen - see app.py's /api/journey/start, which
        schedules this as a FastAPI BackgroundTask right after
        start_journey() returns. Every checkpoint beyond that batch stays
        "pending" until the walker actually gets near it - see
        _notify_progress()'s proximity-triggered lookahead, which is what
        resolves the rest, one small buffer at a time, for the entire
        rest of the trip."""
        with SessionLocal() as session:
            trip = trips.get_trip_by_id(session, trip_id)
            if trip is None:
                return  # deleted (or never existed) - nothing left to do
            self._ensure_checkpoint_metadata(session, trip, up_to_checkpoint_number=INITIAL_METADATA_BATCH)

    def _ensure_checkpoint_metadata(self, session: Session, trip: ActiveTrip, up_to_checkpoint_number: int) -> None:
        """Claims (database/trips.py's claim_checkpoint_for_metadata() -
        atomic, duplicate-job-safe) every checkpoint at or before
        up_to_checkpoint_number that still needs its name/description,
        and submits each one claimed to the shared, process-wide thread
        pool. Safe to call repeatedly/concurrently for the same trip - the
        claim is what guarantees two calls (the initial bootstrap and a
        proximity lookahead landing together, or two overlapping syncs)
        never both resolve the same checkpoint. Uses the session/trip the
        caller already has open rather than starting its own - both
        bootstrap_checkpoint_metadata() and _notify_progress() call this
        from inside a session they're already mid-way through."""
        trip_id = trip.id
        for checkpoint in trip.checkpoints:
            if checkpoint.checkpoint_number > up_to_checkpoint_number or checkpoint.metadata_status == "ready":
                continue
            if trips.claim_checkpoint_for_metadata(session, checkpoint.id):
                coordinates = Coordinates(lat=checkpoint.lat, lng=checkpoint.lng)
                _checkpoint_metadata_executor.submit(self._resolve_checkpoint_metadata, trip_id, checkpoint.id, coordinates)

    def _resolve_checkpoint_metadata(self, trip_id: uuid.UUID, checkpoint_id: uuid.UUID, coordinates: Coordinates) -> None:
        """One checkpoint's real name + AI description, resolved and
        persisted off the main request/sync thread - see
        _ensure_checkpoint_metadata()'s thread pool above. A failure here
        (Nominatim down, or the AI call itself failing) releases the
        claim back to "pending" rather than leaving the checkpoint stuck
        "processing" forever - a later bootstrap/lookahead call retries
        it."""
        try:
            name = resolve_checkpoint_name(coordinates, self._geocoder)
            description = generate_checkpoint_description(name, coordinates.lat, coordinates.lng)
            with SessionLocal() as session:
                row = trips.set_checkpoint_metadata(session, checkpoint_id, name, description)
                if row is None:
                    return  # checkpoint (or its trip) was deleted while this was in flight
                state = _checkpoint_state(row)
            self.events.notify(f"trip_checkpoints:{trip_id}", {"type": "checkpoint_updated", "checkpoint": state})
        except Exception as e:
            print(f"⚠️  checkpoint metadata resolution failed for checkpoint {checkpoint_id}: {type(e).__name__}: {e}")
            with SessionLocal() as session:
                trips.release_checkpoint_metadata_claim(session, checkpoint_id)

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

    def get_checkpoint_backlog(self, user_id: uuid.UUID, trip_id: uuid.UUID) -> tuple[list[dict], bool]:
        """Every checkpoint that exists for this trip (all of them, always -
        see database/trips.py's create_trip()), plus whether the trip is
        already finished - GET /api/journey/{trip_id}/events's (app.py)
        starting snapshot before it subscribes for live checkpoint_updated
        events. "Already finished" is the real "no more events are ever
        coming" signal now (metadata/reveal events keep trickling in for
        the whole rest of an active trip, not just some early generation
        window) - see _notify_progress()'s "finished" milestone branch,
        which fires the matching live checkpoints_ready event. user_id-
        scoped, same as get_map_state() - this is a user-facing endpoint,
        unlike bootstrap_checkpoint_metadata() itself."""
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            return [_checkpoint_state(c) for c in trip.checkpoints], trip.status == "completed"

    def list_trips(self, user_id: uuid.UUID) -> list[dict]:
        """Every trip belonging to this user (in progress or finished),
        summarized for the trips list UI - no per-trip network calls, no
        per-trip route rebuild, just what's already on the row (trips.
        list_trips() eager-loads checkpoints in one batched query) plus
        one batched steps query across every trip returned here. This
        used to be the cheap half of a two-part load: the frontend called
        this, then fetched full map state (_build_map_state(), including
        a full route rebuild - see its own docstring) per active trip just
        to get its current checkpoint and step count. Computing both
        straight from data this method already has removes that second,
        much more expensive round trip entirely - see HomePage.tsx."""
        with SessionLocal() as session:
            trip_rows = trips.list_trips(session, user_id)
            steps_by_trip = self._db.total_steps_by_trip([trip.id for trip in trip_rows])
            return [_trip_summary(trip, steps_by_trip.get(trip.id, 0)) for trip in trip_rows]

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

    def lifetime_steps(self, user_id: uuid.UUID) -> int:
        """Total steps this user has ever logged across every trip
        they've run - the Profile screen's one stat. A thin passthrough
        (see data/total_distance_db.py's lifetime_steps) so app.py still
        only ever talks to this facade, matching every other method
        here."""
        return self._db.lifetime_steps(str(user_id))

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
        """Checkpoint-reveal, checkpoint-hit, and halfway/finished checks,
        in one place so record_steps and record_workout don't each repeat
        this. Fires self.events.notify() per event type; returns the
        newly-hit checkpoints (callers still need that list for their own
        return dict)."""
        _route, progress = _locate(trip)

        newly_revealed = trips.mark_checkpoints_revealed(session, trip, progress.distance_walked_m)
        if newly_revealed:
            # Keep METADATA_LOOKAHEAD checkpoints beyond the furthest one
            # just revealed pre-resolved, so the walker is never the one
            # waiting on Nominatim/AI as they keep moving forward.
            furthest_revealed_number = max(c.checkpoint_number for c in newly_revealed)
            self._ensure_checkpoint_metadata(session, trip, up_to_checkpoint_number=furthest_revealed_number + METADATA_LOOKAHEAD)
            for checkpoint in newly_revealed:
                self.events.notify(f"trip_checkpoints:{trip.id}", {"type": "checkpoint_updated", "checkpoint": _checkpoint_state(checkpoint)})

        newly_hit_checkpoints = trips.mark_checkpoints_hit(session, trip, progress.distance_walked_m)
        for checkpoint in newly_hit_checkpoints:
            percent = (checkpoint.distance_from_start_m / trip.total_distance_m * 100) if trip.total_distance_m else 0.0
            self.events.notify(
                "landmark", f"🏁 Landmark reached: {checkpoint.name} ({percent}% of the way there!)"
            )
            checkpoint_event = CheckpointReachedEvent(
                user_id=trip.user_id,
                user_name=trip.user.email or "Traveler",
                checkpoint_name=checkpoint.name,
                checkpoint_number=checkpoint.checkpoint_number,
                description=checkpoint.description,
            )
            # [TEMP DEBUG] remove before deploying - see notification-flow testing
            print(
                f"📣 [TEMP DEBUG] Emitting CheckpointReachedEvent: user={checkpoint_event.user_name} "
                f"checkpoint=#{checkpoint_event.checkpoint_number} '{checkpoint_event.checkpoint_name}'"
            )
            self.events.notify("checkpoint_reached", checkpoint_event)

        for milestone in milestones_just_crossed(progress.percent_complete, set(trip.milestones_notified)):
            trips.mark_milestone_notified(session, trip, milestone)
            if milestone == "halfway":
                self.events.notify("halfway", "🎉 Halfway to your goal - 50%!")
            elif milestone == "finished":
                trips.complete_trip(session, trip)
                total_steps = self._db.total_steps(str(trip.id))
                self.events.notify("finished", f"🏆 You reached {trip.to_place} in {total_steps} steps! Congrats!")
                # The real "no more checkpoint events are ever coming for
                # this trip" signal now (see get_checkpoint_backlog()'s
                # docstring) - GET /api/journey/{id}/events's live loop
                # (app.py) closes the stream on this.
                self.events.notify(f"trip_checkpoints:{trip.id}", {"type": "checkpoints_ready"})

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
            "route_geometry": _route_geometry_latlng(trip.route_geometry),
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
            # True only once the trip itself is finished - metadata/reveal
            # events keep trickling in for an active trip's whole
            # duration now (checkpoints aren't resolved/revealed all at
            # once any more), so "ready" no longer means "discovery
            # finished early on" the way it used to. Lets the frontend
            # know whether GET /api/journey/{id}/events still has
            # anything left to stream (a finished trip doesn't).
            "checkpoints_ready": trip.status == "completed",
            "total_checkpoints": len(trip.checkpoints),
            # Proximity-revealed, not metadata-ready - a checkpoint shows
            # up on the map (name still filling in, maybe) well before
            # its description is ready. Never conflate the two: "ready"
            # describes the AI/geocoding pipeline's own progress, this
            # describes what the walker has actually uncovered so far.
            "discovered_checkpoints": sum(1 for c in trip.checkpoints if c.revealed_at is not None),
            "checkpoints": [_checkpoint_state(c) for c in trip.checkpoints],
        }

    def search_places(self, query: str, limit: int = 5) -> list[Place]:
        """Autocomplete candidates for app.py's Where From/Where To
        dropdowns - see Geocoder.search_places() for the normalized Place
        shape. Thin passthrough to the geocoder - kept here (not called
        directly by app.py) so the UI only ever talks to the facade,
        matching this module's "single entry point" role."""
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


def _trip_summary(trip: ActiveTrip, total_steps: int = 0) -> dict:
    """The trips-list UI's per-card shape: enough to render a thumbnail,
    the from -> to line, progress, step count, and current checkpoint -
    everything ActiveTripCard/CompletedTripCard need (frontend/src/
    components/TripCard.tsx) - without re-deriving current position or
    rebuilding the route the way _build_map_state() does for the live
    map. total_steps is passed in (one batched query across every trip -
    see list_trips() above), not looked up here per trip.

    trip.checkpoints is expected already eager-loaded (trips.list_trips()
    uses selectinload) - reading it here must never trigger its own
    per-trip query."""
    hit_checkpoints = [c for c in trip.checkpoints if c.hit_at is not None]
    current_checkpoint = hit_checkpoints[-1].name if hit_checkpoints else None
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
        "total_steps": total_steps,
        "current_checkpoint_name": current_checkpoint,
    }


def _thumbnail_route(route_geometry: list[dict], max_points: int = 24) -> list[dict]:
    """route_geometry, downsampled to a small handful of points - plenty
    to draw a recognizable sparkline-style thumbnail on a trip card, at a
    fraction of the full polyline's size. Stripped to lat/lng (see
    _route_geometry_latlng()) - the thumbnail is already tiny, but there's
    still no reason to ship the internal "d" bookkeeping field to a
    client that only ever draws points."""
    geometry = _route_geometry_latlng(route_geometry)
    if len(geometry) <= max_points:
        return geometry
    step = len(geometry) / max_points
    indices = sorted({round(i * step) for i in range(max_points)} | {len(geometry) - 1})
    return [geometry[min(i, len(geometry) - 1)] for i in indices]


def _locate(trip: ActiveTrip) -> tuple[Route, Progress]:
    route = _route_from_geometry(trip.route_geometry)
    progress = locate_on_route(route, trip.meters_walked)
    return route, progress


def _route_from_geometry(route_geometry: list[dict]) -> Route:
    """Rebuilds the same Route shape OSRM originally returned, from the
    trip's stored polyline - no network call back to OSRM needed just to
    locate where the user currently is.

    Every point here carries its own persisted "d" (distance_from_start)
    now - see database/trips.py's create_trip(), which writes it once,
    straight from the real OSRM response. Trusting it (via
    _route_from_persisted_distances() below) means this never re-measures
    every adjacent pair's distance with build_route()'s own
    haversine_meters() call on every single read. That recompute was
    measured at ~200ms of pure CPU for a real stored ~80k-point route
    (a genuinely common size here - cross-continental trips aren't an
    edge case in this app) - the same code path runs on every
    /api/journey/state call, including every 20s poll while a trip's map
    is open, so a long trip's map visibly took longer to appear than a
    short trip's, and every poll after that repeated the same cost. A row
    written before "d" existed falls back to the original, slower
    build_route() path below - same result, just not free."""
    if route_geometry and "d" in route_geometry[0]:
        return _route_from_persisted_distances(route_geometry)
    coords = [Coordinates(lat=point["lat"], lng=point["lng"]) for point in route_geometry]
    return build_route(coords)


def _route_from_persisted_distances(route_geometry: list[dict]) -> Route:
    """The fast path _route_from_geometry() above takes when every point
    already carries its own "d". Builds each RoutePoint directly from
    that persisted distance - distance_to_previous/distance_to_next are
    then one subtraction between neighbors (exactly what build_route()'s
    own gaps[] would have computed, since distance_from_start is just
    their running sum - not an approximation of it), never a fresh
    haversine_meters() call. Neither distance_to_previous nor
    distance_to_next is actually read anywhere on this read path
    (locate_on_route(), _walked_geometry()) - they're computed here only
    to keep returning a real, fully-populated RoutePoint, in case a
    future caller of this Route does need them."""
    n = len(route_geometry)
    total_distance = route_geometry[-1]["d"] if route_geometry else 0.0
    points = []
    for i, point in enumerate(route_geometry):
        distance_from_start = point["d"]
        points.append(RoutePoint(
            coords=Coordinates(lat=point["lat"], lng=point["lng"]),
            point_number=i + 1,
            distance_from_start=distance_from_start,
            distance_to_destination=total_distance - distance_from_start,
            distance_to_previous=distance_from_start - route_geometry[i - 1]["d"] if i > 0 else 0.0,
            distance_to_next=route_geometry[i + 1]["d"] - distance_from_start if i + 1 < n else 0.0,
        ))
    return Route(points=points, total_distance=total_distance, point_count=n)


def _route_geometry_latlng(route_geometry: list[dict]) -> list[dict]:
    """trip.route_geometry's stored shape now carries an internal "d"
    (distance_from_start - see create_trip()) alongside lat/lng, purely
    so this process can rebuild the route cheaply (see
    _route_from_geometry() above). The frontend only ever draws lat/lng
    (frontend/src/components/tripMap.ts) - sending "d" back out in every
    API response would just be re-growing the same long-route payload
    this change exists to shrink, for a field nothing on the other end
    reads."""
    return [{"lat": point["lat"], "lng": point["lng"]} for point in route_geometry]


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
        # Keeping the field name "description_status" (not "metadata_
        # status", the DB column's own, more accurate name since it now
        # also governs name resolution, not just description) - the
        # frontend's existing "!== 'ready' -> still generating" check
        # already treats the new "processing" value exactly like
        # "pending" with zero code changes, and nothing downstream needs
        # the field renamed to keep working.
        "description_status": checkpoint.metadata_status,
        # Proximity-revealed - see ActiveTrip.checkpoint_reveal_radius_m
        # and TripCheckpoint.revealed_at. The frontend only ever renders a
        # checkpoint marker when this is true.
        "revealed": checkpoint.revealed_at is not None,
        "hit": checkpoint.hit_at is not None,
        "hit_at": checkpoint.hit_at.isoformat() if checkpoint.hit_at is not None else None,
    }


def _real_stride_by_type(user_id: uuid.UUID) -> dict:
    """Real per-user stride from Google Health's profile (Profile >
    Google Health settings > Activity > Stride Length), confirmed live -
    empty if there's no connection yet or the pull fails, not a crash."""
    try:
        profile = UserMetric(get_profile(user_id)).metric_obj()
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
# geocoder/router/db handles and the Observer event bus).
travel_facade = TravelFacade()
