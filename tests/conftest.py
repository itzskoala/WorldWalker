# tests/conftest.py
# Shared fixture for tests that hit a real Postgres (not SQLite - UUID
# columns and CHECK constraints don't behave identically on SQLite, and
# tests/test_database_models.py specifically wants to prove the real
# engine enforces the Step 3 schema's constraints).
#
# Points at TEST_DATABASE_URL (a separate database from DATABASE_URL, see
# .env) so the test suite never touches real/dev data.

import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database.models import ActiveTrip, Base, GoogleHealthConnection, TripCheckpoint, User

load_dotenv()

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Each test runs inside its own outer transaction, rolled back at
    teardown - no test ever sees another test's rows, and nothing needs
    manual cleanup between tests.

    A test that triggers a real IntegrityError (e.g. flushing a duplicate
    provider_user_id) makes the ORM roll back its *own* transaction
    immediately - which would normally take our outer transaction down
    with it, since they're the same one. The SAVEPOINT (begin_nested)
    below gives the session its own inner transaction to roll back
    instead, restarted via the event listener every time one ends, so the
    outer transaction we control always survives until this fixture's own
    teardown rolls it back once."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, sess_transaction):
        if sess_transaction.nested and not sess_transaction._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


class _SameSessionEveryTime:
    """Stands in for database.session.SessionLocal in tests: every
    `with SameSessionEveryTime() as session:` call hands back this test's
    own db_session instead of opening a real new connection, and never
    closes it - db_session's own teardown (above) rolls the whole test's
    transaction back. core/facade.py and services/google_health/webhook.py
    both open their own SessionLocal() internally, so both get patched to
    this by the patched_session fixture below - every DB write in a test
    then lands in the one transaction that fixture controls."""

    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc_value, traceback):
        return False


@pytest.fixture
def patched_session(db_session, monkeypatch):
    same_session_every_time = _SameSessionEveryTime(db_session)
    monkeypatch.setattr("core.facade.SessionLocal", same_session_every_time)
    monkeypatch.setattr("services.google_health.webhook.SessionLocal", same_session_every_time)
    monkeypatch.setattr("app.SessionLocal", same_session_every_time)
    return db_session


@pytest.fixture
def user_id(patched_session) -> uuid.UUID:
    """A bare WorldWalker User row - enough to own an ActiveTrip, but with
    no Google Health connection. Use connected_user_id instead for
    anything that goes through auth.connections.get_active_user_id()
    (app.py's endpoints, the webhook)."""
    user = User()
    patched_session.add(user)
    patched_session.commit()
    return user.id


@pytest.fixture
def connected_user_id(patched_session) -> uuid.UUID:
    """A User with an active GoogleHealthConnection - what
    auth.connections.get_active_user_id() needs to resolve a real user for
    an incoming webhook notification or an app.py request."""
    user = User()
    patched_session.add(user)
    patched_session.flush()  # assigns user.id before the connection below references it

    connection = GoogleHealthConnection(
        user_id=user.id,
        provider_user_id=f"test-provider-{user.id}",
        status="active",
    )
    patched_session.add(connection)
    patched_session.commit()
    return user.id


@pytest.fixture
def seed_trip(patched_session):
    """Factory fixture: seed_trip(user_id, route) inserts one active_trips
    row directly - the DB-backed equivalent of the old
    facade._sessions[user_id] dict, for tests that want to drive
    TravelFacade.record_steps()/record_workout()/get_map_state() against a
    trip without going through the real geocoding/OSRM pipeline."""

    def _seed(user_id: uuid.UUID, route, to_place: str = "Chicago, Illinois") -> ActiveTrip:
        trip = ActiveTrip(
            user_id=user_id,
            status="active",
            from_place="Miami, Florida",
            to_place=to_place,
            start_lat=route.points[0].coords.lat,
            start_lng=route.points[0].coords.lng,
            end_lat=route.points[-1].coords.lat,
            end_lng=route.points[-1].coords.lng,
            route_geometry=[{"lat": p.coords.lat, "lng": p.coords.lng} for p in route.points],
            total_distance_m=route.total_distance,
            meters_walked=0.0,
            stride_length_m=None,
            gender=None,
            stride_by_type={},
            workout_intervals=[],
            milestones_notified=[],
            round_trip=False,
            started_at=datetime.now(timezone.utc),
        )
        patched_session.add(trip)
        patched_session.commit()
        return trip

    return _seed


@pytest.fixture
def seed_checkpoint(patched_session):
    """Factory fixture: seed_checkpoint(trip, name, distance_from_start_m)
    inserts one trip_checkpoints row, unhit, for a test to later walk past."""

    def _seed(trip: ActiveTrip, name: str, distance_from_start_m: float, checkpoint_number: int = 1) -> TripCheckpoint:
        checkpoint = TripCheckpoint(
            trip_id=trip.id,
            checkpoint_number=checkpoint_number,
            name=name,
            lat=trip.start_lat,
            lng=trip.start_lng,
            distance_from_start_m=distance_from_start_m,
            description="",
            hit_at=None,
        )
        patched_session.add(checkpoint)
        patched_session.commit()
        return checkpoint

    return _seed
