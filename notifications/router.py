# notifications/router.py
# Lets a logged-in user save/check/remove their own SMTP account for
# checkpoint email notifications - JWT-protected the same way as
# accounts/router.py's routes. Every response here is a plain "configured:
# true/false" - the saved host/username/password are never echoed back
# (see notifications/schemas.py's EmailConfigStatus).

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from accounts.dependencies import get_current_user
from database.models import User
from database.session import SessionLocal
from notifications import email_config
from notifications.schemas import EmailConfigRequest, EmailConfigStatus

router = APIRouter(prefix="/notifications")


@router.put("/email-config", response_model=EmailConfigStatus)
async def set_email_config(request: Request, current_user: User = Depends(get_current_user)):
    # Parsed by hand, not via a `body: EmailConfigRequest` parameter -
    # FastAPI's automatic validation-error response echoes back the
    # *entire* submitted body (including smtp_password) whenever any
    # OTHER field is missing/invalid, as proof of what failed to
    # validate. Confirmed live: PUT with smtp_host omitted returns
    # {"detail":[{... "input": {"smtp_password": "<the real password>", ...}}]}.
    # A generic 422 here never repeats anything the client sent.
    try:
        body = EmailConfigRequest.model_validate(await request.json())
    except (ValidationError, ValueError):  # ValueError also catches malformed (non-JSON) bodies
        raise HTTPException(status_code=422, detail="smtp_host, smtp_port, smtp_username, and smtp_password are all required.")

    with SessionLocal() as session:
        email_config.upsert_config(
            session,
            current_user.id,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_username=body.smtp_username,
            smtp_password=body.smtp_password,
        )
    return EmailConfigStatus(configured=True)


@router.get("/email-config", response_model=EmailConfigStatus)
def get_email_config(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        config = email_config.get_config(session, current_user.id)
    return EmailConfigStatus(configured=config is not None)


@router.delete("/email-config", response_model=EmailConfigStatus)
def delete_email_config(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        email_config.delete_config(session, current_user.id)
    return EmailConfigStatus(configured=False)
