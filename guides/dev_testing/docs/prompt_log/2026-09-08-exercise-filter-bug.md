# 2026-09-08 — Real bug hit live: exercise filter field was wrong

## Prompt (verbatim)
> so i just did a walk and what happened? [pasted server log: webhook 204'd
> fine, then `get_data_points('exercise') -> 400` twice, error body:
> "Member 'exercise.interval.start_time' is not supported for filtering."]
>
> Tell me what went wrong, why, and how you're goign to fix it

## What went wrong
The webhook itself worked (`204 No Content` - Google's notification was
received and acked correctly). The failure was one step later:
`process_notification` tried to pull the real exercise data via
`get_data_points("exercise", ...)`, which builds a filter query assuming
`exercise.interval.start_time` is filterable, the same way `steps` is.
Google rejected it: `INVALID_DATA_POINT_FILTER` -
`"Member 'exercise.interval.start_time' is not supported for filtering."`

## Why
Verified against the real API docs rather than guessing a second time:
`developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list`
confirms `exercise` doesn't support `interval.start_time` at all - it only
supports `interval.civil_start_time`, a **calendar-date** field (the
docs' own example: `civil_start_time >= "2023-11-24"`, a bare date, not a
timestamp). Cross-checked the actual `SessionTimeInterval` type on the
Exercise data point page: it carries both physical fields
(`startTime`/`endTime`) and civil fields (`civilStartTime`/`civilEndTime`,
themselves a date + time-of-day pair, not a single string) - the physical
ones just aren't filterable via the query API for this data type. This
is the same shape of surprise `sleep` already has (`interval.end_time`
only, not `start_time`) - `exercise` turns out to be its own special case
too, just discovered live instead of in advance.

## The fix - two parts, because a coarser filter creates a new problem
1. **`_filter_query`**: for `"exercise"`, filter on
   `interval.civil_start_time` using calendar dates derived from the
   requested window (upper bound bumped a day, to safely include a
   session that started near midnight in the subject's local time).
2. **A new problem this creates**: date-level filtering is coarser than
   what we actually asked for - if two separate exercise sessions happen
   on the same calendar day, the second webhook notification's pull would
   also re-return the *first* session's data point (same civil day), and
   `record_workout` would process it a second time, double-counting its
   distance. Fixed with `_overlaps_window()` in `get_data_points()`: after
   fetching, narrow the results back down to only points whose *own*
   physical `interval.startTime`/`endTime` actually overlaps the requested
   `[start_time, end_time)` - the coarse civil-date filter gets us past
   Google's filterable-field constraint, this narrows back to correctness
   in our own code, without leaking that quirk into
   `process_notification`/`process_health_data`/`backfill_since` (they
   still just call `get_data_points()` and get back exactly what they
   asked for).

## What changed
- **`services/google_health_client.py`**: added `_parse_iso`/`_civil_date`
  helpers, `exercise`'s own branch in `_filter_query`, and
  `_overlaps_window()` applied to `exercise` results in `get_data_points()`.
- **`tests/test_google_health_client.py`**: 3 new tests - the exercise
  filter query's exact shape (civil dates, +1 day upper bound), that a
  same-day-but-outside-the-window point gets dropped, and that a point
  with no interval info is kept rather than risk dropping real data.

## Test result
`pytest -q` → 80 passed (77 -> 80).

## What the user should do now
This walk's exercise/workout data didn't make it in (the pull 400'd
twice - Google's own retry, both hit the same bug). Steps very likely did
still record fine (a separate, unaffected dataType/notification) - only
the workout-specific pull failed. Once the server picks up this fix
(restart it, or it'll auto-reload if running with `--reload`), re-pull
the missed window with `backfill_since("2026-09-08T17:08:14Z",
"2026-09-08T17:14:37Z")` to recover this specific walk instead of losing
it entirely.
