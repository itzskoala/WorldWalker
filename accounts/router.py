# accounts/router.py
# Signup, login, refresh, logout, and "who am I" for the login system.
# The access token goes back in the JSON body (the frontend keeps it in
# memory); the refresh token goes in an HTTP-only cookie.
#
# Signup is one call (POST /signup) that creates the account and issues
# tokens immediately - see accounts/service.py's signup().

import os
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from accounts import email_validation, security, username_validation
from accounts.dependencies import get_current_user
from accounts.google_oauth import GoogleTokenError, verify_google_id_token
from accounts.schemas import (
    AccessTokenResponse,
    GoogleAuthRequest,
    LoginRequest,
    ProfileUpdateRequest,
    SignupRequest,
    UserOut,
)
from accounts.service import (
    authenticate,
    get_user_by_id,
    get_user_by_username,
    signup,
    signup_or_login_google,
    update_username,
)
from database.models import User
from database.session import SessionLocal
from user_profile.profile_page import (
    get_bio,
    get_f_name,
    get_l_name,
    get_lifetime_steps,
    get_member_since,
    get_postcards_sum,
    get_profile_photo,
    get_username,
    set_f_name,
    set_l_name,
    set_profile_photo,
    set_user_bio,
)

router = APIRouter(prefix="/auth")

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"


def _set_refresh_cookie(response: Response, refresh_token: str, remember_me: bool) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        # remember_me=False: no max_age at all: a session cookie, which
        # most browsers drop the moment the browser (not just the tab)
        # closes - the short-lived JWT from create_refresh_token() below
        # is the real backstop for browsers that restore session cookies
        # across restarts anyway.
        max_age=security.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60 if remember_me else None,
    )


def _issue_tokens(response: Response, user_id: uuid.UUID, remember_me: bool = True) -> AccessTokenResponse:
    access_token = security.create_access_token(str(user_id))
    refresh_token = security.create_refresh_token(str(user_id), remember_me=remember_me)
    _set_refresh_cookie(response, refresh_token, remember_me)
    return AccessTokenResponse(access_token=access_token)


@router.get("/validate-email")
def validate_email_route(email: str):
    """The signup form's real-time check (frontend/src/pages/SignupPage.tsx) -
    same syntax+MX check accounts/service.py's signup() reruns
    server-side before ever creating the account, see accounts/email_validation.py."""
    return {"valid": email_validation.is_valid_email(email)}


@router.get("/validate-username")
def validate_username_route(username: str, current_user: User = Depends(get_current_user)):
    """The profile form's real-time check
    (frontend/src/components/profile/ProfileUsernameField.tsx) - the same
    format+uniqueness rules PATCH /auth/me enforces on submit (accounts/
    service.py's update_username()), just without persisting anything.
    Authenticated (unlike /validate-email) so a user's own current
    username never reports itself as taken."""
    if not username_validation.is_valid_format(username):
        return {"valid": False, "reason": "format"}

    if username:
        with SessionLocal() as session:
            existing = get_user_by_username(session, username)
            if existing is not None and existing.id != current_user.id:
                return {"valid": False, "reason": "taken"}

    return {"valid": True, "reason": None}


@router.post("/signup", response_model=AccessTokenResponse)
def signup_route(body: SignupRequest, response: Response):
    """Creates the account and starts the session in one call - the
    signup form's real-time email check and the password-strength meter
    (frontend/src/pages/SignupPage.tsx) are the only front-line checks
    before this; accounts/service.py's signup() re-validates and is what
    actually decides."""
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

    return _issue_tokens(response, user.id, remember_me=body.remember_me)


@router.post("/google", response_model=AccessTokenResponse)
def google_auth_route(body: GoogleAuthRequest, response: Response):
    """The Google button's endpoint (frontend/src/components/
    GoogleSignInButton.tsx) - one route for both "new Google account" and
    "returning Google account", same as Google's own guidance for GIS.
    Verifies the ID token first, so nothing below ever trusts an
    email/sub the client merely claims."""
    try:
        claims = verify_google_id_token(body.credential)
    except GoogleTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))

    with SessionLocal() as session:
        try:
            user = signup_or_login_google(
                session,
                sub=claims["sub"],
                email=claims.get("email"),
                email_verified=claims.get("email_verified", False),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        if not user.is_active:
            raise HTTPException(status_code=401, detail="Account is deactivated")

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


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        username=get_username(user),
        f_name=get_f_name(user),
        l_name=get_l_name(user),
        profile_photo=get_profile_photo(user),
        bio=get_bio(user),
        lifetime_steps=get_lifetime_steps(user),
        postcards_sum=get_postcards_sum(user),
        member_since=get_member_since(user).isoformat(),
    )


@router.get("/me", response_model=UserOut)
def me_route(current_user: User = Depends(get_current_user)):
    return _user_out(current_user)


@router.patch("/me", response_model=UserOut)
def update_me_route(body: ProfileUpdateRequest, current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        user = get_user_by_id(session, current_user.id)
        if body.username is not None:
            try:
                update_username(session, user, body.username)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        if body.f_name is not None:
            set_f_name(session, user, body.f_name)
        if body.l_name is not None:
            set_l_name(session, user, body.l_name)
        if body.bio is not None:
            set_user_bio(session, user, body.bio)
        if body.profile_photo is not None:
            set_profile_photo(session, user, body.profile_photo)
        return _user_out(user)
