# accounts/google_oauth.py
# Verifies a Google Identity Services ID token - the `credential` GIS hands
# the frontend after a user signs in with the Google button (see
# frontend/src/components/GoogleSignInButton.tsx). A client-asserted
# identity can't be trusted, so the token is always re-verified here,
# server-side, against Google's own public keys before accounts/
# service.py ever looks up or creates a user from it.
#
# Uses google-auth's id_token verifier - already a project dependency for
# the unrelated Google Health OAuth flow (auth/google_health_auth.py) -
# rather than adding a new library for this. That flow and this one are
# deliberately separate: GOOGLE_OAUTH_CLIENT_ID there is a "data access"
# grant (steps/sleep/etc via authorization code + refresh tokens);
# GOOGLE_SIGNIN_CLIENT_ID here is only ever an identity assertion (a short-
# lived ID token, no offline access, no scopes) - see .env.example.

import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

_request = google_requests.Request()


class GoogleTokenError(ValueError):
    """Raised when a Google credential can't be trusted: expired, wrong
    audience, bad signature, or GOOGLE_SIGNIN_CLIENT_ID isn't configured
    at all. accounts/router.py turns this into a 401."""


def verify_google_id_token(credential: str) -> dict:
    """Returns the verified token claims (at least "sub", "email",
    "email_verified") for a real, current Google ID token - never call
    accounts/service.py's signup_or_login_google() with anything that
    didn't come back from here."""
    client_id = os.environ.get("GOOGLE_SIGNIN_CLIENT_ID")
    if not client_id:
        raise GoogleTokenError("Google sign-in is not configured")

    try:
        # verify_oauth2_token checks signature, expiry, and audience
        # against Google's live certs, and (internally) that "iss" is
        # really accounts.google.com - nothing here needs to re-check any
        # of that.
        return id_token.verify_oauth2_token(credential, _request, client_id)
    except Exception as e:
        raise GoogleTokenError("Invalid or expired Google credential") from e
