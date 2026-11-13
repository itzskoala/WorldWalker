# database/trips.py

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from backend.database.models import ActiveTrip, TripCheckpoint
from backend.travel_logic.checkpoints import Checkpoint, generate_checkpoint_positions, generate_reveal_radius_m
from backend.travel_logic.route_service import Route

METADATA_CLAIM_STALE_AFTER = timedelta(minutes=2)

IN_PROGRESS_STATUSES = ("active", "paused")
FINISHED_STATUSES = ("completed", "abandoned")

def create_trip(
    session: Session,
    user_id: uuid.UUID,
    from_place: str,
    to_place: str,
    route: Route,
    gender: str | None,
    stride_length_m: float | None,
    stride_by_type: dict[str, float],
    checkpoints: list[Checkpoint] | None = None,
    checkpoint_reveal_radius_m: float | None = None,
) -> ActiveTrip:
    if checkpoints is None:
        checkpoints = generate_checkpoint_positions(route)
    if checkpoint_reveal_radius_m is None:
        checkpoint_reveal_radius_m = generate_reveal_radius_m()

    start_point = route.points[0]
    end_point = route.points[-1]

    trip = ActiveTrip(
        user_id=user_id,
        status="active",
        from_place=from_place,
        to_place=to_place,
        start_lat=start_point.coords.lat,
        start_lng=start_point.coords.lng,
        end_lat=end_point.coords.lat,
        end_lng=end_point.coords.lng,
        route_geometry=[
            {"lat": point.coords.lat, "lng": point.coords.lng, "d": point.distance_from_start}
            for point in route.points
        ],
        total_distance_m=route.total_distance,
        meters_walked=0.0,
        stride_length_m=stride_length_m,
        gender=gender,
        stride_by_type=stride_by_type,
        workout_intervals=[],
        milestones_notified=[],
        checkpoint_reveal_radius_m=checkpoint_reveal_radius_m,
        started_at=datetime.now(timezone.utc),
    )
    session.add(trip)
    session.flush()  # assigns trip.id before the checkpoints below reference it

    for checkpoint in checkpoints:
        session.add(
            TripCheckpoint(
                trip_id=trip.id,
                checkpoint_number=checkpoint.checkpoint_number,
                name=checkpoint.name,
                lat=checkpoint.coordinates.lat,
                lng=checkpoint.coordinates.lng,
                distance_from_start_m=checkpoint.distance_from_start_m,
                description=checkpoint.description,
                metadata_status="ready" if checkpoint.name else "pending",
                revealed_at=None,
                hit_at=None,
            )
        )

    session.commit()
    return trip


def get_trip(session: Session, trip_id: uuid.UUID, user_id: uuid.UUID) -> ActiveTrip | None:
    statement = select(ActiveTrip).where(ActiveTrip.id == trip_id, ActiveTrip.user_id == user_id)
    return session.execute(statement).scalar_one_or_none()


def get_trip_by_id(session: Session, trip_id: uuid.UUID) -> ActiveTrip | None:
    return session.get(ActiveTrip, trip_id)


def claim_checkpoint_for_metadata(session: Session, checkpoint_id: uuid.UUID) -> bool:
    stale_cutoff = datetime.now(timezone.utc) - METADATA_CLAIM_STALE_AFTER
    result = session.execute(
        update(TripCheckpoint)
        .where(
            TripCheckpoint.id == checkpoint_id,
            or_(
                TripCheckpoint.metadata_status == "pending",
                (TripCheckpoint.metadata_status == "processing") & (TripCheckpoint.metadata_requested_at < stale_cutoff),
            ),
        )
        .values(metadata_status="processing", metadata_requested_at=datetime.now(timezone.utc))
    )
    session.commit()
    return result.rowcount == 1


def release_checkpoint_metadata_claim(session: Session, checkpoint_id: uuid.UUID) -> None:
    row = session.get(TripCheckpoint, checkpoint_id)
    if row is None or row.metadata_status == "ready":
        return
    row.metadata_status = "pending"
    row.metadata_requested_at = None
    session.commit()


def set_checkpoint_metadata(session: Session, checkpoint_id: uuid.UUID, name: str, description: str) -> TripCheckpoint | None:
    row = session.get(TripCheckpoint, checkpoint_id)
    if row is None:
        return None
    row.name = name
    row.description = description
    row.metadata_status = "ready"
    session.commit()
    return row


def mark_checkpoints_revealed(session: Session, trip: ActiveTrip, distance_walked_m: float) -> list[TripCheckpoint]:
    newly_revealed = []
    for checkpoint in trip.checkpoints:
        already_revealed = checkpoint.revealed_at is not None
        within_radius = checkpoint.distance_from_start_m - distance_walked_m <= trip.checkpoint_reveal_radius_m
        if within_radius and not already_revealed:
            checkpoint.revealed_at = datetime.now(timezone.utc)
            newly_revealed.append(checkpoint)

    if newly_revealed:
        session.commit()

    return newly_revealed


def get_active_trips(session: Session, user_id: uuid.UUID) -> list[ActiveTrip]:
    statement = (
        select(ActiveTrip)
        .where(ActiveTrip.user_id == user_id, ActiveTrip.status.in_(IN_PROGRESS_STATUSES))
        .order_by(ActiveTrip.started_at.desc())
    )
    return list(session.execute(statement).scalars())


def list_trips(session: Session, user_id: uuid.UUID) -> list[ActiveTrip]:
    statement = (
        select(ActiveTrip)
        .where(ActiveTrip.user_id == user_id)
        .options(selectinload(ActiveTrip.checkpoints))
        .order_by(ActiveTrip.started_at.desc())
    )
    return list(session.execute(statement).scalars())


def add_progress(
    session: Session,
    trip: ActiveTrip,
    meters_delta: float,
    workout_interval: tuple[str, str] | None = None,
) -> None:
    trip.meters_walked += meters_delta
    if workout_interval is not None:
        start_time, end_time = workout_interval
        trip.workout_intervals = [*trip.workout_intervals, [start_time, end_time]]
    session.commit()


def mark_checkpoints_hit(session: Session, trip: ActiveTrip, distance_walked_m: float) -> list[TripCheckpoint]:
    newly_hit_checkpoints = []
    for checkpoint in trip.checkpoints:
        already_hit = checkpoint.hit_at is not None
        just_reached = checkpoint.distance_from_start_m <= distance_walked_m
        if just_reached and not already_hit:
            checkpoint.hit_at = datetime.now(timezone.utc)
            newly_hit_checkpoints.append(checkpoint)
            # [TEMP DEBUG] remove before deploying - see notification-flow testing
            print(f"🎯 [TEMP DEBUG] Checkpoint detected as reached: #{checkpoint.checkpoint_number} '{checkpoint.name}' (trip={trip.id})")

    if newly_hit_checkpoints:
        session.commit()

    return newly_hit_checkpoints


def mark_milestone_notified(session: Session, trip: ActiveTrip, milestone: str) -> None:
    trip.milestones_notified = [*trip.milestones_notified, milestone]
    session.commit()


def complete_trip(session: Session, trip: ActiveTrip) -> None:
    trip.status = "completed"
    session.commit()


def pause_trip(session: Session, trip: ActiveTrip) -> None:
    if trip.status != "active":
        return
    trip.status = "paused"
    trip.paused_at = datetime.now(timezone.utc)
    session.commit()


def resume_trip(session: Session, trip: ActiveTrip) -> None:
    if trip.status != "paused":
        return
    if trip.paused_at is not None:
        trip.total_paused_seconds += (datetime.now(timezone.utc) - trip.paused_at).total_seconds()
    trip.paused_at = None
    trip.status = "active"
    session.commit()


def delete_trip(session: Session, trip: ActiveTrip) -> None:
    session.delete(trip)
    session.commit()


def delete_trips(session: Session, trips_to_delete: list[ActiveTrip]) -> None:
    for trip in trips_to_delete:
        session.delete(trip)
    session.commit()
