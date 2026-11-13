#event_manager.py

from collections import defaultdict


class EventManager:
    def __init__(self):
        self._listeners = defaultdict(list)

    def subscribe(self, event_type: str, listener) -> None:
        if listener not in self._listeners[event_type]:
            self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: str, listener) -> None:
        if listener in self._listeners[event_type]:
            self._listeners[event_type].remove(listener)

    def notify(self, event_type: str, data) -> None:
        print(f"{event_type}: {data}")
        for listener in self._listeners[event_type]:
            listener.update(data)
