# auth/oauth_state.py

'''
Handles OAuth state generation, storage, expiration, and validation
'''

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.database.models import OAuthState

STATE_TTL = timedelta(minutes=10)


def issue_state(session: Session, user_id: uuid.UUID) -> str:
    session.query(OAuthState).filter(OAuthState.expires_at < datetime.now(timezone.utc)).delete()

    state = secrets.token_urlsafe(32)
    session.add(OAuthState(
        state=state, user_id=user_id, expires_at=datetime.now(timezone.utc) + STATE_TTL,
    ))
    session.commit()
    print(f"🔐 auth: issued state {state[:8]}... for user {user_id}")
    return state


def consume_state(session: Session, state: str) -> uuid.UUID | None:
    pending = session.get(OAuthState, state)
    if pending is None:
        return None

    user_id, expires_at = pending.user_id, pending.expires_at
    session.delete(pending)
    session.commit()

    if expires_at < datetime.now(timezone.utc):
        return None
    return user_id
