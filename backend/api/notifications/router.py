# backend/api/notifications/router.py

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from backend.accounts.dependencies import get_current_user
from backend.database.models import User
from backend.database.session import SessionLocal
from backend.notifications import email_config
from backend.api.notifications.schemas import EmailConfigRequest, EmailConfigStatus

router = APIRouter(prefix="/notifications")


@router.put("/email-config", response_model=EmailConfigStatus)
async def set_email_config(request: Request, current_user: User = Depends(get_current_user)):
    try:
        body = EmailConfigRequest.model_validate(await request.json())
    except (ValidationError, ValueError):
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
