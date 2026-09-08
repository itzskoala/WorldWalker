#phone_alert_listener.py
# Not wired to a real SMS sender - no Twilio/etc. credentials configured
# yet. Structurally a correct EventListener; fill in send() once you've
# picked a provider. Not subscribed anywhere until then.

from core.observer_decorator.event_listener import EventListener


class PhoneAlertListener(EventListener):
    def __init__(self, phone_number: str):
        self.phone_number = phone_number

    def update(self, landmark: dict) -> None:
        raise NotImplementedError("No SMS sender configured yet - see file comment.")
