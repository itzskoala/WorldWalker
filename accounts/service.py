# accounts/service.py
# Signup and login business logic - the DB reads/writes for the accounts
# router, kept separate so the router itself only handles HTTP concerns.

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import email_validation, security, username_validation
from database.models import User
from user_profile.profile_page import set_username


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return session.execute(statement).scalar_one_or_none()


def get_user_by_username(session: Session, username: str) -> User | None:
    statement = select(User).where(User.username == username)
    return session.execute(statement).scalar_one_or_none()


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_user_by_google_sub(session: Session, sub: str) -> User | None:
    statement = select(User).where(User.google_sub == sub)
    return session.execute(statement).scalar_one_or_none()


def signup(session: Session, email: str, password: str) -> User:
    """Creates the account directly - POST /auth/signup (accounts/
    router.py) issues tokens from the result immediately, no separate
    verification step. Raises ValueError on an already-registered email
    (accounts/router.py turns that into a 400 the signup form shows
    inline) or one that fails the same validation GET /auth/validate-email
    exposes for the frontend's real-time check (accounts/
    email_validation.py) - never trust the client-side pass alone."""
    if not email_validation.is_valid_email(email):
        raise ValueError("Enter a valid email address")

    if get_user_by_email(session, email) is not None:
        raise ValueError("An account with this email already exists - try logging in instead.")

    user = User(email=email, hashed_password=security.hash_password(password))
    session.add(user)
    session.commit()
    return user


def update_username(session: Session, user: User, username: str) -> None:
    """Validates before handing off to user_profile.profile_page.set_username -
    format (accounts/username_validation.py) and uniqueness against every
    other account. Raises ValueError on either failure; accounts/router.py's
    PATCH /auth/me turns that into a 400 the profile form shows inline
    (frontend/src/components/profile/ProfileUsernameField.tsx), which also
    has its own GET /auth/validate-username real-time check against these
    same two rules - never trust that client-side pass alone."""
    if not username_validation.is_valid_format(username):
        raise ValueError("Username can only contain letters, numbers, and underscores")

    if username:
        existing = get_user_by_username(session, username)
        if existing is not None and existing.id != user.id:
            raise ValueError("Username already in use")

    set_username(session, user, username)


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(session, email)
    if user is None or user.hashed_password is None:
        return None
    if not security.verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


def signup_or_login_google(session: Session, sub: str, email: str | None, email_verified: bool) -> User:
    """The single entry point for "Sign in with Google": returning Google
    user -> that user; brand-new Google account -> a new user; a Google
    account whose email matches an existing email/password account -> that
    account, now also linked to google_sub, never a second row (duplicate-
    account prevention, called out explicitly in accounts/router.py's
    POST /auth/google).

    email_verified must come from the Google ID token itself (see
    accounts/google_oauth.py) - linking to an existing account on an
    unverified email would let anyone sign in as whoever owns that email
    address, no proof required."""
    user = get_user_by_google_sub(session, sub)
    if user is not None:
        return user

    if not email or not email_verified:
        raise ValueError("Google account has no verified email address")

    existing = get_user_by_email(session, email)
    if existing is not None:
        existing.google_sub = sub
        session.commit()
        return existing

    user = User(email=email, google_sub=sub)
    session.add(user)
    session.commit()
    return user
