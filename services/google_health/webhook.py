# services/google_health/webhook.py
# Google pushes a lightweight NOTIFICATION here (dataType + time interval,
# no actual values). We ack it fast (204) and, in the background, pull the
# real data for that interval and route it through the matching strategy.

import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response

from auth.connections import get_active_user_id
from core.facade import travel_facade
from database.session import SessionLocal
from services.google_health.client import get_data_points
from services.fitbitMetrics.fitbit_steps import StepsMetric
from services.fitbitMetrics.fitbit_exercise import ExerciseMetric
from services.fitbitMetrics.fitbit_sleep import SleepMetric
from services.fitbitMetrics.fitbit_heart_rate import HeartRateMetric

load_dotenv()

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
BACKFILL_DATA_TYPES = ("steps", "exercise", "sleep", "heart-rate")

router = APIRouter()


def process_health_data(data_type: str, point: dict, user_id: uuid.UUID) -> None:
    """One real data point (already pulled) -> the matching strategy ->
    a typed object. Steps/exercise drive real travel progress (the
    database TravelFacade owns); sleep/heart-rate are printed structured -
    no persistence yet, nothing reads them back."""
    match data_type:
        case "steps":
            obj = StepsMetric(point).metric_obj()
            print(f"👣 {obj.count} steps between {obj.interval.start_time} and {obj.interval.end_time}")
            try:
                travel_facade.record_steps(user_id, obj.count, obj.interval)
            except ValueError as e:
                print(f"❌ {e}")

        case "exercise":
            obj = ExerciseMetric(point).metric_obj()
            print(f"🏃 {obj.exercise_type} logged. Steps tracked: {obj.metrics_summary.steps}")
            try:
                travel_facade.record_workout(user_id, obj)
            except ValueError as e:
                print(f"❌ {e}")

        case "sleep":
            obj = SleepMetric(point).metric_obj()
            print(f"🛌 Sleep logged: {obj.summary.minutes_asleep} minutes asleep")

        case "heart-rate":
            obj = HeartRateMetric(point).metric_obj()
            print(f"❤️ Heart Rate Pulse: {obj.bpm} BPM")

        case _:
            print(f"❌ Unknown or unhandled dataType: {data_type}")


def process_notification(notification: dict) -> None:
    """A single {"dataType", "operation", "intervals": [...]} entry from
    the webhook payload: pull the real data for each interval, then parse it.
    Resolves the connected user once, up front - single-user MVP, so this is
    always the same account Google is pushing data for. No connection yet
    means there's no trip to credit, so the whole notification is skipped."""
    data_type = notification.get("dataType")
    if not data_type:
        print("❌ Notification missing dataType")
        return

    try:
        with SessionLocal() as session:
            user_id = get_active_user_id(session)
    except RuntimeError as e:
        print(f"❌ Skipping webhook notification - {e}")
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
            process_health_data(data_type, point, user_id)


def backfill_since(start_time: str, end_time: str = None) -> None:
    """One-shot catch-up for the gap BEFORE the webhook ever saw anything.
    Reuses process_notification as-is - a backfilled point goes through
    the exact same pull + dispatch path a live one does."""
    end_time = end_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for data_type in BACKFILL_DATA_TYPES:
        process_notification({
            "dataType": data_type,
            "intervals": [{"physicalTimeInterval": {"startTime": start_time, "endTime": end_time}}],
        })


@router.post("/api/webhook/google-health")
async def handle_google_health_webhook(request: Request, background_tasks: BackgroundTasks):
    if request.headers.get("Authorization") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    # Endpoint-verification handshake (sent once, during subscriber
    # creation): {"type": "verification"}, no "data" key. Must get a plain
    # 200 here, NOT 204 - a 204 fails the handshake.
    if isinstance(payload, dict) and payload.get("type") == "verification":
        return Response(status_code=200)

    notifications = payload if isinstance(payload, list) else [payload]
    for notification in notifications:
        data = notification.get("data")
        if data:
            background_tasks.add_task(process_notification, data)

    # Real notifications: 204 No Content, returned fast - Google requires
    # this; real processing happens in the background task above.
    return Response(status_code=204)
