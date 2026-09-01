# services/google_health_client.py
# Authenticated calls against the Google Health API (v4).
# Docs: https://developers.google.com/health/reference/rest/v4

import httpx

from auth_setup.google_health_auth import get_access_token, refresh_access_token

BASE_URL = "https://health.googleapis.com/v4"


# Sample-type dataTypes (single timestamp, e.g. "sampleTime") filter on
# "sample_time.physical_time" instead of "interval.start_time" - everything
# else WorldWalker tracks is an interval/session type. Confirmed from
# developers.google.com/health/reference/rest/v4/users.dataTypes.dataPoints/list.
SAMPLE_TYPES = {"heart-rate"}


def _filter_query(data_type: str, start_time: str, end_time: str) -> str:
    """Comparators are >= and < only (no <=) for every filterable field.
    "sleep" is a further special case: it only supports filtering on
    interval.end_time, not interval.start_time - also confirmed from the
    list-method reference above."""
    field = data_type.replace("-", "_")
    if data_type == "sleep":
        member = "sleep.interval.end_time"
    elif data_type in SAMPLE_TYPES:
        member = f"{field}.sample_time.physical_time"
    else:
        member = f"{field}.interval.start_time"
    return f'{member} >= "{start_time}" AND {member} < "{end_time}"'


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
    return [point.get(field, point) for point in raw_points]


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
