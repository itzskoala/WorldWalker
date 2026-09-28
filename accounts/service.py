# accounts/service.py
# Signup and login business logic - the DB reads/writes for the accounts
# router, kept separate so the router itself only handles HTTP concerns.

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from accounts import email_validation, security
from database.models import User

# TODO(otp): these back the disabled start_email_signup()/
# verify_email_signup() below - `import os`, `from datetime import
# datetime, timedelta, timezone`, and `from database.models import
# SignupVerification` go with them when this is revived.
# OTP_EXPIRE_MINUTES = int(os.environ.get("OTP_EXPIRE_MINUTES", "10"))
#
# # verify_email_signup() deletes the pending row once this many wrong
# # guesses have been made against it, forcing a fresh /auth/signup/start
# # (and a fresh code) rather than allowing unlimited guessing against a
# # 6-digit space.
# MAX_OTP_ATTEMPTS = 5


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
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


# TODO(otp): the two-step "email a 6-digit code, verify it, then create
# the account" flow - disabled in favor of signup() above creating the
# account directly. accounts/router.py's /signup/start and /signup/verify
# routes, and accounts/otp_email.py's send_otp_email(), are unused while
# this is off. The SignupVerification table/model stays as-is so reviving
# this later is just uncommenting - see accounts/schemas.py's
# SignupStartRequest/SignupVerifyRequest for the matching request shapes.
#
# def start_email_signup(session: Session, email: str, password: str) -> str:
#     """Step 1 of email/password signup (POST /auth/signup/start): no
#     User row is created here - just a pending SignupVerification with a
#     fresh 6-digit code, upserted by email so a second call for the same
#     address (the frontend's "Resend code") replaces the earlier code
#     instead of piling up old ones. Returns the plaintext code so
#     accounts/router.py can hand it to accounts/otp_email.py - nothing in
#     this module ever sends anything itself.
#
#     Raises ValueError before any code is generated or sent: an
#     already-registered email, or one that fails the same validation
#     GET /auth/validate-email exposes for the frontend's real-time check
#     (accounts/email_validation.py) - never trust the client-side pass
#     alone."""
#     if not email_validation.is_valid_email(email):
#         raise ValueError("Enter a valid email address")
#
#     if get_user_by_email(session, email) is not None:
#         raise ValueError("Email already registered")
#
#     code = security.generate_otp_code()
#     now = datetime.now(timezone.utc)
#
#     pending = session.get(SignupVerification, email)
#     if pending is None:
#         pending = SignupVerification(email=email)
#         session.add(pending)
#
#     pending.hashed_password = security.hash_password(password)
#     pending.code_hash = security.hash_password(code)
#     pending.attempts = 0
#     pending.expires_at = now + timedelta(minutes=OTP_EXPIRE_MINUTES)
#     session.commit()
#
#     return code
#
#
# def verify_email_signup(session: Session, email: str, code: str) -> User:
#     """Step 2 (POST /auth/signup/verify) - this call IS account creation,
#     not a step after it: there is no unverified User row sitting around
#     before this succeeds, only the pending SignupVerification row it
#     redeems and deletes."""
#     pending = session.get(SignupVerification, email)
#     if pending is None:
#         raise ValueError("Start over - request a new code")
#
#     if datetime.now(timezone.utc) > pending.expires_at:
#         session.delete(pending)
#         session.commit()
#         raise ValueError("Code expired - request a new one")
#
#     if pending.attempts >= MAX_OTP_ATTEMPTS:
#         session.delete(pending)
#         session.commit()
#         raise ValueError("Too many incorrect attempts - request a new code")
#
#     if not security.verify_password(code, pending.code_hash):
#         pending.attempts += 1
#         session.commit()
#         raise ValueError("Incorrect code")
#
#     user = User(email=email, hashed_password=pending.hashed_password)
#     session.add(user)
#     session.delete(pending)
#     session.commit()
#     return user


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
