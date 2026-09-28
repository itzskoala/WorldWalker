# accounts/otp_email.py
# Sends the signup verification code by email via Resend's HTTP API
# (RESEND_API_KEY/RESEND_FROM_EMAIL - see .env.example). Falls back to
# logging the code to the server console when either is unset, the same
# "degrade gracefully until a deployment configures this" pattern as
# travel_logic/description_generator.py's OLLAMA_API_KEY handling - local
# dev and the test suite can exercise the whole signup flow without a
# real Resend account or a verified sending domain.
#
# Deliberately separate from core/observer_decorator/email_alerts_listener.py:
# that sends checkpoint alerts through each user's OWN SMTP credentials
# (EmailNotificationConfig - a per-user setting only an existing,
# logged-in user has configured). A signup code has to go out before any
# of that exists, from WorldWalker's own platform sender instead.

import os

import httpx

RESEND_API_URL = "https://api.resend.com/emails"


def send_otp_email(email: str, code: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("RESEND_FROM_EMAIL")

    if not api_key or not from_email:
        print(f"📧 signup: RESEND_API_KEY/RESEND_FROM_EMAIL not configured - verification code for {email} is {code}")
        return

    response = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "from": from_email,
            "to": [email],
            "subject": "Your WorldWalker verification code",
            "text": f"Your WorldWalker verification code is {code}. It expires in 10 minutes.",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    print(f"📧 signup: verification code sent to {email}")
