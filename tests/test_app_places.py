# tests/test_app_places.py
# GET /api/places/search's HTTP shape. The actual splitting of a
# provider's raw result into {value, primary, secondary} now happens
# behind the Geocoder interface (travel_logic/geocoder.py's Place and
# NominatimGeocoder.search_places() - see tests/test_geocoder.py and
# tests/test_short_label.py for that) - this endpoint is a thin
# passthrough now, so these tests only cover that it actually passes
# each Place through as JSON, not any provider-specific formatting logic
# of its own.

from fastapi.testclient import TestClient

import app as app_module
from app import app
from travel_logic.geocoder import Place

client = TestClient(app)


def test_search_places_endpoint_returns_whatever_the_geocoder_gives_it(monkeypatch):
    monkeypatch.setattr(
        app_module._geocoder, "search_places",
        lambda query, limit=6: [Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)],
    )
    response = client.get("/api/places/search", params={"q": "Fargo"})
    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "value": "Fargo, North Dakota, United States",
                "primary": "Fargo",
                "secondary": "North Dakota, United States",
                "lat": 46.8772,
                "lng": -96.7898,
            }
        ]
    }


def test_search_places_endpoint_returns_an_empty_list_for_no_matches(monkeypatch):
    monkeypatch.setattr(app_module._geocoder, "search_places", lambda query, limit=6: [])
    response = client.get("/api/places/search", params={"q": "zzzznonexistentplace12345"})
    assert response.status_code == 200
    assert response.json() == {"results": []}
