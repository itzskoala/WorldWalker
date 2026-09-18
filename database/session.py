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

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
