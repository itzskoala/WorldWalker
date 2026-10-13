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
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, selectinload

from database.models import ActiveTrip, TripCheckpoint
from travel_logic.checkpoints import Checkpoint, generate_checkpoint_positions, generate_reveal_radius_m
from travel_logic.route_service import Route

# A claimed-but-unfinished metadata job older than this is presumed dead
# (its worker thread crashed, or the process restarted mid-job) - see
# claim_checkpoint_for_metadata() - rather than left "processing" forever
# with nothing left to ever retry it.
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
    round_trip: bool,
    checkpoints: list[Checkpoint] | None = None,
    checkpoint_reveal_radius_m: float | None = None,
) -> ActiveTrip:
    """Starts a brand new trip for this user, alongside any other trips
    they already have running - multiple concurrent trips are the normal
    case now, not an edge case to guard against.

    checkpoints: every checkpoint's position for the route, generated up
    front (travel_logic/checkpoints.py's generate_checkpoint_positions())
    when not given - the normal path (core/facade.py's start_journey()
    never passes this). An explicit list - including [] - is honored
    as-is instead, which is what tests use to seed known checkpoints, or
    deliberately none.

    checkpoint_reveal_radius_m: this trip's randomized proximity-reveal
    distance, generated (travel_logic/checkpoints.py's
    generate_reveal_radius_m()) when not given - see
    TripCheckpoint.revealed_at and ActiveTrip.checkpoint_reveal_radius_m's
    own docstrings for what this governs."""
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
        # "d": point.distance_from_start, alongside lat/lng - route.points
        # already carries each point's exact, haversine-measured distance
        # from the start (built once, here, from the real OSRM response -
        # see travel_logic/route_service.py's build_route()). Persisting
        # it means core/facade.py's _route_from_geometry() can rebuild
        # this same Route later (every /api/journey/state read, every
        # 20s poll while a trip is open) without re-measuring every
        # adjacent pair's distance via haversine all over again - see
        # that function's own docstring for why that recompute was a
        # real, measured bottleneck for a long route's geometry.
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
        round_trip=round_trip,
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
                # A checkpoint handed in with a real name already (tests
                # seeding a ready-made list) has no metadata left to
                # resolve - "ready" immediately. The normal path (a blank-
                # name position straight from generate_checkpoint_positions())
                # starts "pending" instead, same as always, so core/
                # facade.py's checkpoint-metadata pipeline knows there's
                # real work to do for it.
                metadata_status="ready" if checkpoint.name else "pending",
                revealed_at=None,
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


def get_trip_by_id(session: Session, trip_id: uuid.UUID) -> ActiveTrip | None:
    """Unscoped by user - only for the background checkpoint-metadata job
    (core/facade.py's bootstrap_checkpoint_metadata()), which runs with a
    trip_id it just minted itself (from start_journey(), in the same
    request), never one a client supplied. Every user-facing path still
    goes through get_trip() above."""
    return session.get(ActiveTrip, trip_id)


def claim_checkpoint_for_metadata(session: Session, checkpoint_id: uuid.UUID) -> bool:
    """Atomically flips one checkpoint from "pending" (or a "processing"
    claim old enough to be presumed dead - see METADATA_CLAIM_STALE_AFTER)
    to "processing", and reports whether *this* call is the one that won
    the claim. Core/facade.py's checkpoint-metadata pipeline calls this
    before ever submitting a checkpoint to its background thread pool -
    the initial-batch bootstrap and a proximity-triggered lookahead can
    both try to claim the same checkpoint at once (or a page reload can
    re-trigger a bootstrap for a checkpoint already being worked on), and
    this single UPDATE-with-a-WHERE is what guarantees only one of them
    ever actually processes it.

    A single UPDATE statement, not a read-then-write - the WHERE clause
    itself is the race-proof part; two concurrent calls can't both match
    the same row."""
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
    """Puts a checkpoint back to "pending" after a failed resolution
    attempt (a Nominatim/AI call that raised), so the next bootstrap or
    proximity-triggered lookahead call retries it instead of leaving it
    stuck "processing" forever. No-op if the checkpoint's already
    "ready" (a stale duplicate failure callback arriving after a retry
    already succeeded) or gone."""
    row = session.get(TripCheckpoint, checkpoint_id)
    if row is None or row.metadata_status == "ready":
        return
    row.metadata_status = "pending"
    row.metadata_requested_at = None
    session.commit()


def set_checkpoint_metadata(session: Session, checkpoint_id: uuid.UUID, name: str, description: str) -> TripCheckpoint | None:
    """Fills in a checkpoint's real name and AI description once both are
    known and flips it to "ready". None if the checkpoint (or its trip)
    was deleted out from under a still-running background job."""
    row = session.get(TripCheckpoint, checkpoint_id)
    if row is None:
        return None
    row.name = name
    row.description = description
    row.metadata_status = "ready"
    session.commit()
    return row


def mark_checkpoints_revealed(session: Session, trip: ActiveTrip, distance_walked_m: float) -> list[TripCheckpoint]:
    """Sets revealed_at on every checkpoint now within this trip's own
    randomized reveal radius (checkpoint_reveal_radius_m) that wasn't
    already revealed, and returns just those newly-revealed checkpoints -
    same "set once, never cleared" shape as mark_checkpoints_hit() below,
    and deliberately independent of it: a checkpoint reveals itself a
    little before the walker actually reaches it (that's the whole point
    of the radius), and a checkpoint already passed is trivially "within
    radius" too (distance_from_start_m - distance_walked_m goes
    negative, which is <= any positive radius) - so hit checkpoints are
    always revealed, never the other way around."""
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
    for the "active" / "past" split in the trips list UI.

    selectinload(checkpoints): the trips list UI shows each active trip's
    most-recently-reached checkpoint (core/facade.py's _trip_summary()),
    which needs trip.checkpoints. Without this, accessing that relation
    on each returned trip would lazy-load it with its own separate query
    per trip - one extra round trip per active trip, on top of the one
    this function already makes. selectinload issues exactly one extra
    query total (checkpoints for every trip id returned here), not one
    per trip, regardless of how many trips a user has."""
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
