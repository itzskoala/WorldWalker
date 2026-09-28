# accounts/schemas.py
# Request/response shapes for the accounts router.

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str
    # Drives both the refresh token's lifetime and whether its cookie
    # persists past the browser session - see accounts/security.py's
    # create_refresh_token() and accounts/router.py's _set_refresh_cookie().
    remember_me: bool = True


class SignupRequest(BaseModel):
    email: str
    password: str


# TODO(otp): SignupStartRequest/SignupVerifyRequest backed the two-step
# email-a-code signup flow, disabled for now in accounts/router.py and
# accounts/service.py in favor of direct signup (SignupRequest above).
# Revive these alongside that flow when it comes back.
# class SignupStartRequest(BaseModel):
#     email: str
#     password: str
#
#
# class SignupVerifyRequest(BaseModel):
#     email: str
#     code: str


class GoogleAuthRequest(BaseModel):
    # The GIS credential is a signed JWT, not a raw email/password -
    # accounts/google_oauth.py verifies it before anything trusts the
    # identity inside.
    credential: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: str
