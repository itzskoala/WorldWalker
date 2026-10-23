# tests/test_route_service.py
# build_route's distance bookkeeping - in particular the invariant that
# route.total_distance and route.points[-1].distance_from_start must be
# exactly the same value, not just close. Python 3.12+ made sum() use
# compensated summation for floats, which used to drift from a separate
# manual += accumulator over enough points (see build_route's comment in
# travel_logic/route_service.py) and could push locate_on_route's clamp
# past the end of route.points.
#
# Also OSRMWalkingRouteService's code/status handling - no real network
# calls, requests.get is monkeypatched, same pattern test_geocoder.py uses
# for Nominatim. The fixtures below are OSRM's actual, real responses
# (captured live against https://router.project-osrm.org while
# investigating this - see get_walking_route()'s docstring comment).
# Deliberately NOT tested here: rejecting a route for snapping "too far"
# (e.g. New York -> London, which OSRM answers "Ok" by snapping New York
# ~5,534km away, to Portugal) - that's accepted on purpose. If OSRM can
# place a walking path on the coordinates, it counts, water crossings
# included.

import pytest

from travel_logic import route_service as route_service_module
from travel_logic.route_service import OSRMWalkingRouteService, build_route
from travel_logic.dataclasses.coordinates import Coordinates


def test_build_route_total_distance_exactly_matches_last_point_over_many_points():
    # Enough points, at a granular enough step, for sum()'s compensated
    # summation to diverge from a naive += accumulator if they were ever
    # computed independently again.
    coords = [Coordinates(lat=40.0 + i * 0.0001, lng=-90.0 + i * 0.0001) for i in range(12_000)]
    route = build_route(coords)
    assert route.total_distance == route.points[-1].distance_from_start


def test_build_route_total_distance_matches_last_point_for_a_short_route():
    coords = [Coordinates(41.80, -87.65), Coordinates(41.81, -87.64), Coordinates(41.83, -87.60)]
    route = build_route(coords)
    assert route.total_distance == route.points[-1].distance_from_start


def test_build_route_distance_to_destination_still_reaches_zero_at_the_last_point():
    coords = [Coordinates(41.80, -87.65), Coordinates(41.81, -87.64), Coordinates(41.83, -87.60)]
    route = build_route(coords)
    assert route.points[-1].distance_to_destination == 0.0
    assert route.points[0].distance_to_destination == route.total_distance


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def json(self):
        if self._json_data is None:
            raise route_service_module.requests.exceptions.JSONDecodeError("no json", self.text, 0)
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise route_service_module.requests.HTTPError(f"{self.status_code}")


# Real response, captured live: Fargo -> Minneapolis
# (router.project-osrm.org/route/v1/foot/-96.7898,46.8772;-93.2650,44.9778
# ?overview=false) - an ordinary walking route.
_FARGO_TO_MINNEAPOLIS_OK = {
    "code": "Ok",
    "routes": [{"geometry": {"coordinates": [[-96.7898, 46.8772], [-93.2650, 44.9778]]}, "distance": 376_660.5}],
    "waypoints": [{"distance": 2.180355655}, {"distance": 4.594400234}],
}

# Real response, captured live: New York -> London
# (foot/-74.0060,40.7128;-0.1278,51.5074?overview=false) - "code": "Ok"
# with a ~2,150km route. OSRM snaps the New York point ~5,534km away, to
# Portugal, to make the two ends connect - and that's accepted here on
# purpose (see get_walking_route()'s docstring comment): OSRM placed a
# walking path on real coordinates, water crossing included.
_NEW_YORK_TO_LONDON_OK = {
    "code": "Ok",
    "routes": [{"geometry": {"coordinates": [[-9.497727, 38.78069], [-0.127965, 51.507478]]}, "distance": 2_150_163.9}],
    "waypoints": [{"distance": 5_534_803.173}, {"distance": 14.36820005}],
}

# Real response, captured live: Honolulu -> Los Angeles, HTTP 400
# (foot/-157.8583,21.3069;-118.2437,34.0522?overview=false) - both points
# are real, densely-mapped streets, but genuinely no walkable path
# connects them (no bridge/ferry way modeled across the Pacific). Unlike
# New York -> London above, OSRM can't place *any* path on these
# coordinates - that's still rejected.
_HONOLULU_TO_LOS_ANGELES_NO_ROUTE = {"message": "Impossible route between points", "code": "NoRoute"}


def test_get_walking_route_returns_a_route_for_a_genuine_walk(monkeypatch):
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_FARGO_TO_MINNEAPOLIS_OK))
    route = OSRMWalkingRouteService().get_walking_route(
        Coordinates(46.8772, -96.7898), Coordinates(44.9778, -93.2650)
    )
    assert route.point_count == 2


def test_new_york_to_london_is_accepted_because_osrm_placed_a_route(monkeypatch):
    # OSRM found *a* path (even one that crosses the Atlantic by snapping
    # New York thousands of km away) - that's a deliberate product choice
    # to accept, not an oversight: the app is fine with a route across
    # water. See get_walking_route()'s docstring comment.
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_NEW_YORK_TO_LONDON_OK))
    route = OSRMWalkingRouteService().get_walking_route(Coordinates(40.7128, -74.0060), Coordinates(51.5074, -0.1278))
    assert route.point_count > 0


def test_route_always_starts_and_ends_at_the_real_requested_coordinates(monkeypatch):
    # Regression test for a real, user-reported bug: database/trips.py's
    # create_trip() reads a trip's start/end coordinates straight off
    # route.points[0]/[-1] - so when OSRM's own path starts/ends at
    # wherever it snapped to (here, New York -> Portugal, ~5,534km away)
    # instead of the real requested point, the destination *marker* itself
    # ends up planted at the snap point, and the drawn line stops there
    # too - both wrong, same root cause. The route must always reach the
    # coordinates that were actually asked for, even though OSRM's own
    # geometry (route.points[-2] here) stops at the coastline.
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_NEW_YORK_TO_LONDON_OK))
    start, end = Coordinates(40.7128, -74.0060), Coordinates(51.5074, -0.1278)

    route = OSRMWalkingRouteService().get_walking_route(start, end)

    assert route.points[0].coords == start
    assert route.points[-1].coords == end
    # The real OSRM-returned geometry (Portugal, where New York's end of
    # the path actually snapped to) is still in there, right after the
    # bridged start - nothing about the actual walking path is discarded,
    # just extended to reach the real destination.
    assert route.points[1].coords == Coordinates(38.78069, -9.497727)


def test_an_ordinary_route_does_not_gain_visible_bridging_segments(monkeypatch):
    # A ordinary snap (OSRM landed a few meters from the exact query
    # point, same as the Fargo -> Minneapolis fixture) still triggers the
    # same bridging logic - coordinates from OSRM are essentially never
    # bit-identical to the query float - but the resulting segment is
    # imperceptibly short, not a visible detour.
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_FARGO_TO_MINNEAPOLIS_OK))
    start, end = Coordinates(46.87721, -96.78981), Coordinates(44.97781, -93.26501)

    route = OSRMWalkingRouteService().get_walking_route(start, end)

    assert route.points[0].coords == start
    assert route.points[-1].coords == end
    assert route.points[0].distance_to_next < 5  # meters - not a detour, just float precision
    assert route.points[-1].distance_to_previous < 5


def test_honolulu_to_los_angeles_is_rejected_as_no_route(monkeypatch):
    # Two real, well-mapped points with genuinely no walking path between
    # them at all - OSRM reports "NoRoute" as HTTP 400 with a structured
    # body (confirmed live). This is also a regression guard on a second,
    # independent bug: calling raise_for_status() before checking the
    # body's own "code" field would misreport this real "no route" answer
    # as a transport failure (RouteUnavailable) instead of a genuine "no"
    # (RouteValidation(valid=False)) - see
    # travel_logic/route_validation.py.
    monkeypatch.setattr(
        route_service_module.requests, "get",
        lambda *a, **k: _FakeResponse(_HONOLULU_TO_LOS_ANGELES_NO_ROUTE, status_code=400),
    )
    with pytest.raises(ValueError, match="Impossible route between points"):
        OSRMWalkingRouteService().get_walking_route(Coordinates(21.3069, -157.8583), Coordinates(34.0522, -118.2437))


def test_a_genuine_provider_outage_still_raises_via_http_status(monkeypatch):
    # Unlike NoRoute above, a real outage (a proxy/gateway error page, not
    # OSRM's own JSON) has no "code" field to read - this must fall back
    # to the HTTP status rather than being swallowed as "no route between
    # these points."
    monkeypatch.setattr(
        route_service_module.requests, "get",
        lambda *a, **k: _FakeResponse(json_data=None, status_code=502, text="<html>Bad Gateway</html>"),
    )
    with pytest.raises(route_service_module.requests.HTTPError):
        OSRMWalkingRouteService().get_walking_route(Coordinates(46.8772, -96.7898), Coordinates(44.9778, -93.2650))


# ---------- route_exists() - the yes/no check travel_logic/route_validation.py uses ----------
# Same OSRM responses as get_walking_route()'s own tests above, since
# route_exists() reads the same "code"/"routes" fields - but it must never
# build a Route from them (travel_logic/route_validation.py never uses
# one), so these also guard against that regressing back in.

def test_route_exists_is_true_for_a_genuine_walk(monkeypatch):
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_FARGO_TO_MINNEAPOLIS_OK))
    assert OSRMWalkingRouteService().route_exists(Coordinates(46.8772, -96.7898), Coordinates(44.9778, -93.2650)) is True


def test_route_exists_is_false_when_osrm_reports_no_route(monkeypatch):
    monkeypatch.setattr(
        route_service_module.requests, "get",
        lambda *a, **k: _FakeResponse(_HONOLULU_TO_LOS_ANGELES_NO_ROUTE, status_code=400),
    )
    exists = OSRMWalkingRouteService().route_exists(Coordinates(21.3069, -157.8583), Coordinates(34.0522, -118.2437))
    assert exists is False


def test_route_exists_still_raises_on_a_genuine_provider_outage(monkeypatch):
    # A transport/provider failure is not "no route" - route_exists() must
    # let it propagate, same as get_walking_route(), so
    # travel_logic/route_validation.py can tell the two apart (RouteUnavailable
    # vs. a real RouteValidation(valid=False)).
    monkeypatch.setattr(
        route_service_module.requests, "get",
        lambda *a, **k: _FakeResponse(json_data=None, status_code=502, text="<html>Bad Gateway</html>"),
    )
    with pytest.raises(route_service_module.requests.HTTPError):
        OSRMWalkingRouteService().route_exists(Coordinates(46.8772, -96.7898), Coordinates(44.9778, -93.2650))


def test_route_exists_never_builds_a_route(monkeypatch):
    # The actual point of route_exists() existing separately from
    # get_walking_route(): a caller that only wants yes/no must not pay
    # for build_route()'s per-point distance bookkeeping - see
    # travel_logic/route_validation.py's docstring. Patching build_route
    # itself to blow up proves route_exists() never calls it, for a
    # response shaped just like a real, large route.
    monkeypatch.setattr(route_service_module.requests, "get", lambda *a, **k: _FakeResponse(_FARGO_TO_MINNEAPOLIS_OK))

    def _boom(coords):
        raise AssertionError("route_exists() must not build a Route")

    monkeypatch.setattr(route_service_module, "build_route", _boom)
    assert OSRMWalkingRouteService().route_exists(Coordinates(46.8772, -96.7898), Coordinates(44.9778, -93.2650)) is True
