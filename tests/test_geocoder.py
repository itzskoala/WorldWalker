# tests/test_geocoder.py
# NominatimGeocoder.search_places() - the live autocomplete used by
# app.py's Where From/Where To dropdowns. No real network calls -
# requests.get is monkeypatched, same pattern test_google_health_webhook.py
# uses for get_data_points.
#
# FakePlaceCache below stands in for the real Redis+Postgres PlaceCache
# (travel_logic/place_cache.py) - every instance here gets its own, so
# unlike the old shared LocalPlaceIndex, nothing needs resetting between
# tests. Every geocoder here also gets zero throttle delay so this file
# stays fast to run.

import pytest

from backend.travel_logic import geocoder as geocoder_module
from backend.travel_logic.dataclasses.coordinates import Coordinates
from backend.travel_logic.geocoder import NominatimGeocoder, Place, _place_entry


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise geocoder_module.requests.HTTPError(f"{self.status_code}")


class FakePlaceCache:
    def __init__(self, seed=None):
        self.entries = {}
        self.reverse_cache = {}
        self.cached_queries = {}
        self.store(seed or [])

    def store(self, new_entries):
        for entry in new_entries:
            key = f"{round(entry['lat'], 4)},{round(entry['lng'], 4)}"
            self.entries[key] = entry

    def cache_search(self, query, places):
        self.cached_queries[query] = places

    def search(self, query, limit):
        q = query.strip().lower()
        if not q:
            return []

        matches = [e for e in self.entries.values() if e["primary"].lower().startswith(q)]
        matches.sort(key=lambda e: (len(e["primary"]), e["primary"]))

        places, seen_labels = [], set()
        for e in matches:
            if e["label"] in seen_labels:
                continue
            seen_labels.add(e["label"])
            places.append(Place(value=e["label"], primary=e["primary"], secondary=e["secondary"], lat=e["lat"], lng=e["lng"]))
            if len(places) == limit:
                break
        return places

    def reverse(self, coords):
        return self.reverse_cache.get((round(coords.lat, 3), round(coords.lng, 3)))

    def cache_reverse(self, coords, place):
        self.reverse_cache[(round(coords.lat, 3), round(coords.lng, 3))] = place


def _geocoder(place_cache=None):
    return NominatimGeocoder(place_cache or FakePlaceCache(), min_delay_s=0, max_delay_s=0)


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


def test_search_places_still_hits_the_api_for_a_short_query_when_nothing_cached(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))
    assert _geocoder().search_places("a") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5)
    ]


def test_search_places_treats_none_as_empty():
    assert _geocoder().search_places(None) == []


def test_search_places_returns_empty_list_on_a_provider_error(monkeypatch):
    def failing_get(*a, **k):
        raise geocoder_module.requests.ConnectionError("boom")
    monkeypatch.setattr(geocoder_module.requests, "get", failing_get)
    assert _geocoder().search_places("arizona") == []


# ---------- search_places() x PlaceCache integration ----------

FARGO = _place_entry("Fargo, North Dakota, United States", 46.8772, -96.7898, "city")


def test_search_places_answers_from_the_cache_without_calling_nominatim(monkeypatch):
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))

    result = _geocoder(FakePlaceCache([FARGO])).search_places("F")

    assert result == [
        Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)
    ]
    assert calls == []  # never reached Nominatim - the throttle's budget was never spent


def test_search_places_falls_back_to_nominatim_when_the_cache_has_nothing(monkeypatch):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))

    assert _geocoder().search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_search_places_adds_a_new_nominatim_result_to_the_cache(monkeypatch):
    cache = FakePlaceCache()
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Bismarck, Burleigh County, North Dakota, United States",
            "lat": "46.8083", "lon": "-100.7837", "class": "place", "type": "city",
            "osm_type": "relation", "osm_id": "175905",
        },
    ]))

    _geocoder(cache).search_places("bismarck")

    stored = list(cache.entries.values())
    assert len(stored) == 1
    assert stored[0]["display_name"] == "Bismarck, Burleigh County, North Dakota, United States"
    assert (stored[0]["lat"], stored[0]["lng"]) == (46.8083, -100.7837)
    assert stored[0]["provider_id"] == "relation:175905"

    # A later, single-character query for the same place now answers
    # locally - proof the live Nominatim result actually landed in the
    # cache, not just returned once and forgotten.
    found = cache.search("bis", limit=10)
    assert len(found) == 1


def test_search_places_warms_the_cache_for_the_exact_query_that_hit_nominatim(monkeypatch):
    # A brand-new place answers from Nominatim on the triggering query
    # itself - that same query string must also be cache-warm immediately
    # after, not just the place's own name prefix once a *later* search
    # happens to re-derive it from storage.
    cache = FakePlaceCache()
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Bismarck, Burleigh County, North Dakota, United States",
            "lat": "46.8083", "lon": "-100.7837", "class": "place", "type": "city",
        },
    ]))

    result = _geocoder(cache).search_places("bismarck")

    assert cache.cached_queries["bismarck"] == result


def test_search_places_does_not_duplicate_a_place_already_in_the_cache(monkeypatch):
    # Same real place ("Fargo, Cass County, North Dakota, United States"
    # at these coordinates), reached via two different queries a user
    # might type on the way to the same result - must not become two
    # separate entries in the cache.
    cache = FakePlaceCache([FARGO])
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
    _geocoder(cache).search_places("fargo, cass county")

    assert len(cache.search("Fargo", limit=10)) == 1


def test_search_places_cache_results_include_coordinates():
    # No requests.get monkeypatch at all here - if this reached Nominatim
    # it would try a real network call and fail loudly, which is itself
    # part of what this test is checking.
    result = _geocoder(FakePlaceCache([FARGO])).search_places("Fargo")

    assert result == [
        Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)
    ]


# ---------- reverse_geocode() x PlaceCache integration ----------

def test_reverse_geocode_answers_from_the_cache_without_calling_nominatim(monkeypatch):
    cache = FakePlaceCache()
    cache.cache_reverse(Coordinates(lat=46.8772, lng=-96.7898), "Fargo")
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))

    result = _geocoder(cache).reverse_geocode(Coordinates(lat=46.8772, lng=-96.7898))

    assert result == "Fargo"
    assert calls == []


def test_reverse_geocode_caches_a_new_nominatim_result(monkeypatch):
    cache = FakePlaceCache()
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse({"address": {"city": "Fargo"}}))

    result = _geocoder(cache).reverse_geocode(Coordinates(lat=46.8772, lng=-96.7898))

    assert result == "Fargo"
    assert cache.reverse(Coordinates(lat=46.8772, lng=-96.7898)) == "Fargo"


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
    # cache entry the search grew, even though callers only ever see the
    # shortened one.
    cache = FakePlaceCache()
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Ord, Valley County, Nebraska, 68862, United States",
            "lat": "41.6033379", "lon": "-98.9262134", "class": "boundary", "type": "administrative",
            "address": _ORD_ADDRESS,
        },
    ]))

    _geocoder(cache).search_places("ord")

    entries = list(cache.entries.values())
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
    geocoder = NominatimGeocoder(FakePlaceCache(), contact_email="dev@example.com", min_delay_s=0, max_delay_s=0)

    geocoder.search_places("ariz")
    geocoder.search_places("arizona city")

    assert all("dev@example.com" in ua for ua in seen_user_agents)
    assert seen_user_agents[0] != seen_user_agents[1]  # the per-request suffix actually varies
