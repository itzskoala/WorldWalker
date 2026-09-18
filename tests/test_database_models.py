# tests/test_database_models.py
# Behavioral proof of the Step 3 schema design - the constraints we agreed
# on (one connection per user, one row per real Google account, a status
# that can't be garbage) are actually enforced by the database, not just
# documented in a comment. Runs against real Postgres (see conftest.py).

import pytest
from sqlalchemy.exc import IntegrityError

from database.models import GoogleHealthConnection, User


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
