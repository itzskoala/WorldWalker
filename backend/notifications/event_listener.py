#event_listener.py

from abc import ABC, abstractmethod


class EventListener(ABC):
    @abstractmethod
    def update(self, data) -> None:
        pass
