# tests/test_email_config.py
# notifications/email_config.py's find-or-create/read/delete, proven
# against real Postgres (see tests/test_database_models.py for why real
# Postgres, not SQLite) - and that smtp_username/smtp_password are
# actually encrypted at rest, the same way tests/test_token_encryption.py
# proves it for GoogleHealthConnection's tokens.

from sqlalchemy import text

from database.models import User
from notifications import email_config


def _new_user(session):
    user = User()
    session.add(user)
    session.flush()
    return user


def test_upsert_creates_a_new_config(db_session):
    user = _new_user(db_session)

    config = email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="walker@example.com", smtp_password="app-password",
    )

    assert config.user_id == user.id
    assert config.smtp_host == "smtp.gmail.com"
    assert config.smtp_port == 587
    assert config.smtp_username == "walker@example.com"
    assert config.smtp_password == "app-password"


def test_upsert_twice_updates_the_same_row_in_place(db_session):
    user = _new_user(db_session)
    first = email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="old@example.com", smtp_password="old-password",
    )

    second = email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.outlook.com", smtp_port=25,
        smtp_username="new@example.com", smtp_password="new-password",
    )

    assert second.id == first.id
    assert second.smtp_host == "smtp.outlook.com"
    assert second.smtp_username == "new@example.com"


def test_get_config_returns_none_when_user_has_not_set_one_up(db_session):
    user = _new_user(db_session)
    assert email_config.get_config(db_session, user.id) is None


def test_delete_config_removes_the_row_and_reports_whether_one_existed(db_session):
    user = _new_user(db_session)
    email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="walker@example.com", smtp_password="app-password",
    )

    assert email_config.delete_config(db_session, user.id) is True
    assert email_config.get_config(db_session, user.id) is None
    assert email_config.delete_config(db_session, user.id) is False


def test_smtp_username_and_password_round_trip_through_the_orm(db_session):
    user = _new_user(db_session)
    config = email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="a-real-looking-address@example.com", smtp_password="a-real-looking-app-password",
    )
    db_session.expire_all()  # force a real re-read from the DB, not the identity map

    reloaded = db_session.get(type(config), config.id)
    assert reloaded.smtp_username == "a-real-looking-address@example.com"
    assert reloaded.smtp_password == "a-real-looking-app-password"


def test_smtp_credentials_are_not_stored_in_plaintext(db_session):
    user = _new_user(db_session)
    config = email_config.upsert_config(
        db_session, user.id, smtp_host="smtp.gmail.com", smtp_port=587,
        smtp_username="super-secret-username@example.com", smtp_password="super-secret-app-password",
    )

    # Raw SQL, not the ORM - the ORM's TypeDecorator would silently
    # decrypt this for us, defeating the point of the test.
    raw_username, raw_password = db_session.execute(
        text("SELECT smtp_username, smtp_password FROM email_notification_configs WHERE id = :id"),
        {"id": config.id},
    ).one()

    assert raw_username != "super-secret-username@example.com"
    assert raw_password != "super-secret-app-password"
    assert "super-secret-app-password" not in raw_password
