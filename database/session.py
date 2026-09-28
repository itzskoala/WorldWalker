# database/session.py
# The app's real runtime DB connection (DATABASE_URL) - distinct from
# tests/conftest.py's db_engine fixture, which points at TEST_DATABASE_URL
# so the test suite never touches dev data.

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Copy .env.example to .env and fill it in, "
        "or export DATABASE_URL yourself."
    )

# pool_pre_ping: Neon (and most managed Postgres) closes idle connections
# server-side - without this, a serverless function reusing a warm
# container picks a dead connection back out of the pool and fails with
# psycopg.OperationalError ("SSL connection has been closed
# unexpectedly") instead of transparently reconnecting. Confirmed live in
# production (2026-09-23) on /auth/signup right after a migration.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
