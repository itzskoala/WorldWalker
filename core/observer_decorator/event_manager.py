#event_manager.py
# Publisher infrastructure - Observer pattern, structured exactly as
# https://refactoring.guru/design-patterns/observer lays it out: listeners
# subscribe per event type (not one flat list for everything), and
# notify(event_type, data) only calls the listeners subscribed to the
# event type that actually happened.
#
# This class is generic/reusable on its own - it doesn't know what a
# "landmark" or "steps" is. The concrete publisher (TravelFacade) owns one
# of these (see core/facade.py's self.events) and calls notify() whenever
# something worth telling subscribers about happens - same relationship
# as the site's Editor/EventManager example.

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
        for listener in self._listeners[event_type]:
            listener.update(data)
