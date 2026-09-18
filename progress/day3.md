# Day 3 — Travel logic: location handling, distance, landmarks, notifications

Full blow-by-blow (every prompt + reasoning) is in `docs/prompt_log/`:
`2026-09-03-travel-logic-location-handling.md`. This is the condensed
version for picking work back up.

## TL;DR
Built the actual "walk the world" feature end to end: forward-geocode a
from/to place, get a real walking route, place real cities as landmarks
along it, and turn incoming Fitbit step counts into a live position, an
ETA, and a fired notification when a landmark is crossed. Wired the
Fitbit webhook into it. `app.py` (the website itself) is still the one
missing piece — everything below is reachable today via a Python REPL or
the webhook, not yet a web form.

## What we did today
1. **New `travel_logic/` package** — pure logic, no I/O, ABCs so the
   provider can swap later:
   - `coordinates.py` — `Coordinates(lat, lng)`.
   - `geocoder.py` — `Geocoder` ABC + `NominatimGeocoder` (forward geocode,
     reverse geocode, and `reverse_geocode_city` — city-tier only, used to
     filter route samples down to real cities).
   - `route_service.py` — `RouteService` ABC + `OSRMWalkingRouteService`;
     `Route`/`RoutePoint` carry cumulative mileage per point (haversine).
   - `progress_calculator.py` — `steps_to_miles` (stride resolution: real
     per-user value > gender average > unisex default), `locate_on_route`,
     `average_daily_miles`/`estimate_days_remaining` (empirical pace —
     `None` until the user has actually walked, no guessed fallback).
   - `checkpoints.py` — finds "important" landmarks: samples the route at
     a density that scales with route length (`SPACING_MILES=20`, capped
     `MAX_SAMPLES=60`; a route too short gets 0 samples/API calls), keeps
     only city-tier reverse-geocode hits, dedupes consecutive repeats.
2. **Chose OSRM + Nominatim** over Google Maps Platform (free, no API
   key/billing, sufficient for MVP) — user's call after a tradeoff
   question.
3. **`core/facade.py`** — `TravelFacade`: `start_journey`, `record_steps`,
   `get_map_state`. Single shared `travel_facade` instance +
   `DEFAULT_USER_ID = "me"` (single-user MVP, no auth system yet).
4. **Two SQLite DBs** (both in `data/total_distance.db` — one file, two
   tables, no server/connection string):
   - `data/total_distance_db.py` — `TotalDistanceDB`, `total_distance_log`
     table: one row per Fitbit sync (steps, distance walked/remaining,
     percent, timestamp). `total_steps()`/`today_steps()` are `SUM()`
     queries over it, not separately-maintained counters.
   - `data/landmarks_db.py` — `LandmarksDB`, `route_landmarks` table: one
     row per landmark (name, lat/lng, mile-mark, `notified` flag) — not
     `landmark_1`/`landmark_2`/... columns. "Distance to a landmark" is
     never stored — it's `miles_from_start - miles_walked`, computed live.
5. **`data/intake.py`** — `IntakeRequest` (from_place, to_place, optional
   gender/stride_length_m) + `start_journey_from_intake()`. This is what
   a future `app.py` form handler will call.
6. **Wired the Fitbit webhook** — `fitbit_service.py`'s `"steps"` case now
   calls `travel_facade.record_steps(DEFAULT_USER_ID, obj.count)`, guarded
   by a clean `ValueError`-catch (no active journey yet -> log one line,
   not a traceback).
7. **Fixed `core/observer-decorator/` → `core/observer_decorator/`** — the
   hyphen made it un-importable as a Python package, a real blocker.
   Fixed the actual bugs (`self.observers` typo, malformed
   `EventListener.update`), added `ConsoleAlertListener` (the one real,
   working listener — no email/SMS provider configured yet), and wired
   `record_steps` to call `LandmarkEvents.notify()` for every newly-passed
   landmark.
8. Deleted `core/travel_engine.py` (invalid syntax, never ran — superseded
   by `travel_logic/`) and `core/observer_decorator/observer.py` (empty).

## Decisions made along the way (flagged to the user, not silent)
- **Rejected handing route/distance math to an LLM** — needs to be
  deterministic and accurate; AI is a legitimate fit one layer up (turning
  a checkpoint into flavor text) but that's out of scope for this pass.
- **Stride length**: real per-user value (e.g. from Fitbit/Google Health)
  wins if present, else a gender average, else a unisex default. Confirmed
  Google Health *does* let a user calibrate this (Profile > Activity >
  Stride Length in the app) but it's not confirmed exposed by the v4 REST
  API's documented `getProfile` fields yet — needs a live probe.
- **User caught a real bug**: an early ETA fallback assumed 6000
  steps/day before any real walking happened. Fixed — `None` ("unknown")
  until the user has actually walked; no more guessed pace.
- **Postgres → SQLite**: user's call — single file, no server, no
  connection string, plenty for one user's history.
- **"Important" landmarks** = Nominatim's own city/town/village tier
  classification (a real, free signal), not an invented importance score.
- **Rows, not numbered columns**, for both DBs — a route's landmark count
  varies; numbered columns don't survive that.
- **Sample count scales with route length**, not a fixed number — a
  10-minute walk shouldn't cost 30 wasted reverse-geocode calls.

## Files created
- `travel_logic/__init__.py`, `coordinates.py`, `geocoder.py`,
  `route_service.py`, `progress_calculator.py`, `checkpoints.py`
- `data/total_distance_db.py`, `data/landmarks_db.py`
- `core/observer_decorator/__init__.py`, `console_alert_listener.py`
- `docs/prompt_log/2026-09-03-travel-logic-location-handling.md`

## Files modified
- `core/facade.py` (built out from empty stub)
- `data/intake.py` (built out from empty stub)
- `services/fitbit_pydantic_schema.py` (`UserData.stride_length_m` added)
- `services/fitbit_service.py` (webhook wired to `record_steps`)
- `core/observer_decorator/event_listener.py`, `events.py`,
  `email_alerts_listener.py`, `phone_alert_listener.py` (rewritten;
  folder renamed from `observer-decorator`)
- `.gitignore` (`*.db`)
- `requirements.txt` (net no change — `psycopg2-binary` was added then
  removed when Postgres became SQLite)

## Files deleted
- `core/travel_engine.py` (invalid syntax, never ran)
- `core/observer_decorator/observer.py` (empty)

## Example smoke test + output
No live-network automated tests yet (flagged below) — verified with real
runs instead. This one exercises the full chain: steps in -> position
update -> DB write -> landmark crossed -> notification fired:

```python
from core.facade import TravelFacade
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint
from travel_logic.checkpoints import Checkpoint
import datetime

f = TravelFacade()
route = Route(
    points=[RoutePoint(Coordinates(25.7, -80.2), 0.0), RoutePoint(Coordinates(41.8, -87.6), 100.0)],
    total_miles=100.0,
)
f._sessions["me"] = {
    "route": route, "miles_walked": 0.0, "gender": None, "stride_length_m": None,
    "started_at": datetime.datetime.now(datetime.timezone.utc),
}
f._landmarks_db.save_landmarks("me", [
    Checkpoint(name="TownA", coords=Coordinates(30, -81), miles_from_start=10.0, percent=10.0),
])

state = f.record_steps("me", 30000)
```

Output:
```
🏁 Landmark reached: TownA (10.0% of the way there!)
```
```python
>>> round(state["miles_walked"], 2)
14.2
>>> [l["name"] for l in state["newly_passed_landmarks"]]
['TownA']
```

Plus, unchanged: `venv/bin/python3 -m pytest -q` → `24 passed` (existing
suite, untouched by today's work — see Open items).

## How to run it
See `docs/prompt_log/2026-09-03-travel-logic-location-handling.md`'s last
entry for the full runbook. Short version:

**Quick local check** (no server, hits real Nominatim + OSRM):
```bash
cd /Users/srikotala/Documents/WorldWalker
venv/bin/python3
>>> from core.facade import travel_facade
>>> state = travel_facade.start_journey("me", "Miami, Florida", "Chicago, Illinois", gender="male")
>>> state = travel_facade.record_steps("me", 5000)
```
Inspect: `sqlite3 data/total_distance.db "select * from total_distance_log;"`
and `"select * from route_landmarks;"`.

**Full live pipeline**: same 3-terminal uvicorn/ngrok/register-subscription
dance as day2.md, but seed a journey via the REPL above first — the
webhook's `DEFAULT_USER_ID="me"` needs a session to exist before real
step data has anywhere to go.

## Open items / next session
- **`app.py` is still empty** — the actual website/form. This is the big
  remaining piece: a route calling `start_journey_from_intake`, a route
  exposing `travel_facade.get_map_state` for the frontend map, and the
  map UI itself (`services/maps_service.py` is also still empty).
- **No tests for any of today's work** — `travel_logic/`, both DBs, and
  the observer/notification wiring were only verified with manual smoke
  tests (real runs, shown above), because most of it hits real network
  APIs (Nominatim/OSRM). Worth mocked tests next, same pattern as
  `tests/test_fitbit_metrics.py`.
- **Single-user only** — `DEFAULT_USER_ID = "me"` is a placeholder
  everywhere (facade, webhook, intake). Becomes a real per-session id once
  auth exists.
- **`UserData.stride_length_m` stays `None`** — confirmed Google Health
  *does* store a real calibrated value (Profile > Activity > Stride
  Length in the app), but it's not confirmed exposed by the v4 REST API's
  documented fields. Needs a live `get_profile()` probe with a real token
  to check for an undocumented field.
- **`data/intake.py`'s gender question isn't asked anywhere yet** — no
  actual form exists to collect it; `start_journey`'s `gender` param is
  ready to receive it once one does.
- **Email/SMS notifications are stubbed, not real** —
  `EmailAlertsListener`/`PhoneAlertListener` raise `NotImplementedError`;
  no SMTP/Twilio (or similar) provider chosen or configured. Only
  `ConsoleAlertListener` fires today.
- **`data/models.py` is still empty** — journey session state
  (`TravelFacade._sessions`) is in-memory only, lost on restart. This is
  the same persistence gap day2.md flagged, still open.
- Carried over from day2.md, still true: `notes.txt` has a plaintext
  OAuth client secret (move to a gitignored `.env`); sleep should only
  sync once/day, not every notification; `ExerciseData`/`HeartRateData`/
  `SleepData` don't model every field the real API returns.
