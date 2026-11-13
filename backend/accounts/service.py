# accounts/service.py

'''
Business logic for creating accounts, 
looking up users, authenticating passwords, 
and linking Google accounts
'''

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounts import email_validation, security, username_validation
from backend.database.models import User
from backend.profile.profile_page import set_username


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
    if not email_validation.is_valid_email(email):
        raise ValueError("Enter a valid email address")

    if get_user_by_email(session, email) is not None:
        raise ValueError("An account with this email already exists - try logging in instead.")

    user = User(email=email, hashed_password=security.hash_password(password))
    session.add(user)
    session.commit()
    return user


def update_username(session: Session, user: User, username: str) -> None:
    if not username_validation.is_valid_username(username):
        raise ValueError("Username contains invalid characters or inappropriate language")

    if username:
        existing = get_user_by_username(session, username)
        if existing is not None and existing.id != user.id:
            raise ValueError("This username has been taken!")

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
