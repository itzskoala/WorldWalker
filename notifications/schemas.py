# notifications/schemas.py
# Request/response shapes for the notifications router.

from pydantic import BaseModel


class EmailConfigRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str


class EmailConfigStatus(BaseModel):
    """Whether this user has an email config saved - never the
    host/username/password back out. A user who wants to check what
    they entered re-enters it; this endpoint only ever confirms
    presence/absence."""
    configured: bool
