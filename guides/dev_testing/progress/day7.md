# Day 7 — Real login (JWT), and Google Health connections scoped per user

## TL;DR
Day 6 ended with "the single biggest gap before this is safe to share: a
real session tied to user_id, every endpoint scoped to it instead of
'whichever connection is active.'" That's what today closed out, plus a
live crash found and fixed along the way. WorldWalker now has real
email/password login (JWT access + refresh tokens, a login gate in the
frontend), every trip endpoint requires it, and Google Health connections
are genuinely per-user end to end - the OAuth flow, token refresh, the
webhook, and background API calls all resolve through a specific
`user_id`, never a single ambient connection. Test suite: 191 -> **238
passing**.

## What we did today

1. **Fixed a live crash**: `IndexError: list index out of range` in
   `travel_logic/progress_calculator.py`'s `locate_on_route()`, hit for
   real via `dev_testing/simulate_walk.py`. Root cause: Python 3.12+
   changed `sum()` to use compensated (Neumaier) summation for floats,
   so `travel_logic/route_service.py`'s `total_distance = sum(gaps)` and
   the separately `+=`-accumulated `distance_from_start` on the last
   point could differ by a few ULPs on a long route (12,000+ points) -
   enough for the distance-walked clamp to land past the end of the
   route's own point list. Fixed by deriving `total_distance` from the
   same accumulator instead of a second, independently-rounded sum, and
   clamping `locate_on_route()` against the route's own last point
   rather than its separately-stored total. Repaired the one affected
   trip's data live through the real checkpoint/finish code path (not a
   raw SQL patch) - checkpoint #4 and the "finished" milestone fired
   correctly, once.

2. **Real login: signup, login, JWT access + refresh tokens.** New
   `accounts/` package - `security.py` (bcrypt hashing, access/refresh
   JWT creation with a `type` claim so one can never be used as the
   other), `service.py` (signup/authenticate), `dependencies.py`
   (`get_current_user` - validates signature, expiration, token type,
   and that the user still exists and is active, on every call),
   `router.py` (`/auth/signup`, `/auth/login`, `/auth/refresh`,
   `/auth/logout`, `/auth/me`). Access tokens are short-lived (15 min
   default) and live in the frontend's memory only; refresh tokens
   (7-day default) are `HttpOnly`/`SameSite=Lax` cookies, `Secure`
   unless `COOKIE_SECURE=false` (needed for local http dev). `users`
   gained nullable `email`/`hashed_password` + non-null `is_active`
   (migration `eef93debeb8c`) - nullable because a connection made
   before today's OAuth rework had neither.

3. **Every trip endpoint now requires that login**, not "whichever
   Google Health connection happens to be active." `app.py`'s
   `/api/journey/*` routes swapped `_current_user_id()` (derived from
   the sole active `GoogleHealthConnection`) for
   `Depends(get_current_user)` (derived from the JWT) - a trip's owner
   is now genuinely the logged-in WorldWalker account.

4. **Frontend login gate.** `web/static/js/auth.js` (the one place that
   holds the access token and wraps every `/api/*` call - on a 401 it
   tries exactly one silent refresh+retry before giving up) and
   `web/static/js/auth-ui.js` (wires the login/signup form and the
   topbar user menu, decides whether `#auth-gate` or `#app-shell` is on
   screen). `index.html`/`style.css` grew the gate markup and the user
   menu; every other frontend script now calls `window.Auth.apiFetch`
   instead of a bare `fetch`.

5. **Google Health connections scoped per user - the model already
   supported it, the flow didn't.** `GoogleHealthConnection.user_id` was
   already `unique=True` (one row per user, always was); what wasn't
   scoped was everything reading and writing it.
   - `auth/connections.py`: `get_active_connection()`/
     `get_valid_access_token()` now require `user_id` and can never
     return or act on another user's row. `upsert_connection_from_tokens()`
     now requires an existing WorldWalker `user_id` and **only links**
     Google's account to that user - it no longer auto-creates a
     WorldWalker `User` from Google's identity, and rejects (409) a
     Google account already linked to someone else.
   - **New OAuth shape, WorldWalker identity first**:
     `POST /auth/google/start` (JWT-protected) issues a random,
     server-side, 10-minute, single-use `state` bound to
     `current_user.id`; `GET /auth/google/callback` has **no** JWT (Google's
     redirect can't carry one) and instead recovers `user_id` from that
     state via `consume_state()`. The state store moved from a bare
     `set[str]` to `dict[str, _PendingState]` (user_id + expiry) in
     `auth/google_health_auth.py`.
   - **The webhook maps Google's identity to a WorldWalker user, not an
     ambient guess**: `services/google_health/webhook.py`'s
     `process_notification()` reads the notification's own
     `"user": "users/{healthUserId}"` field and resolves it through a
     new `get_user_id_for_provider_user_id()`, then threads that
     `user_id` through every downstream call.
   - **Background API calls carry a user_id, not a shared token**:
     every function in `services/google_health/client.py`
     (`get_data_points`, `roll_up`, `get_steps_total`,
     `get_heart_rate_summary`, `get_profile`) now takes `user_id` and
     resolves that specific user's token via `_current_access_token(user_id)`.
   - `core/facade.py`'s stride-from-Google-profile lookup and
     `auth/register_webhook_subscription.py`'s manual "sleep"
     subscription (now registered for every connected user found in the
     DB, not one ambient account) updated to match.
   - The frontend's Connect button can no longer be a pre-built href
     (the URL is per-user now) - it's a real button that calls
     `POST /auth/google/start` and navigates to the URL it gets back.

## Decisions made along the way (flagged, not silent)
- Kept a narrow, explicitly-documented single-tenant fallback
  (`get_active_user_id()`/`_any_active_connection()`) for the two call
  sites with no per-request user at all: the pre-login connect banner on
  `/`, and the local dev scripts (`simulate_walk.py`, `pull_data.py`).
  Neither touches or credits another user's data.
- Did not rewire the OAuth *callback* to require a WorldWalker login
  itself - Google's redirect can't carry a bearer token, so `state` is
  the only mechanism; this was scoped and confirmed correct rather than
  assumed.
- `provider_user_id` (Google's healthUserId) was kept as the column
  name rather than renamed to match an illustrative "google_account_id"
  from the ask - no functional reason to rename an already-correct,
  already-unique column.

## Files created
- `accounts/` (`security.py`, `service.py`, `dependencies.py`,
  `router.py`, `schemas.py`)
- `migrations/versions/eef93debeb8c_add_email_hashed_password_is_active_to_.py`
- `web/static/js/auth.js`, `web/static/js/auth-ui.js`
- `tests/test_accounts.py`, `tests/test_frontend_auth_flow.py`,
  `tests/test_route_service.py`
- `progress/day7.md` (this file)

## Files modified
- `travel_logic/route_service.py`, `travel_logic/progress_calculator.py`
  - the distance-mismatch crash fix
- `database/models.py` - `email`/`hashed_password`/`is_active` on `users`;
  comments on `GoogleHealthConnection` corrected to describe the
  user-first model
- `app.py` - JWT-gated trip endpoints, dropped the precomputed
  single-user `CONNECT_URL`
- `auth/connections.py`, `auth/router.py`, `auth/google_health_auth.py`,
  `auth/register_webhook_subscription.py` - per-user connection scoping,
  the new `/auth/google/start` + state-bound callback flow
- `services/google_health/client.py`, `services/google_health/webhook.py`
  - `user_id` threaded through every call, webhook resolves via the
  notification's own Google identity
- `core/facade.py`, `data/intake.py` - stride lookup takes `user_id`;
  stale comments corrected
- `dev_testing/simulate_walk.py`, `dev_testing/pull_data.py` - updated
  for the new `get_active_connection(session, user_id)` signature
- `web/templates/index.html`, `web/static/css/style.css`,
  `web/static/js/app.js`, `web/static/js/trip.js` - login gate markup,
  user menu, Connect button now goes through `/auth/google/start`
- `requirements.txt`, `.env.example` - `pyjwt`, `bcrypt`,
  `JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
  `REFRESH_TOKEN_EXPIRE_DAYS`, `COOKIE_SECURE`
- Test files updated across the board for JWT auth and per-user Google
  Health scoping (`tests/conftest.py`, `test_app_journey_routes.py`,
  `test_auth_router.py`, `test_connections.py`, `test_facade.py`,
  `test_google_health_auth.py`, `test_google_health_client.py`,
  `test_google_health_webhook.py`, `test_progress_calculator.py`)

## Test result
`venv/bin/python3 -m pytest tests/ -q` -> **238 passed** (started the day
at 191 passing from the last session).

## How to run it
```bash
docker compose up -d                        # local Postgres, no-op if already running
venv/bin/python3 -m alembic upgrade head     # picks up eef93debeb8c
venv/bin/python3 -m uvicorn app:app --reload --port 8010
```
Then open `http://127.0.0.1:8010/`, sign up (or log in), click Connect to
link Google Health, and start walking.

## Open items / next session
- **The pre-login `/` page's "is anyone connected" banner is still
  single-tenant** (`app.py`'s `_is_connected()`) - it can't know which
  user is about to log in before they do, so it's left as a best-effort
  default rather than rewired into the login-gate architecture. Low
  risk (read-only, no data access), but worth revisiting if the
  homepage ever needs to be truthful pre-login.
- **`register_webhook_subscription.py` still needs a real public URL**
  (a Vercel deployment or a tunnel) run through it before any real-time
  push works for anyone - unchanged from Day 6, not re-verified today.
- **OAuth `state` store is still in-memory/single-process** (documented
  as such since Day 1 of this flow) - fine for one dev/uvicorn worker,
  would need a shared store (e.g. the database) behind a real
  multi-worker deployment.
