# tests/test_geocoder.py
# NominatimGeocoder.search_places() - the live autocomplete used by
# app.py's Where From/Where To dropdowns. No real network calls -
# requests.get is monkeypatched, same pattern test_google_health_webhook.py
# uses for get_data_points.
#
# No on-disk cache here - every call hits Nominatim (through the
# throttle) or answers from the in-memory LocalPlaceIndex. Every instance
# here gets zero throttle delay so this file stays fast to run.

import pytest

from travel_logic import geocoder as geocoder_module
from travel_logic.geocoder import (
    LocalPlaceIndex,
    NominatimGeocoder,
    Place,
    _place_entry,
)


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise geocoder_module.requests.HTTPError(f"{self.status_code}")


def _geocoder():
    return NominatimGeocoder(min_delay_s=0, max_delay_s=0)


@pytest.fixture(autouse=True)
def _fresh_local_index(monkeypatch):
    # NominatimGeocoder._local_index is a shared class attribute, not
    # per-instance (see its own docstring for why) - search_places()
    # mutates it as a side effect (every real Nominatim result found gets
    # added, see LocalPlaceIndex.add()), so without this, one test's real
    # Nominatim-path call would permanently pollute the shared index for
    # every test that runs after it in this file - a query like "ariz"
    # would stop reaching the mocked Nominatim response at all once an
    # earlier test's "Arizona..." result got indexed. Reset to empty
    # before every test - not the real singleton, which accumulates
    # whatever earlier tests/requests in this process have already
    # resolved and would make these tests' behavior depend on run order.
    # monkeypatch restores the actual singleton once each test ends.
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([]))


def test_search_places_returns_display_names_with_coordinates(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
        {"display_name": "Arizona City, Arizona, United States", "lat": "32.75", "lon": "-111.67", "class": "place"},
    ]))
    assert _geocoder().search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
        Place(value="Arizona City, Arizona, United States", primary="Arizona City", secondary="Arizona, United States", lat=32.75, lng=-111.67),
    ]


def test_search_places_drops_non_geographic_results(monkeypatch):
    # A shop or restaurant (class "shop"/"amenity") isn't a useful answer
    # to "Where from?"/"Where to?" - only real places (place/boundary)
    # belong in the dropdown.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona Diner", "lat": "33.4", "lon": "-112.0", "class": "amenity"},
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))
    assert _geocoder().search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_search_places_skips_the_api_call_for_a_too_short_query(monkeypatch):
    called = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: called.append(1))
    assert _geocoder().search_places("a") == []
    assert called == []


def test_search_places_treats_none_the_same_as_too_short():
    # A UI Dropdown fires its "typing" event with None on focus, before any
    # character is typed - real input this method must not crash on.
    assert _geocoder().search_places(None) == []


def test_search_places_returns_empty_list_on_a_provider_error(monkeypatch):
    def failing_get(*a, **k):
        raise geocoder_module.requests.ConnectionError("boom")
    monkeypatch.setattr(geocoder_module.requests, "get", failing_get)
    assert _geocoder().search_places("arizona") == []


# ---------- search_places() x LocalPlaceIndex integration ----------
# NominatimGeocoder._local_index is shared class-wide (same reasoning as
# the throttle - see the class docstring), so it outlives any one test's
# NominatimGeocoder instance. Every test below that cares about the
# index's exact contents monkeypatches it to a throwaway LocalPlaceIndex
# first - monkeypatch restores the real, seeded one afterward - so these
# tests can't leak entries into each other or into the tests above (whose
# "ariz"/"arizona" queries don't collide with any real seed data anyway).

FARGO = _place_entry("Fargo, North Dakota, United States", 46.8772, -96.7898, "city")


def test_search_places_answers_from_the_local_index_without_calling_nominatim(monkeypatch):
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([FARGO]))
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))

    result = _geocoder().search_places("F")

    assert result == [
        Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)
    ]
    assert calls == []  # never reached Nominatim - the throttle's budget was never spent


def test_search_places_falls_back_to_nominatim_when_the_local_index_has_nothing(monkeypatch):
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([]))
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))

    assert _geocoder().search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_search_places_adds_a_new_nominatim_result_to_the_local_index(monkeypatch):
    index = LocalPlaceIndex([])
    monkeypatch.setattr(NominatimGeocoder, "_local_index", index)
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Bismarck, Burleigh County, North Dakota, United States",
            "lat": "46.8083", "lon": "-100.7837", "class": "place", "type": "city",
            "osm_type": "relation", "osm_id": "175905",
        },
    ]))

    _geocoder().search_places("bismarck")

    # A later, single-character query for the same place now answers
    # locally - proof the live Nominatim result actually landed in the
    # shared index, not just returned once and forgotten.
    found = index.search("bis", limit=10)
    assert len(found) == 1
    assert found[0]["display_name"] == "Bismarck, Burleigh County, North Dakota, United States"
    assert (found[0]["lat"], found[0]["lng"]) == (46.8083, -100.7837)
    assert found[0]["provider_id"] == "relation:175905"


def test_search_places_does_not_duplicate_a_place_already_in_the_index(monkeypatch):
    # Same real place ("Fargo, Cass County, North Dakota, United States"
    # at these coordinates), reached via two different queries a user
    # might type on the way to the same result - must not become two
    # separate entries in the shared index.
    index = LocalPlaceIndex([FARGO])
    monkeypatch.setattr(NominatimGeocoder, "_local_index", index)
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Fargo, Cass County, North Dakota, United States",
            "lat": "46.8772", "lon": "-96.7898", "class": "place", "type": "city",
        },
    ]))

    # "F" alone is already answered by the seed - never reaches Nominatim,
    # so use a query specific enough to miss the seed and force the
    # Nominatim path, the same way a real "search fargo more precisely"
    # query would.
    _geocoder().search_places("fargo, cass county")

    assert len(index.search("Fargo", limit=10)) == 1


def test_search_places_local_results_include_coordinates(monkeypatch):
    # No requests.get monkeypatch at all here - if this reached Nominatim
    # it would try a real network call and fail loudly, which is itself
    # part of what this test is checking.
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([FARGO]))

    result = _geocoder().search_places("Fargo")

    assert result == [
        Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)
    ]


# ---------- search_places() x _short_label() (label shortening) ----------
# _short_label()'s own logic is covered directly in tests/test_short_label.py
# - these are specifically about search_places() actually using it: asking
# Nominatim for the structured data it needs, using the shortened label as
# the public-facing text, and not throwing away the original in the
# process.

# The real address Nominatim returns for "Ord, Nebraska" with
# addressdetails=1 (captured live) - the exact example this feature was
# requested for.
_ORD_ADDRESS = {
    "city": "Ord", "county": "Valley County", "state": "Nebraska",
    "postcode": "68862", "country": "United States", "country_code": "us",
}


def test_search_places_requests_addressdetails_from_nominatim(monkeypatch):
    captured_params = {}

    def fake_get(url, params=None, **kwargs):
        captured_params.update(params or {})
        return _FakeResponse([])

    monkeypatch.setattr(geocoder_module.requests, "get", fake_get)
    _geocoder().search_places("ord")

    assert captured_params.get("addressdetails") == 1


def test_every_nominatim_request_asks_for_english(monkeypatch):
    # Applied once in _get() (see its comment) - checked here through two
    # different call sites (search_places and geocode) to confirm it's
    # not something only one method happens to set. Without this,
    # Nominatim defaults to the result's own locale - confirmed live:
    # "München, Bayern, Deutschland" for a Munich search, "京都市, 京都府,
    # 日本" for Kyoto - not a translation Claude added, Nominatim's own
    # default with no language requested at all.
    captured = []
    monkeypatch.setattr(
        geocoder_module.requests, "get",
        lambda url, params=None, **k: captured.append(params or {}) or _FakeResponse([]),
    )
    geocoder = _geocoder()

    geocoder.search_places("munich")
    with pytest.raises(ValueError):
        geocoder.geocode("munich")  # empty mock response - geocode() raises on no match, expected here

    assert all(p.get("accept-language") == "en" for p in captured)
    assert len(captured) == 2


def test_search_places_shortens_the_label_when_nominatim_provides_an_address(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Ord, Valley County, Nebraska, 68862, United States",
            "lat": "41.6033379", "lon": "-98.9262134", "class": "boundary", "type": "administrative",
            "address": _ORD_ADDRESS,
        },
    ]))

    result = _geocoder().search_places("ord")

    # The public "value" field is the shortened label, not Nominatim's
    # full string - this is the exact case the feature was requested for.
    assert result == [Place(value="Ord, Nebraska", primary="Ord", secondary="Nebraska", lat=41.6033379, lng=-98.9262134)]


def test_search_places_keeps_the_full_original_display_name_internally(monkeypatch):
    # "Only shorten the user-facing label - do NOT discard the original
    # Nominatim data" - the full string must still be sitting in the
    # local index entry the search grew, even though callers only ever
    # see the shortened one.
    index = LocalPlaceIndex([])
    monkeypatch.setattr(NominatimGeocoder, "_local_index", index)
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Ord, Valley County, Nebraska, 68862, United States",
            "lat": "41.6033379", "lon": "-98.9262134", "class": "boundary", "type": "administrative",
            "address": _ORD_ADDRESS,
        },
    ]))

    _geocoder().search_places("ord")

    entries = list(index._entries.values())
    assert len(entries) == 1
    assert entries[0]["display_name"] == "Ord, Valley County, Nebraska, 68862, United States"
    assert entries[0]["label"] == "Ord, Nebraska"
    assert (entries[0]["lat"], entries[0]["lng"]) == (41.6033379, -98.9262134)


def test_search_places_falls_back_to_the_full_display_name_without_an_address(monkeypatch):
    # No "address" key at all (e.g. a provider response that didn't
    # honor addressdetails=1 for some reason) - _short_label() returns
    # None, and the label falls back to the original, full display_name
    # rather than an empty or broken one.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))

    assert _geocoder().search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_geocode_raises_on_no_match(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([]))
    with pytest.raises(ValueError):
        _geocoder().geocode("Nowhereville")


def test_geocode_returns_coordinates_on_a_real_match(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"lat": "44.98", "lon": "-93.26"},
    ]))
    coords = _geocoder().geocode("Minneapolis, MN")
    assert (coords.lat, coords.lng) == (44.98, -93.26)


def test_user_agent_carries_the_contact_email_and_varies_per_request(monkeypatch):
    seen_user_agents = []

    def fake_get(*a, headers=None, **k):
        seen_user_agents.append(headers["User-Agent"])
        return _FakeResponse([{"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"}])

    monkeypatch.setattr(geocoder_module.requests, "get", fake_get)
    geocoder = NominatimGeocoder(contact_email="dev@example.com", min_delay_s=0, max_delay_s=0)

    geocoder.search_places("ariz")
    geocoder.search_places("arizona city")

    assert all("dev@example.com" in ua for ua in seen_user_agents)
    assert seen_user_agents[0] != seen_user_agents[1]  # the per-request suffix actually varies
