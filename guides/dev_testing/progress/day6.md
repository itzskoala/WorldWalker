# Day 6 — Multi-trip support, per-trip steps, and a live rate-limit/data-integrity fire drill

## TL;DR
Started as a UI polish pass (back button, a trips list icon, pause,
loading state) and turned into real multi-trip support end to end: a user
can now run several trips at once, each with its own status, pause state,
and step totals, backed by a trips panel with thumbnails and bulk delete.
Along the way, hit and fixed three real bugs live against the running dev
server - a Nominatim rate-limit block, a genuine SVG `.hidden` property
bug that silently broke icon toggling, and a self-inflicted "table
disappeared out from under a live process" bug - then proved real Google
Health step data actually flows into trip progress with a live pull.
Confirmed (not guessed) that this app is still single-tenant: sharing the
dev link with friends today would crash, not just mix up data. Test
suite: 153 -> **187 passing**.

## What we did today

1. **Multi-trip support, not a single-active-trip model.** A user can now
   have several trips going at once - starting a new one no longer
   abandons the old one. `database/models.py` dropped the "one active
   trip per user" partial unique index and added `paused`/`paused_at`/
   `total_paused_seconds`; `database/trips.py` is a new module
   (`get_active_trips`, `get_trip`, `list_trips`, `pause_trip`/
   `resume_trip`, `delete_trip`/`delete_trips`) replacing the old
   single-trip `get_active_trip`/abandon-on-create logic.

2. **Real steps now fan out across every active trip at once.**
   `TravelFacade.record_steps`/`record_workout` credit every trip the
   user has in `status="active"` with the same real step/workout event -
   pausing a trip is what opts it out. Both now return a list of
   per-trip states instead of one dict.

3. **New endpoints**: `GET /api/journey/list`, `POST /api/journey/{id}/pause`,
   `POST /api/journey/{id}/resume`, `DELETE /api/journey/{id}`,
   `POST /api/journey/delete` (bulk). `GET /api/journey/state` now takes
   `trip_id` instead of assuming there's only one trip.

4. **Frontend: back button, trips panel, pause/resume, loading state.**
   `web/static/js/trip.js` rewritten for multi-trip (rebuilds the map
   when the on-screen trip changes, tracks `currentTripId` for polling).
   `web/static/js/app.js` grew a full trips panel: Active/Past split,
   real SVG thumbnails drawn from each trip's own route geometry,
   checkboxes + bulk delete, per-card pause/resume/delete. Clicking
   "Start Walking" now jumps straight to the map screen with a loading
   spinner instead of swapping the button's own label text (the
   user's specific complaint) and no longer bounces back to the search
   form on a failure - it shows an inline error on the map screen instead,
   since the user objected to the old "kicked home with a message" flow.
   Fixed the map hugging the topbar (real spacing now) and moved the
   trips list icon to the top-left of the map screen per feedback, gated
   behind `is_connected` in both places.

5. **Per-trip step tracking, not per-user.** The user caught that "steps
   today"/"total steps" were global per user, so a paused trip's numbers
   kept moving because of unrelated activity on another trip.
   `data/total_distance_db.py`'s sync log is now keyed by `trip_id`
   (self-migrates an existing file by adding the column), and
   `record_steps`/`record_workout` log one sync row per trip credited,
   not one per real-world event. Verified live: paused one of two active
   trips, credited more steps, confirmed only the still-active trip's
   numbers moved.

6. **Nominatim rate-limit fix, from a real production issue.** Heavy dev
   testing got the dev machine's IP 429'd mid-session (confirmed by
   hitting Nominatim directly with `curl`, no app code involved).
   `travel_logic/geocoder.py` rewritten with: a shared, class-level
   throttle (1-2s randomized gap between requests, global across every
   `NominatimGeocoder` instance in the process, per the user's specific
   ask for randomized timing), a `User-Agent` carrying a real contact
   email (`GEOCODER_CONTACT_EMAIL` in `.env`) plus a random per-request
   suffix, and a local JSON result cache (`data/geocode_cache.json`,
   gitignored) so repeat lookups never re-hit the API.

7. **A real SVG bug, not a flaky UI.** The pause/resume button's icon
   never actually swapped, and the map-loading error icon never showed -
   both used `svgEl.hidden = true/false`. Confirmed via direct DOM
   inspection that `.hidden` (the IDL property) doesn't reliably reflect
   to the `hidden` *content attribute* on `<svg>` elements in this
   browser, so the `[hidden] { display: none !important; }` CSS rule
   kept matching (or not matching) the stale attribute state regardless
   of what the property said. Fixed every SVG visibility toggle to use
   `toggleAttribute("hidden", ...)` instead.

8. **A self-inflicted "no such table" bug, found and fixed for real.**
   Deleted `data/total_distance.db` to clear test data while the live
   server was still running - `TotalDistanceDB` only created its table
   once, at process startup, so the next write hit a fresh, table-less
   file. Made schema setup idempotent and re-run on every connection
   instead of only in `__init__`, so this class of bug can't recur
   regardless of what happens to the file underneath a running process.
   Also surfaced (and flagged, didn't silently patch) that `start_journey`
   isn't atomic from the user's perspective - the Postgres trip commits
   before the SQLite metrics read that can still fail, which is how two
   orphaned trips got created despite the user seeing "coming_soon"
   errors. Cleaned those up; left the atomicity gap itself for later.

9. **Proved real Google Health data actually moves trip progress.** Ran
   a direct `backfill_since()` pull (bypasses the webhook, pulls straight
   from the Google Health API) against the user's real connected
   account - 404 real per-minute step readings landed and credited two
   active trips to 26.6%/2.69mi, live, not simulated.

10. **Investigated real-time push and reported findings instead of
    guessing.** The user assumed the webhook "was the whole point" and
    asked why it wasn't pushing to the local dev server. Two real,
    confirmed reasons, not a code bug: (a) `127.0.0.1` isn't reachable
    from Google's servers at all - no tunnel/public URL has ever been
    set up for this dev instance; (b) a read-only check against
    `auth/register_webhook_subscription.py`'s target endpoint came back
    as a generic Google 404 page, meaning a subscription was likely
    never successfully registered in the first place, independent of the
    localhost problem.

11. **Confirmed the app is single-tenant, precisely, not vaguely.** The
    user wants to share a Vercel link with friends and have each
    person's trips stay separate. Read `auth/connections.py` and
    confirmed `get_active_connection()` does
    `filter_by(status="active").one_or_none()` with no session/cookie
    concept at all - a second real connected user today would make that
    query raise `MultipleResultsFound` and break the app for everyone,
    not just silently mix up data. Scoped what's needed (a real
    session cookie tied to `user_id`, every endpoint reading it instead
    of "whichever connection is active," and webhook per-user
    attribution once that's in place) but held off implementing it
    pending the user's go-ahead, since it's a security-relevant call
    the user should make deliberately.

12. **Docs kept honest, not just code.** `dev_testing/TRIP_MAP.md` got a
    new "start Postgres + migrations" step, the corrected port
    throughout, per-trip steps called out explicitly, and notes on both
    real bugs found today (with their actual fixes, not just "restart
    it"). `dev_testing/CONNECT.md`'s stale port references fixed to
    match.

## Decisions made along the way (flagged to the user, not silent)
- Dev server moved off port 8000 (colliding with an unrelated local
  project, "MediNotes Pro") to port 8010 - documented everywhere it's
  referenced.
- `delete_trip`/`delete_trips` do a real hard delete (not a status
  flip) - the user specifically wants this usable for dev cleanup too,
  not just a product feature.
- Multi-user session/auth work was scoped and explained but **not**
  started without explicit confirmation - asked the user to pick a
  scope (full session + webhook research, session-only, or webhook
  research first) rather than assuming.
- Kept `abandoned` as a legal-but-now-unused trip status (for rows
  written before multi-trip support) rather than migrating historical
  data or removing the DB constraint value.

## Files created
- `database/trips.py`
- `migrations/versions/92ff7381ebca_create_active_trips_and_trip_checkpoints.py`
- `web/static/js/trip.js`
- `dev_testing/simulate_walk.py`, `dev_testing/TRIP_MAP.md`
- `tests/test_app_journey_routes.py`, `tests/test_trips_repository.py`
- `data/geocode_cache.json` (gitignored, runtime-generated)
- `progress/day6.md` (this file)

## Files deleted
- `data/landmarks_db.py` (superseded by the DB-backed trips/checkpoints
  model from the previous session's refactor; this session removed the
  last references)

## Files modified
- `database/models.py` - multi-trip schema (dropped the one-active-trip
  index, added paused state columns)
- `core/facade.py` - fan-out crediting, per-trip step totals, pause/
  resume/delete/list methods, pause-aware elapsed time
- `app.py` - new trip-list/pause/resume/delete routes, `trip_id`-scoped
  state endpoint
- `auth/connections.py`, `services/google_health/webhook.py` - no
  functional change this session, just re-verified against the
  multi-trip facade signature changes
- `data/total_distance_db.py` - trip-scoped sync log, self-healing
  schema
- `travel_logic/geocoder.py` - throttle, cache, real contact User-Agent
- `web/templates/index.html`, `web/static/css/style.css`,
  `web/static/js/app.js` - trips panel, back/pause buttons, loading/error
  states, spacing fix, `is_connected`-gated trip icons
- `dev_testing/CONNECT.md` - port fix
- `.gitignore` - `data/geocode_cache.json`
- Test files updated across the board for the new multi-trip model
  (`tests/conftest.py`, `test_database_models.py`, `test_facade.py`,
  `test_geocoder.py`, `test_google_health_webhook.py`, `test_intake.py`)

## Test result
`venv/bin/python3 -m pytest tests/ -q` -> **187 passed** (started the day
at 153 passing from the last session).

## How to run it
```bash
docker compose up -d                        # local Postgres, no-op if already running
venv/bin/python3 -m alembic upgrade head     # no-op if already at head
venv/bin/python3 -m uvicorn app:app --reload --port 8010
```
Then open `http://127.0.0.1:8010/`, Connect, and start walking. See
`dev_testing/TRIP_MAP.md` for the full walkthrough (multi-trip panel,
pause/resume, `simulate_walk.py` for fake steps) and `dev_testing/CONNECT.md`
for the OAuth connect flow.

## Open items / next session
- **Multi-user sessions.** The single biggest gap before this is safe to
  share: a real cookie-based session tied to `user_id`, every endpoint
  scoped to it instead of "whichever connection is active." Scoped, not
  started - needs the user's go-ahead on approach.
- **Webhook subscription was never actually registered** (confirmed via
  a 404 today, not assumed) - `auth/register_webhook_subscription.py`
  needs a real public URL (a Vercel deployment, or a tunnel for local
  testing) run through it before any real-time push can work at all,
  for anyone.
- **`start_journey` isn't atomic** - a Postgres trip can commit and then
  the response still fail if the SQLite metrics read errors, leaving an
  orphaned trip with no user-visible confirmation. Surfaced, not fixed.
- Dev-machine scratch data (`data/total_distance.db`,
  `data/geocode_cache.json`) will keep accumulating during testing -
  both are gitignored and harmless, but worth an occasional `rm` if
  step counts start looking unrealistic again.
