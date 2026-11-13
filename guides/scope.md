# WorldWalker — Scope

Reference doc for Claude (and anyone else) picking up work on this repo.
For "what shipped and when" see `results.md`; for "what's next" see
`tasks.md`; for "why it's built this way" see `proposal.md`. Day-by-day
narrative logs live in `progress/day*.md` (condensed) and
`docs/prompt_log/` (full blow-by-blow).

## One-line pitch

Turn a person's real, everyday steps (pulled from Google Health) into
progress along a real walking route between two real places on a map —
"walk from Miami to Chicago" one day's steps at a time, with landmarks
and notifications along the way.

## In scope

- **Auth**: email/password signup & login (JWT access + HttpOnly-cookie
  refresh), every trip and Google Health action gated on it.
- **Google Health integration**: OAuth connect/disconnect, a webhook
  that receives step/exercise/heart-rate/sleep notifications, background
  pull tooling, all scoped to a specific logged-in `user_id` — never a
  shared/ambient connection. OAuth CSRF `state` is Postgres-backed
  (`auth/oauth_state.py`), short-lived, and single-use — survives across
  workers, not one `uvicorn` process's memory.
- **Trip planning**: geocode a from/to place (Nominatim), get a real
  walking route (OSRM), sample landmark checkpoints along it, support
  round-trip and one-way.
- **Live progress**: turn incoming steps into an exact position on the
  route (interpolated, not snapped to the nearest waypoint), real
  per-user stride length, workout-aware pace (running ≠ walking).
- **Multi-trip support**: a user can run several trips at once, each
  with its own status (active/paused/completed), pause/resume from its
  Home card.
- **Notifications**: landmark-hit, halfway, and finished events via an
  Observer-pattern dispatcher (`core/facade.py`'s `events`), plus
  optional per-user email checkpoint alerts (`notifications/`).
- **Frontend**: a single-page vanilla-JS app (no framework), 3 screens
  behind a bottom tab bar — **Home** ("My Journeys": active trip cards
  with progress/checkpoint/steps, completed trips below), **Create**
  (plan-a-walk form + globe hero), **Profile** (email, member since,
  lifetime steps) — plus **Trip Detail** (live MapLibre map, progress
  hero, stats, checkpoint timeline), opened from a Home card and
  layered over whichever tab was active. See `web/`.

## Out of scope / explicit non-goals

- **No mocks in the running app.** Every integration (Google Health,
  Nominatim, OSRM) is the real thing, even in dev — `dev_testing/`
  scripts hit real accounts. Tests mock at the HTTP boundary
  (`pytest-httpx`) or patch a specific function, never the whole
  pipeline.
- **Not building a generic fitness tracker.** No manual activity entry,
  no social/leaderboard features, no other wearable integrations beyond
  Google Health (which itself now folds in Fitbit — see
  `services/fitbitMetrics/`, the original Strategy-pattern integration
  this was built on before Google's Fitbit-to-Health-Connect migration).
- **No production ops story yet** — no monitoring, no rate-limit
  handling beyond what's been hit live (Nominatim 429s), no real
  multi-worker deployment plan.

## Tech stack

- **Backend**: FastAPI, SQLAlchemy + Alembic (Postgres), Pydantic,
  `pyjwt` + `bcrypt` for auth, `cryptography` (Fernet) for encrypting
  stored OAuth tokens, `httpx` for outbound calls.
- **Frontend**: vanilla JS (no build step, no framework), Jinja2
  templates, MapLibre GL JS + OpenFreeMap tiles for the live route map,
  a real NASA WebWorldWind globe for the homescreen hero.
- **Infra**: Postgres via `docker-compose.yml` locally; `vercel.json`
  deploys `app.py` directly as a Python app.
- **Tests**: `pytest`, running against a real Postgres
  (`TEST_DATABASE_URL`), not SQLite — see `tests/conftest.py`'s own
  comment on why (UUID/CHECK-constraint behavior differs).

## Module boundaries (who owns what)

| Module | Owns |
|---|---|
| `accounts/` | WorldWalker login itself — signup/login, password hashing, JWT issuance/validation. Knows nothing about Google Health. |
| `auth/` | The Google Health OAuth dance (`google_health_auth.py`, pure HTTP), the CSRF `state` store (`oauth_state.py`, Postgres-backed), per-user connection lifecycle (`connections.py`), the webhook subscription registrar. |
| `core/facade.py` | The **one** entry point the web layer (`app.py`) calls for trip state — journey start/pause/resume/delete/list, recording steps/workouts, building the map-state dict. |
| `travel_logic/` | Pure trip math: geocoding wrapper, route fetching, checkpoint sampling, position-on-route interpolation, description generation. No DB, no HTTP framework. |
| `database/` | SQLAlchemy models, session factory, trip persistence queries, token encryption at rest. |
| `services/google_health/` | The real Google Health HTTP client and the incoming webhook handler — both resolve a specific `user_id`, never an ambient one. |
| `services/fitbitMetrics/` | The original Strategy-pattern per-metric-type parsers (steps/exercise/heart-rate/sleep), still the shape Google Health data flows through. |
| `app.py` | The web layer only — routes, request/response shaping. No travel or auth logic of its own. |
| `web/` | The frontend — templates, CSS, and per-concern JS files (`auth.js`/`auth-ui.js` login, `nav.js` tab switching, `home.js` My Journeys, `app.js` the Create form, `trip.js` Trip Detail, `profile.js` Profile, `globe.js`, `notifications.js` email alerts), each owning one screen/concern and talking to `app.py`'s JSON API. |

## Config

See `.env.example` for the full list. The load-bearing ones: `DATABASE_URL`/
`TEST_DATABASE_URL` (separate DBs), `TOKEN_ENCRYPTION_KEY` (Fernet, for
stored Google OAuth tokens), `JWT_SECRET_KEY` +
`ACCESS_TOKEN_EXPIRE_MINUTES` + `REFRESH_TOKEN_EXPIRE_DAYS` (WorldWalker
login), `WEBHOOK_SECRET` (must match the Google Health subscriber
config), `COOKIE_SECURE` (only `false` for local http dev),
`WEBHOOK_PUBLIC_URL` + `GCP_PROJECT_ID` (real deployment's URL/GCP
project for `auth/register_webhook_subscription.py` - never a tunnel
URL; a tunnel is passed as that script's own CLI argument instead).

## A note on concurrency

This repo has been worked on by more than one Claude Code session at
once (observed directly during the Sep 22 2026 session that wrote this
file — files under `auth/`, `services/google_health/`, and `web/`
changed on disk mid-session from other in-flight work, later landing
together in commit `d7f92cd`). If picking this up fresh, run
`git log --oneline` and `git status` first rather than trusting any
single progress log in isolation — `results.md` is the reconciled,
verified state as of its own last update.
