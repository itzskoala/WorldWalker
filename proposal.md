# WorldWalker — Proposal

The product idea and the design decisions behind it. See `scope.md` for
hard boundaries, `results.md` for what's actually been built,
`tasks.md` for what's left.

## The idea

From the original README: *"a webapp that connects to my [wearable] and
uses my step count to allow me to 'walk the world.'"* Concretely: pick a
real starting point and a real destination anywhere on Earth, get a real
walking route between them, and then every step taken in real life (via
Google Health, which absorbed Fitbit's API in 2025 — see `progress/day1.md`
for the migration research) advances your position along that route.
Pass a real city along the way and it's a landmark, celebrated with a
notification. Reach the end and the trip completes.

The hook is that it's not a simulation or a game with fake distances —
it's your actual daily step count mapped onto an actual road network, so
"I walked to Chicago this month" is a true statement about a real route,
not a made-up milestone.

## Why it's architected this way

- **A facade, not a pile of routes.** `app.py` never touches travel
  logic or the database directly — every trip action goes through
  `core.facade.travel_facade`, one object with a small public surface
  (`start`, `pause_journey`, `resume_journey`, `get_map_state`,
  `list_trips`, `delete_journey(s)`, `record_steps`/`record_workout`).
  Keeps the web layer dumb and the trip logic testable without spinning
  up FastAPI at all.

- **Strategy pattern for metric types.** `services/fitbitMetrics/`
  parses steps, exercise, heart rate, and sleep as separate strategies
  behind a common interface, because each arrives in a genuinely
  different shape from the API and gets interpreted differently
  (exercise minutes move you along the route at a measured pace;
  passive steps use a flat stride length). This predates the Google
  Health migration and survived it — Google Health data still flows
  through the same per-metric shape.

- **Observer pattern for notifications.** `core/facade.py` fires
  `events.notify("landmark"/"halfway"/"finished", message)` and doesn't
  know or care who's listening — decouples "a milestone happened" from
  "how the user finds out," so a new notification channel (push, email,
  whatever) is a new observer, not a new `if` branch threaded through
  the trip logic.

- **Real integrations everywhere, including dev.** No mock Google Health
  server, no fake route data in `dev_testing/` — `simulate_walk.py` and
  `pull_data.py` hit the real connected account. This was a deliberate
  call early on (see `progress/day2.md`): a fake pipeline that "works"
  proves nothing about whether the real one will, and this project has
  hit real integration bugs (API pagination, rate limits, token refresh
  edge cases) that a mock would have hidden.

- **A WorldWalker identity is the source of truth, not Google's.** The
  Sep 22 2026 auth rework (`progress/day7.md`) deliberately made the
  login system (`accounts/`) independent of and prior to the Google
  Health connection (`auth/`) — you sign up for WorldWalker first, *then*
  optionally link a Google account to that identity. This was chosen
  over "log in with Google" specifically so a user's trips, login
  session, and identity don't depend on keeping a third-party OAuth
  grant alive, and so `provider_user_id` (Google's identity) can never
  be trusted as the primary key for anything WorldWalker-side.

- **No framework on the frontend.** Vanilla JS, one file per concern
  (`auth.js` owns the token/refresh contract, `trip.js` owns the live
  map, `home.js` owns the homescreen activity card, `app.js` owns
  search/autocomplete/trips-panel/theme), talking to `app.py`'s JSON API
  over plain `fetch`. Chosen to keep the app inspectable and dependency-
  free for a solo/small project, not a rejection of frameworks in
  general — revisit if the frontend's state management outgrows this.

## Design language (homescreen, Sep 22 2026)

The homescreen was redesigned around Strava's information hierarchy —
*where am I → what have I done → what can I do next* — without copying
its visual style. A warm, outdoor-fitness palette (cream background,
deep charcoal ink, forest-teal as the one primary/brand accent for
movement and progress, a muted sky blue reserved for maps/routes and
secondary info) replaced the earlier Google-Flights-styled blue/white
theme, applied through the existing CSS custom-property system so the
whole app re-skinned consistently rather than picking up a mismatched
homescreen. The result stays deliberately low on cards/sections per the
brief's KISS instruction: one activity-summary card, one plan-a-walk
card, no dashboard sprawl.

## What "done" looks like

Not a fixed scope with a ship date — this is a personal project that
grows a capability at a time (see `results.md`'s day-by-day arc). The
recurring bar for "done" on any given piece has been: it works against
the real external service, it's covered by a test that would actually
catch a regression, and it's been driven end-to-end at least once
(a live browser session or a real webhook notification), not just typed
and assumed correct.
