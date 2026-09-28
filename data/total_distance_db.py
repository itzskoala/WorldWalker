# data/total_distance_db.py
# Postgres-backed sync history: one row per (trip, Fitbit sync) pair. Kept
# out of travel_logic/progress_calculator.py on purpose - that module
# stays pure math/no I/O, this is the one place that touches this data.
#
# Used to be its own SQLite file (total_distance.db) - fine for local dev,
# but Vercel's production filesystem is read-only, so every write crashed
# with "attempt to write a readonly database". Rows now live in Postgres
# (database/models.py's StepSyncLog, see migrations/versions/
# 745142a3bb1c_add_step_sync_log_table.py) - same schema, same query
# shapes, just a real persistent store. SessionLocal is imported and used
# the same lazy way core/facade.py's methods do, so tests/conftest.py's
# patched_session fixture can swap it out per-test.
#
# Scoped by trip_id, not user_id: a user can have several trips going at
# once now (see database/trips.py), and a real step event can credit more
# than one of them at the same time (core/facade.py's record_steps/
# record_workout fan out across every active trip) - each trip logs its
# own row for that same event, so "today's steps"/"total steps" on one
# trip's metrics strip never includes steps another trip racked up.

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from database.models import StepSyncLog
from database.session import SessionLocal


class TotalDistanceDB:
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
        # UTC day boundary, computed here rather than trusting the DB
        # session's timezone - matches the old SQLite version's
        # date(synced_at) = date('now'), which was always a UTC date since
        # synced_at was written as datetime.now(timezone.utc).isoformat().
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
        # Every row already carries user_id (see the module docstring -
        # rows are scoped by trip_id for the per-trip counters above, but
        # each one also knows who it belongs to), so a lifetime total
        # across every trip a user has ever run is the same SUM with the
        # other column, not a new concept or a fetch-every-trip loop from
        # the caller.
        with SessionLocal() as session:
            return (
                session.query(func.coalesce(func.sum(StepSyncLog.steps), 0))
                .filter(StepSyncLog.user_id == uuid.UUID(str(user_id)))
                .scalar()
            )
