# accounts/schemas.py

'''
Request/response shapes for the accounts router.
'''

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = True


class SignupRequest(BaseModel):
    email: str
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: str
    username: str | None = None
    f_name: str | None = None
    l_name: str | None = None
    profile_photo: str | None = None
    bio: str | None = None
    lifetime_steps: int
    postcards_sum: int
    member_since: str


class ProfileUpdateRequest(BaseModel):
    username: str | None = None
    f_name: str | None = None
    l_name: str | None = None
    bio: str | None = None
    profile_photo: str | None = None
