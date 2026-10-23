# tests/test_route_validation.py
# validate_walking_route() - the immediate "can I walk this" check behind
# POST /api/route/validate (app.py), fired by CreatePage.tsx right after
# both Where From/Where To fields resolve to coordinates. No real network
# calls or database - a stub RouteService stands in for
# OSRMWalkingRouteService, same pattern test_geocoder.py uses for
# Nominatim.
#
# validate_walking_route() only ever calls route_exists() (a plain
# yes/no), never get_walking_route() - see its own docstring on why: it
# never uses the actual Route, and get_walking_route() always builds one.
# OSRMWalkingRouteService.route_exists()'s own "OSRM's no-route answer ->
# False, a transport failure -> let the exception propagate" translation
# is tested directly in test_route_service.py; this stub stands in one
# layer up, already speaking that same plain bool/raise contract.

import pytest
import requests

from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.route_validation import (
    MIN_WALKING_ROUTE_METERS,
    RouteUnavailable,
    RouteValidation,
    validate_walking_route,
)

MINNEAPOLIS = Coordinates(lat=44.9778, lng=-93.2650)
SAINT_PAUL = Coordinates(lat=44.9537, lng=-93.0900)  # a real, several-mile walk from Minneapolis


class _StubRouter:
    """error, if given, is raised from route_exists() instead of returning
    exists - and every call (whether it happens at all, and with what
    arguments) is recorded, so a test can assert OSRM was never actually
    reached."""

    def __init__(self, exists=True, error=None):
        self._exists = exists
        self._error = error
        self.calls = []

    def route_exists(self, start, end):
        self.calls.append((start, end))
        if self._error is not None:
            raise self._error
        return self._exists


def test_same_location_is_invalid_without_calling_osrm():
    router = _StubRouter()
    result = validate_walking_route(router, MINNEAPOLIS, MINNEAPOLIS)
    assert result == RouteValidation(valid=False, reason="too_close")
    assert router.calls == []


def test_points_under_the_threshold_are_invalid_without_calling_osrm():
    nearby = Coordinates(lat=MINNEAPOLIS.lat + 0.001, lng=MINNEAPOLIS.lng)  # ~111m north
    router = _StubRouter()
    result = validate_walking_route(router, MINNEAPOLIS, nearby, min_distance_m=1609.344)
    assert result == RouteValidation(valid=False, reason="too_close")
    assert router.calls == []


def test_threshold_is_configurable_per_call():
    # Same two points as the "under threshold" case above, but with a
    # smaller min_distance_m passed explicitly - now far enough apart that
    # OSRM does get asked, and the stub reports a real route.
    nearby = Coordinates(lat=MINNEAPOLIS.lat + 0.001, lng=MINNEAPOLIS.lng)  # ~111m north
    router = _StubRouter()
    result = validate_walking_route(router, MINNEAPOLIS, nearby, min_distance_m=50.0)
    assert result == RouteValidation(valid=True)
    assert router.calls == [(MINNEAPOLIS, nearby)]


def test_default_threshold_is_about_a_mile():
    assert MIN_WALKING_ROUTE_METERS == pytest.approx(1609.344)


def test_no_walking_route_is_invalid_with_a_reason():
    router = _StubRouter(exists=False)
    result = validate_walking_route(router, MINNEAPOLIS, SAINT_PAUL)
    assert result == RouteValidation(valid=False, reason="no_route")


def test_valid_walking_route_keeps_both_locations():
    router = _StubRouter(exists=True)
    result = validate_walking_route(router, MINNEAPOLIS, SAINT_PAUL)
    assert result == RouteValidation(valid=True)


def test_a_provider_failure_raises_rather_than_reporting_no_route():
    # Distinguishes "OSRM said no" (route_exists() returns False ->
    # reason="no_route") from "couldn't even ask OSRM" (RouteUnavailable)
    # - a caller must not treat a transient failure the same as a real
    # "no route" answer (that's what would silently clear a field just
    # because the provider hiccuped).
    router = _StubRouter(error=requests.ConnectionError("boom"))
    with pytest.raises(RouteUnavailable):
        validate_walking_route(router, MINNEAPOLIS, SAINT_PAUL)


def test_a_timeout_also_raises_rather_than_reporting_no_route():
    router = _StubRouter(error=requests.Timeout("timed out"))
    with pytest.raises(RouteUnavailable):
        validate_walking_route(router, MINNEAPOLIS, SAINT_PAUL)


def test_a_malformed_response_raises_rather_than_reporting_no_route():
    # requests.exceptions.JSONDecodeError (a garbled/truncated OSRM body)
    # is both a RequestException *and* a ValueError - route_exists() must
    # still treat it as "couldn't check" (propagated here, then raised as
    # RouteUnavailable), not translate it into a plain "no route" False.
    router = _StubRouter(error=requests.exceptions.JSONDecodeError("bad json", "", 0))
    with pytest.raises(RouteUnavailable):
        validate_walking_route(router, MINNEAPOLIS, SAINT_PAUL)
