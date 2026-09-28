#email_alerts_listener.py
# Concrete Subscriber (refactoring.guru's role): on a checkpoint_reached
# event, sends an email through the REACHED USER'S OWN SMTP account
# (notifications/email_config.py) - WorldWalker holds no shared sender
# account anywhere. One listener instance serves every user (subscribed
# once in core/facade.py), so the config is looked up fresh per event
# rather than passed in at construction.

from redmail import EmailSender

from core.observer_decorator.event_listener import EventListener
from core.observer_decorator.events import CheckpointReachedEvent
from database.session import SessionLocal
from notifications import email_config


class EmailAlertsListener(EventListener):
    def update(self, event: CheckpointReachedEvent) -> None:
        # Everything below is best-effort, same as generate_description()'s
        # AI-call fallback - the DB lookup included. A dead SMTP account,
        # a network blip, or a transient DB error (Neon closing an idle
        # connection, say - see database/session.py's pool_pre_ping) must
        # never break the steps/workout sync this event fired from.

        # [TEMP DEBUG] remove before deploying - see notification-flow testing
        print(
            f"📧 [TEMP DEBUG] EmailAlertsListener received event: user={event.user_name} "
            f"(id={event.user_id}) checkpoint=#{event.checkpoint_number} '{event.checkpoint_name}'"
        )
        try:
            with SessionLocal() as session:
                config = email_config.get_config(session, event.user_id)

            if config is None:
                # [TEMP DEBUG] remove before deploying
                print(f"📧 [TEMP DEBUG] No email config for user {event.user_id} - nothing to send, skipping")
                return  # this user hasn't set up an email account to notify - nothing to send

            # [TEMP DEBUG] remove before deploying - host/port only, never username/password
            print(f"🔑 [TEMP DEBUG] Email credentials retrieved for user {event.user_id} (host={config.smtp_host}:{config.smtp_port})")

            sender = EmailSender(
                host=config.smtp_host,
                port=config.smtp_port,
                username=config.smtp_username,
                password=config.smtp_password,
            )
            subject = f"You've reached checkpoint #{event.checkpoint_number}: {event.checkpoint_name}!"
            body_text = (
                f"{event.user_name} has reached {event.checkpoint_name}! "
                f"You're at checkpoint #{event.checkpoint_number}!\n\n"
                f"{event.description}"
            )

            # [TEMP DEBUG] remove before deploying - never logs username/password
            print(f"📤 [TEMP DEBUG] Red Mail attempting send: host={config.smtp_host}:{config.smtp_port} subject={subject!r}")
            sender.send(subject=subject, receivers=[config.smtp_username], text=body_text)
            # [TEMP DEBUG] remove before deploying
            print(f"✅ [TEMP DEBUG] Email sent successfully for user {event.user_id}, checkpoint #{event.checkpoint_number}")
        except Exception as e:
            # [TEMP DEBUG] the str(e) below is temporary, for local testing
            # visibility only - PERMANENT/production code must log only
            # type(e).__name__ (see the line below this one), never str(e):
            # an SMTP library's (or DB driver's) error text can echo back
            # server responses or query parameters we don't control and
            # shouldn't assume are safe to print. Remove the str(e) line
            # before deploying.
            print(f"❌ [TEMP DEBUG] Checkpoint email failed for user {event.user_id}: {type(e).__name__}: {e}")
            print(f"✉️  Checkpoint email failed for user {event.user_id}: {type(e).__name__}")
