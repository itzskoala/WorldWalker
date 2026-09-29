# WorldWalker — Results

What's actually been built and verified, most recent first. This is the
reconciled state — cross-checked against the real test suite and a live
browser session, not just copied from a single session's own notes.
Full narrative detail lives in `progress/day*.md`; open work lives in
`tasks.md`.

## Current state (as of Sep 23 2026)

- **285 tests passing** (`venv/bin/python -m pytest -q`), 0 failing.
- Real email/password login (JWT access + refresh) gates every trip
  action and every Google Health action.
- Google Health connections are fully per-user, end to end — OAuth
  start/callback (Postgres-backed CSRF state, not in-process), token
  refresh, the incoming webhook, and every background API call resolve a
  specific `user_id`.
- Frontend is a 3-screen app - **Home** ("My Journeys": active trip cards
  with route/progress/current-checkpoint/steps, completed trips below),
  **Create** (the original plan-a-walk form, untouched), **Profile**
  (email, member-since date, lifetime steps) - navigated via a fixed
  bottom tab bar. Opening a journey card takes over with **Trip Detail**:
  a large rounded live map, a progress hero (name + big bar/percentage),
  a 4-stat grid, and a done/current/upcoming checkpoint timeline.
- A user can plan a walk (real geocoding + real walking route), run
  several trips at once (pause/resume/delete from their Home card), and
  see live progress on a MapLibre map as real steps come in.
- Warm outdoor-fitness palette (cream/charcoal/forest-teal/sky-blue)
  applied app-wide via the existing CSS token system - verified in both
  light and dark mode live in Chrome.
- Known-broken/open: see `tasks.md` — nothing currently broken in main,
  but several real gaps (webhook never confirmed against a real deployed
  URL, `start_journey` non-atomicity) remain.

## Timeline

**Day 1 — Research.** Scoped how to talk to Google Health (which
absorbed the Fitbit API): Google Cloud project, OAuth 2.0 client,
scopes, the 100-user dev cap. No code — pure research, captured in
`progress/day1.md`.

**Day 2 — Real data pipeline.** Fixed a broken Strategy-pattern MVP that
couldn't run at all. Ended with real Fitbit steps/exercise/heart-rate/
sleep flowing live from the webhook into the terminal, all 4 metrics
parsed correctly.

**Day 3 — Travel logic core.** Built "walk the world" end to end at the
logic layer: forward-geocode a from/to place, fetch a real walking
route, place real cities as landmark checkpoints, turn incoming steps
into a live position/ETA, fire a notification on a landmark crossing.
Not yet reachable from a web form — REPL/webhook only.

**Day 4 — Exact positioning, workout pace, observer pattern.** Position
became an exact interpolated point on the route (not snap-to-nearest-
waypoint). Workouts move you at a real measured pace instead of one flat
stride constant. Notifications became a proper Observer-pattern
dispatch instead of ad hoc calls.

**Day 5 — Un-broke a refactor; real pipeline end to end.** Picked up
after a meters/AI-checkpoint refactor landed broken (facade couldn't
import, OAuth chain missing a module, webhook gone). Rebuilt to a real
working state: Connect button through OAuth, direct-pull dev tooling, a
real webhook, real per-user stride from Google Health's own profile, two
live API-cost bugs found and fixed (a 404, a 120s timeout). Test suite:
78 (6 files failing to collect) → 152 passing.

**Day 6 — Multi-trip support.** Started as UI polish, became real
multi-trip support: several simultaneous trips per user, each with its
own status/pause state/step totals, a trips panel with thumbnails and
bulk delete. Fixed three live bugs (a Nominatim rate-limit block, a real
SVG `.hidden` bug, a self-inflicted table-disappeared-mid-process bug).
Confirmed (not guessed) the app was still single-tenant — sharing the
dev link would crash. Test suite: 153 → 187 passing.

**Day 7 — Real login; Google Health scoped per user.** Closed the
single-tenant gap day 6 flagged. Added `accounts/` (JWT signup/login),
gated every trip endpoint on it, and reworked the OAuth flow so a
WorldWalker user is always the source of truth (state-bound
`/auth/google/start` → callback recovers `user_id` from state, never
from Google's identity). Also fixed a live `IndexError` crash in
`locate_on_route()` caused by a Python 3.12 float-summation change on
long routes. Test suite: 191 → 238 passing.

**Also Day 7 (same date, homescreen + auth-flow session) — Frontend
auth UI and homescreen redesign.** Built the login/signup gate
(`auth.js`/`auth-ui.js`) and wired every trip/Google-Health JS action
through a bearer-token `apiFetch` with automatic refresh-and-retry on
401. Redesigned the homescreen around a Strava-inspired "where am I →
what have I done → what can I do next" hierarchy: a new warm
outdoor-fitness color palette applied app-wide via the existing CSS
token system, and a new activity-summary card (`home.js`) showing
today's steps and current-trip progress, or lifetime stats, or an empty
state — sourced entirely from existing endpoints, no new backend
surface. Added `tests/test_frontend_auth_flow.py` proving the exact
request sequence the frontend performs (signup/login → authenticated
request; expired token → refresh → retry). Verified live in Chrome, not
just by test suite.

**Day 7 (continued) — 3-screen redesign: Home / Create / Profile.**
Reworked the single-scroll homescreen into a proper navigation
structure, at the user's explicit direction (Strava-style "My Journeys"
was the ask). Retired the trips-panel slide-over drawer and its
bulk-select UI entirely - Home's card list replaces it with a simpler,
always-visible single-select list (pause/resume/delete stay as per-card
actions). Create is the exact original plan-a-walk form/logic,
relocated to its own tab, globe hero included, functionally untouched.
Trip Detail (opened from a Home card) got a real rework: a bigger
rounded map, a progress hero (trip name + big bar/percentage), a
trimmed 4-stat grid (Steps, Distance, Current checkpoint, Checkpoints),
and a new checkpoint timeline (done/current/upcoming, built from the
checkpoints array the API already returned - no new data). Backend grew
two small, real additions to support Profile: `UserOut.created_at`
(the column already existed) and `GET /api/journey/stats` ->
`lifetime_steps` (a `SUM(steps) WHERE user_id=?` over the existing sync
log, which already carried `user_id` per row). Caught and fixed one real
bug live in Chrome: the Back button from Trip Detail left the screen
blank (`#screens`' own `hidden` was never cleared, only the tab inside
it) - not caught by the test suite, since it's DOM-visibility logic with
no backend equivalent. Test suite: 238 → 285 passing (6 new backend
tests; no JS test runner in this project, so the interaction flows below
are what actually proved the frontend correct).

## Verified-working user flows (driven live, not just tested)

- Sign up → land on Home → log out → reload → still logged out.
- Log in → session survives a page reload (silent refresh via cookie).
- Home / Create / Profile tabs all switch correctly; Profile shows the
  real logged-in user's email, member-since date, and lifetime steps.
- Start a walk → Home shows it as an active journey card with live
  progress, current checkpoint, and step count.
- Opening a journey card → Trip Detail's map, progress hero, stats, and
  checkpoint timeline all render from real data; pause/resume/delete
  from the Home card all round-trip through the real API; Back returns
  cleanly to Home (post-fix).
- Real Google Health step data flowing into trip progress (confirmed
  Day 6, re-confirmed structurally Day 7's per-user rework).
- Light and dark mode both verified on the redesigned screens.
