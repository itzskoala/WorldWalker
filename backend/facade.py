#facade.py

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from backend.database import trips
from backend.database.models import ActiveTrip, TripCheckpoint
from backend.database.session import SessionLocal
from backend.travel_logic.dataclasses.coordinates import Coordinates
from backend.travel_logic.geocoder import Place, create_geocoder
from backend.travel_logic.route_service import OSRMWalkingRouteService, Route, RoutePoint, build_route
from backend.travel_logic.progress_calculator import (
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
    _parse_iso,
)
from backend.travel_logic.checkpoints import resolve_checkpoint_name
from backend.travel_logic.description_generator import generate_checkpoint_description
from backend.data.total_distance_db import TotalDistanceDB
from backend.services.google_health.client import get_profile
from backend.services.health_metrics.user_data import UserMetric
from backend.notifications.event_manager import EventManager

load_dotenv()

METERS_PER_MILE = 1609.344

# How many checkpoints (by checkpoint_number, from the start) get their
# name/description resolved right away, as soon as a trip exists 
INITIAL_METADATA_BATCH = 4

# How many checkpoints beyond the furthest currently-revealed one stay
# pre-resolved at all times - small enough that a long route's checkpoints
# mostly sit "pending" until the walker is actually near them (the whole
# point of resolving metadata lazily)
METADATA_LOOKAHEAD = 2

_checkpoint_metadata_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="checkpoint-metadata")

class TravelFacade:
    def __init__(self):
        self._geocoder = create_geocoder()
        self._router = OSRMWalkingRouteService()
        self._db = TotalDistanceDB()
        self.events = EventManager()

    def start_journey(
        self,
        user_id: uuid.UUID,
        from_place: str,
        to_place: str,
        gender: str | None = None,
        stride_length_m: float | None = None,
        from_coords: Coordinates | None = None,
        to_coords: Coordinates | None = None,
    ) -> dict:
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
            )
            trips.mark_checkpoints_revealed(session, trip, distance_walked_m=0.0)
            return self._build_map_state(trip)

    def bootstrap_checkpoint_metadata(self, trip_id: uuid.UUID) -> None:
        with SessionLocal() as session:
            trip = trips.get_trip_by_id(session, trip_id)
            if trip is None:
                return  # deleted (or never existed) - nothing left to do
            self._ensure_checkpoint_metadata(session, trip, up_to_checkpoint_number=INITIAL_METADATA_BATCH)

    def _ensure_checkpoint_metadata(self, session: Session, trip: ActiveTrip, up_to_checkpoint_number: int) -> None:
        trip_id = trip.id
        for checkpoint in trip.checkpoints:
            if checkpoint.checkpoint_number > up_to_checkpoint_number or checkpoint.metadata_status == "ready":
                continue
            if trips.claim_checkpoint_for_metadata(session, checkpoint.id):
                coordinates = Coordinates(lat=checkpoint.lat, lng=checkpoint.lng)
                _checkpoint_metadata_executor.submit(self._resolve_checkpoint_metadata, trip_id, checkpoint.id, coordinates)

    def _resolve_checkpoint_metadata(self, trip_id: uuid.UUID, checkpoint_id: uuid.UUID, coordinates: Coordinates) -> None:
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
        with SessionLocal() as session:
            active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
            if not active_trips:
                raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

            states = []
            for trip in active_trips:
                skip = interval is not None and (
                    _parse_iso(interval.end_time) <= trip.started_at
                    or interval_within_any(interval.start_time, interval.end_time, trip.workout_intervals)
                )
                if skip:
                    state = self._build_map_state(trip)
                    state["newly_hit_checkpoints"] = []
                    states.append(state)
                    continue

                stride_m = resolve_stride_m(google_health_stride_m=trip.stride_length_m, gender=trip.gender)
                meters_delta = steps_to_meters(steps, stride_m)
                trips.add_progress(session, trip, meters_delta)

                self._record_sync(user_id, steps, trip)

                newly_hit_checkpoints = self._notify_progress(session, trip)
                state = self._build_map_state(trip)
                state["newly_hit_checkpoints"] = [_checkpoint_state(c) for c in newly_hit_checkpoints]
                states.append(state)

            return states

    def record_workout(self, user_id: uuid.UUID, exercise) -> list[dict]:
        with SessionLocal() as session:
            active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
            if not active_trips:
                raise ValueError(f"No active journey for user_id={user_id!r} - call start_journey first")

            summary = exercise.metrics_summary
            duration_hours = interval_duration_hours(exercise.interval.start_time, exercise.interval.end_time)

            states = []
            for trip in active_trips:
                if _parse_iso(exercise.interval.end_time) <= trip.started_at:
                    state = self._build_map_state(trip)
                    state["newly_hit_checkpoints"] = []
                    states.append(state)
                    continue

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

            
                if distance_m:
                    workout_interval = (exercise.interval.start_time, exercise.interval.end_time)
                    trips.add_progress(session, trip, distance_m, workout_interval=workout_interval)

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
        with SessionLocal() as session:
            trip = trips.get_trip(session, trip_id, user_id)
            if trip is None:
                raise ValueError(f"No trip {trip_id!r} for user_id={user_id!r}")
            return [_checkpoint_state(c) for c in trip.checkpoints], trip.status == "completed"

    def list_trips(self, user_id: uuid.UUID) -> list[dict]:
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
        return self._db.lifetime_steps(str(user_id))

    def delete_journeys(self, user_id: uuid.UUID, trip_ids: list[uuid.UUID]) -> int:
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
        _route, progress = _locate(trip)

        newly_revealed = trips.mark_checkpoints_revealed(session, trip, progress.distance_walked_m)
        if newly_revealed:
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
            "checkpoints_ready": trip.status == "completed",
            "total_checkpoints": len(trip.checkpoints),
            "discovered_checkpoints": sum(1 for c in trip.checkpoints if c.revealed_at is not None),
            "checkpoints": [_checkpoint_state(c) for c in trip.checkpoints],
        }

    def search_places(self, query: str, limit: int = 5) -> list[Place]:
        return self._geocoder.search_places(query, limit)

    def current_location_place(self, lat: float, lng: float) -> str:
        return self._geocoder.reverse_geocode(Coordinates(lat=lat, lng=lng))


def _elapsed_seconds(trip: ActiveTrip, now: datetime) -> float:
    ongoing_pause_seconds = (now - trip.paused_at).total_seconds() if trip.paused_at is not None else 0.0
    return (now - trip.started_at).total_seconds() - trip.total_paused_seconds - ongoing_pause_seconds


def _trip_summary(trip: ActiveTrip, total_steps: int = 0) -> dict:
    hit_checkpoints = [c for c in trip.checkpoints if c.hit_at is not None]
    current_checkpoint = hit_checkpoints[-1].name if hit_checkpoints else None
    return {
        "trip_id": str(trip.id),
        "status": trip.status,
        "from_place": trip.from_place,
        "to_place": trip.to_place,
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
    if route_geometry and "d" in route_geometry[0]:
        return _route_from_persisted_distances(route_geometry)
    coords = [Coordinates(lat=point["lat"], lng=point["lng"]) for point in route_geometry]
    return build_route(coords)


def _route_from_persisted_distances(route_geometry: list[dict]) -> Route:
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
    return [{"lat": point["lat"], "lng": point["lng"]} for point in route_geometry]


def _walked_geometry(route: Route, progress: Progress) -> list[dict]:
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
        "description_status": checkpoint.metadata_status,
        "revealed": checkpoint.revealed_at is not None,
        "hit": checkpoint.hit_at is not None,
        "hit_at": checkpoint.hit_at.isoformat() if checkpoint.hit_at is not None else None,
    }


def _real_stride_by_type(user_id: uuid.UUID) -> dict:
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
# and app.py's routes both need the same facade 
travel_facade = TravelFacade()
