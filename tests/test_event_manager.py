# tests/test_event_manager.py
# Publisher infrastructure (Observer pattern -
# https://refactoring.guru/design-patterns/observer): subscribe/unsubscribe
# per event type, notify() only reaches listeners subscribed to that type.

from core.observer_decorator.event_manager import EventManager
from core.observer_decorator.event_listener import EventListener


class _RecordingListener(EventListener):
    def __init__(self):
        self.received = []

    def update(self, data) -> None:
        self.received.append(data)


def test_notify_calls_update_on_subscribed_listeners():
    events = EventManager()
    listener = _RecordingListener()
    events.subscribe("landmark", listener)

    events.notify("landmark", "hit a landmark")

    assert listener.received == ["hit a landmark"]


def test_notify_only_reaches_listeners_for_that_event_type():
    events = EventManager()
    landmark_listener = _RecordingListener()
    finished_listener = _RecordingListener()
    events.subscribe("landmark", landmark_listener)
    events.subscribe("finished", finished_listener)

    events.notify("landmark", "hit a landmark")

    assert landmark_listener.received == ["hit a landmark"]
    assert finished_listener.received == []


def test_one_listener_can_subscribe_to_multiple_event_types():
    events = EventManager()
    listener = _RecordingListener()
    events.subscribe("halfway", listener)
    events.subscribe("finished", listener)

    events.notify("halfway", "halfway there")
    events.notify("finished", "done!")

    assert listener.received == ["halfway there", "done!"]


def test_subscribing_the_same_listener_twice_does_not_duplicate_calls():
    events = EventManager()
    listener = _RecordingListener()
    events.subscribe("landmark", listener)
    events.subscribe("landmark", listener)

    events.notify("landmark", "hit a landmark")

    assert listener.received == ["hit a landmark"]


def test_unsubscribe_stops_future_notifications():
    events = EventManager()
    listener = _RecordingListener()
    events.subscribe("landmark", listener)
    events.unsubscribe("landmark", listener)

    events.notify("landmark", "hit a landmark")

    assert listener.received == []


def test_notify_with_no_subscribers_does_not_raise():
    events = EventManager()
    events.notify("landmark", "nobody is listening")
