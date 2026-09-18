#event_listener.py
# Subscriber interface - https://refactoring.guru/design-patterns/observer
from abc import ABC, abstractmethod


class EventListener(ABC):
    @abstractmethod
    def update(self, data) -> None:
        """Called by EventManager.notify() for every event type this
        listener is subscribed to. `data` is whatever the publisher passed
        to notify() - for TravelFacade's events today, a ready-to-display
        message string."""
