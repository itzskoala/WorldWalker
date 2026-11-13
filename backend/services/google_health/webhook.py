# services/google_health/webhook.py

import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response

from backend.auth.connections import get_user_id_for_provider_user_id
from backend.facade import travel_facade
from backend.database.session import SessionLocal
from backend.services.google_health.client import get_data_points
from backend.services.health_metrics.steps import StepsMetric
from backend.services.health_metrics.exercise import ExerciseMetric

load_dotenv()

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
BACKFILL_DATA_TYPES = ("steps", "exercise")

router = APIRouter()


def process_health_data(data_type: str, point: dict, user_id: uuid.UUID) -> None:
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

        case _:
            print(f"❌ Unknown or unhandled dataType: {data_type}")


def _provider_user_id(notification: dict) -> str | None:
    return notification.get("healthUserId")


def process_notification(notification: dict) -> None:
    data_type = notification.get("dataType")
    if not data_type:
        print("❌ Notification missing dataType")
        return

    provider_user_id = _provider_user_id(notification)
    if provider_user_id is None:
        print("❌ Notification missing a healthUserId - can't tell which WorldWalker account this belongs to")
        return

    try:
        with SessionLocal() as session:
            user_id = get_user_id_for_provider_user_id(session, provider_user_id)
    except RuntimeError as e:
        print(f"❌ Skipping webhook notification - {e}")
        return

    for interval_wrapper in notification.get("intervals", []):
        interval = interval_wrapper.get("physicalTimeInterval", {})
        start_time, end_time = interval.get("startTime"), interval.get("endTime")
        if not start_time or not end_time:
            continue

        try:
            points = get_data_points(data_type, start_time, end_time, user_id)
        except Exception as e:
            print(f"❌ Failed to pull {data_type} for {start_time}-{end_time}: {e}")
            continue

        for point in points:
            process_health_data(data_type, point, user_id)


def backfill_since(provider_user_id: str, start_time: str, end_time: str = None) -> None:
    end_time = end_time or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for data_type in BACKFILL_DATA_TYPES:
        process_notification({
            "dataType": data_type,
            "healthUserId": provider_user_id,
            "intervals": [{"physicalTimeInterval": {"startTime": start_time, "endTime": end_time}}],
        })


@router.post("/api/webhook/google-health")
async def handle_google_health_webhook(request: Request, background_tasks: BackgroundTasks):
    if request.headers.get("Authorization") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    if isinstance(payload, dict) and payload.get("type") == "verification":
        return Response(status_code=200)

    notifications = payload if isinstance(payload, list) else [payload]
    for notification in notifications:
        data = notification.get("data")
        if data:
            background_tasks.add_task(process_notification, data)

    return Response(status_code=204)
