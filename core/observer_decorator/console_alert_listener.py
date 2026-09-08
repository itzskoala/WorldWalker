#console_alert_listener.py
# Concrete Subscriber (refactoring.guru's LoggingListener role): reports
# every event it's subscribed to straight to the terminal. No email/SMTP
# or SMS/Twilio credentials configured yet (see email_alerts_listener.py /
# phone_alert_listener.py), so this is the one listener wired up today.

from core.observer_decorator.event_listener import EventListener


class ConsoleAlertListener(EventListener):
    def update(self, message: str) -> None:
        print(message)
