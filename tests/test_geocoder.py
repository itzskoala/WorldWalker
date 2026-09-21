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

import pytest

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


def _geocoder(tmp_path):
    return NominatimGeocoder(cache_path=tmp_path / "geocode_cache.json", min_delay_s=0, max_delay_s=0)


def test_search_places_returns_display_names(monkeypatch, tmp_path):
    monkeypatch.setattr(geocoder_module.requests, "get", lambda *a, **k: _FakeResponse([
        {"display_name": "Arizona, United States"},
        {"display_name": "Arizona City, Arizona, United States"},
    ]))
    assert _geocoder(tmp_path).search_places("ariz") == [
        "Arizona, United States",
        "Arizona City, Arizona, United States",
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
        {"display_name": "Arizona, United States"},
    ]))
    geocoder = _geocoder(tmp_path)

    assert geocoder.search_places("ariz") == ["Arizona, United States"]
    assert geocoder.search_places("ariz") == ["Arizona, United States"]
    assert len(calls) == 1  # the second call was served from cache, not a second request


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


def test_user_agent_carries_the_contact_email_and_varies_per_request(monkeypatch, tmp_path):
    seen_user_agents = []

    def fake_get(*a, headers=None, **k):
        seen_user_agents.append(headers["User-Agent"])
        return _FakeResponse([{"display_name": "Arizona, United States"}])

    monkeypatch.setattr(geocoder_module.requests, "get", fake_get)
    geocoder = NominatimGeocoder(
        contact_email="dev@example.com", cache_path=tmp_path / "cache.json", min_delay_s=0, max_delay_s=0
    )

    geocoder.search_places("ariz")
    geocoder.search_places("arizona city")

    assert all("dev@example.com" in ua for ua in seen_user_agents)
    assert seen_user_agents[0] != seen_user_agents[1]  # the per-request suffix actually varies
