# tests/test_geocoder.py
# NominatimGeocoder.search_places() - the live autocomplete used by
# app.py's Where From/Where To dropdowns. No real network calls -
# requests.get is monkeypatched, same pattern test_google_health_webhook.py
# uses for get_data_points.
#
# Every instance here gets its own tmp_path cache file and zero throttle
# delay: the real cache_path/min_delay_s/max_delay_s defaults (a real file
# under data/, a 1-2s gap between requests) are what production wants, but
# would leak test artifacts onto disk and make this file slow to run - see
# travel_logic/geocoder.py's docstring for why the delay is real there.

import json

import pytest

from travel_logic import geocoder as geocoder_module
from travel_logic.geocoder import (
    LocalPlaceIndex,
    NominatimGeocoder,
    Place,
    _is_valid_place_dict,
    _is_valid_search_result_cache,
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


def _geocoder(tmp_path):
    return NominatimGeocoder(cache_path=tmp_path / "geocode_cache.json", min_delay_s=0, max_delay_s=0)


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


def test_search_places_returns_display_names_with_coordinates(monkeypatch, tmp_path):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
        {"display_name": "Arizona City, Arizona, United States", "lat": "32.75", "lon": "-111.67", "class": "place"},
    ]))
    assert _geocoder(tmp_path).search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
        Place(value="Arizona City, Arizona, United States", primary="Arizona City", secondary="Arizona, United States", lat=32.75, lng=-111.67),
    ]


def test_search_places_drops_non_geographic_results(monkeypatch, tmp_path):
    # A shop or restaurant (class "shop"/"amenity") isn't a useful answer
    # to "Where from?"/"Where to?" - only real places (place/boundary)
    # belong in the dropdown.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona Diner", "lat": "33.4", "lon": "-112.0", "class": "amenity"},
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))
    assert _geocoder(tmp_path).search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_search_places_self_heals_a_stale_pre_dict_cache_entry(monkeypatch, tmp_path):
    # data/geocode_cache.json can hold entries written before search_places()
    # returned {"display_name", "lat", "lng"} dicts (it used to return
    # plain display-name strings) - a real, observed crash (TypeError:
    # string indices must be integers) when a stale entry like this got
    # trusted as-is by a caller expecting the current shape. A shape
    # mismatch must be treated as a cache miss - one more real lookup,
    # same as if nothing had been cached - not returned broken.
    cache_path = tmp_path / "geocode_cache.json"
    cache_path.write_text(json.dumps({"search:ariz:5": ["Arizona, United States"]}))

    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    assert geocoder.search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5)
    ]
    # Self-healed on disk too, not left broken for the next call (or the
    # next process to load this same cache file).
    assert json.loads(cache_path.read_text())["search:ariz:5"] == [
        {"value": "Arizona, United States", "primary": "Arizona", "secondary": "United States", "lat": 34.0, "lng": -111.5}
    ]


def test_search_places_skips_the_api_call_for_a_too_short_query(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: called.append(1))
    assert _geocoder(tmp_path).search_places("a") == []
    assert called == []


def test_search_places_treats_none_the_same_as_too_short(tmp_path):
    # A UI Dropdown fires its "typing" event with None on focus, before any
    # character is typed - real input this method must not crash on.
    assert _geocoder(tmp_path).search_places(None) == []


def test_search_places_returns_empty_list_on_a_provider_error(monkeypatch, tmp_path):
    def failing_get(*a, **k):
        raise geocoder_module.requests.ConnectionError("boom")
    monkeypatch.setattr(geocoder_module.requests, "get", failing_get)
    assert _geocoder(tmp_path).search_places("arizona") == []


def test_search_places_uses_the_cache_on_a_repeat_query(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))
    geocoder = _geocoder(tmp_path)
    expected = [Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5)]

    assert geocoder.search_places("ariz") == expected
    assert geocoder.search_places("ariz") == expected
    assert len(calls) == 1  # the second call was served from cache, not a second request


# ---------- search_places() x LocalPlaceIndex integration ----------
# NominatimGeocoder._local_index is shared class-wide (same reasoning as
# the throttle - see the class docstring), so it outlives any one test's
# NominatimGeocoder instance. Every test below that cares about the
# index's exact contents monkeypatches it to a throwaway LocalPlaceIndex
# first - monkeypatch restores the real, seeded one afterward - so these
# tests can't leak entries into each other or into the tests above (whose
# "ariz"/"arizona" queries don't collide with any real seed data anyway).

FARGO = _place_entry("Fargo, North Dakota, United States", 46.8772, -96.7898, "city")


def test_search_places_answers_from_the_local_index_without_calling_nominatim(monkeypatch, tmp_path):
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([FARGO]))
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))

    result = _geocoder(tmp_path).search_places("F")

    assert result == [
        Place(value="Fargo, North Dakota, United States", primary="Fargo", secondary="North Dakota, United States", lat=46.8772, lng=-96.7898)
    ]
    assert calls == []  # never reached Nominatim - the throttle's budget was never spent


def test_search_places_falls_back_to_nominatim_when_the_local_index_has_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([]))
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))

    assert _geocoder(tmp_path).search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_search_places_adds_a_new_nominatim_result_to_the_local_index(monkeypatch, tmp_path):
    index = LocalPlaceIndex([])
    monkeypatch.setattr(NominatimGeocoder, "_local_index", index)
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Bismarck, Burleigh County, North Dakota, United States",
            "lat": "46.8083", "lon": "-100.7837", "class": "place", "type": "city",
            "osm_type": "relation", "osm_id": "175905",
        },
    ]))

    _geocoder(tmp_path).search_places("bismarck")

    # A later, single-character query for the same place now answers
    # locally - proof the live Nominatim result actually landed in the
    # shared index, not just returned once and forgotten.
    found = index.search("bis", limit=10)
    assert len(found) == 1
    assert found[0]["display_name"] == "Bismarck, Burleigh County, North Dakota, United States"
    assert (found[0]["lat"], found[0]["lng"]) == (46.8083, -100.7837)
    assert found[0]["provider_id"] == "relation:175905"


def test_search_places_does_not_duplicate_a_place_already_in_the_index(monkeypatch, tmp_path):
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
    _geocoder(tmp_path).search_places("fargo, cass county")

    assert len(index.search("Fargo", limit=10)) == 1


def test_search_places_local_results_include_coordinates(monkeypatch, tmp_path):
    # No requests.get monkeypatch at all here - if this reached Nominatim
    # it would try a real network call and fail loudly, which is itself
    # part of what this test is checking.
    monkeypatch.setattr(NominatimGeocoder, "_local_index", LocalPlaceIndex([FARGO]))

    result = _geocoder(tmp_path).search_places("Fargo")

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


def test_search_places_requests_addressdetails_from_nominatim(monkeypatch, tmp_path):
    captured_params = {}

    def fake_get(url, params=None, **kwargs):
        captured_params.update(params or {})
        return _FakeResponse([])

    monkeypatch.setattr(geocoder_module.requests, "get", fake_get)
    _geocoder(tmp_path).search_places("ord")

    assert captured_params.get("addressdetails") == 1


def test_every_nominatim_request_asks_for_english(monkeypatch, tmp_path):
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
    geocoder = _geocoder(tmp_path)

    geocoder.search_places("munich")
    with pytest.raises(ValueError):
        geocoder.geocode("munich")  # empty mock response - geocode() raises on no match, expected here

    assert all(p.get("accept-language") == "en" for p in captured)
    assert len(captured) == 2


def test_search_places_shortens_the_label_when_nominatim_provides_an_address(monkeypatch, tmp_path):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {
            "display_name": "Ord, Valley County, Nebraska, 68862, United States",
            "lat": "41.6033379", "lon": "-98.9262134", "class": "boundary", "type": "administrative",
            "address": _ORD_ADDRESS,
        },
    ]))

    result = _geocoder(tmp_path).search_places("ord")

    # The public "value" field is the shortened label, not Nominatim's
    # full string - this is the exact case the feature was requested for.
    assert result == [Place(value="Ord, Nebraska", primary="Ord", secondary="Nebraska", lat=41.6033379, lng=-98.9262134)]


def test_search_places_keeps_the_full_original_display_name_internally(monkeypatch, tmp_path):
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

    _geocoder(tmp_path).search_places("ord")

    entries = list(index._entries.values())
    assert len(entries) == 1
    assert entries[0]["display_name"] == "Ord, Valley County, Nebraska, 68862, United States"
    assert entries[0]["label"] == "Ord, Nebraska"
    assert (entries[0]["lat"], entries[0]["lng"]) == (41.6033379, -98.9262134)


def test_search_places_falls_back_to_the_full_display_name_without_an_address(monkeypatch, tmp_path):
    # No "address" key at all (e.g. a provider response that didn't
    # honor addressdetails=1 for some reason) - _short_label() returns
    # None, and the label falls back to the original, full display_name
    # rather than an empty or broken one.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"},
    ]))

    assert _geocoder(tmp_path).search_places("ariz") == [
        Place(value="Arizona, United States", primary="Arizona", secondary="United States", lat=34.0, lng=-111.5),
    ]


def test_geocode_raises_and_caches_a_no_match_result(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([]))
    geocoder = _geocoder(tmp_path)

    with pytest.raises(ValueError):
        geocoder.geocode("Nowhereville")
    with pytest.raises(ValueError):
        geocoder.geocode("Nowhereville")
    assert len(calls) == 1  # the cached "no match" is what raised the second time


def test_geocode_caches_a_real_match(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1) or _FakeResponse([
        {"lat": "44.98", "lon": "-93.26"},
    ]))
    geocoder = _geocoder(tmp_path)

    first = geocoder.geocode("Minneapolis, MN")
    second = geocoder.geocode("Minneapolis, MN")

    assert (first.lat, first.lng) == (44.98, -93.26)
    assert (second.lat, second.lng) == (44.98, -93.26)
    assert len(calls) == 1


def test_geocode_cache_survives_a_new_instance_on_the_same_path(monkeypatch, tmp_path):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"lat": "44.98", "lon": "-93.26"},
    ]))
    cache_path = tmp_path / "geocode_cache.json"
    NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0).geocode("Minneapolis, MN")

    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))
    reopened = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)
    reopened.geocode("Minneapolis, MN")

    assert calls == []  # loaded straight from the file this second instance never wrote to itself


# ---------- cache validation (the "Libson" regression) ----------
# A confusing-but-schema-valid match (a real OSM neighbourhood named
# "Libson Woods" mislabeled as just "Raleigh, North Carolina" by
# _short_label()) led to auditing data/geocode_cache.json for real, and
# turned up three genuinely bad patterns already sitting in it: entries
# in an older pre-dict shape, entries with unusable data, and empty
# "found nothing" results cached as if permanent. These lock in the fix:
# _is_valid_place_dict()/_is_valid_search_result_cache() reject all three,
# and search_places() evicts-and-retries a bad cached entry on read and
# never writes an empty or failed answer to the cache in the first place.


def test_is_valid_place_dict_accepts_a_well_formed_entry():
    assert _is_valid_place_dict(
        {"value": "Lisbon, Portugal", "primary": "Lisbon", "secondary": "Portugal", "lat": 38.7077507, "lng": -9.1365919}
    )


def test_is_valid_place_dict_rejects_a_missing_key():
    assert not _is_valid_place_dict({"value": "Lisbon", "lat": 38.7, "lng": -9.1})  # no primary/secondary


def test_is_valid_place_dict_rejects_the_old_pre_dict_shape():
    # The exact shape that used to crash every caller downstream - see
    # test_search_places_self_heals_a_stale_pre_dict_cache_entry above.
    assert not _is_valid_place_dict({"display_name": "Arizona, United States", "lat": 34.0, "lng": -111.5})


def test_is_valid_place_dict_rejects_blank_display_text():
    assert not _is_valid_place_dict({"value": "  ", "primary": "", "secondary": "Portugal", "lat": 38.7, "lng": -9.1})


def test_is_valid_place_dict_rejects_non_numeric_coordinates():
    assert not _is_valid_place_dict(
        {"value": "Lisbon", "primary": "Lisbon", "secondary": "Portugal", "lat": "38.7", "lng": -9.1}
    )


def test_is_valid_place_dict_rejects_out_of_range_coordinates():
    assert not _is_valid_place_dict({"value": "Nowhere", "primary": "Nowhere", "secondary": "", "lat": 999.0, "lng": -9.1})


def test_is_valid_place_dict_rejects_booleans_as_coordinates():
    # bool is an int subclass in Python - must not slip past the numeric
    # check and be treated as a real lat/lng.
    assert not _is_valid_place_dict({"value": "Nowhere", "primary": "Nowhere", "secondary": "", "lat": True, "lng": -9.1})


def test_is_valid_search_result_cache_rejects_an_empty_list():
    assert not _is_valid_search_result_cache([])


def test_is_valid_search_result_cache_rejects_a_list_with_one_bad_entry():
    good = {"value": "Lisbon, Portugal", "primary": "Lisbon", "secondary": "Portugal", "lat": 38.7, "lng": -9.1}
    bad = {"value": "Nowhere", "primary": "Nowhere", "secondary": "", "lat": 999.0, "lng": -9.1}
    assert not _is_valid_search_result_cache([good, bad])


def test_search_places_evicts_an_invalid_cached_entry_and_retries(monkeypatch, tmp_path):
    # A schema-valid-looking but nonsensical cached entry (an impossible
    # latitude) - not something this process would write itself anymore,
    # but exactly the shape a corrupted or hand-edited cache file (or an
    # older, less careful version of this code) could leave behind.
    cache_path = tmp_path / "geocode_cache.json"
    cache_path.write_text(json.dumps({
        "search:nowhere:5": [{"value": "Nowhere", "primary": "Nowhere", "secondary": "", "lat": 999.0, "lng": 0.0}],
    }))
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Nowhere, Texas, United States", "lat": "31.0", "lon": "-100.0", "class": "place"},
    ]))
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    result = geocoder.search_places("nowhere")

    assert result == [
        Place(value="Nowhere, Texas, United States", primary="Nowhere", secondary="Texas, United States", lat=31.0, lng=-100.0)
    ]
    # The bad entry was actually overwritten on disk - evicted, then
    # replaced by the real retry's result, not just bypassed in memory.
    on_disk = json.loads(cache_path.read_text())["search:nowhere:5"]
    assert on_disk == [
        {"value": "Nowhere, Texas, United States", "primary": "Nowhere", "secondary": "Texas, United States", "lat": 31.0, "lng": -100.0}
    ]


def test_search_places_evicts_a_cached_empty_result_and_retries(monkeypatch, tmp_path):
    cache_path = tmp_path / "geocode_cache.json"
    cache_path.write_text(json.dumps({"search:somewhere:5": []}))
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Somewhere, Ohio, United States", "lat": "40.0", "lon": "-82.0", "class": "place"},
    ]))
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    assert geocoder.search_places("somewhere") == [
        Place(value="Somewhere, Ohio, United States", primary="Somewhere", secondary="Ohio, United States", lat=40.0, lng=-82.0)
    ]


def test_search_places_never_caches_an_empty_result(monkeypatch, tmp_path):
    cache_path = tmp_path / "geocode_cache.json"
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    # First call: Nominatim answers, but nothing passes the geographic-
    # class filter - a legitimate "found nothing" response.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "A Shop", "lat": "1.0", "lon": "1.0", "class": "shop"},
    ]))
    assert geocoder.search_places("nothinghere") == []
    assert not cache_path.exists() or "search:nothinghere:6" not in json.loads(cache_path.read_text())

    # Second call, same query: a real match now exists - must not be
    # blocked by a stale empty answer cached from the first call.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Nothinghere, Kansas, United States", "lat": "39.0", "lon": "-98.0", "class": "place"},
    ]))
    assert geocoder.search_places("nothinghere") == [
        Place(value="Nothinghere, Kansas, United States", primary="Nothinghere", secondary="Kansas, United States", lat=39.0, lng=-98.0)
    ]


def test_search_places_never_caches_a_transient_failure(monkeypatch, tmp_path):
    cache_path = tmp_path / "geocode_cache.json"
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    def failing_get(*a, **k):
        raise geocoder_module.requests.ConnectionError("boom")

    monkeypatch.setattr(geocoder_module.requests, "get", failing_get)
    assert geocoder.search_places("flaky") == []
    assert not cache_path.exists() or "search:flaky:6" not in json.loads(cache_path.read_text())

    # Same query, now that the network's back - must not be stuck behind
    # a cached failure from the call above.
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Flaky, Oregon, United States", "lat": "44.0", "lon": "-121.0", "class": "place"},
    ]))
    assert geocoder.search_places("flaky") == [
        Place(value="Flaky, Oregon, United States", primary="Flaky", secondary="Oregon, United States", lat=44.0, lng=-121.0)
    ]


def test_search_places_reuses_a_valid_cached_entry_without_calling_nominatim(monkeypatch, tmp_path):
    cache_path = tmp_path / "geocode_cache.json"
    cache_path.write_text(json.dumps({
        "search:lisbon:5": [
            {"value": "Lisbon, Portugal", "primary": "Lisbon", "secondary": "Portugal", "lat": 38.7077507, "lng": -9.1365919}
        ],
    }))
    calls = []
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: calls.append(1))
    geocoder = NominatimGeocoder(cache_path=cache_path, min_delay_s=0, max_delay_s=0)

    assert geocoder.search_places("lisbon") == [
        Place(value="Lisbon, Portugal", primary="Lisbon", secondary="Portugal", lat=38.7077507, lng=-9.1365919)
    ]
    assert calls == []  # a valid cached entry is trusted - no Nominatim call spent


def test_user_agent_carries_the_contact_email_and_varies_per_request(monkeypatch, tmp_path):
    seen_user_agents = []

    def fake_get(*a, headers=None, **k):
        seen_user_agents.append(headers["User-Agent"])
        return _FakeResponse([{"display_name": "Arizona, United States", "lat": "34.0", "lon": "-111.5", "class": "boundary"}])

    monkeypatch.setattr(geocoder_module.requests, "get", fake_get)
    geocoder = NominatimGeocoder(
        contact_email="dev@example.com", cache_path=tmp_path / "cache.json", min_delay_s=0, max_delay_s=0
    )

    geocoder.search_places("ariz")
    geocoder.search_places("arizona city")

    assert all("dev@example.com" in ua for ua in seen_user_agents)
    assert seen_user_agents[0] != seen_user_agents[1]  # the per-request suffix actually varies
