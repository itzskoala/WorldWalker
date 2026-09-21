# Connecting to Google Health (dev test)

Bypasses travel logic entirely - just proves the OAuth connection works and
pulls real data straight from Google Health.

## 1. Start the app
```bash
venv/bin/python3 -m uvicorn app:app --reload
```

## 2. Connect
Open http://127.0.0.1:8000/ in your browser and click **Connect**. Approve
the Google consent screen (the 4 WorldWalker health scopes). You'll be
redirected back to `/auth/google/callback`, which saves the connection to
Postgres and bounces you back to `/`.

Watch the terminal running uvicorn - you'll see:
```
🔐 auth: issued state ...
🔐 auth: code exchanged (scopes: ...)
🔐 auth: new WorldWalker user created (provider_user_id=...)
🔐 auth: connection established
```

## 3. Pull real data
In a second terminal:
```bash
venv/bin/python3 dev_testing/pull_data.py                 # last 24h (default)
venv/bin/python3 dev_testing/pull_data.py --today          # local midnight -> now
venv/bin/python3 dev_testing/pull_data.py --hours 6         # last 6h
venv/bin/python3 dev_testing/pull_data.py --start 2026-09-20 --end 2026-09-21   # explicit window
```
Prints steps (server-side rollup total), heart rate, sleep, and activity
for the requested window, plus your profile. `--today` uses this
machine's local time zone (not UTC) - if your system clock/timezone is
set correctly, that's "today" in your own time. `--start`/`--end` accept
a bare date or a full timestamp; times with no timezone offset are read
as local too. Re-run any time - it always reads whatever's currently
connected, no re-auth needed unless you disconnect. `--help` lists all
options.

## Notes
- Needs `credentials.json` (OAuth client) and `DATABASE_URL` (Postgres) in
  `.env` - both already set up if `venv/bin/python3 -m alembic current`
  shows a revision.
- No webhook/service-account setup required for this - that's only for
  real-time push notifications, not a direct pull.
- Empty results just mean Google Health has nothing in that window (e.g.
  no workout logged) - not a bug. Widen the window with `--hours`/`--start`/`--end`.
- To disconnect: `curl -X POST http://127.0.0.1:8000/auth/google/disconnect`
