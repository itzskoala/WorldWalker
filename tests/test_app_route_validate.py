# tests/test_app_route_validate.py
# POST /api/route/validate - the HTTP layer around
# travel_logic.route_validation.validate_walking_route() (see
# tests/test_route_validation.py for the validation rules themselves).
# No real OSRM calls - app.py's module-level _router is monkeypatched,
# same pattern tests/test_app_journey_routes.py uses for _router/_geocoder.
# No trip is ever created by this endpoint, so no database session is
# needed here (unlike /api/journey/start's tests).

import requests
from fastapi.testclient import TestClient

import app as app_module
from app import app

client = TestClient(app)

_BODY = {"from_lat": 44.9778, "from_lng": -93.2650, "to_lat": 44.9537, "to_lng": -93.0900}


def test_valid_route_reports_valid(monkeypatch):
    monkeypatch.setattr(app_module._router, "route_exists", lambda start, end: True)
    response = client.post("/api/route/validate", json=_BODY)
    assert response.status_code == 200
    assert response.json() == {"valid": True, "reason": None}


def test_no_route_reports_invalid_with_a_reason(monkeypatch):
    monkeypatch.setattr(app_module._router, "route_exists", lambda start, end: False)
    response = client.post("/api/route/validate", json=_BODY)
    assert response.status_code == 200
    assert response.json() == {"valid": False, "reason": "no_route"}


def test_same_location_reports_invalid_without_calling_osrm(monkeypatch):
    def fail_if_called(start, end):
        raise AssertionError("OSRM should never be called for an identical point")

    monkeypatch.setattr(app_module._router, "route_exists", fail_if_called)
    same_point = {"from_lat": 44.9778, "from_lng": -93.2650, "to_lat": 44.9778, "to_lng": -93.2650}
    response = client.post("/api/route/validate", json=same_point)
    assert response.status_code == 200
    assert response.json() == {"valid": False, "reason": "too_close"}


def test_a_provider_failure_is_a_502_not_a_false_valid(monkeypatch):
    def raise_connection_error(start, end):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(app_module._router, "route_exists", raise_connection_error)
    response = client.post("/api/route/validate", json=_BODY)
    assert response.status_code == 502
    assert "valid" not in response.json()


def test_out_of_range_latitude_is_rejected_with_a_400_not_a_500(monkeypatch):
    def fail_if_called(start, end):
        raise AssertionError("OSRM should never be called for an out-of-range coordinate")

    monkeypatch.setattr(app_module._router, "route_exists", fail_if_called)
    bad_body = {**_BODY, "from_lat": 999}
    response = client.post("/api/route/validate", json=bad_body)
    assert response.status_code == 400


def test_non_finite_coordinate_is_rejected_with_a_400_not_a_500(monkeypatch):
    # Python's json module accepts "Infinity"/"NaN" as an extension, so
    # this reaches the endpoint as a real (non-finite) float rather than a
    # parse error. A pydantic Field(ge=..., le=...) constraint would also
    # reject it, but rendering that rejection would itself 500 - Starlette's
    # JSONResponse can't serialize a raw inf/nan echoed back in the error
    # body (allow_nan=False, per the JSON spec) - so this must come back
    # as this endpoint's own hand-built 400, not a 422/500.
    def fail_if_called(start, end):
        raise AssertionError("OSRM should never be called for a non-finite coordinate")

    monkeypatch.setattr(app_module._router, "route_exists", fail_if_called)
    response = client.post(
        "/api/route/validate",
        content=b'{"from_lat": Infinity, "from_lng": -93.2650, "to_lat": 44.9537, "to_lng": -93.0900}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid coordinates."}


def test_nan_coordinate_is_rejected_with_a_400_not_a_500(monkeypatch):
    # NaN fails every ge/le comparison too, but is its own non-finite case
    # worth covering separately - math.isfinite() is what actually catches
    # it (plain range checks like `-90 <= lat <= 90` would too, since any
    # comparison against NaN is False, but that's incidental, not the
    # documented reason it's rejected).
    def fail_if_called(start, end):
        raise AssertionError("OSRM should never be called for a NaN coordinate")

    monkeypatch.setattr(app_module._router, "route_exists", fail_if_called)
    response = client.post(
        "/api/route/validate",
        content=b'{"from_lat": NaN, "from_lng": -93.2650, "to_lat": 44.9537, "to_lng": -93.0900}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "Invalid coordinates."}
