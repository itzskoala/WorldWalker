# services/fitbit_service.py
#
# Google pushes a lightweight NOTIFICATION here (dataType + time interval,
# no actual values - see docs/prompt_log/). We ack it fast (204) and, in
# the background, pull the real data for that interval and route it
# through the matching strategy.

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Response
from services.google_health_client import get_data_points
from services.fitbitMetrics.fitbit_steps import StepsMetric
from services.fitbitMetrics.fitbit_exercise import ExerciseMetric
from services.fitbitMetrics.fitbit_sleep import SleepMetric
from services.fitbitMetrics.fitbit_heart_rate import HeartRateMetric

app = FastAPI()

WEBHOOK_SECRET = "Bearer MySuperSecureSecretToken"


def process_health_data(data_type: str, point: dict):
    """One real data point (already pulled) -> the matching strategy."""
    match data_type:
        case "steps":
            obj = StepsMetric(point).metric_obj()
            print(f"👣 {obj.count} steps between {obj.interval.start_time} and {obj.interval.end_time}")

        case "exercise":
            obj = ExerciseMetric(point).metric_obj()
            print(f"🏃 {obj.exercise_type} logged. Steps tracked: {obj.metrics_summary.steps}")

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
