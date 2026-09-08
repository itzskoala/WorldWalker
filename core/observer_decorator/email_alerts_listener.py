#email_alerts_listener.py
# Not wired to a real mail sender - no SMTP/SendGrid/etc. credentials
# configured yet. Structurally a correct EventListener; fill in send()
# once you've picked a provider. Not subscribed anywhere until then.

from core.observer_decorator.event_listener import EventListener


class EmailAlertsListener(EventListener):
    def __init__(self, email: str):
        self.email = email

    def update(self, landmark: dict) -> None:
        raise NotImplementedError("No email sender configured yet - see file comment.")
