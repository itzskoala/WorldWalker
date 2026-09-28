# auth/oauth_state.py
# Persists the OAuth `state` CSRF token in Postgres (database/models.py's
# OAuthState) instead of an in-process dict - a real deployment runs more
# than one Uvicorn worker, and a state issued by one must be consumable
# by whichever worker handles the callback. auth/google_health_auth.py
# stays pure OAuth HTTP and never touches this table itself - it takes an
# already-issued state as a plain string; auth/router.py calls both.

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from database.models import OAuthState

# Short-lived on purpose: this only needs to outlive the redirect to
# Google and back, not a real session.
STATE_TTL = timedelta(minutes=10)


def issue_state(session: Session, user_id: uuid.UUID) -> str:
    """A fresh, random, single-use state bound to this WorldWalker user -
    auth/router.py's callback must present it back (once, before it
    expires) to recover user_id. Also opportunistically clears out any
    expired, never-consumed states - nothing else ever deletes those."""
    session.query(OAuthState).filter(OAuthState.expires_at < datetime.now(timezone.utc)).delete()

    state = secrets.token_urlsafe(32)
    session.add(OAuthState(
        state=state, user_id=user_id, expires_at=datetime.now(timezone.utc) + STATE_TTL,
    ))
    session.commit()
    print(f"🔐 auth: issued state {state[:8]}... for user {user_id}")
    return state


def consume_state(session: Session, state: str) -> uuid.UUID | None:
    """The WorldWalker user_id this state was issued for, or None if
    it's unknown, already used, or expired. Deletes the row on every
    call (even an expired hit) so each state is single-use - replaying
    an old callback URL (or a guessed/leaked state) fails the second
    time."""
    pending = session.get(OAuthState, state)
    if pending is None:
        return None

    user_id, expires_at = pending.user_id, pending.expires_at
    session.delete(pending)
    session.commit()

    if expires_at < datetime.now(timezone.utc):
        return None
    return user_id
