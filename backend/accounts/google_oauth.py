# accounts/google_oauth.py

'''
Verify that a credential received from Google's frontend authentication process is legitimate 
'''
import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

_request = google_requests.Request()


class GoogleTokenError(ValueError):
    """Raised when a Google credential can't be trusted: expired, wrong
    audience, bad signature, or GOOGLE_SIGNIN_CLIENT_ID isn't configured
    at all. accounts/router.py turns this into a 401."""


def verify_google_id_token(credential):
    client_id = os.environ.get("GOOGLE_SIGNIN_CLIENT_ID") #this client id is my own client id
    if not client_id:
        raise GoogleTokenError("Google sign-in is not configured")

    try:
        return id_token.verify_oauth2_token(credential, _request, client_id)
    except Exception as e:
        raise GoogleTokenError("Invalid or expired Google credential") from e
