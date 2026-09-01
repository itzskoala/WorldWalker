# 2026-09-01 — Real Google Health data pipeline (OAuth + webhook rebuild)

## Prompt (verbatim)
> Can you tell me how to run the program, I'd like to test it for myself

## Answer
Gave `uvicorn` run steps + curl examples for each metric. Along the way,
found `venv/bin/uvicorn` was broken (its shebang pointed at the venv's old
path from before the repo was renamed from `MeVsTheWrld` to `WorldWalker`)
— worked around it with `python3 -m uvicorn` for that turn. Verified the
webhook actually works live via a real `curl` POST + server log check.

---

## Prompt (verbatim)
> recreate the venv and tell me how to run the program with my real data

## Answer
Recreated `venv/` from scratch (fixes the broken shebang permanently).
For "real data," researched the actual Google Health API docs
(developers.google.com/health) rather than assume, since nothing in the
repo did OAuth or webhook registration yet. That research uncovered a
mismatch with today's earlier fix worth a full re-plan (see plan file
`vast-humming-canyon.md`, rewritten for this task):

- The real webhook push is a lightweight **notification** (dataType +
  time interval only), not the metric values. Real data needs a follow-up
  **pull**: `GET /v4/users/me/dataTypes/{dataType}/dataPoints?filter=...`
- Real dataType strings are kebab-case (`steps`, `exercise`, `sleep`,
  `heart-rate`), not `heart_rate`.
- Real per-type shapes differ from the guessed schema (numbers as
  strings, nested under `summary`/`metricsSummary`).
- Subscription registration needs a **service account** (Cloud Console,
  manual step) separate from the OAuth client already in
  `credentials.json`.
- Google requires an immediate `204` response, processing async.

User approved the plan. Built:
- `services/google_health_auth.py` — code exchange + refresh (`httpx`,
  `.tokens.json`, gitignored).
- `services/google_health_client.py` — `get_data_points()` pull (used for
  both the webhook-notify-then-pull flow and future historical backfill),
  `get_profile()`.
- Rebuilt `fitbit_pydantic_schema.py` against the real dataPoint shapes
  (`StepsData` new, `SleepData`/`ExerciseData`/`HeartRateData` reshaped,
  `UserData` trimmed to `age`+`member_since`).
- New `fitbit_steps.py` strategy. The other 3 strategy files needed **zero
  changes** — they just pass the dict through, proving the strategy
  pattern's value.
- Rewrote `fitbit_service.py`: webhook now acks `204` fast, background
  task pulls real data per notification and routes it.
- `scripts/authorize.py`, `scripts/register_webhook_subscription.py`
  (one-off setup scripts).
- `.gitignore` (new) — credentials/tokens/venv never get committed.
- `requirements.txt` += `httpx`, `pytest-httpx`, `google-auth`.
- Tests: 17 passing (`tests/test_fitbit_metrics.py`,
  `test_fitbit_service.py` rewritten for real shapes + notify/pull flow;
  new `test_google_health_auth.py`, `test_google_health_client.py` with
  HTTP mocked via `pytest-httpx`).

## Mid-turn questions answered
- **"I do want UserMetrics — one-time? what data?"** — yes, one-time-ish
  (no push notification exists for profile changes); looked up the real
  endpoint and found it's limited to `age` + `member_since`, much thinner
  than the gender/height/weight fields guessed earlier. Two conflicting
  paths in the docs (`/v4/users/getProfile` vs `/v4/users/me/profile`) —
  flagged as unverified, needs a real call to confirm.
- **"Where is steps tracked as the primary metric?"** — clarified that
  line only described which incoming event type *will* drive route
  progress once that logic is built; `core/travel_engine.py` (where
  steps → miles-toward-Texas would actually happen) is still empty. Not
  built yet, separate future pass.

## Flagged as unverified / needs a real API call to confirm
- Exact profile endpoint path.
- Service-account OAuth scope string for subscription registration
  (`scripts/register_webhook_subscription.py`) — best guess from docs
  that name IAM roles but not an explicit scope.
- `filter` query field-name convention for the dataPoints pull
  (`google_health_client.py`) — pattern confirmed for `exercise` in the
  codelab, assumed to generalize to the other 3 types.
These are normal "first real integration call" unknowns — expect one
small fix once you're hitting the live API with a real token.

## Test result
`pytest -q` — 17 passed. Live sanity check: webhook returned `204`
immediately and the background task correctly attempted (and, expectedly,
failed pre-authorization on) a real pull.

## Your next steps to get real data flowing
1. `venv/bin/python3 -m scripts.authorize` — opens the consent URL, you
   paste back the code, saves `.tokens.json`.
2. In Google Cloud Console: create a service account, grant it the Google
   Health API role, download the key as `service-account.json` at repo
   root.
3. `ngrok http 8000` (or similar) while `uvicorn` runs locally.
4. `venv/bin/python3 scripts/register_webhook_subscription.py <ngrok-url> <project-id>`.
5. Walk around / trigger a Health Connect sync on your phone, watch the
   server log.

---

## Prompts (running manual-setup session, verbatim where short)
> which one is it? [ngrok Forwarding vs Web Interface URL]
> ModuleNotFoundError: No module named 'services' [running `python3 scripts/authorize.py` directly]
> just give me a better command to run it or tell me what repo to be in
> great i authoriazed but now [ModuleNotFoundError: No module named 'requests']
> 403 Forbidden on register_webhook_subscription.py
> 403 error: "The caller does not have permission" (after adding response-body logging)
> 400 error: FAILED_PRECONDITION
> [pasted the successful subscriber-creation response]

## Answer / bugs found and fixed while walking through the manual steps
Four real, separate issues surfaced getting this actually working end to
end — logging each since they're genuinely non-obvious:

1. **`python3 scripts/authorize.py` fails to import `services`.** Running
   a script directly puts the script's own directory on `sys.path`, not
   the repo root. Fix: run it as a module instead —
   `venv/bin/python3 -m scripts.authorize`. (Same root cause as the
   earlier broken-venv-shebang issue: how Python resolves imports depends
   on *how* you invoke it, not just which directory you're standing in.)
2. **`register_webhook_subscription.py` — missing `requests` package.**
   `google-auth`'s HTTP transport depends on `requests`, which wasn't in
   `requirements.txt` even though `google-auth` was. Added it.
3. **403 `PERMISSION_DENIED` on subscriber creation.** Root cause: passed
   the GCP **project ID** (`coral-core-506316-d1`) where the API actually
   wants the **project NUMBER**. Found the number hiding in
   `credentials.json`'s `client_id` prefix (`580356155767-...`) — Google
   OAuth client IDs are conventionally `{project_number}-{random}`.
   Also fixed the service-account OAuth scope in the same script: my
   earlier guess (`auth/health`) isn't a real scope — confirmed by the
   token endpoint falling back to minting an `id_token` instead of an
   `access_token`. Correct scope is the broad `cloud-platform`, same
   pattern as the sibling Cloud Healthcare API.
4. **400 `FAILED_PRECONDITION` on subscriber creation, my bug.** Google's
   subscriber-creation call does a synchronous verification handshake
   against the webhook endpoint, and the "authorized ping" must get back
   a plain `200`/`201` — but `fitbit_service.py`'s webhook route had
   `status_code=204` hardcoded at the route-decorator level, so it
   returned 204 for *everything*, including the verification ping. Fixed
   by detecting `{"type": "verification"}` payloads and returning `200`
   for those specifically, keeping `204` for real notification pushes
   (which Google does require to be 204). Updated
   `test_webhook_verification_ping_is_accepted` to match.

Subscriber creation succeeded after these 4 fixes: `"done": true`,
`projects/580356155767/subscribers/worldwalker`, all 4 data types.

## Test result
`pytest -q` — 17 passed (after updating the verification-ping test for
the 200-vs-204 fix).

---

## Prompt (verbatim)
> [pasted a 400 Bad Request on token exchange, re-running scripts/authorize.py]

## Answer / bug found and fixed
5. **`exchange_code()` sent a mangled auth code, my bug.** The browser
   address bar shows the redirect URL's query string URL-encoded (e.g.
   `%2F` for `/`), and the instructions said "copy everything after
   code=" — so the pasted code was the encoded form
   (`4%2F0ATsMZq...`). `exchange_code()` sent that straight into the POST
   body, where `httpx` re-encoded the `%` itself, so Google received a
   double-encoded code that didn't match what it issued -> 400. Fixed by
   URL-decoding the pasted code defensively in
   `services/google_health_auth.py::exchange_code` (`urllib.parse.unquote`,
   safe no-op if already decoded). The burned code needed a fresh consent
   round afterward (auth codes are single-use, even on a failed attempt).

## Test result
`pytest -q` — 17 passed.

---

## Prompt (verbatim)
> wait no, nothing should be deliberatly left out, the whole idea is that
> i can see the newest metric /whatever the cloud gives me at every sync,
> i'd like to see the resulsts streamed to the terminal in live time

## Context
I'd hit a 409 `SLEEP_ALREADY_EXISTS` ("A sleep log with an overlapping
interval already exists") registering the subscriber with all 4 data
types under `AUTOMATIC` policy, and my first instinct was to just drop
`sleep` from the subscription and move on. User correctly rejected that —
the whole point is every metric, live, nothing excluded. Went and
actually solved it instead.

## Answer / what "sleep" actually needed (4 more bugs, all fixed)
Google's docs bury this: `sleep` needs `MANUAL` subscriptionCreatePolicy,
not `AUTOMATIC` (their own example pairs steps/weight with AUTOMATIC,
sleep with MANUAL) — `MANUAL` means creating a per-user `Subscription`
resource explicitly (`POST .../subscribers/{id}/subscriptions`, body
`{"user": "users/{healthUserId}", "dataTypes": [...]}`), rather than the
blanket subscriber-level config. Getting there took 4 more fixes:

6. **`healthUserId` needed a `users.getIdentity` call** — added
   `get_health_user_id()` to `google_health_client.py`
   (`GET /v4/users/me/identity`), and a new `.profile.readonly` scope in
   `google_health_auth.py`.
7. **Scope typo, my bug.** Wrote `googlehealth.profile` (no `.readonly`),
   which isn't a real scope — contradicted my own earlier research, which
   had the correct `.profile.readonly` string. Got a 403 on the identity
   call even after a fresh re-auth, because the grant never actually
   included it. Fixed the string, required one more re-auth cycle.
8. **`FAILED_PRECONDITION` creating the per-user sleep subscription.** The
   subscriber's own config never declared it supports `sleep` under
   `MANUAL` at all — `subscriberConfigs` needs to be a *list* with one
   entry per policy (`{dataTypes: [steps,exercise,heart-rate], policy:
   AUTOMATIC}` + `{dataTypes: [sleep], policy: MANUAL}`), not just the
   AUTOMATIC entry alone. Added the second entry to
   `register_webhook_subscription.py`'s subscriber-creation body.
9. **Made the script idempotent.** Added a DELETE of any existing
   `worldwalker` subscriber before recreating — re-running with a changed
   config otherwise seemed to merge with stale config from a prior run
   rather than replace it (this is also just generally needed going
   forward, since ngrok's URL rotates every restart).

**Result: subscriber created with all 4 data types, manual sleep
subscription created for `healthUserId 7503159920197361012`.** Both API
calls returned success.

## Test result
`pytest -q` — 17 passed throughout all of the above fixes.

---

## Prompts (re-running the script after ngrok's URL rotated, verbatim where short)
> [pasted: DELETE 400 FAILED_PRECONDITION, then POST 409 SLEEP_ALREADY_EXISTS on subscriber creation]
> [pasted: PATCH 400 "update_mask must be provided and cannot be empty"]
> [pasted the successful PATCH response + "already exists, skipping"]

## Answer / made the script actually re-runnable (2 more fixes)
Re-running the original delete-then-create script (needed whenever ngrok's
URL rotates) broke: DELETE 400'd because the subscriber still had the
manual sleep subscription attached as a child (Google won't delete a
subscriber with active children), so the subsequent create hit the
still-existing subscriber and 409'd. Root design flaw: delete+recreate is
the wrong pattern here entirely. Fixed by rewriting
`register_webhook_subscription.py` to upsert instead:

10. **PATCH-if-exists, POST-if-not**, replacing delete+create. `PATCH`
    initially 400'd - `"update_mask must be provided and cannot be
    empty"` - fixed by adding `?updateMask=endpointUri,subscriberConfigs,endpointAuthorization`
    (comma-joined from the body's own keys).
11. **Check-before-create for the sleep subscription** - lists existing
    subscriptions first and skips creating one if this `healthUserId`
    already has one, instead of hitting `ALREADY_EXISTS` on every re-run.

Verified working: re-ran against a new ngrok URL, got a clean `PATCH`
update (all 4 data types, new `endpointUri`) and correct
"already exists, skipping" on the sleep subscription. The script is now
safe to re-run any time ngrok rotates, no more manual intervention.

## Test result
`pytest -q` — 17 passed.

---

## Prompt (verbatim)
> [pasted the uvicorn server log: real webhook traffic arriving (200s and
> the expected verification-handshake 401s), but the pull step 400ing on
> steps and sleep]

## Answer / the last unverified guess, now fixed with real evidence
`get_data_points`'s filter query was always the weakest-evidence part of
this build (flagged from the start). First real traffic proved the guess
(`interval.start_time`) wrong; added response-body printing on failure so
the next error would be diagnosable instead of a blind guess, then fixed
it in two rounds using Google's own (quite detailed) error messages:

12. First fix attempt (`{dataType}.interval.civil_start_time`, taken from
    the one confirmed example - the exercise codelab) was still wrong for
    2 of 3 remaining types. Google's error responses this time actually
    named the problem precisely - wrong comparator (`<=` invalid, only
    `>=`/`<` supported) and wrong value format for steps; "member not
    supported for filtering" for heart-rate and sleep entirely.
13. Fetched the actual `list` method reference and got the real, complete
    picture: filter field depends on the data type's *category* -
    interval types (steps, exercise) use `{type}.interval.start_time`;
    sample types (heart-rate) use `{type}.sample_time.physical_time`;
    **sleep is a special case that only supports filtering by
    `interval.end_time`, not `start_time`, at all.** Rewrote
    `get_data_points`/`_filter_query` in `google_health_client.py` to
    branch by category instead of one-size-fits-all.
14. Also wrapped the pull+parse in `process_notification`
    (`fitbit_service.py`) in try/except - a failed pull now logs one
    clean line instead of a 40-line ASGI traceback flooding the terminal.

Added `tests/test_google_health_client.py` coverage for all 3 filter
branches (interval/sample/sleep).

## Test result
`pytest -q` — 21 passed.

---

## Prompt (verbatim)
> [pasted a ValidationError: StepsData missing "interval" and "count" -
> real pull now succeeding (filter fix worked), but parsing failed]

## Answer / the envelope-wrapping assumption, confirmed for real
This was the one structural assumption flagged as genuinely uncertain
back when the schema was first rebuilt (see the very first entries in
this file): whether each dataPoint response is flat or wrapped in an
envelope keyed by data type. Now confirmed with a real payload: it's
wrapped - `{"dataSource": {...}, "steps": {"interval": ..., "count": "5"}}`,
not flat. Fixed by unwrapping in `get_data_points`
(`google_health_client.py`) right after the filter fix, since it already
knows which data type it requested - `point.get(field, point)` per
result, so the fitbitMetrics strategies keep receiving the flat dict
their schema expects, unchanged. Added
`tests/test_google_health_client.py` coverage for both a plain type
(`steps`) and a hyphenated one (`heart-rate` -> `heart_rate` envelope
key).

This was the last unverified assumption from the original schema rebuild
- all four flagged unknowns (profile endpoint, service-account scope,
filter syntax, envelope shape) are now confirmed against real API
responses rather than docs guesses.

## Test result
`pytest -q` — 23 passed.

---

## Prompt (verbatim)
> [pasted: 👣 steps line printed correctly, but heart-rate's parse failed
> with the same "field required" shape as the steps bug just fixed]

## Answer / one more envelope-key naming wrinkle
Steps confirmed the unwrap fix works. Heart-rate still failed because its
envelope key isn't snake_case `heart_rate` (what `data_type.replace("-",
"_")` produced) - every other field in this API's JSON body is camelCase
(`startTime`, `beatsPerMinute`, `dataSource`...), so the real key is
`heartRate`. The snake_case form is a *different*, separate naming
convention specific to filter query field names (proto-style), not the
JSON body itself - two conventions coexisting in one API. Added
`_camel_case()` to `google_health_client.py` and used it for the envelope
unwrap instead of the snake_case helper (which stays as-is, still correct
for `_filter_query`). Updated the hyphenated-type test to
`heartRate` and added a direct test for `_camel_case`.

## Test result
`pytest -q` — 24 passed.
