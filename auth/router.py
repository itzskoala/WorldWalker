# auth/router.py
# The real OAuth callback: Google redirects the user's browser here
# directly (no more copy/pasting a code out of the address bar). Included
# into services/fitbit_service.py's FastAPI app - see that file's comment
# on mount order.
#
# Every dependency is called through its module object (google_health_auth,
# connections) rather than imported by name, so tests can monkeypatch it -
# see tests/test_auth_router.py.

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from auth import connections, google_health_auth
from database.session import SessionLocal

router = APIRouter()


@router.get("/auth/google/callback")
def google_callback(request: Request):
    params = request.query_params

    error = params.get("error")
    if error:
        print(f"🔐 auth: Google returned an error on callback: {error}")
        return HTMLResponse(f"<h1>Connection failed</h1><p>Google said: {error}</p>", status_code=400)

    code = params.get("code")
    state = params.get("state")

    if not code or not state or not google_health_auth.consume_state(state):
        print("🔐 auth: callback rejected - missing or invalid/expired state")
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
            connections.upsert_connection_from_tokens(session, tokens)
            session.commit()
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
def google_disconnect():
    with SessionLocal() as session:
        try:
            connection = connections.get_active_connection(session)
        except RuntimeError:
            return HTMLResponse(
                "<h1>Not connected</h1><p>There's no active connection to disconnect.</p>",
                status_code=404,
            )
        connections.disconnect(session, connection)

    return HTMLResponse("<h1>Disconnected</h1><p>Your Google Health connection has been removed.</p>")
