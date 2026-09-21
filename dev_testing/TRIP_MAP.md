# Testing the trip map (dev test)

Watches the live map (`web/static/js/trip.js`) update as a trip
progresses, without waiting on a real Google Health sync. Assumes you've
already connected once - see `CONNECT.md`.

## 0. Postgres + migrations (only needed if it's not already running)

Trips live in Postgres (`active_trips`/`trip_checkpoints`), not a
per-process dict, so it has to be up before the app will start cleanly.

```bash
docker compose up -d                    # starts the local Postgres container
venv/bin/python3 -m alembic upgrade head   # applies any pending schema migrations
```

`docker compose up -d` is a no-op if the container's already running.
`alembic upgrade head` is a no-op if you're already at head - check with
`venv/bin/python3 -m alembic current`. If Docker itself isn't running
(`docker info` errors with "Cannot connect to the Docker daemon"), open
Docker Desktop first.

## 1. Start the app

```bash
venv/bin/python3 -m uvicorn app:app --reload --port 8010
```

`--reload` means editing any `.py` file restarts the server automatically -
you don't need to kill/relaunch it yourself after a code change. Port 8010,
not the default 8000 - this repo's dev instance has stood on 8010 all
session to stay clear of other local projects that squat on 8000/3000.

## 2. Connect (if you haven't already)

Open http://127.0.0.1:8010/ and click **Connect**. See `CONNECT.md` for
what to expect in the terminal.

## 3. Start a trip

Pick a real "Where from?" and "Where to?" and click **Start Walking**. The
screen switches to the map view immediately (a loading spinner while
`/api/journey/start` is in flight), then fills in: a full (dashed, muted)
route line, a green start pin and a red end pin, and a blue "you are here"
marker sitting right on the start pin. No checkpoint pins yet - that's
expected, see below.

A user can have several trips going at once now - starting another trip
doesn't replace this one. Click the list icon in the topbar to see every
trip (Active/Past), pause or resume one, delete one, or click a card to
open its map. Copy a trip's id from there (or from the `trip_id` field in
the JSON below) for the `--trip-id` flag in step 5.

## 4. See the full map state (the normally-invisible layer)

Reload the page with `?debug=1` appended, e.g.
`http://127.0.0.1:8010/?debug=1`. Every checkpoint on the trip now shows as
a faint dashed "ghost" pin, even though none are hit yet. This is the data
that already exists on the server (every checkpoint was generated and
saved when the trip started - see `travel_logic/checkpoints.py` and
`database/trips.py`'s `create_trip`) but that the normal product view
intentionally keeps hidden until you actually reach each one.

You can see the same thing as raw JSON without the browser at all - grab a
trip id from the list endpoint first, since `state` now needs one:

```bash
curl -s http://127.0.0.1:8010/api/journey/list | python3 -m json.tool   # find a trip_id
curl -s "http://127.0.0.1:8010/api/journey/state?trip_id=<trip_id>" | python3 -m json.tool
```

Every checkpoint is always in that response, each tagged `"hit": true` or
`"hit": false` - the frontend, not the endpoint, decides what to draw.

## 5. Fake some walking

In a second terminal:

```bash
venv/bin/python3 dev_testing/simulate_walk.py                  # credits ~3000 steps to every active trip
venv/bin/python3 dev_testing/simulate_walk.py --steps 5000       # a specific step count, same fan-out
venv/bin/python3 dev_testing/simulate_walk.py --to-checkpoint    # walk ONE trip just far enough to cross its next unhit checkpoint
venv/bin/python3 dev_testing/simulate_walk.py --finish           # walk ONE trip the rest of the way to complete it
venv/bin/python3 dev_testing/simulate_walk.py --finish --trip-id <trip_id>  # pick which trip, if more than one is active
```

Plain `--steps` runs (the default too) credit every trip you currently have
in the "active" status at once - pause a trip from the trips panel first if
you don't want it moving. `--to-checkpoint`/`--finish` need one specific
trip's route to compute a step count against, so they require `--trip-id`
whenever you have more than one active trip (the script prints the ids to
choose from if you forget it).

Each run prints the resulting distance/percent and any checkpoints it just
crossed, per trip credited. Back in the browser (give it up to ~20s for the
next poll, or reopen the trip from the trips panel), confirm:

- the "you are here" marker moved further along the route
- the green "walked so far" line got longer, following the real route
  (not a straight line to the marker)
- if `--to-checkpoint` crossed one: a solid pin appears at that
  checkpoint and stays there on every later poll/reload - and if you're on
  the `?debug=1` view, that checkpoint's pin flips from a ghost to a solid
  pin instead of a new one appearing next to it
- the metrics strip (walked, left, checkpoints hit, steps today/total,
  time walking) updated - steps today/total are per-TRIP now
  (`data/total_distance_db.py` is keyed by trip_id), so crediting one trip
  never moves another trip's numbers unless it was also active and got
  fanned-out credit for the same real event

Run `--to-checkpoint` a few times in a row to watch checkpoints get hit one
at a time. Run `--finish` to complete the trip - the map shows 100% for a
couple of seconds, then the page returns to the search form on its own.

## 6. Reload mid-trip

Trips are real database rows (`active_trips`/`trip_checkpoints`), not a
per-process dict, so nothing is lost across a page reload or restarting
`uvicorn`. Reloading the page always lands back on the search/home screen
though, even mid-trip - with several trips possibly active at once there's
no single "the" trip to jump back into automatically. Open the topbar's
list icon and click the trip's card to get back to its map.

## Notes

- `simulate_walk.py` calls `TravelFacade.record_steps()` directly - the
  exact function the real Google Health webhook calls
  (`services/google_health/webhook.py`). It's a shortcut around waiting for
  a real sync, not a different code path.
- The green line is "how far along the known route the user has gotten,"
  not a live GPS trail - there's no location tracking in this app. See
  `core/facade.py`'s `_walked_geometry()` if you want the exact math.
- If `/api/journey/start` returns `{"coming_soon": true}`, an external
  dependency (geocoding, OSRM, or the AI describer) failed - check the
  `uvicorn` terminal for the real error it printed. A common one during
  heavy dev testing: Nominatim (the free geocoder) 429s if you hit it too
  fast. `travel_logic/geocoder.py` already throttles (~1-2s between
  requests, shared across the whole process) and caches every real lookup
  in `data/geocode_cache.json`, so repeat "Minneapolis"-type queries don't
  re-hit it - but a fresh place name still costs one real request, and a
  burst of many different fresh places in a short window can still get
  rate-limited. If it does, just wait a bit and retry.
- If a request logs `OperationalError: no such table: total_distance_log`,
  something deleted `data/total_distance.db` out from under a running
  server (e.g. a manual `rm` while `uvicorn` was still up). This self-heals
  on the very next request now (`TotalDistanceDB` re-runs its schema setup
  on every connection) - no restart needed, just retry.
