# tests/test_geocoder.py
# NominatimGeocoder.search_places() - the live autocomplete used by
# app.py's Where From/Where To dropdowns. No real network calls -
# requests.get is monkeypatched, same pattern test_fitbit_service.py uses
# for get_data_points.

from travel_logic import geocoder as geocoder_module
from travel_logic.geocoder import NominatimGeocoder


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise geocoder_module.requests.HTTPError(f"{self.status_code}")


def test_search_places_returns_display_names(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States"},
        {"display_name": "Arizona City, Arizona, United States"},
    ]))
    assert NominatimGeocoder().search_places("ariz") == [
        "Arizona, United States",
        "Arizona City, Arizona, United States",
    ]


def test_search_places_skips_the_api_call_for_a_too_short_query(monkeypatch):
    called = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: called.append(1))
    assert NominatimGeocoder().search_places("a") == []
    assert called == []


def test_search_places_treats_none_the_same_as_too_short():
    # A UI Dropdown fires its "typing" event with None on focus, before any
    # character is typed - real input this method must not crash on.
    assert NominatimGeocoder().search_places(None) == []


def test_search_places_returns_empty_list_on_a_provider_error(monkeypatch):
    def failing_get(*a, **k):
        raise geocoder_module.requests.ConnectionError("boom")
    monkeypatch.setattr(geocoder_module.requests, "get", failing_get)
    assert NominatimGeocoder().search_places("arizona") == []
