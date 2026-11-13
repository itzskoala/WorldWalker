# Day 2 — Fitbit strategy pattern fix → live real-data pipeline

Full blow-by-blow (every prompt + reasoning) is in `docs/prompt_log/`:
`2026-09-01-fitbit-strategy-fix.md` and
`2026-09-01-google-health-real-data-pipeline.md`. This is the condensed
version for picking work back up.

## TL;DR
Started the day with a broken strategy-pattern MVP that couldn't run at
all. Ended it with real Fitbit steps/exercise/heart-rate/sleep data
flowing live from Google Health's webhook into the terminal, parsed
correctly. Nothing dropped, all 4 metrics working.

## What we did today
1. **Fixed the Strategy pattern** (`services/fitbitMetrics/`) — the
   classes weren't real classes (dead nested functions), had a typo
   (`"excersise"` vs `"exercise"`), a copy-paste naming bug, and
   `fitbit_service.py` never actually called them. Wired the webhook's
   `match/case` to build the strategy and call `.metric_obj()`.
2. **Discovered the whole thing was built against the wrong API shape.**
   This project connects to the **Google Health API**
   (developers.google.com/health), not the classic Fitbit Web API — the
   original schema was Fitbit-shaped and didn't match reality at all.
   Rebuilt `fitbit_pydantic_schema.py` against real documented/confirmed
   response shapes.
3. **Built the whole OAuth + webhook pipeline from scratch**, since none
   of it existed:
   - `auth_setup/google_health_auth.py` + `auth_setup/authorize.py` —
     token exchange/refresh, one-time CLI consent flow
   - `services/google_health_client.py` — pulls real data after a webhook
     notification (`get_data_points`), plus `get_profile`/`get_health_user_id`
   - `auth_setup/register_webhook_subscription.py` — idempotent
     subscriber + per-user subscription management
   - `services/fitbit_service.py` — webhook acks `204` fast, pulls +
     parses in a background task
4. **Reorganized auth files into `auth_setup/`** (this session's last
   ask) — `google_health_auth.py`, `authorize.py`,
   `register_webhook_subscription.py` now live together, separate from
   the request-handling path in `services/`.
5. Recreated a broken `venv/` (stale shebang paths from a project
   rename), added `.gitignore`, cleaned up a stray leftover file.
6. **24 tests, all mocked, no real network** — strategies, webhook
   routing, auth flow, filter-query construction, envelope unwrapping.

## How to run it

**One-time setup** (already done): `credentials.json` +
`service-account.json` at repo root, deps installed
(`venv/bin/python3 -m pip install -q -r requirements.txt`),
`venv/bin/python3 auth_setup/authorize.py` run once (paste the consent
code, saves `.tokens.json`).

**Every time you want to test with real data**, in order:

1. Terminal 1 — the server:
   ```bash
   venv/bin/uvicorn services.fitbit_service:app --reload
   ```
   Watch this terminal for 👣🏃❤️🛌.

2. Terminal 2 — public tunnel:
   ```bash
   ngrok http 8000
   ```
   Copy the `Forwarding` URL (`https://....ngrok-free.dev`).

3. Terminal 3 — register the subscription (safe to re-run any time the
   ngrok URL rotates; it's idempotent):
   ```bash
   venv/bin/python3 auth_setup/register_webhook_subscription.py <ngrok-url> 580356155767
   ```

4. Walk around, or trigger a Health Connect sync on your phone. Watch
   Terminal 1.

Terminals 1+2 must be up *before* step 3 — registration does a live
verification ping against your endpoint.

**Sanity check first** (optional, cheap, no live services needed):
```bash
venv/bin/python3 -m pytest -q
```
Should say `24 passed`.

## Key highlights / hardest-won lessons
These are the ones worth remembering before touching this API again:
- **Google's webhook only sends a notification** (dataType + time
  interval), never the actual values — you always pull after.
- **The pulled dataPoint is wrapped**: `{"dataSource": {...}, "<camelCase
  type>": {...}}`. The envelope key is **camelCase** (`heartRate`), but
  the **filter query field name** is a totally different, **snake_case**
  convention (`heart_rate.sample_time.physical_time`) — two naming
  systems in one API.
- **Filter fields differ by category**: interval types (steps, exercise)
  use `{type}.interval.start_time`; sample types (heart-rate) use
  `{type}.sample_time.physical_time`; **sleep only supports filtering by
  `interval.end_time`, never `start_time`**. Comparators are `>=`/`<`
  only — no `<=`.
- **`sleep` needs `MANUAL` subscription policy**, not `AUTOMATIC` (which
  409s as `SLEEP_ALREADY_EXISTS`) — meaning a separate per-user
  `Subscription` resource keyed by `healthUserId` (from a
  `users.getIdentity` call, needs its own scope).
- **Auth for subscription management is a service account** with the
  broad `cloud-platform` scope — different from the user-level OAuth
  token used to actually read data, and the webhook registration path
  wants the GCP **project number**, not the project ID.
- **Re-registering a subscriber should PATCH, not delete-then-create** —
  deleting one with an active child subscription (sleep) 400s.
- venv/script portability: a plain `python3 some/script.py` puts that
  script's own directory on `sys.path`, not the repo root — needed a
  `sys.path.insert` shim in every standalone script.

## Improvements made along the way (not just bug fixes)
- Registration script is now idempotent — safe to re-run every time
  ngrok's URL rotates, no manual cleanup.
- Failed background-task pulls log one clean line instead of a 40-line
  ASGI traceback.
- `docs/prompt_log/` convention established and used consistently — every
  prompt + answer logged, per your standing preference (saved to memory).

## Open items / next session
- **`core/travel_engine.py`** — steps → miles → % progress toward the
  CA→TX goal. Currently just comments, not even valid Python yet. This
  is the actual "walk the world" feature — today's work only proves data
  reaches the app reliably, it doesn't do anything with it yet.
- **`core/facade.py`**, **`core/observer-decorator/*`** — Facade +
  Observer/Decorator scaffolding for wiring ingestion → travel engine →
  notifications. Empty or pseudocode, not valid Python yet.
- **`data/models.py`, `data/intake.py`** — no persistence layer exists;
  right now everything just prints and is gone. Needed before progress
  can survive a restart.
- **`app.py`, `services/maps_service.py`** — the actual web app / map UI.
  Empty stubs.
- **Richer `UserData`/profile** — proposed mid-session (People API for
  name/gender/DOB via `users.getIdentity`-adjacent scopes, height/weight
  via their own `dataTypes`), then set aside to fix the live pipeline
  instead. Revisit if you still want full profile fields captured once
  per authorization.
- **Sleep sync frequency** — your own TODO comment in
  `fitbit_service.py`: only sync sleep once per day at first sync, not
  every notification.
- **Security**: `notes.txt` at repo root still has a plaintext Google
  OAuth client secret — move to a gitignored `.env` before `git init`.
- **Schema gaps flagged but unconfirmed**: `ExerciseData` doesn't model
  `splits`; `HeartRateData` doesn't model `metadata`
  (motionContext/sensorLocation); `SleepData` doesn't model the `stages`
  list — fine for now (Pydantic silently ignores undeclared fields), add
  if a future feature needs them.
