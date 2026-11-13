# data/total_distance_db.py

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from backend.database.models import StepSyncLog
from backend.database.session import SessionLocal


class TotalDistanceDB:
    def total_steps_by_trip(self, trip_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not trip_ids:
            return {}
        with SessionLocal() as session:
            rows = (
                session.query(StepSyncLog.trip_id, func.sum(StepSyncLog.steps))
                .filter(StepSyncLog.trip_id.in_(trip_ids))
                .group_by(StepSyncLog.trip_id)
                .all()
            )
            return {trip_id: total for trip_id, total in rows}


    def record_sync(
        self,
        user_id: str,
        trip_id: str,
        steps: int,
        distance_walked_miles: float,
        distance_remaining_miles: float,
        percent_complete: float,
        synced_at: datetime,
    ) -> None:
        with SessionLocal() as session:
            session.add(StepSyncLog(
                user_id=uuid.UUID(str(user_id)),
                trip_id=uuid.UUID(str(trip_id)),
                steps=steps,
                distance_walked_miles=distance_walked_miles,
                distance_remaining_miles=distance_remaining_miles,
                percent_complete=percent_complete,
                synced_at=synced_at,
            ))
            session.commit()

    def total_steps(self, trip_id: str) -> int:
        with SessionLocal() as session:
            return (
                session.query(func.coalesce(func.sum(StepSyncLog.steps), 0))
                .filter(StepSyncLog.trip_id == uuid.UUID(str(trip_id)))
                .scalar()
            )

    def today_steps(self, trip_id: str) -> int:
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        with SessionLocal() as session:
            return (
                session.query(func.coalesce(func.sum(StepSyncLog.steps), 0))
                .filter(
                    StepSyncLog.trip_id == uuid.UUID(str(trip_id)),
                    StepSyncLog.synced_at >= start_of_day,
                    StepSyncLog.synced_at < end_of_day,
                )
                .scalar()
            )

    def lifetime_steps(self, user_id: str) -> int:
        with SessionLocal() as session:
            return (
                session.query(func.coalesce(func.sum(StepSyncLog.steps), 0))
                .filter(StepSyncLog.user_id == uuid.UUID(str(user_id)))
                .scalar()
            )
