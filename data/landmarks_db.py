#landmarks_db.py
# One row per landmark on a user's route - written once when a journey
# starts (not per-sync, unlike total_distance_log). Rows, not
# landmark_1/landmark_2/... columns: a route's landmark count varies, and
# numbered columns don't survive that.
#
# "Distance to a landmark" is NOT stored here - it's just
# landmark.miles_from_start - miles_walked, computed live wherever it's
# needed (see core/facade.py). Storing it would mean rewriting every row
# on every sync for no reason.

import sqlite3
from data.total_distance_db import DEFAULT_DB_PATH

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS route_landmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    miles_from_start REAL NOT NULL,
    percent REAL NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);
"""

CLEAR_FOR_USER_SQL = "DELETE FROM route_landmarks WHERE user_id = ?;"

INSERT_SQL = """
INSERT INTO route_landmarks (user_id, name, lat, lng, miles_from_start, percent)
VALUES (?, ?, ?, ?, ?, ?);
"""

ALL_FOR_USER_SQL = """
SELECT id, name, lat, lng, miles_from_start, percent, notified
FROM route_landmarks WHERE user_id = ? ORDER BY miles_from_start;
"""

UNNOTIFIED_PASSED_SQL = """
SELECT id, name, lat, lng, miles_from_start, percent
FROM route_landmarks WHERE user_id = ? AND notified = 0 AND miles_from_start <= ?
ORDER BY miles_from_start;
"""

MARK_NOTIFIED_SQL = "UPDATE route_landmarks SET notified = 1 WHERE id = ?;"


class LandmarksDB:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self._db_path = db_path
        with self._connect() as conn:
            conn.execute(CREATE_TABLE_SQL)

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def save_landmarks(self, user_id: str, checkpoints: list) -> None:
        """Replaces any prior landmark set for this user - called once,
        right after a route is built."""
        with self._connect() as conn:
            conn.execute(CLEAR_FOR_USER_SQL, (user_id,))
            conn.executemany(
                INSERT_SQL,
                [(user_id, c.name, c.coords.lat, c.coords.lng, c.miles_from_start, c.percent) for c in checkpoints],
            )

    def all_landmarks(self, user_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(ALL_FOR_USER_SQL, (user_id,)).fetchall()
        return [_row_to_dict(r, has_notified=True) for r in rows]

    def landmarks_just_passed(self, user_id: str, miles_walked: float) -> list:
        """Unnotified landmarks at or behind the current position - marks
        them notified so each one only fires once. Call this after every
        sync; feed the result to whatever sends notifications."""
        with self._connect() as conn:
            rows = conn.execute(UNNOTIFIED_PASSED_SQL, (user_id, miles_walked)).fetchall()
            conn.executemany(MARK_NOTIFIED_SQL, [(row[0],) for row in rows])
        return [_row_to_dict(r, has_notified=False) for r in rows]


def _row_to_dict(row: tuple, has_notified: bool) -> dict:
    d = {
        "name": row[1],
        "coords": {"lat": row[2], "lng": row[3]},
        "miles_from_start": row[4],
        "percent": row[5],
    }
    if has_notified:
        d["notified"] = bool(row[6])
    return d
