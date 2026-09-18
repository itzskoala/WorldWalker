# tests/conftest.py
# Shared fixture for tests that hit a real Postgres (not SQLite - UUID
# columns and CHECK constraints don't behave identically on SQLite, and
# tests/test_database_models.py specifically wants to prove the real
# engine enforces the Step 3 schema's constraints).
#
# Points at TEST_DATABASE_URL (a separate database from DATABASE_URL, see
# .env) so the test suite never touches real/dev data.

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database.models import Base

load_dotenv()

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Each test runs inside its own outer transaction, rolled back at
    teardown - no test ever sees another test's rows, and nothing needs
    manual cleanup between tests.

    A test that triggers a real IntegrityError (e.g. flushing a duplicate
    provider_user_id) makes the ORM roll back its *own* transaction
    immediately - which would normally take our outer transaction down
    with it, since they're the same one. The SAVEPOINT (begin_nested)
    below gives the session its own inner transaction to roll back
    instead, restarted via the event listener every time one ends, so the
    outer transaction we control always survives until this fixture's own
    teardown rolls it back once."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()

    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, sess_transaction):
        if sess_transaction.nested and not sess_transaction._parent.nested:
            sess.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
