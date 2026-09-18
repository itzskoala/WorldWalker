# tests/test_google_health_client.py
# Pull client, with the real HTTP call mocked out (pytest-httpx) and the
# token-getting seam (_current_access_token) mocked out too - this file
# tests get_data_points/get_profile/get_health_user_id's own logic, not
# how a valid token gets produced (that's auth/connections.py's job,
# proven against real Postgres in tests/test_connections.py).

import httpx
import pytest

from services.google_health import client as google_health_client


def test_get_data_points_returns_the_list(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={"dataPoints": [{"count": "10"}]})

    points = google_health_client.get_data_points("steps", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"count": "10"}]


def test_get_data_points_unwraps_the_type_envelope(monkeypatch, httpx_mock):
    # Real shape: {"dataSource": {...}, "steps": {...}} - not flat.
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={
        "dataPoints": [{"dataSource": {"recordingMethod": "AUTOMATICALLY_RECORDED"}, "steps": {"count": "5"}}]
    })

    points = google_health_client.get_data_points("steps", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"count": "5"}]


def test_get_data_points_unwraps_hyphenated_type(monkeypatch, httpx_mock):
    # "heart-rate" dataType -> "heartRate" envelope key (camelCase, like
    # every other field in the API's JSON body - confirmed against a real
    # response; distinct from the snake_case used in filter field names).
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={
        "dataPoints": [{"dataSource": {}, "heartRate": {"beatsPerMinute": "72"}}]
    })

    points = google_health_client.get_data_points("heart-rate", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"beatsPerMinute": "72"}]


def test_get_data_points_forces_a_refresh_and_retries_once_on_401(monkeypatch, httpx_mock):
    calls = []

    def fake_token(force_refresh=False):
        calls.append(force_refresh)
        return "AT"

    monkeypatch.setattr(google_health_client, "_current_access_token", fake_token)

    httpx_mock.add_response(status_code=401)
    httpx_mock.add_response(json={"dataPoints": []})

    google_health_client.get_data_points("steps", "a", "b")

    # First call uses the (possibly cached) token; the 401 forces exactly
    # one refresh-and-retry, not a loop.
    assert calls == [False, True]


def test_camel_case_hyphenated_and_plain():
    assert google_health_client._camel_case("heart-rate") == "heartRate"
    assert google_health_client._camel_case("steps") == "steps"


def test_filter_query_interval_type():
    q = google_health_client._filter_query("steps", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")
    assert q == 'steps.interval.start_time >= "2026-09-01T00:00:00Z" AND steps.interval.start_time < "2026-09-01T01:00:00Z"'


def test_filter_query_sample_type():
    q = google_health_client._filter_query("heart-rate", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")
    assert q == 'heart_rate.sample_time.physical_time >= "2026-09-01T00:00:00Z" AND heart_rate.sample_time.physical_time < "2026-09-01T01:00:00Z"'


def test_filter_query_sleep_uses_end_time():
    q = google_health_client._filter_query("sleep", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")
    assert q == 'sleep.interval.end_time >= "2026-09-01T00:00:00Z" AND sleep.interval.end_time < "2026-09-01T01:00:00Z"'


def test_filter_query_exercise_uses_civil_start_date_not_physical_start_time():
    # exercise.interval.start_time isn't filterable at all (confirmed
    # live: a real 400 INVALID_DATA_POINT_FILTER) - only civil_start_time,
    # a calendar-date field, so bounds are dates, and the upper bound is
    # bumped a day past end_time's own date to stay inclusive of it.
    q = google_health_client._filter_query("exercise", "2026-09-08T17:08:14Z", "2026-09-08T17:14:37.662868023Z")
    assert q == 'exercise.interval.civil_start_time >= "2026-09-08" AND exercise.interval.civil_start_time < "2026-09-09"'


def test_get_data_points_exercise_drops_points_outside_the_requested_window(monkeypatch, httpx_mock):
    # civil_start_time only filters by calendar day, so a second workout
    # earlier the same day can come back too - narrowed down in code so a
    # later notification doesn't re-process (and double-count) it.
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={
        "dataPoints": [
            {"exercise": {"interval": {"startTime": "2026-09-08T07:00:00Z", "endTime": "2026-09-08T07:30:00Z"}, "exerciseType": "RUNNING"}},
            {"exercise": {"interval": {"startTime": "2026-09-08T17:08:14Z", "endTime": "2026-09-08T17:14:37Z"}, "exerciseType": "WALKING"}},
        ]
    })

    points = google_health_client.get_data_points("exercise", "2026-09-08T17:08:14Z", "2026-09-08T17:14:37.662868023Z")

    assert len(points) == 1
    assert points[0]["exerciseType"] == "WALKING"


def test_get_data_points_exercise_keeps_a_point_with_no_interval_rather_than_drop_it(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={"dataPoints": [{"exercise": {"exerciseType": "WALKING"}}]})

    points = google_health_client.get_data_points("exercise", "2026-09-08T17:08:14Z", "2026-09-08T17:14:37Z")

    assert len(points) == 1


def test_get_profile_returns_json(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT")
    httpx_mock.add_response(json={"age": 31, "memberSince": "2021-02-10"})

    profile = google_health_client.get_profile()

    assert profile == {"age": 31, "memberSince": "2021-02-10"}


def test_get_health_user_id_uses_the_ambient_token_by_default(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "_current_access_token", lambda force_refresh=False: "AT-from-db")
    httpx_mock.add_response(json={"healthUserId": "abc123"}, match_headers={"Authorization": "Bearer AT-from-db"})

    assert google_health_client.get_health_user_id() == "abc123"


def test_get_health_user_id_uses_an_explicit_token_when_given(monkeypatch, httpx_mock):
    # Called right after exchange_code(), before any DB row exists to read
    # an ambient token back out of - _current_access_token() must NOT be hit.
    def fail_if_called(force_refresh=False):
        raise AssertionError("should not read the ambient token when one was passed explicitly")

    monkeypatch.setattr(google_health_client, "_current_access_token", fail_if_called)
    httpx_mock.add_response(json={"healthUserId": "abc123"}, match_headers={"Authorization": "Bearer just-exchanged"})

    result = google_health_client.get_health_user_id(access_token="just-exchanged")

    assert result == "abc123"


def test_get_health_user_id_does_not_retry_on_401_with_an_explicit_token(monkeypatch, httpx_mock):
    # No refresh flow makes sense yet for a token that isn't persisted
    # anywhere - an immediate 401 here means something is genuinely wrong,
    # so it should surface as an error, not silently retry.
    def fail_if_called(force_refresh=False):
        raise AssertionError("should not attempt any refresh with an explicit token")

    monkeypatch.setattr(google_health_client, "_current_access_token", fail_if_called)
    httpx_mock.add_response(status_code=401)

    with pytest.raises(httpx.HTTPStatusError):
        google_health_client.get_health_user_id(access_token="just-exchanged")
