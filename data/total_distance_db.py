#total_distance_db.py
# SQLite-backed sync history: one row per Fitbit sync (facade.record_steps
# call). Kept out of travel_logic/progress_calculator.py on purpose - that
# module stays pure math/no I/O, this is the one place that touches a DB.
# SQLite over Postgres for the MVP: single file, no server/connection
# string to set up, plenty for one user's sync history - swap later if
# this ever needs concurrent writers.

import sqlite3
from datetime import datetime

DEFAULT_DB_PATH = "data/total_distance.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS total_distance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    steps INTEGER NOT NULL,
    distance_walked_miles REAL NOT NULL,
    distance_remaining_miles REAL NOT NULL,
    percent_complete REAL NOT NULL,
    synced_at TEXT NOT NULL
);
"""

INSERT_SQL = """
INSERT INTO total_distance_log
    (user_id, steps, distance_walked_miles, distance_remaining_miles, percent_complete, synced_at)
VALUES (?, ?, ?, ?, ?, ?);
"""

# Total/today's steps are SUMs over this same log, not separately-stored
# counters - one write per sync, nothing that can drift out of sync with it.
TOTAL_STEPS_SQL = "SELECT COALESCE(SUM(steps), 0) FROM total_distance_log WHERE user_id = ?;"
TODAY_STEPS_SQL = "SELECT COALESCE(SUM(steps), 0) FROM total_distance_log WHERE user_id = ? AND date(synced_at) = date('now');"


class TotalDistanceDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def record_sync(
        self,
        user_id: str,
        steps: int,
        distance_walked_miles: float,
        distance_remaining_miles: float,
        percent_complete: float,
        synced_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                INSERT_SQL,
                (user_id, steps, distance_walked_miles, distance_remaining_miles, percent_complete, synced_at.isoformat()),
            )

    def total_steps(self, user_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(TOTAL_STEPS_SQL, (user_id,)).fetchone()[0]

    def today_steps(self, user_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(TODAY_STEPS_SQL, (user_id,)).fetchone()[0]
