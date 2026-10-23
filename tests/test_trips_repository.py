# tests/test_trips_repository.py
# database/trips.py's own behavior, independent of TravelFacade: a user can
# have several trips going at once, progress/checkpoint/milestone
# bookkeeping updates the right rows, pause/resume track paused time, and
# complete_trip/delete_trip remove a trip from the active set.
# Runs against real Postgres (tests/conftest.py's db_session fixture).

from datetime import datetime, timedelta, timezone

import pytest

from database import trips
from database.models import TripCheckpoint, User
from travel_logic.checkpoints import Checkpoint
from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint

TOTAL_DISTANCE_M = 10_000.0


class _FakeDatetime:
    """Stands in for database.trips's `datetime` import so pause/resume
    tests can control "now" precisely instead of racing a real clock -
    holds a one-item list (`now_holder`) so a test can mutate what .now()
    returns between calls."""

    def __init__(self, now_holder):
        self._now_holder = now_holder

    def now(self, tz=None):
        return self._now_holder[0]


def _route() -> Route:
    return Route(
        points=[
            RoutePoint(Coordinates(0.0, 0.0), point_number=1, distance_from_start=0.0,
                       distance_to_destination=TOTAL_DISTANCE_M, distance_to_previous=0.0, distance_to_next=TOTAL_DISTANCE_M),
            RoutePoint(Coordinates(0.0, 0.09), point_number=2, distance_from_start=TOTAL_DISTANCE_M,
                       distance_to_destination=0.0, distance_to_previous=TOTAL_DISTANCE_M, distance_to_next=0.0),
        ],
        total_distance=TOTAL_DISTANCE_M,
        point_count=2,
    )


def _checkpoint(name: str, distance_from_start_m: float, checkpoint_number: int = 1) -> Checkpoint:
    return Checkpoint(
        name=name,
        coordinates=Coordinates(0.0, 0.04),
        checkpoint_number=checkpoint_number,
        distance_from_start_m=distance_from_start_m,
        distance_to_destination_m=TOTAL_DISTANCE_M - distance_from_start_m,
        description="A stop along the way.",
    )


def _make_user(db_session):
    user = User()
    db_session.add(user)
    db_session.commit()
    return user.id


def test_create_trip_persists_the_trip_and_its_checkpoints(db_session):
    user_id = _make_user(db_session)

    trip = trips.create_trip(
        session=db_session,
        user_id=user_id,
        from_place="Miami, Florida",
        to_place="Chicago, Illinois",
        route=_route(),
        checkpoints=[_checkpoint("Midway", 5_000.0)],
        gender=None,
        stride_length_m=None,
        stride_by_type={},
        round_trip=False,
    )

    assert trip.status == "active"
    assert trip.total_distance_m == TOTAL_DISTANCE_M
    assert len(trip.route_geometry) == 2
    assert [c.name for c in trip.checkpoints] == ["Midway"]
    assert trip.checkpoints[0].hit_at is None

    # Each stored point carries its own real, already-measured distance
    # from the start (route.points[i].distance_from_start, straight off
    # the Route this trip was created from) - core/facade.py's
    # _route_from_geometry() reads this back to rebuild the Route on
    # every later read without re-measuring every pair via haversine all
    # over again. Losing this (storing just {lat, lng}) is exactly what
    # made a long trip's /api/journey/state measurably slower than a
    # short one's - see that function's own docstring.
    assert [point["d"] for point in trip.route_geometry] == [0.0, TOTAL_DISTANCE_M]


def test_create_trip_does_not_disturb_an_existing_active_trip(db_session):
    # A user can have several trips going at once now - starting a second
    # one is additive, not a replacement (see database/trips.py's module
    # docstring).
    user_id = _make_user(db_session)

    first_trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )
    second_trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="C", to_place="D",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    db_session.refresh(first_trip)
    assert first_trip.status == "active"
    assert second_trip.status == "active"
    assert {t.id for t in trips.get_active_trips(db_session, user_id)} == {first_trip.id, second_trip.id}


def test_get_active_trips_returns_empty_list_when_there_is_no_trip(db_session):
    user_id = _make_user(db_session)
    assert trips.get_active_trips(db_session, user_id) == []


def test_get_trip_is_scoped_to_the_owning_user(db_session):
    owner_id = _make_user(db_session)
    other_user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=owner_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    assert trips.get_trip(db_session, trip.id, owner_id).id == trip.id
    assert trips.get_trip(db_session, trip.id, other_user_id) is None


def test_pause_then_resume_accumulates_total_paused_seconds(db_session, monkeypatch):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    fake_now = [datetime(2026, 9, 8, 9, 0, 0, tzinfo=timezone.utc)]
    monkeypatch.setattr(trips, "datetime", _FakeDatetime(fake_now))

    trips.pause_trip(db_session, trip)
    assert trip.status == "paused"
    assert trip.paused_at == fake_now[0]

    fake_now[0] = fake_now[0] + timedelta(seconds=90)
    trips.resume_trip(db_session, trip)

    assert trip.status == "active"
    assert trip.paused_at is None
    assert trip.total_paused_seconds == pytest.approx(90.0)

    # Pausing/resuming again adds to the running total instead of
    # overwriting it.
    trips.pause_trip(db_session, trip)
    fake_now[0] = fake_now[0] + timedelta(seconds=30)
    trips.resume_trip(db_session, trip)
    assert trip.total_paused_seconds == pytest.approx(120.0)


def test_pause_and_resume_are_no_ops_in_the_wrong_state(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    trips.resume_trip(db_session, trip)  # not paused - no-op
    assert trip.status == "active"

    trips.complete_trip(db_session, trip)
    trips.pause_trip(db_session, trip)  # finished, not active - no-op
    assert trip.status == "completed"


def test_delete_trip_removes_it_and_its_checkpoints(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[_checkpoint("Midway", 5_000.0)], gender=None,
        stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    trip_id = trip.id

    trips.delete_trip(db_session, trip)

    assert trips.get_trip(db_session, trip_id, user_id) is None
    assert db_session.query(TripCheckpoint).filter_by(trip_id=trip_id).count() == 0


def test_delete_trips_removes_only_the_given_ones(db_session):
    user_id = _make_user(db_session)
    keep = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )
    delete_me = trips.create_trip(
        session=db_session, user_id=user_id, from_place="C", to_place="D",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    trips.delete_trips(db_session, [delete_me])

    assert trips.get_trip(db_session, keep.id, user_id) is not None
    assert trips.get_trip(db_session, delete_me.id, user_id) is None


def test_list_trips_returns_every_trip_regardless_of_status(db_session):
    user_id = _make_user(db_session)
    active = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )
    finished = trips.create_trip(
        session=db_session, user_id=user_id, from_place="C", to_place="D",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )
    trips.complete_trip(db_session, finished)

    assert {t.id for t in trips.list_trips(db_session, user_id)} == {active.id, finished.id}


def test_add_progress_accumulates_meters_walked_and_records_workout_intervals(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    trips.add_progress(db_session, trip, 1_000.0)
    trips.add_progress(db_session, trip, 500.0, workout_interval=("2026-09-08T09:00:00Z", "2026-09-08T09:30:00Z"))

    assert trip.meters_walked == 1_500.0
    assert trip.workout_intervals == [["2026-09-08T09:00:00Z", "2026-09-08T09:30:00Z"]]


def test_mark_checkpoints_hit_only_returns_newly_hit_ones_each_call(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(),
        checkpoints=[_checkpoint("Near", 2_000.0, checkpoint_number=1), _checkpoint("Far", 8_000.0, checkpoint_number=2)],
        gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )

    newly_hit_at_3000m = trips.mark_checkpoints_hit(db_session, trip, distance_walked_m=3_000.0)
    assert [c.name for c in newly_hit_at_3000m] == ["Near"]

    # Walking further doesn't re-report "Near" - only the newly-crossed one.
    newly_hit_at_9000m = trips.mark_checkpoints_hit(db_session, trip, distance_walked_m=9_000.0)
    assert [c.name for c in newly_hit_at_9000m] == ["Far"]

    still_hit = trips.mark_checkpoints_hit(db_session, trip, distance_walked_m=9_000.0)
    assert still_hit == []


def test_complete_trip_flips_status_and_drops_out_of_get_active_trips(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None,
        stride_by_type={}, round_trip=False,
    )

    trips.complete_trip(db_session, trip)

    assert trip.status == "completed"
    assert trips.get_active_trips(db_session, user_id) == []


# --- create_trip: checkpoint positions + reveal radius generated up front ---

def test_create_trip_generates_checkpoint_positions_when_none_are_given(db_session):
    # No checkpoints=... at all - the real start_journey() path. Every
    # position for the whole route is generated and persisted
    # immediately, blank name/description, "pending" metadata.
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )

    assert len(trip.checkpoints) > 0
    for checkpoint in trip.checkpoints:
        assert checkpoint.name == ""
        assert checkpoint.metadata_status == "pending"
        assert checkpoint.revealed_at is None
        assert 0 < checkpoint.distance_from_start_m < TOTAL_DISTANCE_M


def test_create_trip_generates_a_reveal_radius_within_the_configured_range_when_none_is_given(db_session):
    from travel_logic.checkpoints import CHECKPOINT_REVEAL_RADIUS_MIN_M, CHECKPOINT_REVEAL_RADIUS_MAX_M

    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )

    assert CHECKPOINT_REVEAL_RADIUS_MIN_M <= trip.checkpoint_reveal_radius_m <= CHECKPOINT_REVEAL_RADIUS_MAX_M


def test_create_trip_persists_an_explicit_reveal_radius_instead_of_generating_one(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
        checkpoint_reveal_radius_m=88.0,
    )

    assert trip.checkpoint_reveal_radius_m == 88.0


def test_create_trip_persists_the_same_radius_on_reload_not_a_fresh_random_one(db_session):
    # Simulates a refresh/reconnect: re-reading the same trip must never
    # see a different radius than what was generated at creation.
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    original_radius = trip.checkpoint_reveal_radius_m

    reloaded = trips.get_trip(db_session, trip.id, user_id)

    assert reloaded.checkpoint_reveal_radius_m == original_radius


# --- mark_checkpoints_revealed: proximity-based discovery ---

def test_mark_checkpoints_revealed_only_reveals_checkpoints_within_the_radius(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(),
        checkpoints=[_checkpoint("Near", 1_000.0, checkpoint_number=1), _checkpoint("Far", 9_000.0, checkpoint_number=2)],
        gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
        checkpoint_reveal_radius_m=75.0,
    )

    # Walking to 950m puts "Near" (at 1000m) within the 75m radius but
    # leaves "Far" (at 9000m) well outside it.
    newly_revealed = trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=950.0)

    assert [c.name for c in newly_revealed] == ["Near"]
    near, far = trip.checkpoints
    assert near.revealed_at is not None
    assert far.revealed_at is None


def test_mark_checkpoints_revealed_stays_revealed_once_set_even_after_walking_past_it(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[_checkpoint("Near", 1_000.0, checkpoint_number=1)],
        gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
        checkpoint_reveal_radius_m=75.0,
    )

    trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=950.0)
    first_revealed_at = trip.checkpoints[0].revealed_at
    assert first_revealed_at is not None

    # Walking far past it doesn't re-reveal (and the timestamp doesn't move).
    again = trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=9_000.0)

    assert again == []
    assert trip.checkpoints[0].revealed_at == first_revealed_at


def test_mark_checkpoints_revealed_only_returns_the_newly_revealed_ones_each_call(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(),
        checkpoints=[_checkpoint("Near", 2_000.0, checkpoint_number=1), _checkpoint("Far", 8_000.0, checkpoint_number=2)],
        gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
        checkpoint_reveal_radius_m=75.0,
    )

    revealed_at_1950m = trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=1_950.0)
    assert [c.name for c in revealed_at_1950m] == ["Near"]

    revealed_at_7950m = trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=7_950.0)
    assert [c.name for c in revealed_at_7950m] == ["Far"]

    still_revealed = trips.mark_checkpoints_revealed(db_session, trip, distance_walked_m=7_950.0)
    assert still_revealed == []


# --- checkpoint metadata claim/release/set ---

def test_claim_checkpoint_for_metadata_wins_once_and_blocks_a_second_concurrent_claim(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    checkpoint = TripCheckpoint(trip_id=trip.id, checkpoint_number=1, name="", lat=0.0, lng=0.0, distance_from_start_m=1000.0)
    db_session.add(checkpoint)
    db_session.commit()

    first_claim = trips.claim_checkpoint_for_metadata(db_session, checkpoint.id)
    second_claim = trips.claim_checkpoint_for_metadata(db_session, checkpoint.id)

    assert first_claim is True
    assert second_claim is False  # already "processing" from the first claim, and not stale yet
    db_session.refresh(checkpoint)
    assert checkpoint.metadata_status == "processing"


def test_claim_checkpoint_for_metadata_never_reclaims_an_already_ready_checkpoint(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="Chicago", lat=0.0, lng=0.0,
        distance_from_start_m=1000.0, metadata_status="ready",
    )
    db_session.add(checkpoint)
    db_session.commit()

    assert trips.claim_checkpoint_for_metadata(db_session, checkpoint.id) is False


def test_claim_checkpoint_for_metadata_reclaims_a_stale_processing_checkpoint(db_session, monkeypatch):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="", lat=0.0, lng=0.0, distance_from_start_m=1000.0,
        metadata_status="processing", metadata_requested_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db_session.add(checkpoint)
    db_session.commit()

    # A claim this old is presumed dead (its worker crashed, or the
    # process restarted mid-job) - safe to retry rather than stuck
    # "processing" forever.
    assert trips.claim_checkpoint_for_metadata(db_session, checkpoint.id) is True


def test_release_checkpoint_metadata_claim_puts_it_back_to_pending(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="", lat=0.0, lng=0.0, distance_from_start_m=1000.0,
        metadata_status="processing", metadata_requested_at=datetime.now(timezone.utc),
    )
    db_session.add(checkpoint)
    db_session.commit()

    trips.release_checkpoint_metadata_claim(db_session, checkpoint.id)

    db_session.refresh(checkpoint)
    assert checkpoint.metadata_status == "pending"
    assert checkpoint.metadata_requested_at is None
    # A later call can claim it again - the retry this release exists for.
    assert trips.claim_checkpoint_for_metadata(db_session, checkpoint.id) is True


def test_set_checkpoint_metadata_fills_in_name_and_description_and_flips_to_ready(db_session):
    user_id = _make_user(db_session)
    trip = trips.create_trip(
        session=db_session, user_id=user_id, from_place="A", to_place="B",
        route=_route(), checkpoints=[], gender=None, stride_length_m=None, stride_by_type={}, round_trip=False,
    )
    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="", lat=0.0, lng=0.0, distance_from_start_m=1000.0,
        metadata_status="processing",
    )
    db_session.add(checkpoint)
    db_session.commit()

    row = trips.set_checkpoint_metadata(db_session, checkpoint.id, "Chicago", "A real fun fact.")

    assert row.name == "Chicago"
    assert row.description == "A real fun fact."
    assert row.metadata_status == "ready"
