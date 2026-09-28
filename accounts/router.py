# accounts/router.py
# Signup, login, refresh, logout, and "who am I" for the login system.
# The access token goes back in the JSON body (the frontend keeps it in
# memory); the refresh token goes in an HTTP-only cookie.

import os
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from accounts import security
from accounts.dependencies import get_current_user
from accounts.schemas import AccessTokenResponse, LoginRequest, SignupRequest, UserOut
from accounts.service import authenticate, get_user_by_id, signup
from database.models import User
from database.session import SessionLocal

router = APIRouter(prefix="/auth")

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=security.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )


def _issue_tokens(response: Response, user_id: uuid.UUID) -> AccessTokenResponse:
    access_token = security.create_access_token(str(user_id))
    refresh_token = security.create_refresh_token(str(user_id))
    _set_refresh_cookie(response, refresh_token)
    return AccessTokenResponse(access_token=access_token)


@router.post("/signup", response_model=AccessTokenResponse)
def signup_route(body: SignupRequest, response: Response):
    with SessionLocal() as session:
        try:
            user = signup(session, body.email, body.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return _issue_tokens(response, user.id)


@router.post("/login", response_model=AccessTokenResponse)
def login_route(body: LoginRequest, response: Response):
    with SessionLocal() as session:
        user = authenticate(session, body.email, body.password)

    if user is None:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    return _issue_tokens(response, user.id)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_route(request: Request):
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        payload = security.decode_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != security.REFRESH_TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user_id = uuid.UUID(payload["sub"])
    with SessionLocal() as session:
        user = get_user_by_id(session, user_id)

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer exists or is inactive")

    access_token = security.create_access_token(str(user.id))
    return AccessTokenResponse(access_token=access_token)


@router.post("/logout")
def logout_route(response: Response):
    response.delete_cookie(REFRESH_COOKIE_NAME)
    return {"detail": "Logged out"}


@router.get("/me", response_model=UserOut)
def me_route(current_user: User = Depends(get_current_user)):
    return UserOut(id=str(current_user.id), email=current_user.email, is_active=current_user.is_active)
