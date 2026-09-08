# tests/test_google_health_client.py
# Pull client, with the real HTTP call mocked out (pytest-httpx).

from services import google_health_client


def test_get_data_points_returns_the_list(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    httpx_mock.add_response(json={"dataPoints": [{"count": "10"}]})

    points = google_health_client.get_data_points("steps", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"count": "10"}]


def test_get_data_points_unwraps_the_type_envelope(monkeypatch, httpx_mock):
    # Real shape: {"dataSource": {...}, "steps": {...}} - not flat.
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    httpx_mock.add_response(json={
        "dataPoints": [{"dataSource": {"recordingMethod": "AUTOMATICALLY_RECORDED"}, "steps": {"count": "5"}}]
    })

    points = google_health_client.get_data_points("steps", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"count": "5"}]


def test_get_data_points_unwraps_hyphenated_type(monkeypatch, httpx_mock):
    # "heart-rate" dataType -> "heartRate" envelope key (camelCase, like
    # every other field in the API's JSON body - confirmed against a real
    # response; distinct from the snake_case used in filter field names).
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    httpx_mock.add_response(json={
        "dataPoints": [{"dataSource": {}, "heartRate": {"beatsPerMinute": "72"}}]
    })

    points = google_health_client.get_data_points("heart-rate", "2026-09-01T00:00:00Z", "2026-09-01T01:00:00Z")

    assert points == [{"beatsPerMinute": "72"}]


def test_get_data_points_refreshes_token_once_on_401(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    calls = []
    monkeypatch.setattr(google_health_client, "refresh_access_token", lambda: calls.append("refreshed"))

    httpx_mock.add_response(status_code=401)
    httpx_mock.add_response(json={"dataPoints": []})

    google_health_client.get_data_points("steps", "a", "b")

    assert calls == ["refreshed"]


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
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
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
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    httpx_mock.add_response(json={"dataPoints": [{"exercise": {"exerciseType": "WALKING"}}]})

    points = google_health_client.get_data_points("exercise", "2026-09-08T17:08:14Z", "2026-09-08T17:14:37Z")

    assert len(points) == 1


def test_get_profile_returns_json(monkeypatch, httpx_mock):
    monkeypatch.setattr(google_health_client, "get_access_token", lambda: "AT")
    httpx_mock.add_response(json={"age": 31, "memberSince": "2021-02-10"})

    profile = google_health_client.get_profile()

    assert profile == {"age": 31, "memberSince": "2021-02-10"}
