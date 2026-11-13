# 2026-09-08 — progress_calculator.py: exact position on the route

Discussion/design pass on `travel_logic/progress_calculator.py`, picking up
from `progress/day3.md`'s open items, ending in the interpolation fix +
empty-route guard actually being implemented (see last entry).

## Prompt (verbatim)
> Okay claude refrence this: /Users/srikotala/Documents/WorldWalker/progress/day3.md

## Answer
Read `progress/day3.md` and recapped where the project stands: `travel_logic/`
package, both SQLite DBs, `TravelFacade`, `data/intake.py`, and the Fitbit
webhook are all done; `app.py` (the actual web form/routes) is still the
biggest open piece. Noted `progress_calculator.py` was open in the user's
IDE and asked whether to pick up there or jump to `app.py`.

---

## Prompt (verbatim)
> Yes let's work on progress_calc tell me what the file currently does. and what it should be doing

## Answer
Read `travel_logic/progress_calculator.py` and broke down its three pieces:
1. **Steps → miles** (`resolve_stride_m`/`steps_to_miles`) — stride priority
   chain (real value > gender average > unisex default). Correct, matches plan.
2. **Pace/ETA** (`average_daily_miles`/`estimate_days_remaining`) — empirical
   only, `None` until real progress exists. Correct, matches the bug fix
   from day3.md.
3. **Position on route** (`locate_on_route`) — takes cumulative `miles_walked`
   and returns the *first existing `RoutePoint`* whose own mileage is ≥
   `miles_walked`. Flagged as the real bug: since `route.points` are
   irregularly spaced OSRM samples, this snaps the map position forward in
   jumps every time a new sampled point is crossed, instead of moving
   smoothly — it doesn't interpolate between two bracketing points.

Also flagged: `locate_on_route` throws an unguarded `IndexError` on an
empty `route.points` list (`route.points[-1]`), and the file has no tests
yet (open item from day3.md, still true — this file is pure math, easiest
one in `travel_logic/` to cover).

---

## Prompt (verbatim)
> 1.) Position on route logic: the business logic is that whenever a person makes progress like walking irl, then it's like they're walking on the walking route to the desntiaotn. So then every step is worth a change in coordiantes.
>
> so what is a routePoint doing? since it doesn't carry corrdinates
>
> How can we go about this? Think your answer carefully and meticulously.
>
> 2). Throw a guard for an empty route, but the idea also is that if a route can't be created (if the user gives a route that can't be created via the API, then the web app will catc hthis asking the user to make a new one)

## Answer
**RoutePoint correction**: it does carry coordinates already
(`coords: Coordinates` field in `route_service.py`). What it actually is:
one vertex from OSRM's raw polyline geometry, tagged with cumulative
distance-from-start — a dense but *irregularly spaced* list of fixed
waypoints, not a smooth number line. `locate_on_route` was only ever
landing on existing waypoints, never a point between them, which is why
per-step coordinate movement wasn't really happening.

**Proposed fix**: bracket `miles_walked` between the two consecutive
`RoutePoint`s that straddle it, compute how far between them as a fraction,
and linearly blend their lat/lng by that fraction. Return a *synthesized*
`RoutePoint(coords=interpolated, miles_from_start=miles_walked)` — doesn't
need to exist in `route.points`; `facade.py` only ever reads
`progress.position.coords`, so this is a drop-in. Sketched the rewrite using
`bisect` on the (already sorted) mileage list for an O(log n) bracket
search instead of the current linear scan. Justified straight-line lat/lng
blending (not great-circle/slerp) as accurate enough since OSRM's polyline
vertices are close together — over that short a distance a straight line
and a great-circle arc are indistinguishable.

**Guard split, per the user's framing**: agreed these are two different
things. `RouteService.get_walking_route` already raises `ValueError` when
OSRM can't find a route at all (`route_service.py`) — that's the real
"bad from/to place" case, and it happens in `start_journey`, before a
`Route` object exists. That's exactly the error `app.py` (once built)
should catch and turn into "please pick a different route" — not something
to handle inside `progress_calculator.py`. The guard being added to
`locate_on_route` is a narrower defensive backstop for a `Route` that's
already been constructed but is somehow empty (corrupted session data, a
bug elsewhere) — should never happen if `get_walking_route` did its job, so
it raises the same `ValueError` type for consistency, just to fail loud
instead of crashing with a confusing `IndexError`.

---

## Prompt (verbatim)
> 1. The fix: interpolate between the two bracketing waypoints. -> how does google maps does it? Why do we have to do some guess work here? Is there not a way to grab the exact location on a path? I'd like not to do guesswork

## Answer
Distinguished two different problems that were getting conflated:
- **Google Maps' live-nav problem**: a noisy real GPS reading (~5-20m
  error) that might sit near multiple candidate roads — it has to guess
  which road you're on and where. That's genuine guesswork, solved with
  probabilistic map-matching (Hidden Markov Model / Viterbi over the road
  graph). It's a guess because the *input* is uncertain.
- **Our problem**: no GPS at all — just a step count from Fitbit, converted
  to one distance number, placed on one already-known path. There's no
  ambiguous signal to resolve.

Key point: a polyline is *defined* as straight segments between its
vertices — that's the path's actual shape, not a simplification of a
smoother "true" path every map renderer draws it the same way. So placing
a point at a given arc-length distance along that polyline, via linear
interpolation between the two bracketing vertices, **is** the exact
location at that distance, not an estimate — same idea as a progress bar
placing a dot at 62% along its track. The two places real approximation
does exist in the pipeline are upstream and unavoidable: stride length
(steps → miles is inherently statistical, already documented in day3.md's
fallback chain) and haversine's spherical-Earth assumption (~0.5% error,
standard practice). By the time `miles_walked` reaches `locate_on_route`,
it's already the best number available — that function's job is exact
placement, not estimation.

---

## Prompt (verbatim)
> one question does the path the api return us not have coordiantes for every point on the path? like a point for every gps cord, I'm just wondering why can't we follow the walkign path perfectly? like if a user walked 4000 steps thne we'd calcuate where there location would be on the map? how owuld this calcuation be done

## Answer
Clarified what OSRM's returned points actually represent: a vertex exists
**exactly where the path's direction changes**, not one per meter or per
possible GPS location. A straight stretch of sidewalk gets only its two
endpoints (that's all a straight line needs); a curvy stretch gets many
points close together. So a straight segment between two consecutive OSRM
points *is* the real path in that stretch, not a simplification of it — if
the sidewalk actually curved there, OSM would have recorded another vertex
to capture it. Also noted `route_service.py` already requests
`overview: "full"` — OSRM's maximum-detail setting, not a generalized one.

Walked through the concrete 4000-step calculation end to end:
1. `steps_to_miles(4000, stride)` — at the default 0.762m stride:
   `4000 × 0.762 / 1609.344 ≈ 1.89 miles`.
2. Add to the running cumulative total (e.g. → `12.34` miles since journey
   start).
3. Find the two bracketing `RoutePoint`s, e.g. mile 12.00
   `(41.8000, -87.6500)` and mile 12.50 `(41.8100, -87.6400)`.
4. Fraction between them: `(12.34 - 12.00) / (12.50 - 12.00) = 0.68`.
5. Interpolate: `lat = 41.8000 + 0.68 × (41.8100 - 41.8000) = 41.8068`,
   `lng = -87.6500 + 0.68 × (-87.6400 - (-87.6500)) = -87.6432`.

`(41.8068, -87.6432)` is the exact point 12.34 miles along the real
sidewalk geometry — matches the `locate_on_route` rewrite proposed above.

---

## Prompt (verbatim)
> genius! record that answer to an md file/prompts

## Answer
Wrote this file (`docs/prompt_log/2026-09-08-progress-calculator-position-interpolation.md`),
covering every prompt + answer from this session's `progress_calculator.py`
discussion, per the standing logging convention. Implementation (the
interpolation rewrite + empty-route guard) still pending user go-ahead at
this point.

---

## Prompt (verbatim)
> do the gps coordiantes handle elevatnion and the fact? I'd i think for the interpolation method, let's get as accurate as possible. Let's use a spline + Natural neighbour . Why: Elevation changes are naturally continuous and smooth. Spline creates a smooth, visually appealing surface that matches hills and valleys without blocky artifacts. Natural Neighbor is excellent if your points are clustered tightly along the track but sparse everywhere else.

## Answer
**No elevation data exists in the pipeline today**: `Coordinates` is
lat/lng only, OSRM's GeoJSON geometry is 2D (`[lng, lat]` pairs, no
z-value), and the public OSRM demo server used here doesn't serve
elevation for foot routing at all (needs a self-hosted instance with a
DEM/SRTM dataset baked into the profile — separate infrastructure, not
built). Flagged as a genuinely separate future feature (would need a new
elevation API queried per point), not something to fold into this fix.

**Why Natural Neighbor + spline don't fit even for lat/lng**: both are
built for interpolating a value at an arbitrary point *scattered in open
2D space* surrounded by sample points on multiple sides (e.g. estimating
elevation between scattered survey sensors across a valley) — legitimate
when you don't know the true shape between samples and smooth continuous
terrain is a reasonable assumption. Our problem isn't that shape: the
user's position is constrained to lie exactly on one known 1D line (the
route polyline), so at any moment only two points matter — immediately
before and after, on the line. Nothing "surrounds" the query point, so
Natural Neighbor has nothing to contribute. And a spline would be actively
wrong here, not just unnecessary: we already established a straight
segment between two consecutive OSRM vertices *is* the real path (that's
why no extra vertex was recorded) — a spline would invent curvature at
exactly the place we're already certain the ground truth is straight,
making the position less accurate. Recommended keeping straight-line
arc-length interpolation as the objectively correct choice for a path
whose ground truth we already have exactly, not a "good enough" shortcut.

---

## Prompt (verbatim)
> So then what interpolation fix are we doing to do

## Answer
Recapped the final, agreed method plainly (guard on empty route -> clamp
`miles_walked` -> bisect-search the sorted mileage list for the bracketing
`RoutePoint`s -> linear fraction along that segment -> linear lat/lng
blend by that fraction -> synthesized `RoutePoint`/`Progress`), then
implemented it in `travel_logic/progress_calculator.py`:
- Added `bisect` + `Coordinates` imports.
- Rewrote `locate_on_route`: raises `ValueError` on an empty route
  (consistent with `RouteService.get_walking_route`'s own exception type);
  clamps `miles_walked` into `[0, total_miles]`; bisects the sorted
  mileage list instead of a linear scan; interpolates lat/lng linearly
  between the bracketing points and returns a synthesized `RoutePoint` at
  the exact `miles_walked` mileage.
- `steps_to_miles`, `average_daily_miles`, `estimate_days_remaining`
  untouched.

Verified: `pytest -q` still 24 passed (no prior test covered
`locate_on_route`, so this confirms nothing else broke, not the new logic
itself). Manually checked the exact 4000-step example from two prompts
ago — reproduced `(41.8068, -87.6432)` exactly — plus clamp-past-end,
start-of-route, and the empty-route `ValueError` guard all behaving
correctly.

**Flagged, not done**: still no permanent test file for
`travel_logic/progress_calculator.py` (day3.md's open item) — the checks
above were ad hoc, not added to `tests/`.

---

## Prompt (verbatim)
> write the tests for progress_calculator.py

## Answer
Added `tests/test_progress_calculator.py` (15 tests, matching the style of
`tests/test_fitbit_metrics.py`): `resolve_stride_m`'s priority chain,
`steps_to_miles`, `average_daily_miles`/`estimate_days_remaining`'s
"None until real progress/pace exists" behavior, and `locate_on_route`'s
interpolation (reproducing the exact 12.34-mile worked example from
earlier in this file), exact-vertex hits, start/end clamping, negative-
input clamping, and the empty-route `ValueError` guard. `pytest -q`:
39 passed (24 pre-existing + 15 new). Closes the "no tests for
`progress_calculator.py`" item from `day3.md`.

The follow-up "activities/workout pace" question in this same turn is
logged separately in
`docs/prompt_log/2026-09-08-workout-pace-activity-tracking.md` - different
topic (feeding Fitbit exercise events into position, not the route-position
math this file covers).
