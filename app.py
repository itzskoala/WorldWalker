# app.py
# The web UI. Owns no travel/auth logic itself - every action here reports
# to core.facade.travel_facade (journey state) or auth.google_health_auth
# (the Google Health OAuth flow). Pure FastAPI + a static Google-Flights-
# styled frontend (web/) - no UI framework dependency.

import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import NominatimGeocoder
from auth.connections import get_active_user_id
from auth.router import router as auth_router
from database.session import SessionLocal
from services.google_health.webhook import router as webhook_router
from data.intake import IntakeRequest, start_journey_from_intake
from core.facade import travel_facade

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="WorldWalker")
app.include_router(auth_router)
app.include_router(webhook_router)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

_geocoder = NominatimGeocoder()


# Computed once at import time (credentials.json doesn't change between
# requests) and handed to the template as a real <a target="_blank"> href -
# NOT window.open() from a JS callback fired after a fetch() round-trip,
# which Chrome's popup blocker silently swallows since that runs outside
# the original click's user-gesture window (hit this for real building the
# previous Gradio version - see docs/prompt_log/2026-09-13-gradio-ui.md).
def _build_connect_url() -> Optional[str]:
    try:
        from auth.google_health_auth import build_auth_url
        return build_auth_url()
    except Exception as e:
        print(f"⚠️  Connect disabled: couldn't build the Google OAuth URL ({e})")
        return None


CONNECT_URL = _build_connect_url()


def _is_connected() -> bool:
    """Whether the site's one Google Health connection is currently
    active - checked fresh on every request (unlike CONNECT_URL above),
    since this can flip from one request to the next as the user
    connects/disconnects."""
    with SessionLocal() as session:
        try:
            get_active_user_id(session)
            return True
        except RuntimeError:
            return False


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"connect_url": CONNECT_URL, "is_connected": _is_connected()}
    )


def _place_suggestion(display_name: str) -> dict:
    """Split Nominatim's "Miami, Miami-Dade County, Florida, United States"
    into a bold primary line + a muted secondary line for the dropdown -
    matches Google Flights' two-line airport/city rows."""
    primary, _, rest = display_name.partition(", ")
    return {"value": display_name, "primary": primary or display_name, "secondary": rest}


@app.get("/api/places/search")
def search_places(q: str = Query(default="", max_length=200)):
    results = _geocoder.search_places(q, limit=6)
    return {"results": [_place_suggestion(r) for r in results]}


@app.get("/api/places/reverse")
def reverse_place(lat: float, lng: float):
    try:
        place = _geocoder.reverse_geocode(Coordinates(lat=lat, lng=lng))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return {"place": place}


def _current_user_id():
    """The real, connected WorldWalker user - trips are keyed on this UUID,
    not a placeholder id. Returns (user_id, None) on success or (None,
    error_response) when nobody's connected yet, so callers can just
    `user_id, error = _current_user_id(); if error: return error`."""
    with SessionLocal() as session:
        try:
            return get_active_user_id(session), None
        except RuntimeError as e:
            return None, JSONResponse({"error": str(e)}, status_code=400)


class JourneyStartRequest(BaseModel):
    from_place: str
    to_place: str
    round_trip: bool = False


@app.post("/api/journey/start")
def start_journey(body: JourneyStartRequest):
    if not body.from_place or not body.to_place:
        return JSONResponse({"error": "Pick both a starting point and a destination."}, status_code=400)

    user_id, error = _current_user_id()
    if error is not None:
        return error

    try:
        intake = IntakeRequest(
            from_place=body.from_place,
            to_place=body.to_place,
            round_trip=body.round_trip,
            user_id=user_id,
        )
        state = start_journey_from_intake(intake)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        # Real external dependencies (geocoding, routing, AI descriptions)
        # can fail at runtime - fail soft with a friendly message instead
        # of a 500.
        print(f"⚠️  /api/journey/start failed: {type(e).__name__}: {e}")
        return JSONResponse({"coming_soon": True}, status_code=200)

    # The full map-ready state (route polyline, start/end, checkpoints,
    # metrics) - web/static/js/trip.js needs all of it to draw the map,
    # not just a text summary.
    return {"coming_soon": False, **state}


@app.get("/api/journey/state")
def journey_state(trip_id: uuid.UUID):
    """Polled by web/static/js/trip.js while a trip is on screen - the same
    map-ready shape start_journey() returns, always with every checkpoint
    included (tagged hit: true/false), not just the hit ones. Filtering
    that down to "only what a normal user should see" is the frontend's
    job (see web/static/js/trip.js and dev_testing/TRIP_MAP.md's ?debug=1
    flag), not this endpoint's. A user can have several trips going at
    once now, so trip_id says which one - see web/static/js/trip.js's
    show()."""
    user_id, error = _current_user_id()
    if error is not None:
        return error

    try:
        return travel_facade.get_map_state(user_id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.get("/api/journey/list")
def journey_list():
    """Every trip belonging to the connected user, active or finished -
    web/static/js/app.js's trips panel splits this into "Active" (status
    active/paused) and "Past" (completed/abandoned) sections client-side."""
    user_id, error = _current_user_id()
    if error is not None:
        return error

    return {"trips": travel_facade.list_trips(user_id)}


@app.post("/api/journey/{trip_id}/pause")
def pause_journey(trip_id: uuid.UUID):
    user_id, error = _current_user_id()
    if error is not None:
        return error

    try:
        return travel_facade.pause_journey(user_id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.post("/api/journey/{trip_id}/resume")
def resume_journey(trip_id: uuid.UUID):
    user_id, error = _current_user_id()
    if error is not None:
        return error

    try:
        return travel_facade.resume_journey(user_id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.delete("/api/journey/{trip_id}")
def delete_journey(trip_id: uuid.UUID):
    user_id, error = _current_user_id()
    if error is not None:
        return error

    try:
        travel_facade.delete_journey(user_id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)
    return Response(status_code=204)


class JourneyDeleteBulkRequest(BaseModel):
    trip_ids: list[uuid.UUID]


@app.post("/api/journey/delete")
def delete_journeys(body: JourneyDeleteBulkRequest):
    """Multi-select delete from the trips panel - one request instead of
    the frontend firing a DELETE per selected card."""
    user_id, error = _current_user_id()
    if error is not None:
        return error

    deleted_count = travel_facade.delete_journeys(user_id, body.trip_ids)
    return {"deleted": deleted_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
