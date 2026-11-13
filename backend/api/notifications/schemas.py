# notifications/schemas.py

from pydantic import BaseModel


class EmailConfigRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str


class EmailConfigStatus(BaseModel):
    configured: bool
