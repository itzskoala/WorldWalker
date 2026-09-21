# Day 5 — Un-breaking the refactor, real Google Health data flowing end to end

## TL;DR
Picked up right after the meters/AI-checkpoint refactor landed broken:
`core/facade.py` couldn't even import, the OAuth connection chain had a
missing module, and the real webhook was gone. By the end of today: the
whole pipeline actually works against a real connected account - Connect
button through OAuth, direct-pull dev tooling, a real webhook, the
Strategy pattern actually wired to something, real per-user stride from
Google Health's own profile, and two API-cost bugs found and fixed live
(a 404 and a 120-second timeout). Test suite: 78 (6 files failing to
collect) -> **152 passing, 0 excluded**.

## What we did today

1. **Fixed the broken refactor.** `travel_logic/` had moved to meters +
   AI-described checkpoints; `core/facade.py`, `data/landmarks_db.py`,
   and their tests were still on the old miles-based `Checkpoint`/`Route`
   shape. Converged facade on meters internally, converting to miles
   only at the SQLite DB boundary. `landmarks_db.save_landmarks` now
   takes plain dicts instead of a specific object shape, decoupling it
   from whatever `Checkpoint` class travel_logic uses.

2. **`services/google_health/client.py` didn't exist.** The real
   Google Health API logic (`get_data_points`, `get_profile`,
   `get_health_user_id`, the per-data-type filter-query quirks) had been
   deleted with the old `.tokens.json`-based auth and never rebuilt at
   its new home. Recovered it from git history, rewired to the new
   DB-backed token flow (`auth/connections.py`), which also unblocked
   `auth/connections.py` itself (it imports this module to resolve
   `healthUserId` during the OAuth exchange).

3. **Mounted the OAuth callback.** `auth/router.py`'s `/auth/google/callback`
   existed but `app.py` never included it - Connect would hit a real
   Google consent screen and then 404 on the way back. One-line fix.

4. **`dev_testing/` - a standalone way to prove the connection works**
   without needing travel logic finished. `pull_data.py` pulls
   steps/heart-rate/sleep/exercise/profile directly (no webhook needed
   for this), with an editable time window (`--today`, `--hours`,
   `--start`/`--end` - `--today` uses the machine's local time zone, not
   UTC). `CONNECT.md` documents the whole Connect -> pull loop.

5. **Found and fixed two live API bugs, not guessed:**
   - `get_profile()` called `/v4/users/getProfile` (404) - an earlier
     unverified guess. Confirmed against Google's real REST reference:
     it's `/v4/{name=users/*/profile}`.
   - Pulling `--today` heart-rate data (sampled every 2-3 seconds) hung
     past two minutes once pagination was fixed to actually follow
     `nextPageToken` instead of silently truncating at page 1. Fixed by
     switching heart-rate to Google's `rollUp` endpoint
     (`beatsPerMinuteAvg/Min/Max`, one API call regardless of range
     length) instead of pulling every raw sample - same pattern already
     used for `get_steps_total`. 6.8s end to end afterward, was a 120s+
     timeout.

6. **Implemented real pagination** in `get_data_points` - loops on
   `nextPageToken` (default page size caps as low as 25 for
   sleep/exercise, 1440 otherwise), with the existing 401-retry-once
   logic now applied per page, not just the first.

7. **Diagnosed a real sleep data gap**, not a bug: `--start 2026-09-04`
   returned only 12 sleep sessions, all dated Sept 10-20. Confirmed via
   a raw sorted dump that nothing exists before the 10th - not a
   pagination/off-by-a-day filter issue (ruled both out), a genuine gap
   upstream on Fitbit's/Google's side.

8. **Wired real per-user stride into `TravelFacade`.** A live `get_profile()`
   pull surfaced `userConfiguredWalkingStrideLengthMm`/`...RunningStrideLengthMm`
   - real per-user, per-activity-type data `UserData` had a placeholder,
   unconfirmed field for. `start_journey` now seeds `stride_by_type` from
   this and defaults the general `stride_length_m` to the real walking
   figure. Per an inline `#TODO` left in `record_workout`
   ("I DONT WANT CALIBRATION RIGHT NOW"), removed the
   calibrate-from-a-past-workout step entirely - it was overwriting the
   real seeded stride with a value derived from one workout's own data.

9. **Built the real webhook** (`services/google_health/webhook.py`),
   recovered from git history (`services/fitbit_service.py`, deleted in
   the last commit) and rebuilt as an `APIRouter` mounted into `app.py`
   (matching how `auth/router.py` is already wired in, not a second
   standalone app). `WEBHOOK_SECRET` deduplicated out of two hardcoded
   strings into one shared `.env` value.

10. **The Strategy pattern (`services/fitbitMetrics/`) is no longer
    orphaned.** The webhook's `process_health_data` dispatches every
    pulled raw dict through `StepsMetric`/`ExerciseMetric`/`SleepMetric`/
    `HeartRateMetric` into typed objects. Steps/exercise feed
    `TravelFacade.record_steps`/`record_workout` - proven with a real
    test that a webhook-shaped point actually lands in the SQLite
    `TotalDistanceDB`, not just that a function got called. Sleep/heart-rate
    are shaped and printed, not persisted - a deliberate YAGNI call
    (nothing reads them back yet), flagged rather than silently decided.
    `dev_testing/pull_data.py` uses the same Strategy classes now, so its
    output matches what the real pipeline sees.

## Decisions made along the way (flagged to the user, not silent)
- Facade converged on meters (matching the already-committed travel_logic
  direction) rather than reverting travel_logic back to miles - less
  code, keeps the already-tested meters-based math untouched.
- Sleep/heart-rate: structured and printed, no new DB table - nothing
  consumes historical sleep/heart-rate yet, so a schema/migration for it
  would be premature.
- Removed workout calibration-from-history per the user's own inline
  TODO, in favor of the real Google Health-configured stride.
- No pagination added to `roll_up` - it only ever requests one bucket
  (`windowSize` = the full range), so multi-page responses don't happen
  in practice; its real constraint is Google's max *range* length
  (14-90 days), a different problem than page-token pagination.

## Files created
- `services/google_health/client.py`, `services/google_health/webhook.py`
- `dev_testing/pull_data.py`, `dev_testing/CONNECT.md`
- `tests/test_google_health_webhook.py`
- `progress/day5.md` (this file)

## Files deleted
- `tests/test_fitbit_service.py` (superseded by `test_google_health_webhook.py`)

## Files modified
- `core/facade.py` - meters internally, miles at the DB boundary, real
  stride seeding, calibration removed
- `data/landmarks_db.py` - `save_landmarks` takes plain dicts
- `app.py` - mounts `auth_router` and `webhook_router`, top-level imports
  instead of a lazy try/except (the import chain is stable now)
- `services/fitbit_pydantic_schema.py` - `UserData` stride fields
  corrected to the real per-activity-type ones
- `auth/register_webhook_subscription.py` - `WEBHOOK_SECRET` from env,
  not a hardcoded string duplicated across two files
- `tests/test_facade.py`, `tests/test_auth_router.py`,
  `tests/test_geocoder.py`, `tests/test_google_health_client.py` - updated
  for the above, plus new coverage for `roll_up`/`get_steps_total`
  (previously untested) and `get_heart_rate_summary`

## Test result
`venv/bin/python3 -m pytest -q` -> **152 passed** (started the day at 78
passing / 6 files failing to even collect).

## How to run it
```bash
venv/bin/python3 -m uvicorn app:app --reload
```
Then follow `dev_testing/CONNECT.md`: click Connect on `http://127.0.0.1:8000/`,
approve, then `venv/bin/python3 dev_testing/pull_data.py --today`.

## Open items / next session
- The webhook exists but no subscription is registered yet
  (`auth/register_webhook_subscription.py` needs `service-account.json` +
  a public URL via ngrok) - direct-pull dev testing works without it,
  but nothing pushes to WorldWalker in real time until that's done.
- Sleep/heart-rate have no persistence - revisit once something actually
  needs to read them back.
- `data/models.py` is still empty - `TravelFacade._sessions` is still
  in-memory, the same long-open gap flagged since day 3.
- Travel-logic UI flow (actually starting a journey from the website)
  still isn't proven end-to-end with a real journey + real syncs.
