# 2026-09-08 — Observer pattern: landmark, halfway, finished notifications

Building on the existing `core/observer_decorator/` scaffold from day3 to
add two new notification triggers (halfway, finished) alongside the
existing landmark one, ending in a rewrite matching
https://refactoring.guru/design-patterns/observer's structure exactly, per
explicit instruction. Separate topic from same day's
`2026-09-08-progress-calculator-position-interpolation.md` and
`2026-09-08-workout-pace-activity-tracking.md`.

## Prompt (verbatim)
> okay now let's wokrko on the notificatio logic, i'd like you to use a obseravor pattern.
>
> The notifications I'd like happene whenever a user hits a landmark
>
> Halfway mark to a users goal - 50%
>
> And a final you reached {destination} in {total_steps}! congrats!
>
> how are you going to scope this out/plan it first and tell me
>
> think carefully and KISS

## Answer
Read the existing `core/observer_decorator/` files - `EventListener` ABC,
`LandmarkEvents` (Subject, hardcoded to landmark-shaped dicts, one flat
subscriber list), `ConsoleAlertListener` (the only real listener; email/
phone stubbed). Identified the gap: halfway/finished don't fit the
landmark dict shape at all (finished needs `total_steps`, halfway needs
nothing landmark-specific), and `events.py` itself already flagged this
exact fork ("no eventType routing - YAGNI until a second event type
actually exists").

Proposed (no code yet, per "plan it first"): generalize the payload to a
pre-built `{"kind": ..., "message": str}` instead of a landmark-shaped
dict; detect halfway/finished with a small pure `milestones_just_crossed`
function in `progress_calculator.py`, guarded by an in-memory
`session["milestones_notified"]` set (not a DB table - these aren't real
places like landmarks, a two-line check is enough); extract a shared
`_notify_progress` helper so `record_steps`/`record_workout` don't
duplicate the landmark-check logic. Flagged (not decided silently)
renaming `LandmarkEvents` -> `JourneyEvents` for accuracy.

---

## Prompt (verbatim)
> How do you think we should impelment the observor pattern then? Right now let's forget about the emial + phone listener. The colosle logic should be changed/routed to the webapp. Obviously I want it to appear on the web app, a notificaoitn

## Answer
Named the real problem: a backend event fired from a webhook's background
task has no direct line to a browser - `print()` works today only because
nothing has to "arrive" anywhere. Compared WebSockets/SSE (real push, but
real infrastructure, and `app.py` has zero routes yet) vs. polling (a
plain GET the browser calls periodically - more work than `print()`, but
the same shape the map will need anyway once it exists, so not wasted).
Proposed: a `WebAppAlertListener` (drop-in `EventListener` replacing
`ConsoleAlertListener`) that appends to a small in-memory
`data/notifications_store.py` (pop-and-clear "mailbox," not a persisted
notified-flag log like `route_landmarks` - notifications are transient,
not a historical record); one new `GET /api/notifications` endpoint in
`app.py` (its first real route) to drain it. Flagged rather than assuming:
"routed to the webapp" reads as *replacing* console, though the pattern
makes running both trivial if server-side visibility during dev is still
wanted.

---

## Prompt (verbatim)
> Impleelment it as stated in this website; https://refactoring.guru/design-patterns/observer. Forget about the notifications to console + web app logic. Set up the design pattern. For now we'll report to termianl

## Answer
Scope cut back to just the pattern itself, terminal-only. Fetched the
actual page rather than relying on memory of it, to match its structure
precisely: **Publisher** infrastructure is called `EventManager`
(subscribe/unsubscribe/notify keyed by **event type**, a
`Map<eventType, List<listener>>` - not one flat list), and the concrete
business object (their `Editor` example) owns an `events: EventManager`
field, calling `events.notify(eventType, data)` when its own state
changes. Recognized this fits our 3 event kinds (landmark/halfway/
finished) more naturally than the "kind" field inside a payload proposed
last turn - the EventManager's own eventType keying handles that
distinction natively, so it was dropped in favor of matching the
reference structure.

## What changed
- **`core/observer_decorator/event_manager.py`** (new, replaces
  `events.py`): `EventManager` - generic, reusable, doesn't know what a
  "landmark" is. `subscribe(event_type, listener)`,
  `unsubscribe(event_type, listener)`, `notify(event_type, data)` calling
  `listener.update(data)` for every listener registered under that type.
- **`core/observer_decorator/events.py`** deleted.
- **`core/observer_decorator/event_listener.py`**: `update()` generalized
  from `update(self, landmark: dict)` to `update(self, data)` - the
  Subscriber interface no longer assumes landmark-shaped data.
- **`core/observer_decorator/console_alert_listener.py`**: `update()` now
  just `print(message)` - formatting moved to the call site (`facade.py`),
  so this listener doesn't need to know how to format 3 different event
  kinds.
- **`travel_logic/progress_calculator.py`**: added
  `milestones_just_crossed(percent_complete, already_notified) -> set` -
  pure, `>=` not `==` so a sync that jumps straight past a threshold still
  fires it; caller owns updating `already_notified`.
- **`core/facade.py`**:
  - `TravelFacade` now owns `self.events = EventManager()` (public field,
    matching the reference's `Editor.events` - the "Publisher" role),
    subscribing one `ConsoleAlertListener` instance to all three event
    types (`"landmark"`, `"halfway"`, `"finished"`).
  - Session gains `destination` (the `to_place` string, for the finished
    message) and `milestones_notified` (a set, guards against re-firing).
  - New shared `_notify_progress(user_id, session, progress)` - replaces
    the landmark-check block duplicated in `record_steps`/`record_workout`,
    and adds the halfway/finished check on top of it. Messages:
    `"🏁 Landmark reached: {name} ({percent}% of the way there!)"`,
    `"🎉 Halfway to your goal - 50%!"`,
    `"🏆 You reached {destination} in {total_steps} steps! Congrats!"`.
- **Tests**: new `tests/test_event_manager.py` (6 tests) for the Publisher
  infrastructure itself (per-event-type routing, duplicate-subscribe,
  unsubscribe, no-subscribers-is-fine). `tests/test_progress_calculator.py`
  gained 4 tests for `milestones_just_crossed`. `tests/test_facade.py`
  gained 3 tests wiring an observer test double
  (`_RecordingListener`) to confirm the landmark/halfway/finished messages
  actually fire with the right content, exactly once each.

## Test result
`pytest -q` → 74 passed (61 -> 74). Confirmed no leftover references to
`LandmarkEvents`/`core.observer_decorator.events` anywhere in the repo.

## Open items / not done (explicitly deferred by the user this pass)
- Email/phone listeners untouched, not wired - deferred.
- No web-app delivery (no notification store, no API endpoint) - deferred
  back to terminal-only per this turn's explicit instruction; the plan
  from the previous turn (`WebAppAlertListener` + `data/notifications_store.py`
  + `GET /api/notifications`) is still there if picked back up later.
