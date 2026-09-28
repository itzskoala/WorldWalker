# auth/router.py
# The Google OAuth flow: /auth/google/start (JWT-protected) issues the
# consent URL for the logged-in WorldWalker user; Google redirects the
# user's browser straight to /auth/google/callback, which is NOT
# JWT-protected (Google's redirect can't carry a bearer token) - the
# OAuth `state` google_health_auth.py issued is what recovers which
# WorldWalker user this callback belongs to. Included into app.py's
# FastAPI app, alongside services/google_health/webhook.py's router.
#
# Every dependency is called through its module object (google_health_auth,
# connections) rather than imported by name, so tests can monkeypatch it -
# see tests/test_auth_router.py.

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from accounts.dependencies import get_current_user
from auth import connections, google_health_auth
from database.models import User
from database.session import SessionLocal

router = APIRouter()


@router.post("/auth/google/start")
def google_start(current_user: User = Depends(get_current_user)):
    return {"auth_url": google_health_auth.build_auth_url(current_user.id)}


@router.get("/auth/google/callback")
def google_callback(request: Request):
    params = request.query_params

    error = params.get("error")
    if error:
        print(f"🔐 auth: Google returned an error on callback: {error}")
        return HTMLResponse(f"<h1>Connection failed</h1><p>Google said: {error}</p>", status_code=400)

    code = params.get("code")
    state = params.get("state")
    user_id = google_health_auth.consume_state(state) if state else None

    if not code or user_id is None:
        print("🔐 auth: callback rejected - missing code, or invalid/expired/reused state")
        return HTMLResponse(
            "<h1>Connection failed</h1><p>This link is invalid or has expired. "
            "Go back and click Connect again.</p>",
            status_code=400,
        )

    try:
        tokens = google_health_auth.exchange_code(code)
    except Exception as e:
        print(f"🔐 auth: token exchange failed: {e}")
        return HTMLResponse(
            "<h1>Connection failed</h1><p>Could not complete authorization with Google.</p>",
            status_code=502,
        )

    try:
        with SessionLocal() as session:
            connections.upsert_connection_from_tokens(session, user_id, tokens)
            session.commit()
    except ValueError as e:
        print(f"🔐 auth: connection rejected: {e}")
        return HTMLResponse(f"<h1>Connection failed</h1><p>{e}</p>", status_code=409)
    except Exception as e:
        print(f"🔐 auth: failed to save the connection: {e}")
        return HTMLResponse(
            "<h1>Connection failed</h1><p>Could not save your connection. Please try again.</p>",
            status_code=502,
        )

    print("🔐 auth: connection established")
    return HTMLResponse(
        '<meta http-equiv="refresh" content="3;url=/">'
        "<h1>Connected!</h1><p>Taking you back to WorldWalker...</p>"
    )


@router.post("/auth/google/disconnect")
def google_disconnect(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        try:
            connection = connections.get_active_connection(session, current_user.id)
        except RuntimeError:
            return HTMLResponse(
                "<h1>Not connected</h1><p>There's no active connection to disconnect.</p>",
                status_code=404,
            )
        connections.disconnect(session, connection)

    return HTMLResponse("<h1>Disconnected</h1><p>Your Google Health connection has been removed.</p>")
