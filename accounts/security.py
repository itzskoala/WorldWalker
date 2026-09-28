# accounts/security.py
# Password hashing and JWT creation/decoding for the login system.

import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not set. Add one to .env (see .env.example).")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
# "Remember me" left unchecked at login (accounts/router.py's login_route)
# still gets a real session, just a short-lived one as a server-side
# backstop - paired with a session cookie (no max_age) so most browsers
# also drop it the moment the tab closes.
SESSION_REFRESH_TOKEN_EXPIRE_HOURS = int(os.environ.get("SESSION_REFRESH_TOKEN_EXPIRE_HOURS", "12"))

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed_password.encode())


def _create_token(user_id: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, ACCESS_TOKEN_TYPE, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(user_id: str, remember_me: bool = True) -> str:
    expires_delta = (
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        if remember_me
        else timedelta(hours=SESSION_REFRESH_TOKEN_EXPIRE_HOURS)
    )
    return _create_token(user_id, REFRESH_TOKEN_TYPE, expires_delta)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def generate_otp_code() -> str:
    """A fresh 6-digit signup verification code (accounts/service.py's
    start_email_signup()) - secrets.choice, not random, since this is a
    value someone could otherwise guess or replay. Stored via
    hash_password()/verify_password() above, same as a real password -
    a 6-digit space is small, but it's still never kept in the clear."""
    return "".join(secrets.choice("0123456789") for _ in range(6))
