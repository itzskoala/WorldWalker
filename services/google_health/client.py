# services/google_health/client.py
# Authenticated calls against the Google Health API (v4).
# Docs: https://developers.google.com/health/reference/rest/v4
#
# Every call here acts on behalf of one specific WorldWalker user_id,
# threaded all the way through from the caller (the webhook, a facade
# call, a dev script) - never an ambient "whichever connection is
# active." Token handling goes through auth/connections.py (DB-backed),
# via _current_access_token() - the one seam tests mock out.
# get_health_user_id is the exception: it always takes an explicit
# access_token, since it's called right after exchange_code(), before any
# DB row (and so any user_id to look one up by) exists yet.

from datetime import datetime, timedelta

import httpx

BASE_URL = "https://health.googleapis.com/v4"

# Sample-type dataTypes (single timestamp, e.g. "sampleTime") filter on
# "sample_time.physical_time" instead of "interval.start_time" - everything
# else WorldWalker tracks is an interval/session type.
SAMPLE_TYPES = {"heart-rate"}


def _parse_iso(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def _civil_date(timestamp: str, plus_days: int = 0) -> str:
    return (_parse_iso(timestamp).date() + timedelta(days=plus_days)).isoformat()


def _filter_query(data_type: str, start_time: str, end_time: str) -> str:
    """Two data types don't filter on interval.start_time the way "steps"
    does: "sleep" only supports interval.end_time; "exercise" only
    supports interval.civil_start_time (a calendar-date field, confirmed
    live via a real 400 INVALID_DATA_POINT_FILTER) - widened to whole
    civil days here, narrowed back to the real window in get_data_points()
    via _overlaps_window()."""
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
    interval = point.get("interval", {})
    point_start, point_end = interval.get("startTime"), interval.get("endTime")
    if not point_start or not point_end:
        return True  # can't check - keep it rather than risk dropping real data
    return _parse_iso(point_end) > _parse_iso(start_time) and _parse_iso(point_start) < _parse_iso(end_time)


def _camel_case(data_type: str) -> str:
    first, *rest = data_type.split("-")
    return first + "".join(word.capitalize() for word in rest)


def _current_access_token(user_id, force_refresh: bool = False) -> str:
    from auth import connections
    from database.session import SessionLocal

    with SessionLocal() as session:
        return connections.get_valid_access_token(session, user_id, force_refresh=force_refresh)


def _fetch_data_points_page(url: str, filter_query: str, user_id, page_token: str = None) -> dict:
    """One page, with the same retry-once-on-401 behavior get_data_points
    always had - now applied per page, not just the first."""
    response = _get(url, filter_query, _current_access_token(user_id), page_token)
    if response.status_code == 401:
        response = _get(url, filter_query, _current_access_token(user_id, force_refresh=True), page_token)

    if response.status_code >= 400:
        print(f"get_data_points({url!r}) -> {response.status_code}:\n{response.text}")
    response.raise_for_status()
    return response.json()


def get_data_points(data_type: str, start_time: str, end_time: str, user_id) -> list[dict]:
    """Pull every real data point for a dataType within a time interval,
    for this specific WorldWalker user - loops on nextPageToken so a
    range with more points than fit in one page (default/max is as low
    as 25 for sleep/exercise, 1440 default otherwise) doesn't silently
    truncate."""
    url = f"{BASE_URL}/users/me/dataTypes/{data_type}/dataPoints"
    filter_query = _filter_query(data_type, start_time, end_time)
    field = _camel_case(data_type)

    points = []
    page_token = None
    while True:
        body = _fetch_data_points_page(url, filter_query, user_id, page_token)
        raw_points = body.get("dataPoints", [])
        points.extend(point.get(field, point) for point in raw_points)

        page_token = body.get("nextPageToken")
        if not page_token:
            break

    if data_type == "exercise":
        points = [p for p in points if _overlaps_window(p, start_time, end_time)]

    return points


def roll_up(data_type: str, start_time: str, end_time: str, user_id) -> list[dict]:
    """Server-side aggregated totals over a range, for this specific
    WorldWalker user - reconciles time zone gaps/DST/etc. on Google's
    side instead of summing raw dataPoints ourselves. One bucket covering
    the whole range.

    Path confirmed live: POST /v4/{parent=users/*/dataTypes/*}/dataPoints:rollUp."""
    url = f"{BASE_URL}/users/me/dataTypes/{data_type}/dataPoints:rollUp"
    window_seconds = int((_parse_iso(end_time) - _parse_iso(start_time)).total_seconds())
    body = {"range": {"startTime": start_time, "endTime": end_time}, "windowSize": f"{window_seconds}s"}

    response = _post(url, body, _current_access_token(user_id))
    if response.status_code == 401:
        response = _post(url, body, _current_access_token(user_id, force_refresh=True))

    if response.status_code >= 400:
        print(f"roll_up({data_type!r}) -> {response.status_code}:\n{response.text}")
    response.raise_for_status()
    return response.json().get("rollupDataPoints", [])


def get_steps_total(start_time: str, end_time: str, user_id) -> int:
    """Total steps for the range, per Google's own rollup - confirmed
    field name: StepsRollupValue.countSum (int64-as-string)."""
    points = roll_up("steps", start_time, end_time, user_id)
    return sum(int(p["steps"]["countSum"]) for p in points)


def get_heart_rate_summary(start_time: str, end_time: str, user_id) -> dict:
    """Avg/min/max bpm for the range, per Google's own rollup - confirmed
    fields: HeartRateRollupValue.beatsPerMinuteAvg/Max/Min. One API call
    regardless of range length; heart-rate samples every few seconds, so
    pulling every raw point for a wide window (get_data_points) means
    dozens of paginated requests for no reason if all you want is a
    summary. {} if there's no data in the range."""
    points = roll_up("heart-rate", start_time, end_time, user_id)
    if not points:
        return {}
    values = [p["heartRate"] for p in points]
    return {
        "avg_bpm": sum(v["beatsPerMinuteAvg"] for v in values) / len(values),
        "min_bpm": min(v["beatsPerMinuteMin"] for v in values),
        "max_bpm": max(v["beatsPerMinuteMax"] for v in values),
    }


def get_profile(user_id) -> dict:
    """One-time-ish pull, not webhook-driven, for this specific
    WorldWalker user. Documented fields are limited to age + membership
    start date.

    Path confirmed live: GET /v4/{name=users/*/profile} per Google's REST
    reference - not /v4/users/getProfile (404, an earlier unverified guess)."""
    headers = {"Authorization": f"Bearer {_current_access_token(user_id)}"}
    response = httpx.get(f"{BASE_URL}/users/me/profile", headers=headers)
    response.raise_for_status()
    return response.json()


def get_health_user_id(access_token: str) -> str:
    """Always called with an explicit access_token, right after
    exchange_code() - before any DB row (and so any user_id) exists yet
    to look an ambient token up by."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = httpx.get(f"{BASE_URL}/users/me/identity", headers=headers)
    response.raise_for_status()
    return response.json()["healthUserId"]


def _get(url: str, filter_query: str, token: str, page_token: str = None) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"}
    params = {"filter": filter_query}
    if page_token:
        params["pageToken"] = page_token
    return httpx.get(url, headers=headers, params=params)


def _post(url: str, body: dict, token: str) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    return httpx.post(url, headers=headers, json=body)
