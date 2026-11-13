# accounts/dependencies.py

'''
Centralizes authentication so every protected endpoint can simply request current_user 
instead of implementing JWT validation itself
'''
import uuid

import jwt
from fastapi import HTTPException, Request

from backend.accounts import security
from backend.accounts.service import get_user_by_id
from backend.database.models import User
from backend.database.session import SessionLocal


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return header[len("Bearer "):]


def get_current_user(request: Request) -> User:
    token = _bearer_token(request)

    try:
        payload = security.decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if payload.get("type") != security.ACCESS_TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Not an access token")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid access token"
        )
    
    with SessionLocal() as session:
        user = get_user_by_id(session, user_id)

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer exists or is inactive")

    return user
