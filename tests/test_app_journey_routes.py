# tests/test_app_journey_routes.py
# app.py's two trip-facing endpoints: POST /api/journey/start and
# GET /api/journey/state. Both are gated on a real Google Health
# connection (auth.connections.get_active_user_id) - the concrete meaning
# of "as soon as the user connects successfully" from the feature's
# design. Runs against the real app, with SessionLocal patched (see
# tests/conftest.py's patched_session fixture) so all of it stays inside
# this test's own rolled-back transaction.

import uuid

from fastapi.testclient import TestClient

from app import app
from core.facade import travel_facade
from travel_logic.coordinates import Coordinates
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
    route back, and a short 2-point route has no checkpoints to sample
    (travel_logic/checkpoints.py rounds a route this short down to zero)."""
    monkeypatch.setattr(travel_facade._geocoder, "geocode", lambda place: Coordinates(0.0, 0.0))
    monkeypatch.setattr(travel_facade._router, "get_walking_route", lambda start, end: _short_route())
    monkeypatch.setattr("core.facade.get_profile", lambda: {})


def test_start_journey_requires_a_connection(patched_session):
    response = client.post("/api/journey/start", json={"from_place": "Miami", "to_place": "Chicago"})

    assert response.status_code == 400
    assert "connect" in response.json()["error"].lower()


def test_start_journey_requires_both_places(connected_user_id):
    response = client.post("/api/journey/start", json={"from_place": "", "to_place": "Chicago"})
    assert response.status_code == 400


def test_start_journey_returns_full_map_state_for_the_connected_user(connected_user_id, monkeypatch):
    _mock_geocoding_and_routing(monkeypatch)

    response = client.post("/api/journey/start", json={"from_place": "Miami", "to_place": "Chicago"})

    assert response.status_code == 200
    body = response.json()
    assert body["coming_soon"] is False
    assert body["to_place"] == "Chicago"
    assert len(body["route_geometry"]) == 2
    assert body["checkpoints"] == []
    assert body["percent_complete"] == 0.0


def test_journey_state_requires_a_connection(patched_session):
    response = client.get("/api/journey/state", params={"trip_id": str(uuid.uuid4())})
    assert response.status_code == 400


def test_journey_state_404s_with_an_unknown_trip_id(connected_user_id):
    response = client.get("/api/journey/state", params={"trip_id": str(uuid.uuid4())})
    assert response.status_code == 404


def test_journey_state_returns_the_requested_trip(connected_user_id, seed_trip):
    trip = seed_trip(connected_user_id, _short_route())

    response = client.get("/api/journey/state", params={"trip_id": str(trip.id)})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "active"
    assert body["to_place"] == "Chicago, Illinois"  # seed_trip's default
    assert len(body["route_geometry"]) == 2


def test_journey_list_returns_every_trip_for_the_connected_user(connected_user_id, seed_trip):
    seed_trip(connected_user_id, _short_route(), to_place="Chicago, Illinois")
    seed_trip(connected_user_id, _short_route(), to_place="Denver, Colorado")

    response = client.get("/api/journey/list")

    assert response.status_code == 200
    to_places = {t["to_place"] for t in response.json()["trips"]}
    assert to_places == {"Chicago, Illinois", "Denver, Colorado"}


def test_pause_then_resume_round_trips_through_the_api(connected_user_id, seed_trip):
    trip = seed_trip(connected_user_id, _short_route())

    paused = client.post(f"/api/journey/{trip.id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = client.post(f"/api/journey/{trip.id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"


def test_delete_journey_removes_it_from_the_list(connected_user_id, seed_trip):
    trip = seed_trip(connected_user_id, _short_route())

    response = client.delete(f"/api/journey/{trip.id}")
    assert response.status_code == 204

    listing = client.get("/api/journey/list")
    assert listing.json()["trips"] == []


def test_bulk_delete_only_removes_the_given_trips(connected_user_id, seed_trip):
    keep = seed_trip(connected_user_id, _short_route(), to_place="Chicago, Illinois")
    delete_me = seed_trip(connected_user_id, _short_route(), to_place="Denver, Colorado")

    response = client.post("/api/journey/delete", json={"trip_ids": [str(delete_me.id)]})

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    remaining_ids = {t["trip_id"] for t in client.get("/api/journey/list").json()["trips"]}
    assert remaining_ids == {str(keep.id)}
