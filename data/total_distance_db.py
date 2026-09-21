#total_distance_db.py
# SQLite-backed sync history: one row per (trip, Fitbit sync) pair. Kept
# out of travel_logic/progress_calculator.py on purpose - that module
# stays pure math/no I/O, this is the one place that touches a DB.
# SQLite over Postgres for the MVP: single file, no server/connection
# string to set up, plenty for one user's sync history - swap later if
# this ever needs concurrent writers.
#
# Scoped by trip_id, not user_id: a user can have several trips going at
# once now (see database/trips.py), and a real step event can credit more
# than one of them at the same time (core/facade.py's record_steps/
# record_workout fan out across every active trip) - each trip logs its
# own row for that same event, so "today's steps"/"total steps" on one
# trip's metrics strip never includes steps another trip racked up.

import sqlite3
from datetime import datetime

DEFAULT_DB_PATH = "data/total_distance.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS total_distance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    trip_id TEXT,
    steps INTEGER NOT NULL,
    distance_walked_miles REAL NOT NULL,
    distance_remaining_miles REAL NOT NULL,
    percent_complete REAL NOT NULL,
    synced_at TEXT NOT NULL
);
"""

INSERT_SQL = """
INSERT INTO total_distance_log
    (user_id, trip_id, steps, distance_walked_miles, distance_remaining_miles, percent_complete, synced_at)
VALUES (?, ?, ?, ?, ?, ?, ?);
"""

# Total/today's steps are SUMs over this same log, not separately-stored
# counters - one write per (trip, sync), nothing that can drift out of
# sync with it.
TOTAL_STEPS_SQL = "SELECT COALESCE(SUM(steps), 0) FROM total_distance_log WHERE trip_id = ?;"
TODAY_STEPS_SQL = "SELECT COALESCE(SUM(steps), 0) FROM total_distance_log WHERE trip_id = ? AND date(synced_at) = date('now');"


class TotalDistanceDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path

    def _connect(self):
        # Re-runs the (idempotent) schema setup on every connection, not
        # just once at construction time - this process holds one
        # TravelFacade/TotalDistanceDB instance for its whole lifetime, so
        # if the underlying file is ever deleted or replaced out from under
        # it (a dev-machine cleanup step, a fresh deploy volume, ...) the
        # next write self-heals instead of failing with "no such table".
        conn = sqlite3.connect(self._db_path)
        conn.execute(CREATE_TABLE_SQL)
        self._ensure_trip_id_column(conn)
        return conn

    def _ensure_trip_id_column(self, conn: sqlite3.Connection) -> None:
        """A DB file written before multi-trip support has no trip_id
        column - add it (nullable, so pre-existing rows just aren't
        attributable to any one trip) instead of requiring a fresh file."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(total_distance_log)")}
        if "trip_id" not in columns:
            conn.execute("ALTER TABLE total_distance_log ADD COLUMN trip_id TEXT")

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
        with self._connect() as conn:
            conn.execute(
                INSERT_SQL,
                (user_id, trip_id, steps, distance_walked_miles, distance_remaining_miles, percent_complete, synced_at.isoformat()),
            )

    def total_steps(self, trip_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(TOTAL_STEPS_SQL, (trip_id,)).fetchone()[0]

    def today_steps(self, trip_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(TODAY_STEPS_SQL, (trip_id,)).fetchone()[0]
