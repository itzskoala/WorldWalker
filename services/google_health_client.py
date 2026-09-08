# services/google_health_client.py
# Authenticated calls against the Google Health API (v4).
# Docs: https://developers.google.com/health/reference/rest/v4

from datetime import datetime, timedelta

import httpx

from auth_setup.google_health_auth import get_access_token, refresh_access_token

BASE_URL = "https://health.googleapis.com/v4"


# Sample-type dataTypes (single timestamp, e.g. "sampleTime") filter on
# "sample_time.physical_time" instead of "interval.start_time" - everything
# else WorldWalker tracks is an interval/session type. Confirmed from
# developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list.
SAMPLE_TYPES = {"heart-rate"}


def _parse_iso(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _civil_date(timestamp: str, plus_days: int = 0) -> str:
    return (_parse_iso(timestamp).date() + timedelta(days=plus_days)).isoformat()


def _filter_query(data_type: str, start_time: str, end_time: str) -> str:
    """Comparators are >= and < only (no <=) for every filterable field.
    Two data types don't support filtering on interval.start_time the way
    "steps" does - confirmed against the real API, not assumed:
    - "sleep" only supports interval.end_time.
    - "exercise" only supports interval.civil_start_time - a CALENDAR-DATE
      field (confirmed live: a real 400 INVALID_DATA_POINT_FILTER hit when
      this assumed interval.start_time worked here too, then confirmed
      against developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list).
      Since it's date-granularity, not a precise timestamp, we widen to
      whole civil days here (the exclusive upper bound is bumped a day to
      safely cover a session that started near midnight in the subject's
      local time) and narrow back down to the real requested window in
      get_data_points() after fetching - see _overlaps_window().
    """
    field = data_type.replace("-", "_")
    if data_type == "sleep":
        member = "sleep.interval.end_time"
        return f'{member} >= "{start_time}" AND {member} < "{end_time}"'
    if data_type == "exercise":
        member = "exercise.interval.civil_start_time"
        return f'{member} >= "{_civil_date(start_time)}" AND {member} < "{_civil_date(end_time, plus_days=1)}"'
    if data_type in SAMPLE_TYPES:
        member = f"{field}.sample_time.physical_time"
    else:
        member = f"{field}.interval.start_time"
    return f'{member} >= "{start_time}" AND {member} < "{end_time}"'


def _overlaps_window(point: dict, start_time: str, end_time: str) -> bool:
    """True if this point's own physical interval actually overlaps
    [start_time, end_time). Only meaningful for data types whose API
    filter is coarser than what we actually asked for (exercise's
    civil-date filter can return other sessions from the same calendar
    day) - without this, a second exercise notification the same day
    would re-pull and re-process an earlier session, double-counting it."""
    interval = point.get("interval", {})
    point_start, point_end = interval.get("startTime"), interval.get("endTime")
    if not point_start or not point_end:
        return True  # can't check - keep it rather than risk dropping real data
    return _parse_iso(point_end) > _parse_iso(start_time) and _parse_iso(point_start) < _parse_iso(end_time)


def get_data_points(data_type: str, start_time: str, end_time: str) -> list[dict]:
    """Pull the real data points for a dataType within a time interval.
    Called after a webhook notification tells us data changed for that
    interval; the same call works for a future historical-backfill job.

    Each raw dataPoint is wrapped in an envelope -
    {"dataSource": {...}, "steps": {"interval": ..., "count": "5"}} -
    confirmed against a real response; unwrapped here so callers (the
    fitbitMetrics strategies) get the flat dict their schema expects.
    """
    url = f"{BASE_URL}/users/me/dataTypes/{data_type}/dataPoints"
    filter_query = _filter_query(data_type, start_time, end_time)

    response = _get(url, filter_query)
    if response.status_code == 401:
        refresh_access_token()
        response = _get(url, filter_query)

    if response.status_code >= 400:
        print(f"get_data_points({data_type!r}) -> {response.status_code}:\n{response.text}")
    response.raise_for_status()

    field = _camel_case(data_type)
    raw_points = response.json().get("dataPoints", [])
    points = [point.get(field, point) for point in raw_points]

    if data_type == "exercise":
        points = [p for p in points if _overlaps_window(p, start_time, end_time)]

    return points


def _camel_case(data_type: str) -> str:
    """"heart-rate" -> "heartRate" - the JSON envelope key matches the
    camelCase convention every other field in this API uses (startTime,
    beatsPerMinute, ...), confirmed against a real heart-rate response;
    NOT the snake_case used in filter query field names (a separate,
    proto-style naming convention - see _filter_query)."""
    first, *rest = data_type.split("-")
    return first + "".join(word.capitalize() for word in rest)


def get_profile() -> dict:
    """One-time-ish pull, not webhook-driven (Google doesn't push profile
    change notifications). NOTE: docs disagree on the exact path
    (/v4/users/getProfile vs /v4/users/me/profile) - verify against a
    real call once you have a token; documented fields are limited to
    age + membership start date."""
    return _get_json(f"{BASE_URL}/users/getProfile")


def get_health_user_id() -> str:
    """Your healthUserId, needed to create a MANUAL subscription (see
    scripts/register_webhook_subscription.py - "sleep" needs this, unlike
    steps/exercise/heart-rate which work under the AUTOMATIC policy)."""
    return _get_json(f"{BASE_URL}/users/me/identity")["healthUserId"]


def _get(url: str, filter_query: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    return httpx.get(url, headers=headers, params={"filter": filter_query})


def _get_json(url: str) -> dict:
    headers = {"Authorization": f"Bearer {get_access_token()}"}
    response = httpx.get(url, headers=headers)
    if response.status_code == 401:
        refresh_access_token()
        headers = {"Authorization": f"Bearer {get_access_token()}"}
        response = httpx.get(url, headers=headers)
    response.raise_for_status()
    return response.json()
