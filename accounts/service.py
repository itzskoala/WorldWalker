# accounts/service.py
# Signup and login business logic - the DB reads/writes for the accounts
# router, kept separate so the router itself only handles HTTP concerns.

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import security
from database.models import User


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return session.execute(statement).scalar_one_or_none()


def get_user_by_id(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def signup(session: Session, email: str, password: str) -> User:
    if "@" not in email:
        raise ValueError("Enter a valid email address")

    if get_user_by_email(session, email) is not None:
        raise ValueError("Email already registered")

    user = User(email=email, hashed_password=security.hash_password(password))
    session.add(user)
    session.commit()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(session, email)
    if user is None or user.hashed_password is None:
        return None
    if not security.verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user
