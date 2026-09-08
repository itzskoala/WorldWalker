# services/fitbit_service.py
#
# Google pushes a lightweight NOTIFICATION here (dataType + time interval,
# no actual values - see docs/prompt_log/). We ack it fast (204) and, in
# the background, pull the real data for that interval and route it
# through the matching strategy.

from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Response
from services.google_health_client import get_data_points
from services.fitbitMetrics.fitbit_steps import StepsMetric
from services.fitbitMetrics.fitbit_exercise import ExerciseMetric
from services.fitbitMetrics.fitbit_sleep import SleepMetric
from services.fitbitMetrics.fitbit_heart_rate import HeartRateMetric
from core.facade import travel_facade, DEFAULT_USER_ID

app = FastAPI()

WEBHOOK_SECRET = "Bearer MySuperSecureSecretToken"


def process_health_data(data_type: str, point: dict):
    """One real data point (already pulled) -> the matching strategy."""
    match data_type:
        case "steps":
            obj = StepsMetric(point).metric_obj()
            print(f"👣 {obj.count} steps between {obj.interval.start_time} and {obj.interval.end_time}")
            try:
                travel_facade.record_steps(DEFAULT_USER_ID, obj.count, obj.interval)
            except ValueError as e:
                print(f"❌ {e}")

        case "exercise":
            obj = ExerciseMetric(point).metric_obj()
            print(f"🏃 {obj.exercise_type} logged. Steps tracked: {obj.metrics_summary.steps}")
            try:
                travel_facade.record_workout(DEFAULT_USER_ID, obj)
            except ValueError as e:
                print(f"❌ {e}")

        case "sleep":
            obj = SleepMetric(point).metric_obj() #only need to sleep to grab sleep ONCE at the first sync of the day...need to implement this! 
            print(f"🛌 Sleep logged: {obj.summary.minutes_asleep} minutes asleep")

        case "heart-rate":
            obj = HeartRateMetric(point).metric_obj()
            print(f"❤️ Heart Rate Pulse: {obj.bpm} BPM")

        case _:
            print(f"❌ Unknown or unhandled dataType: {data_type}")


def process_notification(notification: dict):
    """A single {"dataType", "operation", "intervals": [...]} entry from
    the webhook payload: pull the real data for each interval, then parse it."""
    data_type = notification.get("dataType")
    if not data_type:
        print("❌ Notification missing dataType")
        return

    for interval_wrapper in notification.get("intervals", []):
        interval = interval_wrapper.get("physicalTimeInterval", {})
        start_time, end_time = interval.get("startTime"), interval.get("endTime")
        if not start_time or not end_time:
            continue

        try:
            points = get_data_points(data_type, start_time, end_time)
        except Exception as e:
            print(f"❌ Failed to pull {data_type} for {start_time}-{end_time}: {e}")
            continue

        for point in points:
            process_health_data(data_type, point)


BACKFILL_DATA_TYPES = ("steps", "exercise", "sleep", "heart-rate")


def backfill_since(start_time: str, end_time: str = None) -> None:
    """One-shot catch-up for the gap BEFORE the webhook ever saw anything -
    e.g. a journey started last Saturday but the watch's first real sync
    doesn't happen until today. The webhook only ever reports data forward
    from whenever Google actually pushes a notification; it has no way to
    tell you about a gap that predates that. Call this once, manually,
    right after start_journey (not on a schedule - YAGNI until repeated
    catch-up is actually needed).

    Reuses process_notification as-is: builds the same
    {"dataType", "intervals": [...]}} shape a real webhook notification
    carries, so a backfilled point goes through the exact same pull +
    dispatch path a live one does - one pipeline, not two.

    start_time/end_time: ISO 8601 UTC, e.g. "2026-09-05T00:00:00Z".
    end_time defaults to now.

    Known limitation: get_data_points() doesn't paginate - fine for the
    few-day gaps this is meant for, but a very long backfill could
    silently truncate if a dataType has more points than one API page
    holds. Revisit if that turns out to matter.
    """
    end_time = end_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for data_type in BACKFILL_DATA_TYPES:
        process_notification({
            "dataType": data_type,
            "intervals": [{"physicalTimeInterval": {"startTime": start_time, "endTime": end_time}}],
        })


# This is the Webhook Endpoint Google talks to
@app.post("/api/webhook/google-health")
async def handle_google_health_webhook(request: Request, background_tasks: BackgroundTasks):
    # Verify the secret token matches what you configured in Google Cloud.
    if request.headers.get("Authorization") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    # Endpoint-verification handshake (sent once, during subscriber
    # creation): {"type": "verification"}, no "data" key. Must get a plain
    # 200/201 here, NOT 204 - a 204 fails the handshake and subscriber
    # creation comes back as FAILED_PRECONDITION.
    if isinstance(payload, dict) and payload.get("type") == "verification":
        return Response(status_code=200)

    notifications = payload if isinstance(payload, list) else [payload]
    for notification in notifications:
        data = notification.get("data")
        if data:
            background_tasks.add_task(process_notification, data)

    # Real notifications: 204 No Content, returned fast - Google requires
    # this; real processing happens in the background tasks above.
    return Response(status_code=204)
