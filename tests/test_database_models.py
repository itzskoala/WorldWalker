# tests/test_database_models.py
# Behavioral proof of the Step 3 schema design - the constraints we agreed
# on (one connection per user, one row per real Google account, a status
# that can't be garbage) are actually enforced by the database, not just
# documented in a comment. Runs against real Postgres (see conftest.py).

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from database.models import ActiveTrip, GoogleHealthConnection, TripCheckpoint, User


def _make_user_and_connection(db_session, provider_user_id="google-user-1"):
    user = User()
    db_session.add(user)
    db_session.flush()  # assigns user.id without committing

    connection = GoogleHealthConnection(
        user_id=user.id,
        provider_user_id=provider_user_id,
        access_token="at",
        refresh_token="rt",
    )
    db_session.add(connection)
    db_session.flush()
    return user, connection


def test_creating_a_user_works(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()

    assert user.id is not None
    assert user.created_at is not None


def test_creating_a_connection_tied_to_a_user_works(db_session):
    user, connection = _make_user_and_connection(db_session)

    assert connection.user_id == user.id
    assert connection.status == "active"  # default, not passed explicitly


def test_duplicate_provider_user_id_is_rejected(db_session):
    """The same real Google account can't back two different WorldWalker users."""
    _make_user_and_connection(db_session, provider_user_id="same-google-account")

    other_user = User()
    db_session.add(other_user)
    db_session.flush()

    dupe = GoogleHealthConnection(
        user_id=other_user.id,
        provider_user_id="same-google-account",
        access_token="at2",
        refresh_token="rt2",
    )
    db_session.add(dupe)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_a_user_cannot_have_two_connections(db_session):
    user, _ = _make_user_and_connection(db_session, provider_user_id="first-account")

    second = GoogleHealthConnection(
        user_id=user.id,
        provider_user_id="second-account",
        access_token="at2",
        refresh_token="rt2",
    )
    db_session.add(second)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_a_user_cascades_to_their_connection(db_session):
    user, connection = _make_user_and_connection(db_session)
    connection_id = connection.id

    db_session.delete(user)
    db_session.flush()

    assert db_session.get(GoogleHealthConnection, connection_id) is None


def test_status_only_accepts_active_or_disconnected(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()

    bad = GoogleHealthConnection(
        user_id=user.id,
        provider_user_id="whatever",
        status="not-a-real-status",
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.flush()


# --- ActiveTrip / TripCheckpoint (database/trips.py's schema) ---

def _make_trip(db_session, user_id, status="active", from_place="Miami, Florida", to_place="Chicago, Illinois"):
    trip = ActiveTrip(
        user_id=user_id,
        status=status,
        from_place=from_place,
        to_place=to_place,
        start_lat=25.7, start_lng=-80.2,
        end_lat=41.8, end_lng=-87.6,
        route_geometry=[{"lat": 25.7, "lng": -80.2}, {"lat": 41.8, "lng": -87.6}],
        total_distance_m=160934.4,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(trip)
    db_session.flush()
    return trip


def test_creating_a_trip_works_with_sensible_defaults(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()

    trip = _make_trip(db_session, user.id)

    assert trip.id is not None
    assert trip.status == "active"
    assert trip.meters_walked == 0.0
    assert trip.round_trip is False
    assert trip.stride_by_type == {}
    assert trip.workout_intervals == []
    assert trip.milestones_notified == []


def test_trip_status_only_accepts_active_paused_completed_or_abandoned(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()

    _make_trip(db_session, user.id, status="paused")

    with pytest.raises(IntegrityError):
        _make_trip(db_session, user.id, status="wandering-off")


def test_a_user_can_have_two_active_trips_at_once(db_session):
    """No uniqueness constraint on (user_id, status='active') any more - a
    user can walk toward several destinations at the same time. See
    database/trips.py's module docstring."""
    user = User()
    db_session.add(user)
    db_session.flush()
    _make_trip(db_session, user.id)
    _make_trip(db_session, user.id)

    assert db_session.query(ActiveTrip).filter_by(user_id=user.id, status="active").count() == 2


def test_deleting_a_user_cascades_to_their_trips(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()
    trip = _make_trip(db_session, user.id)
    trip_id = trip.id

    db_session.delete(user)
    db_session.flush()

    assert db_session.get(ActiveTrip, trip_id) is None


def test_deleting_a_trip_cascades_to_its_checkpoints(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()
    trip = _make_trip(db_session, user.id)

    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="TownA",
        lat=30.0, lng=-81.0, distance_from_start_m=10_000.0,
    )
    db_session.add(checkpoint)
    db_session.flush()
    checkpoint_id = checkpoint.id

    db_session.delete(trip)
    db_session.flush()

    assert db_session.get(TripCheckpoint, checkpoint_id) is None


def test_checkpoint_hit_at_defaults_to_unhit(db_session):
    user = User()
    db_session.add(user)
    db_session.flush()
    trip = _make_trip(db_session, user.id)

    checkpoint = TripCheckpoint(
        trip_id=trip.id, checkpoint_number=1, name="TownA",
        lat=30.0, lng=-81.0, distance_from_start_m=10_000.0,
    )
    db_session.add(checkpoint)
    db_session.flush()

    assert checkpoint.hit_at is None
    assert trip.checkpoints == [checkpoint]
