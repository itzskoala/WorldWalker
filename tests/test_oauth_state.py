# tests/test_oauth_state.py
# auth/oauth_state.py's DB-backed OAuth CSRF state store - proven against
# real Postgres (see tests/test_connections.py's own comment on why: UUID
# and CHECK-constraint/FK behavior doesn't match SQLite). Replaces the old
# in-process dict (tests/test_google_health_auth.py used to cover this) so
# a state survives across workers/processes, not just one uvicorn worker.

from datetime import datetime, timedelta, timezone

import pytest

from auth import oauth_state
from database.models import OAuthState, User


def _new_user(session) -> User:
    user = User()
    session.add(user)
    session.flush()
    return user


def test_issue_state_persists_a_row_in_the_database(db_session):
    user = _new_user(db_session)

    state = oauth_state.issue_state(db_session, user.id)

    row = db_session.get(OAuthState, state)
    assert row is not None
    assert row.user_id == user.id


def test_issue_state_sets_an_expiry_in_the_future(db_session):
    user = _new_user(db_session)

    state = oauth_state.issue_state(db_session, user.id)

    row = db_session.get(OAuthState, state)
    assert row.expires_at > datetime.now(timezone.utc)
    assert row.expires_at <= datetime.now(timezone.utc) + oauth_state.STATE_TTL


def test_issue_state_gives_each_call_a_different_token(db_session):
    user = _new_user(db_session)

    state1 = oauth_state.issue_state(db_session, user.id)
    state2 = oauth_state.issue_state(db_session, user.id)

    assert state1 != state2


def test_consume_state_returns_the_user_id_it_was_issued_for(db_session):
    user = _new_user(db_session)
    state = oauth_state.issue_state(db_session, user.id)

    assert oauth_state.consume_state(db_session, state) == user.id


def test_consume_state_is_single_use(db_session):
    user = _new_user(db_session)
    state = oauth_state.issue_state(db_session, user.id)

    first = oauth_state.consume_state(db_session, state)
    second = oauth_state.consume_state(db_session, state)

    assert first == user.id
    assert second is None


def test_consume_state_deletes_the_row_even_on_first_use(db_session):
    user = _new_user(db_session)
    state = oauth_state.issue_state(db_session, user.id)

    oauth_state.consume_state(db_session, state)

    assert db_session.get(OAuthState, state) is None


def test_consume_state_rejects_an_unknown_state(db_session):
    assert oauth_state.consume_state(db_session, "never-issued") is None


def test_consume_state_rejects_a_missing_or_empty_state(db_session):
    assert oauth_state.consume_state(db_session, "") is None


def test_consume_state_rejects_an_expired_state(db_session):
    user = _new_user(db_session)
    db_session.add(OAuthState(
        state="stale-state", user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    db_session.commit()

    assert oauth_state.consume_state(db_session, "stale-state") is None


def test_consume_state_removes_an_expired_state_too(db_session):
    # Single-use applies even to a hit that gets rejected for being
    # expired - a leaked/logged old state can't be replayed once it's
    # expired either.
    user = _new_user(db_session)
    db_session.add(OAuthState(
        state="stale-state", user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    ))
    db_session.commit()

    oauth_state.consume_state(db_session, "stale-state")

    assert db_session.get(OAuthState, "stale-state") is None


def test_multiple_users_get_independent_states(db_session):
    user_a = _new_user(db_session)
    user_b = _new_user(db_session)

    state_a = oauth_state.issue_state(db_session, user_a.id)
    state_b = oauth_state.issue_state(db_session, user_b.id)

    assert oauth_state.consume_state(db_session, state_a) == user_a.id
    assert oauth_state.consume_state(db_session, state_b) == user_b.id


def test_issuing_a_new_state_cleans_up_expired_ones(db_session):
    user = _new_user(db_session)
    db_session.add(OAuthState(
        state="long-expired", user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    db_session.commit()

    oauth_state.issue_state(db_session, user.id)

    assert db_session.get(OAuthState, "long-expired") is None


def test_deleting_a_user_cascades_to_their_pending_states(db_session):
    user = _new_user(db_session)
    state = oauth_state.issue_state(db_session, user.id)

    db_session.delete(user)
    db_session.commit()

    assert db_session.get(OAuthState, state) is None
