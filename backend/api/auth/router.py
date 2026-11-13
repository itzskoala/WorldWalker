# auth/router.py

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse

from backend.accounts.dependencies import get_current_user
from backend.auth import connections, google_health_auth, oauth_state
from backend.database import trips
from backend.database.models import User
from backend.database.session import SessionLocal
from backend.services.google_health import webhook as google_health_webhook

router = APIRouter()


def backfill_active_trips(user_id, provider_user_id):
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        active_trips = [t for t in trips.get_active_trips(session, user_id) if t.status == "active"]
        if not active_trips:
            return
        connection = connections.get_active_connection(session, user_id)
        start_time_dt = min(trip.started_at for trip in active_trips)
        if connection.last_synced_at and connection.last_synced_at > start_time_dt:
            start_time_dt = connection.last_synced_at
        start_time = start_time_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        google_health_webhook.backfill_since(provider_user_id, start_time)
    except Exception as e:
        print(f"🔐 auth: backfill after connect failed: {e}")
        return

    with SessionLocal() as session:
        connections.mark_synced(session, user_id, now)


@router.post("/auth/google/start")
def google_start(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        state = oauth_state.issue_state(session, current_user.id)
    return {"auth_url": google_health_auth.build_auth_url(state)}


@router.get("/auth/google/callback")
def google_callback(request: Request, background_tasks: BackgroundTasks):
    params = request.query_params

    error = params.get("error")
    if error:
        print(f"🔐 auth: Google returned an error on callback: {error}")
        return HTMLResponse(f"<h1>Connection failed</h1><p>Google said: {error}</p>", status_code=400)

    code = params.get("code")
    state = params.get("state")
    user_id = None
    if state:
        with SessionLocal() as session:
            user_id = oauth_state.consume_state(session, state)

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
            connection = connections.upsert_connection_from_tokens(session, user_id, tokens)
            session.commit()
            provider_user_id = connection.provider_user_id
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
    background_tasks.add_task(backfill_active_trips, user_id, provider_user_id)
    return HTMLResponse(
        '<meta http-equiv="refresh" content="3;url=/">'
        "<h1>Connected!</h1><p>Taking you back to WorldWalker...</p>"
    )


@router.get("/auth/google/status")
def google_status(current_user: User = Depends(get_current_user)):
    with SessionLocal() as session:
        try:
            connections.get_active_connection(session, current_user.id)
            return {"connected": True}
        except RuntimeError:
            return {"connected": False}


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
