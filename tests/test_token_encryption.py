# tests/test_token_encryption.py
# Proves access_token/refresh_token are actually encrypted at rest, not
# just "never printed anywhere" - the plaintext-check test below reads the
# raw column with a plain SQL SELECT, bypassing the ORM's decrypting
# TypeDecorator entirely, so it can't be fooled by the ORM quietly
# decrypting on the way back out.

from cryptography.fernet import Fernet
from sqlalchemy import text

from database.models import GoogleHealthConnection, User


def _make_connection(db_session, provider_user_id, access_token, refresh_token):
    user = User()
    db_session.add(user)
    db_session.flush()

    connection = GoogleHealthConnection(
        user_id=user.id,
        provider_user_id=provider_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    db_session.add(connection)
    db_session.flush()
    return connection


def test_stored_token_round_trips_through_the_orm(db_session):
    connection = _make_connection(
        db_session, "round-trip-user", "a-real-looking-access-token", "a-real-looking-refresh-token"
    )
    db_session.expire_all()  # force a real re-read from the DB, not the identity map

    reloaded = db_session.get(GoogleHealthConnection, connection.id)
    assert reloaded.access_token == "a-real-looking-access-token"
    assert reloaded.refresh_token == "a-real-looking-refresh-token"


def test_token_is_not_stored_in_plaintext(db_session):
    connection = _make_connection(
        db_session, "plaintext-check-user", "super-secret-access-token", "super-secret-refresh-token"
    )

    # Raw SQL, not the ORM - the ORM's TypeDecorator would silently
    # decrypt this for us, defeating the point of the test.
    raw_access_token = db_session.execute(
        text("SELECT access_token FROM google_health_connections WHERE id = :id"),
        {"id": connection.id},
    ).scalar_one()

    assert raw_access_token != "super-secret-access-token"
    assert "super-secret-access-token" not in raw_access_token


def test_null_tokens_stay_null(db_session):
    connection = _make_connection(db_session, "null-token-user", None, None)
    db_session.expire_all()

    reloaded = db_session.get(GoogleHealthConnection, connection.id)
    assert reloaded.access_token is None
    assert reloaded.refresh_token is None


def test_token_undecryptable_under_current_key_reads_back_as_none(db_session):
    """Reproduces the production incident directly: a row whose
    access_token/refresh_token were encrypted under a DIFFERENT
    TOKEN_ENCRYPTION_KEY than the one this process is running with (e.g.
    a previous deployment's key) must read back as None, not raise -
    before this fix, loading this exact row crashed
    /auth/google/status with cryptography.exceptions.InvalidSignature,
    deep inside the ORM's row materialization."""
    connection = _make_connection(db_session, "stale-key-user", "placeholder", "placeholder")

    other_key_ciphertext = Fernet(Fernet.generate_key()).encrypt(b"some-access-token").decode()
    db_session.execute(
        text("UPDATE google_health_connections SET access_token = :ciphertext WHERE id = :id"),
        {"ciphertext": other_key_ciphertext, "id": connection.id},
    )
    db_session.commit()
    db_session.expire_all()

    reloaded = db_session.get(GoogleHealthConnection, connection.id)
    assert reloaded.access_token is None
