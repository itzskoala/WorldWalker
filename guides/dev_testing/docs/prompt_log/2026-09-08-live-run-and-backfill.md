# 2026-09-08 — Running it live end-to-end + historical backfill

Full-pipeline runbook (existing auth/webhook/ngrok machinery from day2.md,
plus the day3.md journey-seeding step), and a new backfill capability for
the "journey started before the watch's first real sync" gap. Separate
topic from the same day's earlier entries (position interpolation,
workout pace, observer pattern).

## Prompt (verbatim)
> let's get this working live: Tell me how to run everything from scracth.
>
> I'd like you to keep the BACKEND/CONNECTION TO FITBIT air, KISS, remove any important logic, YANGI, and SOLID.
>
> Remember this must be effiecent and effective.

## Prompt, mid-turn (verbatim)
> I'd also like to see data pulled from every sync. Let's say my start date for an activity was last saturday adn I haven't synced my watched until then, well now i sync my watch and I'd like for all the data since I started my WorldWalk to be synced in the dbs visable on website as well.

## Answer

**Verified before writing the runbook** (didn't just repeat day2.md from
memory): `credentials.json`, `.tokens.json`, and `service-account.json`
all already exist at repo root; ngrok is installed
(`/opt/homebrew/bin/ngrok`); `notes.txt`/`credentials.json`/`.tokens.json`
are all already in `.gitignore` and untracked by git - the plaintext
OAuth-secret concern flagged repeatedly in day2/day3 turns out to already
be safe, nothing to fix there before going live.

**The backfill gap, and why it's real**: `fitbit_service.py`'s webhook is
push-only and forward-looking - Google notifies about an interval only
once it actually happens to sync, so a journey that conceptually started
days before the watch's first real sync has no path to get that gap's
data in at all today. This was actually already anticipated (and
deliberately deferred) in the very first day1 prompt log entry
(`2026-09-01-fitbit-strategy-fix.md`): "a future batch-pull job... would
reuse the same strategies per-record from a separate batch-pull
component, not change the strategies themselves." This is that component,
built now because it's actually needed to go live meaningfully.

**Design, kept deliberately minimal (SOLID/KISS/YAGNI per this turn's
instruction)**: `backfill_since(start_time, end_time=None)` in
`services/fitbit_service.py`, next to `process_notification` which it
directly reuses - it does not duplicate the pull-and-dispatch loop.
Instead it builds the exact same `{"dataType", "intervals": [...]}` shape
a real webhook notification carries and calls `process_notification` with
it, once per tracked dataType (`steps`, `exercise`, `sleep`,
`heart-rate`). Single Responsibility stays intact: `process_notification`
still owns "pull + dispatch for one dataType/interval," regardless of
whether the interval came from a live webhook push or a manual backfill
call - one pipeline, not two. No new session state, no scheduling, no new
files - called manually once, right after `start_journey`, matching the
MVP's existing manual-REPL-orchestration reality (no `app.py` yet).

**Flagged, not solved (documented in the function's own docstring)**:
`get_data_points()` doesn't paginate - fine for the few-day gaps this is
built for, but a very long backfill range could silently truncate if a
dataType has more points than one API page holds. Not fixed now - would
be guessing at Google's actual page-size/pagination-token shape without
confirming it against a real response first, which is exactly the kind of
speculative complexity YAGNI says to skip until it's shown to matter.

## What changed
- **`services/fitbit_service.py`**: added `datetime`/`timezone` import,
  `BACKFILL_DATA_TYPES` constant, and `backfill_since()`.
- **`tests/test_fitbit_service.py`**: 3 new tests - pulls all 4 tracked
  types for the given range, defaults `end_time` to "now" when omitted,
  and routes pulled points through the real `process_health_data`
  pipeline (verified via the same `"1250 steps"` capsys check the
  existing tests already use).

## Test result
`pytest -q` → 77 passed (74 -> 77).

## The runbook (given to the user directly in this turn, not just logged)
1. `venv/bin/python3 -m pip install -q -r requirements.txt` (once).
2. `venv/bin/python3 auth_setup/authorize.py` (once, or if the refresh
   token ever breaks) - saves `.tokens.json`. Already done - skippable
   unless auth actually fails.
3. Terminal 1: `venv/bin/uvicorn services.fitbit_service:app --reload`.
4. Terminal 2: `ngrok http 8000` - copy the `Forwarding` URL.
5. Terminal 3: `venv/bin/python3 auth_setup/register_webhook_subscription.py <ngrok-url> 580356155767`
   (idempotent - safe to re-run whenever the ngrok URL rotates). Terminals
   1+2 must already be up first - registration does a live verification
   ping.
6. Seed a journey (no `app.py` form yet) via a fourth terminal/REPL:
   `travel_facade.start_journey("me", "<from>", "<to>", gender=...)`.
7. If the journey's real start predates today: `backfill_since("<ISO
   start time>")` once, to pull the gap - new this turn.
8. Sync the watch / walk around - watch Terminal 1 for 👣🏃❤️🛌 and the
   observer-pattern notifications (🏁🎉🏆) from the same day's earlier work.

## Open items / not done
- No pagination handling in `get_data_points`/`backfill_since` - flagged
  above, revisit if a real backfill range turns out to need it.
- Still no `app.py` - journey-seeding and backfill remain manual REPL
  steps, same gap flagged since day3.md.

---

## Prompt (verbatim)
> [KeyError traceback: register_webhook_subscription.py -> get_health_user_id()
> -> refresh_access_token() -> tokens["refresh_token"] KeyError]

## Answer
Read `.tokens.json`'s actual keys rather than guessing - confirmed it has
`access_token`/`expires_in`/`scope`/`token_type`/`obtained_at` but no
`refresh_token` at all. Root cause: `build_auth_url()` requests
`access_type=offline` but not `prompt=consent` - Google only issues a
refresh_token on a user's very first consent grant for a client, and
silently omits it on every re-authorization after that. The original
Sep 1 `authorize.py` run's access token (1-hour lifetime) had nothing to
refresh with once it expired.

## What changed
- **`auth_setup/google_health_auth.py`**: `build_auth_url()` now includes
  `prompt=consent`, forcing a fresh consent screen (and a fresh
  refresh_token) on the next `authorize.py` run regardless of prior
  grants. `refresh_access_token()` now raises a clear `RuntimeError` with
  the actual fix ("rerun authorize.py") if `refresh_token` is ever missing
  again, instead of a raw `KeyError` traceback.

## Test result
`pytest -q` → 77 passed (no regressions from the auth fix).

## Next step for the user
Rerun `venv/bin/python3 auth_setup/authorize.py` to get a fresh
`.tokens.json` with a real `refresh_token`, then retry
`register_webhook_subscription.py`.
