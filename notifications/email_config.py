# notifications/email_config.py
# Find-or-create/read/delete for a user's own EmailNotificationConfig row
# - same shape as auth/connections.py's GoogleHealthConnection handling,
# one row per user, upsert-in-place on reconnect. No shared WorldWalker
# sender account exists anywhere in this module (or anywhere else) -
# every config here is one user's own SMTP account, read back only to
# send that same user's own checkpoint notifications (see
# core/observer_decorator/email_alerts_listener.py).

from sqlalchemy.orm import Session

from database.models import EmailNotificationConfig


def upsert_config(
    session: Session, user_id, smtp_host: str, smtp_port: int, smtp_username: str, smtp_password: str
) -> EmailNotificationConfig:
    config = session.query(EmailNotificationConfig).filter_by(user_id=user_id).one_or_none()
    if config is None:
        config = EmailNotificationConfig(user_id=user_id)
        session.add(config)

    config.smtp_host = smtp_host
    config.smtp_port = smtp_port
    config.smtp_username = smtp_username
    config.smtp_password = smtp_password

    session.commit()
    return config


def get_config(session: Session, user_id) -> EmailNotificationConfig | None:
    """This user's own config, or None if they haven't set one up - never
    an error, since not every user opts into email notifications."""
    return session.query(EmailNotificationConfig).filter_by(user_id=user_id).one_or_none()


def delete_config(session: Session, user_id) -> bool:
    config = get_config(session, user_id)
    if config is None:
        return False
    session.delete(config)
    session.commit()
    return True
