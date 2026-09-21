# database/trips.py
# Everything that reads or writes an ActiveTrip/TripCheckpoint row - the
# real, persistent home for a journey in progress. Mirrors
# auth/connections.py's role for GoogleHealthConnection: "when to touch
# these rows, and what to do with the result." The schema itself lives in
# database/models.py; core/facade.py is the only caller, and it never
# touches ActiveTrip/TripCheckpoint directly - this module is the one seam
# between the ORM and the rest of the app.
#
# A user can have several trips going at once - there is no "one active
# trip per user" constraint. Real steps get credited to every one of a
# user's status="active" trips at once (see core/facade.py's record_steps/
# record_workout); pausing a trip is what opts it out of that.
#
# Every function here takes an already-open SQLAlchemy Session and commits
# its own changes - each one is a complete, standalone unit of work (start a
# trip, record one sync's worth of progress, ...), not a step inside some
# larger transaction a caller needs to control.

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import ActiveTrip, TripCheckpoint
from travel_logic.checkpoints import Checkpoint
from travel_logic.route_service import Route

IN_PROGRESS_STATUSES = ("active", "paused")
FINISHED_STATUSES = ("completed", "abandoned")


def create_trip(
    session: Session,
    user_id: uuid.UUID,
    from_place: str,
    to_place: str,
    route: Route,
    checkpoints: list[Checkpoint],
    gender: str | None,
    stride_length_m: float | None,
    stride_by_type: dict[str, float],
    round_trip: bool,
) -> ActiveTrip:
    """Starts a brand new trip for this user, alongside any other trips
    they already have running - multiple concurrent trips are the normal
    case now, not an edge case to guard against."""
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
        route_geometry=[{"lat": point.coords.lat, "lng": point.coords.lng} for point in route.points],
        total_distance_m=route.total_distance,
        meters_walked=0.0,
        stride_length_m=stride_length_m,
        gender=gender,
        stride_by_type=stride_by_type,
        workout_intervals=[],
        milestones_notified=[],
        round_trip=round_trip,
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
                hit_at=None,
            )
        )

    session.commit()
    return trip


def get_trip(session: Session, trip_id: uuid.UUID, user_id: uuid.UUID) -> ActiveTrip | None:
    """A single trip by id, scoped to the requesting user - callers must
    never trust a trip_id alone (it's client-supplied), since that would
    let one user read or mutate another's trip."""
    statement = select(ActiveTrip).where(ActiveTrip.id == trip_id, ActiveTrip.user_id == user_id)
    return session.execute(statement).scalar_one_or_none()


def get_active_trips(session: Session, user_id: uuid.UUID) -> list[ActiveTrip]:
    """Every trip currently in progress (status "active" or "paused") for
    this user - the set record_steps()/record_workout() fan real progress
    out across. Ordered newest-first, matching list_trips()."""
    statement = (
        select(ActiveTrip)
        .where(ActiveTrip.user_id == user_id, ActiveTrip.status.in_(IN_PROGRESS_STATUSES))
        .order_by(ActiveTrip.started_at.desc())
    )
    return list(session.execute(statement).scalars())


def list_trips(session: Session, user_id: uuid.UUID) -> list[ActiveTrip]:
    """Every trip belonging to this user, in progress or not - the source
    for the "active" / "past" split in the trips list UI."""
    statement = select(ActiveTrip).where(ActiveTrip.user_id == user_id).order_by(ActiveTrip.started_at.desc())
    return list(session.execute(statement).scalars())


def add_progress(
    session: Session,
    trip: ActiveTrip,
    meters_delta: float,
    workout_interval: tuple[str, str] | None = None,
) -> None:
    """Credits newly-covered distance to the trip. workout_interval, when
    given, is recorded so a later "steps" event covering the same window
    doesn't get double-counted - see
    travel_logic/progress_calculator.py's interval_within_any(), which
    reads this same list back."""
    trip.meters_walked += meters_delta
    if workout_interval is not None:
        start_time, end_time = workout_interval
        trip.workout_intervals = [*trip.workout_intervals, [start_time, end_time]]
    session.commit()


def mark_checkpoints_hit(session: Session, trip: ActiveTrip, distance_walked_m: float) -> list[TripCheckpoint]:
    """Sets hit_at on every checkpoint distance_walked_m has now reached
    that wasn't already hit, and returns just those newly-hit checkpoints -
    hit_at is set once and never cleared, so a checkpoint already hit on an
    earlier call is never returned again."""
    newly_hit_checkpoints = []
    for checkpoint in trip.checkpoints:
        already_hit = checkpoint.hit_at is not None
        just_reached = checkpoint.distance_from_start_m <= distance_walked_m
        if just_reached and not already_hit:
            checkpoint.hit_at = datetime.now(timezone.utc)
            newly_hit_checkpoints.append(checkpoint)

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
    """No-op if the trip is already paused (or finished) - callers don't
    need to check status themselves first."""
    if trip.status != "active":
        return
    trip.status = "paused"
    trip.paused_at = datetime.now(timezone.utc)
    session.commit()


def resume_trip(session: Session, trip: ActiveTrip) -> None:
    """Folds the just-finished pause into total_paused_seconds before
    clearing paused_at, so core.facade's elapsed-time math never loses
    track of time already spent paused."""
    if trip.status != "paused":
        return
    if trip.paused_at is not None:
        trip.total_paused_seconds += (datetime.now(timezone.utc) - trip.paused_at).total_seconds()
    trip.paused_at = None
    trip.status = "active"
    session.commit()


def delete_trip(session: Session, trip: ActiveTrip) -> None:
    """A real delete, not a status flip - trip_checkpoints cascades via the
    FK's ondelete="CASCADE". Used by the trips list UI's delete/multi-select
    actions and, per the person building this, for clearing out dev/test
    trips too."""
    session.delete(trip)
    session.commit()


def delete_trips(session: Session, trips_to_delete: list[ActiveTrip]) -> None:
    for trip in trips_to_delete:
        session.delete(trip)
    session.commit()
