# app.py
# The web UI. Owns no travel/auth logic itself - every action here reports
# to core.facade.travel_facade (journey state) or auth.google_health_auth
# (the Fitbit/Google Health OAuth flow). Pure FastAPI + a static
# Google-Flights-styled frontend (web/) - no UI framework dependency.
#
# core.facade / data.intake are currently mid-refactor on this branch and
# don't import cleanly yet (see travel_logic/progress_calculator.py and
# services/google_health/), so the journey-start endpoint below imports
# them lazily, per-request, inside a try/except - the UI stays fully
# operational (search, current location, Connect) even while that chain
# is being rebuilt, and starts working the moment it imports cleanly again.
# No further app.py changes needed when that lands.

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import NominatimGeocoder

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="WorldWalker")
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


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html", {"connect_url": CONNECT_URL}
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


class JourneyStartRequest(BaseModel):
    from_place: str
    to_place: str
    round_trip: bool = False


@app.post("/api/journey/start")
def start_journey(body: JourneyStartRequest):
    if not body.from_place or not body.to_place:
        return JSONResponse({"error": "Pick both a starting point and a destination."}, status_code=400)

    try:
        from data.intake import IntakeRequest, start_journey_from_intake
        from core.facade import DEFAULT_USER_ID

        intake = IntakeRequest(
            from_place=body.from_place,
            to_place=body.to_place,
            round_trip=body.round_trip,
            user_id=DEFAULT_USER_ID,
        )
        state = start_journey_from_intake(intake)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        # Journey logic is still being rebuilt on this branch - fail soft
        # instead of a 500, so the UI can show a friendly "coming soon"
        # message rather than a broken request.
        print(f"⚠️  /api/journey/start: backend not wired up yet ({type(e).__name__}: {e})")
        return JSONResponse({"coming_soon": True}, status_code=200)

    return {
        "coming_soon": False,
        "miles_remaining": state["miles_remaining"],
        "landmark_count": len(state["landmarks"]),
        "estimated_days_remaining": state["estimated_days_remaining"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
