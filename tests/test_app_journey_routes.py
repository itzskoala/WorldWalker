# tests/test_app_journey_routes.py
# app.py's trip-facing endpoints - all gated on a logged-in user now
# (accounts.dependencies.get_current_user), not a Google Health
# connection. Runs against the real app, with SessionLocal patched (see
# tests/conftest.py's patched_session fixture) so all of it stays inside
# this test's own rolled-back transaction.

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import event

from app import app
from core.facade import travel_facade
from database.models import StepSyncLog, User
from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint

client = TestClient(app)

TOTAL_DISTANCE_M = 10_000.0


def _short_route() -> Route:
    return Route(
        points=[
            RoutePoint(Coordinates(0.0, 0.0), point_number=1, distance_from_start=0.0,
                       distance_to_destination=TOTAL_DISTANCE_M, distance_to_previous=0.0, distance_to_next=TOTAL_DISTANCE_M),
            RoutePoint(Coordinates(0.0, 0.09), point_number=2, distance_from_start=TOTAL_DISTANCE_M,
                       distance_to_destination=0.0, distance_to_previous=TOTAL_DISTANCE_M, distance_to_next=0.0),
        ],
        total_distance=TOTAL_DISTANCE_M,
        point_count=2,
    )


def _mock_geocoding_and_routing(monkeypatch):
    """No real Nominatim/OSRM calls in a test - start_journey only needs a
    route back. Checkpoint *positions* are generated synchronously from
    the route (no network call - see travel_logic/checkpoints.py's
    generate_checkpoint_positions()), so _short_route()'s 10km still
    produces a few of them with blank names. bootstrap_checkpoint_metadata
    is the background job that would normally resolve those names/
    descriptions (and, for any later sync, the proximity-reveal
    lookahead would resolve more) - stubbed out here to a no-op so no
    test ever launches a real background thread that outlives it and
    goes on to hit Nominatim/the real database after this test's own
    monkeypatches/session have already been torn down."""
    monkeypatch.setattr(travel_facade._geocoder, "geocode", lambda place: Coordinates(0.0, 0.0))
    monkeypatch.setattr(travel_facade._router, "get_walking_route", lambda start, end: _short_route())
    monkeypatch.setattr("core.facade.get_profile", lambda user_id: {})
    monkeypatch.setattr(travel_facade, "bootstrap_checkpoint_metadata", lambda trip_id: None)


def test_start_journey_requires_authentication(patched_session):
    response = client.post("/api/journey/start", json={"from_place": "Miami", "to_place": "Chicago"})
    assert response.status_code == 401


def test_start_journey_requires_both_places(user_id, auth_headers):
    response = client.post(
        "/api/journey/start", json={"from_place": "", "to_place": "Chicago"}, headers=auth_headers(user_id)
    )
    assert response.status_code == 400


def test_start_journey_returns_full_map_state_for_the_logged_in_user(user_id, auth_headers, monkeypatch):
    _mock_geocoding_and_routing(monkeypatch)

    response = client.post(
        "/api/journey/start", json={"from_place": "Miami", "to_place": "Chicago"}, headers=auth_headers(user_id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coming_soon"] is False
    assert body["to_place"] == "Chicago"
    assert len(body["route_geometry"]) == 2
    # Every checkpoint's position exists immediately now (see
    # database/trips.py's create_trip()) - just with a blank name/
    # description, since nothing's resolved that yet, and not yet
    # revealed, since the walker hasn't moved.
    assert len(body["checkpoints"]) == body["total_checkpoints"] > 0
    assert all(c["name"] == "" and c["revealed"] is False for c in body["checkpoints"])
    assert body["discovered_checkpoints"] == 0
    assert body["percent_complete"] == 0.0


def _long_distance_route(point_count: int = 19_659, total_distance_m: float = 2_753_583.0) -> Route:
    """A synthetic stand-in for a real cross-country OSRM response - same
    order of magnitude as the real Jacksonville, FL -> Fargo, ND route
    (~2,754km, 19,659 geometry points) this is a regression test for.
    Built directly rather than via build_route()'s per-pair haversine
    loop - this only needs realistic sizes for create_trip()/the HTTP
    round trip to exercise, not geometrically accurate points."""
    points = []
    for i in range(point_count):
        distance_from_start = total_distance_m * i / (point_count - 1)
        points.append(RoutePoint(
            Coordinates(lat=30.0 + i * 1e-4, lng=-81.0 - i * 1e-4),
            point_number=i + 1,
            distance_from_start=distance_from_start,
            distance_to_destination=total_distance_m - distance_from_start,
            distance_to_previous=0.0 if i == 0 else total_distance_m / (point_count - 1),
            distance_to_next=0.0 if i == point_count - 1 else total_distance_m / (point_count - 1),
        ))
    return Route(points=points, total_distance=total_distance_m, point_count=point_count)


def test_start_journey_succeeds_for_a_long_distance_route(user_id, auth_headers, monkeypatch):
    """Regression test: a real Jacksonville, FL -> Fargo, ND attempt
    failed in production with a generic "Couldn't start that walk - try
    again." - investigation found every authenticated request for that
    account 500ing on an identity-provisioning bug (since fixed, and the
    whole Clerk-based identity system it was part of since reverted -
    see tests/test_accounts.py), not anything route-length/OSRM-specific.
    This test locks in the other half of that investigation: a long
    route's own size (tens of thousands of geometry points, dozens of
    checkpoints - see
    travel_logic/checkpoints.py's _sample_count()) must not, on its own,
    break or slow down trip creation through the real endpoint."""
    monkeypatch.setattr(travel_facade._geocoder, "geocode", lambda place: Coordinates(30.3322, -81.6557))
    monkeypatch.setattr(travel_facade._router, "get_walking_route", lambda start, end: _long_distance_route())
    monkeypatch.setattr("core.facade.get_profile", lambda user_id: {})
    monkeypatch.setattr(travel_facade, "bootstrap_checkpoint_metadata", lambda trip_id: None)

    response = client.post(
        "/api/journey/start",
        json={
            "from_place": "Jacksonville, Florida",
            "to_place": "Fargo, North Dakota",
            "from_lat": 30.3322, "from_lng": -81.6557,
            "to_lat": 46.8772, "to_lng": -96.7898,
        },
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coming_soon"] is False
    assert body["total_distance_m"] == 2_753_583.0
    assert len(body["route_geometry"]) == 19_659
    # travel_logic/checkpoints.py's _sample_count(): floor(2753.583^0.55) - a
    # long route gets many checkpoints, not an arbitrary cap.
    assert len(body["checkpoints"]) > 50


def test_start_journey_returns_a_specific_message_when_osrm_reports_no_route(user_id, auth_headers, monkeypatch):
    """A genuine "no walkable route" answer from OSRM (e.g. two points
    with no connecting path) must reach the client as the specific,
    actionable 400 app.py already has for it - not the generic
    coming_soon fallback reserved for a provider/transport failure."""
    def _no_route(start, end):
        raise ValueError(f"No walking route between {start} and {end}: NoRoute")
    monkeypatch.setattr(travel_facade._router, "get_walking_route", _no_route)

    response = client.post(
        "/api/journey/start",
        json={
            "from_place": "Honolulu, Hawaii",
            "to_place": "Los Angeles, California",
            "from_lat": 21.3, "from_lng": -157.8,
            "to_lat": 34.0, "to_lng": -118.2,
        },
        headers=auth_headers(user_id),
    )

    assert response.status_code == 400
    assert response.json()["error"] == "We couldn't find a walkable route between those two places."


def test_start_journey_skips_geocoding_when_the_request_carries_resolved_coordinates(user_id, auth_headers, monkeypatch):
    # The Chile Chico fix, exercised through the real HTTP endpoint: when
    # the frontend's autocomplete already resolved from_place/to_place to
    # coordinates, /api/journey/start must use them directly rather than
    # re-geocoding the free-text label - geocode() is made to raise here
    # so the test fails loudly if that re-geocode path is ever hit again.
    def _explode(place):
        raise ValueError(f"No match for '{place}'")
    monkeypatch.setattr(travel_facade._geocoder, "geocode", _explode)
    monkeypatch.setattr(travel_facade._router, "get_walking_route", lambda start, end: _short_route())
    monkeypatch.setattr("core.facade.get_profile", lambda user_id: {})
    # Same reason as _mock_geocoding_and_routing() above - the route's
    # checkpoints (positions only, blank names) get created for real;
    # this just stops the background metadata job that would otherwise
    # try to resolve them against the real geocoder/describer.
    monkeypatch.setattr(travel_facade, "bootstrap_checkpoint_metadata", lambda trip_id: None)

    response = client.post(
        "/api/journey/start",
        json={
            "from_place": "Chile Chico Airport (CCH), Chile Chico, CL",
            "to_place": "Santiago, Chile",
            "from_lat": -46.5406, "from_lng": -71.7233,
            "to_lat": -33.4489, "to_lng": -70.6693,
        },
        headers=auth_headers(user_id),
    )

    assert response.status_code == 200
    assert response.json()["coming_soon"] is False


def test_journey_state_requires_authentication(patched_session):
    response = client.get("/api/journey/state", params={"trip_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_journey_state_404s_with_an_unknown_trip_id(user_id, auth_headers):
    response = client.get(
        "/api/journey/state", params={"trip_id": str(uuid.uuid4())}, headers=auth_headers(user_id)
    )
    assert response.status_code == 404


def test_journey_state_returns_the_requested_trip(user_id, auth_headers, seed_trip):
    trip = seed_trip(user_id, _short_route())

    response = client.get("/api/journey/state", params={"trip_id": str(trip.id)}, headers=auth_headers(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["to_place"] == "Chicago, Illinois"  # seed_trip's default
    assert len(body["route_geometry"]) == 2


def test_journey_state_404s_for_another_users_trip(user_id, auth_headers, seed_trip, patched_session):
    trip = seed_trip(user_id, _short_route())

    other_user = User()
    patched_session.add(other_user)
    patched_session.commit()

    response = client.get("/api/journey/state", params={"trip_id": str(trip.id)}, headers=auth_headers(other_user.id))
    assert response.status_code == 404


def test_journey_list_returns_every_trip_for_the_logged_in_user(user_id, auth_headers, seed_trip):
    seed_trip(user_id, _short_route(), to_place="Chicago, Illinois")
    seed_trip(user_id, _short_route(), to_place="Denver, Colorado")

    response = client.get("/api/journey/list", headers=auth_headers(user_id))

    assert response.status_code == 200
    to_places = {t["to_place"] for t in response.json()["trips"]}
    assert to_places == {"Chicago, Illinois", "Denver, Colorado"}


def test_journey_list_includes_total_steps_and_current_checkpoint(
    user_id, auth_headers, seed_trip, seed_checkpoint, patched_session
):
    # ActiveTripCard (frontend/src/components/TripCard.tsx) needs these
    # two fields straight from the trips list - this used to mean
    # HomePage.tsx making a second, much more expensive full-state fetch
    # per active trip (core/facade.py's _build_map_state(), a full route
    # rebuild) just to read them. list_trips() now computes both itself.
    trip = seed_trip(user_id, _short_route())
    seed_checkpoint(trip, "Midway", distance_from_start_m=5_000.0, checkpoint_number=1)
    passed = seed_checkpoint(trip, "Near the end", distance_from_start_m=9_000.0, checkpoint_number=2)
    passed.hit_at = datetime.now(timezone.utc)
    patched_session.add(StepSyncLog(
        user_id=user_id, trip_id=trip.id, steps=1234,
        distance_walked_miles=1.0, distance_remaining_miles=5.0, percent_complete=10.0,
        synced_at=datetime.now(timezone.utc),
    ))
    patched_session.commit()

    response = client.get("/api/journey/list", headers=auth_headers(user_id))

    assert response.status_code == 200
    [listed] = response.json()["trips"]
    assert listed["total_steps"] == 1234
    # The most recently-reached checkpoint by checkpoint_number, not just
    # whichever was seeded/hit last in time - "Midway" (#1) was never hit.
    assert listed["current_checkpoint_name"] == "Near the end"


def test_journey_list_current_checkpoint_is_none_before_anything_is_hit(user_id, auth_headers, seed_trip, seed_checkpoint):
    trip = seed_trip(user_id, _short_route())
    seed_checkpoint(trip, "Midway", distance_from_start_m=5_000.0)

    response = client.get("/api/journey/list", headers=auth_headers(user_id))

    [listed] = response.json()["trips"]
    assert listed["current_checkpoint_name"] is None
    assert listed["total_steps"] == 0


def test_journey_list_query_count_does_not_grow_with_more_active_trips(
    user_id, auth_headers, seed_trip, seed_checkpoint, db_engine
):
    # Regression guard for the N+1 this replaced: before this fix, reading
    # trip.checkpoints lazy-loaded with its own query per trip, and
    # total_steps()/today_steps() (data/total_distance_db.py) each opened
    # a brand new session per trip on top of that - five active trips
    # used to mean 1 + 5*(1 trip-row fetch is already covered by the list
    # query, but +1 lazy checkpoints +2 steps queries) extra round trips.
    # It's now a handful of queries total, however many trips there are.
    for i in range(5):
        trip = seed_trip(user_id, _short_route(), to_place=f"Place {i}")
        seed_checkpoint(trip, f"Checkpoint {i}", distance_from_start_m=1_000.0)

    statements = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", _record)
    try:
        response = client.get("/api/journey/list", headers=auth_headers(user_id))
    finally:
        event.remove(db_engine, "before_cursor_execute", _record)

    assert response.status_code == 200
    assert len(response.json()["trips"]) == 5
    # One query to resolve the authenticated user, one for the trips, one
    # batched selectinload for every trip's checkpoints, one batched
    # grouped SUM for every trip's steps - fixed, not one-per-trip.
    assert len(statements) <= 4, statements


def test_pause_then_resume_round_trips_through_the_api(user_id, auth_headers, seed_trip):
    trip = seed_trip(user_id, _short_route())
    headers = auth_headers(user_id)

    paused = client.post(f"/api/journey/{trip.id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/api/journey/{trip.id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"


def test_delete_journey_removes_it_from_the_list(user_id, auth_headers, seed_trip):
    trip = seed_trip(user_id, _short_route())
    headers = auth_headers(user_id)

    response = client.delete(f"/api/journey/{trip.id}", headers=headers)
    assert response.status_code == 204

    listing = client.get("/api/journey/list", headers=headers)
    assert listing.json()["trips"] == []


def test_bulk_delete_only_removes_the_given_trips(user_id, auth_headers, seed_trip):
    keep = seed_trip(user_id, _short_route(), to_place="Chicago, Illinois")
    delete_me = seed_trip(user_id, _short_route(), to_place="Denver, Colorado")
    headers = auth_headers(user_id)

    response = client.post("/api/journey/delete", json={"trip_ids": [str(delete_me.id)]}, headers=headers)

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    remaining_ids = {t["trip_id"] for t in client.get("/api/journey/list", headers=headers).json()["trips"]}
    assert remaining_ids == {str(keep.id)}


def test_journey_stats_requires_authentication(patched_session):
    response = client.get("/api/journey/stats")
    assert response.status_code == 401


def test_unhandled_dependency_failure_returns_json_not_a_bare_crash(user_id, patched_session, monkeypatch):
    """Regression test for app.py's global exception_handler. The real
    production incident here wasn't route-length-specific at all: an
    unhandled exception inside a FastAPI Depends() (accounts/
    dependencies.py's get_current_user, raised at the time by an
    identity-provisioning bug in a now-reverted Clerk-based auth system -
    see tests/test_accounts.py for the auth system that replaced it) runs
    *before* any route's own try/except gets a chance, so it reached the
    client as Starlette's bare "Internal Server Error" text - not JSON, which is exactly what
    made frontend/src/api/httpClient.ts's parseErrorMessage fall back to
    "Couldn't start that walk - try again." with zero diagnosable detail.
    This locks in that *any* such failure, on *any* route, now comes back
    as a real JSON body instead, whatever the underlying cause - the
    specific provisioning bug is fixed separately, but a future
    not-yet-imagined failure in a dependency must never regress back to a
    bare crash page."""
    from accounts.dependencies import get_current_user
    from app import app

    def _boom():
        raise RuntimeError("simulated dependency failure")

    app.dependency_overrides[get_current_user] = _boom
    try:
        # raise_server_exceptions=False: the default TestClient re-raises
        # whatever an unhandled exception's own handler already turned
        # into a response, purely so a test can tell a genuine
        # programming error apart from this exact scenario - app.py's
        # global exception_handler already ran and sent a real response
        # (confirmed by the server-side log line above) by the time that
        # re-raise would happen; this just asks for that response instead.
        no_raise_client = TestClient(app, raise_server_exceptions=False)
        response = no_raise_client.get("/api/journey/list")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"error": "Something went wrong on our end. Please try again."}


def test_journey_stats_returns_lifetime_steps(user_id, patched_session, auth_headers, seed_trip):
    # frontend/src/pages/ProfilePage.tsx's one stat - travel_facade's shared step
    # log is Postgres-backed now (data/total_distance_db.py), so it's
    # already isolated inside this test's own rolled-back transaction via
    # the patched_session fixture, same as every other write here.
    seed_trip(user_id, _short_route())
    travel_facade.record_steps(user_id, 2500)

    response = client.get("/api/journey/stats", headers=auth_headers(user_id))

    assert response.status_code == 200
    assert response.json()["lifetime_steps"] == 2500
