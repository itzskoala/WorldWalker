#console_alert_listener.py
# Concrete Subscriber (refactoring.guru's LoggingListener role): reports
# every event it's subscribed to straight to the terminal.

from core.observer_decorator.event_listener import EventListener


class ConsoleAlertListener(EventListener):
    def update(self, message: str) -> None:
        print(message)
