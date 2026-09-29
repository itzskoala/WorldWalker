# WorldWalker — Tasks

Open items and backlog, most load-bearing first. Check this against
`git log`/`git status` before starting anything — items here get
resolved (or superseded) by whichever session picks them up next, and
this file can lag by a session. See `results.md` for what's already
shipped, `scope.md` for what's explicitly not planned.

## Known gaps (flagged in prior sessions, not yet fixed)

- [x] **Webhook subscription registration now takes a real public URL,
  cleanly.** `auth/register_webhook_subscription.py` accepts
  `WEBHOOK_PUBLIC_URL`/`GCP_PROJECT_ID` from `.env` (CLI args still
  override, for one-off dev-tunnel runs) and refuses to register a
  localhost/non-https address, so a config mistake fails loudly instead
  of silently registering a subscription that can never deliver
  anything. **Still open**: nobody has actually run it against a real
  deployed URL yet — the script is correct and tested
  (`tests/test_register_webhook_subscription.py`), but real-time push
  is not yet *confirmed working* in production. Don't claim it works
  until that run has happened.
- [x] **OAuth CSRF `state` store moved to Postgres.** New
  `auth/oauth_state.py` + `database.models.OAuthState`
  (migration `d0451e36b216`) - a state now survives across workers, has
  a 10-minute TTL, is deleted (single-use) on every consume whether
  valid or not, and cascades away if the user is deleted. Cleared the
  matching non-goal from `scope.md`. See `tests/test_oauth_state.py`.
  `auth/google_health_auth.py` no longer tracks state at all - it stays
  pure OAuth HTTP, taking an already-issued state as a plain argument.
- [ ] **`start_journey` isn't atomic.** A Postgres trip row can commit
  and then the response still fail if a downstream read (the SQLite
  metrics store) errors — leaves an orphaned trip with no user-visible
  confirmation. Surfaced Day 6, not yet fixed.
- [x] **Pre-login `/` banner no longer claims a connection status.**
  `app.py`'s `index()` always passes `is_connected=False` (a neutral
  default, not a check — the route makes no database call at all now);
  the trips-panel buttons that used to be conditioned on the old
  single-tenant flag are now unconditionally rendered and rely on
  `#app-shell`'s existing auth-gate wrapper for real visibility, so
  removing that conditional doesn't leak the topbar pre-login. See
  `tests/test_index_route.py`.
- [ ] **Dev-machine scratch data accumulates.** `data/total_distance.db`
  and `data/geocode_cache.json` are gitignored but grow during testing —
  worth an occasional `rm` if step counts start looking unrealistic.

## Frontend / Home / Create / Profile follow-ups

- [x] **Trip Detail's Back button left a blank screen.** `trip.js`'s
  `hide()` restored `#tab-bar` and called `Nav.showScreen("home")`, but
  never cleared `#screens`' own `hidden` (only `enterTripView()` set
  it) - `Nav.showScreen()` only toggles the individual `.screen`
  elements inside `#screens`, not the wrapper itself. Fixed live, caught
  by manual browser testing, not the test suite (no JS test runner in
  this project - see `scope.md`'s note on that).
- [x] **Dark mode verified on the redesigned screens**, not just
  spot-checked - Home, Create, Profile, and Trip Detail all checked live
  in dark mode.
- [ ] **Home's active-trip cards fetch full state per trip
  (N+1)** (`web/static/js/home.js`'s `render()`) - fine at personal-app
  scale (a handful of simultaneous trips), but if this app ever needs to
  scale to many concurrent trips per user, `_trip_summary` growing
  `total_steps`/current-checkpoint fields directly would be the real
  fix, not client-side fan-out.
- [ ] **Mobile viewport (~420px) wasn't visually re-verified after the
  3-screen redesign** - the automated browser tool's window resize
  didn't take effect on the tab actually being driven (window resized,
  `document.documentElement.clientWidth` didn't follow), so this is
  covered by the same responsive CSS patterns already used elsewhere,
  not by a fresh screenshot. Worth an actual phone/DevTools check before
  calling mobile done.
- [ ] **Connect-button disconnect confirmation is a plain
  `window.confirm()`.** Consistent with the rest of the app's
  no-custom-modals approach so far, but worth a real confirmation UI if
  more destructive actions like this get added.

## Explicitly deferred (do not start without a go-ahead)

- **Bulk multi-select was dropped when the trips-panel drawer was
  retired for the Home screen** (Sep 23 2026 redesign) - Home's cards
  are single-select only now (pause/resume/delete per card). Restoring
  bulk actions is a deliberate product call, not a bug to silently fix.
- **Home's card list beyond active/completed** (sorting, filtering,
  named/favorited trips) needs the user's direction first, not assumed
  scope.
- **Any second wearable/data source beyond Google Health.** Scope
  explicitly stops at Google Health (which already folds in Fitbit).

## Housekeeping

- [ ] `.agents/`, `.claude/`, `skills-lock.json` are currently untracked
  — confirm with the user whether these should be committed or
  `.gitignore`d before the next commit that touches them.
- [ ] `credentials.json`, `service-account.json`, `.tokens.json` are
  real credential files sitting in the repo root (gitignored — verify
  that's actually true with `git check-ignore` before ever running a
  broad `git add`).
