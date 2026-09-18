# 2026-09-08 — Workout pace feeding route position

Design discussion + implementation for making Fitbit/Google Health
exercise (workout) events, not just the raw daily step count, drive
position on the route - with a real, device-measured pace differentiating
running from walking instead of one flat stride constant. Continues same
day's `docs/prompt_log/2026-09-08-progress-calculator-position-interpolation.md`
(the route-position math itself, a different topic from this file).

## Prompt (verbatim)
> Also let's work on the activties -> right now I now steps coutn determines a person's distanceo nthe map. We use just the step count daily from Fitbit, I'd also like it so that, recongize the pace if a user created a workout and then use that pace calculation to determine where a person's gps coordationes would be time = distance/speed. If a user never inputs a workput then just default to the default step counter + using their stride legnth. Regardless the default step counter daily metric should always be on.
>
> how could we do this? plan and tell me

## Answer
Read `services/fitbit_pydantic_schema.py`'s `ExerciseData`/`ExerciseMetricsSummary`
and `services/fitbit_service.py` - confirmed the `"exercise"` webhook case
was wired to nothing (just a print statement), only `"steps"` fed
`record_steps`. Proposed a 4-part plan:
1. Compute a workout's own distance, priority order: `distance_millimeters`
   direct > steps x stride > skip if neither present.
2. Derive a real personal stride (`distance ÷ steps`) from a workout that
   reports both, calibrating `resolve_stride_m`'s existing priority chain
   with real data instead of waiting on the unconfirmed profile field.
3. Avoid double-counting: Google likely fires both a `"steps"` event and
   an `"exercise"` event for the same real walk. Track each workout's time
   interval on the session; skip a `"steps"` event's distance if its
   interval falls entirely inside an already-recorded workout interval.
   Flagged the known approximation: partial overlaps aren't pro-rated.
4. Wiring: `"steps"` case passes its interval through; new
   `travel_facade.record_workout` wired to `"exercise"`, reusing the
   landmark/DB/notify plumbing `record_steps` already has.

Deliberately did NOT propose live extrapolation into future/unknown time
(projecting position forward using a finished workout's pace until the
next real sync) - reasoned that every event we get describes an interval
that's already over (pulled after the fact, per `fitbit_service.py`'s own
docstring), so guessing forward would repeat the guessed-6000-steps/day
ETA mistake already fixed once. Flagged as a legitimate but separate
display-layer feature if ever wanted.

---

## Prompt (verbatim)
> Give me an example of how thigns would work from initial input

## Answer
Walked through a concrete two-day timeline with real numbers: `start_journey`
seeds a session with no calibrated stride yet -> an ordinary morning steps
event (3000 steps, no workout) uses the generic male-average stride -> an
evening tracked workout (45 min, distance_millimeters=3.2km, steps=4200)
adds its own measured distance directly AND calibrates a real stride
(0.7619 m/step) from distance÷steps, recording its interval as covered ->
a duplicate `"steps"` event for that same 18:00-18:45 window gets its
distance skipped (interval already covered) but its raw step count still
logged so `today_steps()` stays accurate -> the next morning's plain steps
event now uses the newly-calibrated 0.7619m stride instead of the generic
0.78m male average. Closed with locate_on_route (from the earlier design)
turning whatever `miles_walked` results into an exact map position.

---

## Prompt (verbatim)
> Good but I think you acutally are able to pull paces from workouts. I'd like that to be invovled in the calcuation of distance on the map obviously running will take you further than walking

## Answer
Corrected the plan: today's `ExerciseMetricsSummary` schema has no raw
pace/speed field (only calories/distance/steps/heart-rate), so pace can
currently only be derived (distance ÷ duration), not read directly -
flagged as worth a live-API check given `day3.md` already notes this
schema doesn't model every field the real API returns. Identified the
actual bug the user was pointing at: the steps-only fallback (case 2 in
the distance priority chain) applied one flat WALKING stride to any
exercise type, including a run - undercounting a run's real distance.
Proposed fixing it by keying stride/pace calibration per `exercise_type`
(`stride_by_type`/`pace_by_type` dicts) instead of one flat session-wide
value, with the same three-tier priority as gender-based stride: real
per-type calibrated value > generic per-type default (e.g. a running
stride default vs. a walking one, same category of assumption as the
existing `MALE_STRIDE_M`/`FEMALE_STRIDE_M`) > existing flat default only
if the type is unrecognized. Raised one open question rather than
deciding it silently: should non-foot exercise types (biking, swimming)
count toward route progress at all?

---

## Prompt (verbatim)
> Non-foot excersies should not be counted as progress for now. Only foot excersies for now.
>
> Also yes update ExerciseMetricsSummary to be pulling average pace/pace from acitivties and use that calcuation

## Answer
Before adding any field, fetched the real API reference
(`developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints#exercise`)
rather than guessing a field name - confirmed two real fields exist:
`averageSpeedMillimetersPerSecond` and `averagePaceSecondsPerMeter`, plus
the foot-based exercise type enum values (`WALKING`, `POWER_WALKING`,
`INCLINE_WALK`, `TREADMILL_WALK`, `STROLLER_WALK`, `RUNNING`, `TRAIL_RUN`,
`INCLINE_RUN`, `HIKING`, `NORDIC_WALKING`).

## What changed
- **`services/fitbit_pydantic_schema.py`**: `ExerciseMetricsSummary` gains
  `average_speed_mm_per_s` (alias `averageSpeedMillimetersPerSecond`) and
  `average_pace_s_per_m` (alias `averagePaceSecondsPerMeter`), both
  optional.
- **`travel_logic/progress_calculator.py`** (pure logic, no I/O, matches
  the file's existing convention):
  - `FOOT_EXERCISE_TYPES` - the on-foot subset of the exercise type enum;
    anything else never counts toward progress.
  - `DEFAULT_STRIDE_M_BY_TYPE` - generic running/hiking/etc. stride
    defaults, same role as the existing gender averages.
  - `WorkoutCalibration` dataclass + `calibrate_from_workout()` - what one
    workout teaches us about this user's real stride (`distance ÷ steps`)
    and/or pace (device-reported average speed/pace, else
    `distance ÷ duration` as a fallback) for its activity type, to reuse
    on a future workout of the same type missing that data.
  - `workout_distance_miles()` - a completed workout's distance, in
    priority order: direct `distance_mm` > device-reported average
    speed/pace x duration > steps x calibrated-or-default per-type stride
    > calibrated per-type pace x duration. Returns `None` (not a guess)
    if the type isn't foot-based or nothing usable was given.
  - `interval_duration_hours()` / `interval_within_any()` - ISO-timestamp
    helpers; the latter is the double-count guard (is a `"steps"` event's
    window fully inside an already-credited workout's window).
- **`core/facade.py`**:
  - Session gains `stride_by_type`, `pace_by_type_mph`, `workout_intervals`.
  - `record_steps` now takes an optional `interval`; if it's fully covered
    by a workout already recorded, the WHOLE event is skipped (not just
    its distance) - see bug note below.
  - New `record_workout(user_id, exercise)`: computes distance via
    `workout_distance_miles`, applies it to `miles_walked`, saves any new
    calibration, and - only when real distance was actually credited -
    records the workout's interval as covered (so a workout with
    insufficient data to compute anything doesn't also suppress the
    fallback general steps event for the same window). Reuses the same
    landmark-notify/DB-record flow `record_steps` has.
- **`services/fitbit_service.py`**: `"steps"` case now passes `obj.interval`
  through; `"exercise"` case wired to `travel_facade.record_workout`
  (was previously just a print statement).
- **Tests**: `tests/test_progress_calculator.py` gained 22 tests for the
  new pure functions (foot-type gating, each priority tier of
  `workout_distance_miles`, `calibrate_from_workout`'s stride/pace
  derivation and priority, the interval helpers). New
  `tests/test_facade.py` (5 tests) - `record_workout` crediting distance
  and calibrating stride, `record_steps` skipping an already-covered
  window, an uncovered window still adding distance normally, a non-foot
  workout adding no distance and not blocking steps, and a workout with
  no distance/steps falling back to a calibrated pace from a prior run of
  the same type. DBs in these tests point at `tmp_path`, never the real
  `data/total_distance.db`.

## Bug caught during testing, fixed before landing
First pass at `record_steps` kept logging the raw step count to the DB
even when its distance was being skipped as already-covered - reasoning
was "the daily step count should always be on." That was wrong: it
double-counted the *step total* (`today_steps()`/`total_steps()`) the same
way the original bug double-counted *distance*, since `record_workout` had
already logged that same step count via its own DB row. A test written to
assert `today_steps() == 4200` after a duplicate steps event caught this
(got `8400`). Fixed: when a `"steps"` event's interval is already covered
by a recorded workout, skip the event entirely (no distance, no DB row) -
it's Google reporting the same real walk twice through two different
streams, not two real amounts of activity.

## Decisions made without asking (flagged here, not silent)
- No live extrapolation into unknown future time - every event describes
  an interval already over; guessing forward would repeat the fixed
  guessed-ETA mistake. Flagged as a separate possible feature if wanted.
- Partial interval overlaps between a `"steps"` event and a workout aren't
  pro-rated - a steps event only partly inside a workout window is still
  skipped/kept whole, not split proportionally. Approximation, not hidden.

## Test result
`venv/bin/python3 -m pytest -q` → 61 passed. Confirmed `data/total_distance.db`'s
mtime was untouched by the new tests (they use `tmp_path`).

## Open items / not done
- No live probe yet confirming Google Health's real webhook payload
  actually populates `averageSpeedMillimetersPerSecond`/
  `averagePaceSecondsPerMeter` for a real device - schema now models them
  per the REST reference, but only a live event will confirm they're
  actually sent.
- `FOOT_EXERCISE_TYPES` is the on-foot subset found via one documentation
  fetch, not exhaustively cross-checked against the full 200+-value enum -
  revisit if a foot-based type turns out to be missing from it.
