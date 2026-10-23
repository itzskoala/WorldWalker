# app.py
# The web UI. Owns no travel/auth logic itself - every action here reports
# to core.facade.travel_facade (journey state) or auth.google_health_auth
# (the Google Health OAuth flow). FastAPI backend + a React/TypeScript/
# Vite frontend (frontend/, built to frontend/dist/) - this file serves
# that build's static assets and hands every non-API GET to its
# index.html, letting react-router (frontend/src/App.tsx) decide what to
# render client-side.

import json
import math
import mimetypes
import os
import queue
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.gzip import GZipMiddleware

# Python's mimetypes module resolves this from the host's system mime
# database, which the slim Debian base image used for the production
# container doesn't ship with a .webp entry - StaticFiles below would
# otherwise serve frontend/public/hero's real *.webp bytes correctly but
# labeled as application/octet-stream (confirmed in that container; the
# usual macOS/Linux dev machine already resolves this correctly, so the
# gap is image-specific, not code-specific).
mimetypes.add_type("image/webp", ".webp")

from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.geocoder import create_geocoder
from travel_logic.route_service import OSRMWalkingRouteService
from travel_logic.route_validation import RouteUnavailable, validate_walking_route
from accounts.dependencies import get_current_user
from accounts.router import router as accounts_router
from auth.router import router as auth_router
from core.observer_decorator.event_listener import EventListener
from database.models import User
from notifications.router import router as notifications_router
from services.google_health.webhook import router as webhook_router
from data.intake import IntakeRequest, start_journey_from_intake
from core.facade import travel_facade

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
# Routers below own these prefixes - a request under one of them that
# reaches the catch-all SPA route at the bottom of this file (nothing
# matched) is a real 404, not "serve index.html and let react-router
# sort it out".
API_PREFIXES = ("api/", "auth/", "notifications/")

app = FastAPI(title="WorldWalker")
# A long trip's /api/journey/state (polled every 20s while its map is
# open - frontend/src/pages/TripDetailPage.tsx) carries one {lat, lng}
# object per route point, and a real stored route here can run into the
# tens of thousands of points (confirmed against real data - a
# cross-continental walk is not a hypothetical in this app) - several MB
# of JSON, uncompressed, on every single request. That's a much bigger
# contributor to "this trip's map took a while to appear" than any
# server-side CPU cost: gzip shrinks this kind of repetitive
# float/key-heavy JSON by roughly 85-90% in practice, and every browser
# already sends Accept-Encoding: gzip, so this is free on the client side
# - no API shape change, nothing for any caller to opt into.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(accounts_router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(notifications_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Starlette's own default for an uncaught exception is a bare
    "Internal Server Error" text body, not JSON - every client here
    (frontend/src/api/httpClient.ts's parseErrorMessage) can only fall
    back to its own generic per-call message when that happens, with no
    way to tell "OSRM is down" from "the database rejected a write" from
    a real bug. That's exactly what masked a real one for a while
    (2026-10, during a brief Clerk-based identity experiment since
    reverted - see accounts/dependencies.py's get_current_user): a
    FastAPI Depends() failure runs *before* a route's own try/except
    ever gets a chance, so no per-route handler below could have caught
    it either way - only a handler registered here, for the whole app,
    sees every one of those. The traceback this prints is what actually
    diagnosed that incident (Vercel's own runtime logs capture stdout) -
    still the right fallback for whatever's next, known cause or not."""
    print(f"⚠️  Unhandled error on {request.method} {request.url.path}:\n{traceback.format_exc()}")
    return JSONResponse({"error": "Something went wrong on our end. Please try again."}, status_code=500)
# On Vercel, frontend/dist exists only in local dev (`npm run build`) -
# vercel.json's own routes serve /assets, /images, /hero, and everything
# else that isn't /api, /auth, or /notifications straight from the
# @vercel/static-build output there, so this Python function never even
# sees those requests in that deployment. On the single-container Docker/
# Cloud Run image (Dockerfile), there is no separate static-routing layer
# - frontend/dist is built into the image and these mounts are what
# actually serve it in production. StaticFiles(directory=...) raises at
# import time if the directory is missing, which crashed every route on
# Vercel before this guard - see the postmortem: frontend/dist genuinely
# never existed in the Python function's filesystem there, so the whole
# app failed to even import. Kept defensive here for the same reason.
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")
if (FRONTEND_DIST / "images").is_dir():
    # Everything under frontend/public/ (favicon aside) - e.g. the auth
    # hero photos (frontend/public/images/) - lands at dist's root next
    # to assets/, same as /assets above.
    app.mount("/images", StaticFiles(directory=FRONTEND_DIST / "images"), name="frontend-images")
if (FRONTEND_DIST / "hero").is_dir():
    # frontend/src/components/PhotoCollage.tsx's landing-page photos
    # (frontend/public/hero/*.webp) - vercel.json routes /hero/(.*)
    # separately from /images/(.*), so this needs its own mount rather
    # than folding into the /images one above.
    app.mount("/hero", StaticFiles(directory=FRONTEND_DIST / "hero"), name="frontend-hero")

_geocoder = create_geocoder()
_router = OSRMWalkingRouteService()


def _google_signin_client_id() -> str:
    """Public (not secret) - the client ID GIS needs in the browser to
    render the Google button (frontend/src/components/GoogleSignInButton.tsx).
    Empty means Google sign-in isn't configured for this deployment; that
    component hides the button rather than rendering one that can't work."""
    return os.environ.get("GOOGLE_SIGNIN_CLIENT_ID", "")


def _apple_signin_client_id() -> str:
    """Public (not secret) - the Services ID Apple's JS SDK needs to
    render the real Sign in with Apple button
    (frontend/src/components/AppleSignInButton.tsx). Empty means it isn't
    configured yet (no backend callback exists for it either) - that
    component still renders the real button chrome, just without calling
    AppleID.auth.init(), so it looks right without pretending to work."""
    return os.environ.get("APPLE_SIGNIN_CLIENT_ID", "")


# The frontend has no server-side templating, so it can't have
# google_client_id baked into its HTML - it fetches this instead, once,
# on the login/signup pages. Same value, same "empty means not
# configured" contract the old Jinja2 templates used.
@app.get("/api/config")
def public_config():
    return {"google_client_id": _google_signin_client_id(), "apple_client_id": _apple_signin_client_id()}


@app.get("/api/places/search")
def search_places(q: str = Query(default="", max_length=200)):
    # Each Place is already in the exact shape the frontend's
    # PlaceSuggestion type expects (travel_logic/geocoder.py's Place
    # docstring) - whichever Geocoder is behind _geocoder did the
    # provider-specific work (splitting Nominatim's comma-joined
    # display_name today, something else for a different provider) before
    # this ever saw it, so there's no reshaping left to do here.
    return {"results": [asdict(place) for place in _geocoder.search_places(q, limit=6)]}


@app.get("/api/places/reverse")
def reverse_place(lat: float, lng: float):
    try:
        place = _geocoder.reverse_geocode(Coordinates(lat=lat, lng=lng))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return {"place": place}


class RouteValidateRequest(BaseModel):
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float


def _valid_coordinate(lat: float, lng: float) -> bool:
    return math.isfinite(lat) and math.isfinite(lng) and -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0


@app.post("/api/route/validate")
def validate_route(body: RouteValidateRequest):
    """Whether a walking route exists between two already-resolved
    locations - CreatePage.tsx calls this right after both Where From/
    Where To fields pick up coordinates, to clear an unwalkable selection
    before "Start Walking" (which does this same OSRM call again, but as
    part of actually persisting a trip - see core/facade.py's
    start_journey()). A 502 here means OSRM itself couldn't be reached,
    not that no route exists - the frontend must tell those apart (see
    RouteUnavailable's docstring).

    The range/finiteness check below is by hand, not a pydantic Field
    constraint: Python's own json module accepts "Infinity"/"NaN" as an
    extension, so a request really can arrive with a non-finite
    from_lat/etc. A pydantic ge/le constraint would reject that too, but
    FastAPI's default 422 handler echoes the rejected value back in the
    error body, and Starlette's JSONResponse can't render a raw inf/nan
    (json.dumps(..., allow_nan=False), per the JSON spec) - so validating
    that way would 500 while trying to report the very error meant to
    avoid one. Answering with a plain, hand-built body sidesteps that."""
    if not (_valid_coordinate(body.from_lat, body.from_lng) and _valid_coordinate(body.to_lat, body.to_lng)):
        return JSONResponse({"error": "Invalid coordinates."}, status_code=400)

    try:
        result = validate_walking_route(
            _router,
            Coordinates(lat=body.from_lat, lng=body.from_lng),
            Coordinates(lat=body.to_lat, lng=body.to_lng),
        )
    except RouteUnavailable as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    return {"valid": result.valid, "reason": result.reason}


class JourneyStartRequest(BaseModel):
    from_place: str
    to_place: str
    round_trip: bool = False
    # Optional: the coordinates the frontend's autocomplete already
    # resolved from_place/to_place to - see IntakeRequest's own docstring
    # on why these are preferred over re-geocoding the text.
    from_lat: Optional[float] = None
    from_lng: Optional[float] = None
    to_lat: Optional[float] = None
    to_lng: Optional[float] = None


@app.post("/api/journey/start")
def start_journey(body: JourneyStartRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    if not body.from_place or not body.to_place:
        return JSONResponse({"error": "Pick both a starting point and a destination."}, status_code=400)

    try:
        intake = IntakeRequest(
            from_place=body.from_place,
            to_place=body.to_place,
            round_trip=body.round_trip,
            user_id=current_user.id,
            from_lat=body.from_lat,
            from_lng=body.from_lng,
            to_lat=body.to_lat,
            to_lng=body.to_lng,
        )
        state = start_journey_from_intake(intake)
    except ValueError as e:
        # start_journey()'s own ValueErrors carry a raw, developer-facing
        # repr (geocoder.py's "No match for '<place>'", route_service.py's
        # "No walking route between Coordinates(lat=...) and
        # Coordinates(lat=...): <detail>") - never meant for the client to
        # render verbatim. CreatePage.tsx's own pre-flight POST
        # /api/route/validate is the real gate against an unwalkable pair
        # reaching here at all; this 400 is the last-resort fallback for
        # whatever slips past that (a race between picking a location and
        # that check landing, a direct API call, ...), so a single generic
        # message covers it - the real detail still goes to the server log.
        print(f"⚠️  /api/journey/start: {e}")
        return JSONResponse({"error": "We couldn't find a walkable route between those two places."}, status_code=400)
    except Exception as e:
        # Real external dependencies (geocoding, routing) can fail at
        # runtime - fail soft with a friendly message instead of a 500.
        print(f"⚠️  /api/journey/start failed: {type(e).__name__}: {e}")
        return JSONResponse({"coming_soon": True}, status_code=200)

    # The map/route is the critical path - every checkpoint's position
    # already exists in state["checkpoints"] by the time this returns
    # (see core/facade.py's start_journey()), just with name/description
    # still blank for most of them. Resolving those is the slow part that
    # runs after this response is on its way back to the browser: this
    # kicks off just the first few checkpoints' worth, and
    # frontend/src/pages/TripDetailPage.tsx picks up the rest live, as the
    # walker approaches each one, via GET /api/journey/{trip_id}/events.
    background_tasks.add_task(travel_facade.bootstrap_checkpoint_metadata, uuid.UUID(state["trip_id"]))

    return {"coming_soon": False, **state}


def _sse_message(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class _CheckpointEventListener(EventListener):
    """One per open /api/journey/{trip_id}/events connection - EventManager
    (core/observer_decorator/event_manager.py) calls update() from
    whatever thread is running generate_checkpoints_for_trip()
    (core/facade.py), on the trip's own generate_checkpoints_for_trip
    background task thread; this SSE route reads back out of the queue on
    its own request-handling thread. A plain queue.Queue is the
    thread-safe handoff between the two."""

    def __init__(self):
        self.queue: "queue.Queue[dict]" = queue.Queue()

    def update(self, data) -> None:
        self.queue.put(data)


# 25s: comfortably under most proxies'/browsers' idle-connection timeouts,
# short enough that a client that vanished (closed tab, lost network) gets
# noticed reasonably soon via the generator's GeneratorExit rather than
# leaking a subscribed listener for the life of the process.
SSE_KEEPALIVE_SECONDS = 25


@app.get("/api/journey/{trip_id}/events")
def journey_events(trip_id: uuid.UUID, current_user: User = Depends(get_current_user)):
    """Live checkpoint_added/checkpoint_updated/checkpoints_ready events
    for one trip. checkpoint_updated now covers two independent things -
    a checkpoint's name/description finishing (core.facade.TravelFacade's
    checkpoint-metadata pipeline, kicked off a little at a time by
    /api/journey/start above and then lazily, as the walker approaches
    each one, by _notify_progress()) and a checkpoint being proximity-
    revealed on the map (also _notify_progress()) - the progressive-reveal
    half of "instant map, checkpoints reveal and fill in as the walker
    gets there" (frontend/src/pages/TripDetailPage.tsx). checkpoints_ready
    now means the trip itself finished, not "checkpoint discovery
    finished" - see get_checkpoint_backlog()'s docstring. Ownership is
    checked the same way journey_state() above does, via
    get_checkpoint_backlog()'s trips.get_trip(session, trip_id, user_id).

    Subscribes BEFORE reading the current checkpoint list, not after -
    otherwise a checkpoint created in between those two steps would be
    silently missed. The live loop then skips re-sending any
    checkpoint_added already covered by that starting snapshot (by
    checkpoint_number), so that ordering doesn't turn into a duplicate
    marker instead."""
    event_type = f"trip_checkpoints:{trip_id}"
    listener = _CheckpointEventListener()
    travel_facade.events.subscribe(event_type, listener)

    try:
        backlog, already_ready = travel_facade.get_checkpoint_backlog(current_user.id, trip_id)
    except ValueError:
        travel_facade.events.unsubscribe(event_type, listener)
        return JSONResponse({"error": "No such trip."}, status_code=404)

    def event_stream():
        try:
            backlog_numbers = set()
            for checkpoint in backlog:
                backlog_numbers.add(checkpoint["checkpoint_number"])
                yield _sse_message("checkpoint_added", {"checkpoint": checkpoint})

            if already_ready:
                yield _sse_message("checkpoints_ready", {})
                return

            while True:
                try:
                    event = listener.queue.get(timeout=SSE_KEEPALIVE_SECONDS)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue

                if event["type"] == "checkpoint_added" and event["checkpoint"]["checkpoint_number"] in backlog_numbers:
                    continue  # already sent in the starting snapshot above
                yield _sse_message(event["type"], {k: v for k, v in event.items() if k != "type"})
                if event["type"] == "checkpoints_ready":
                    return
        finally:
            travel_facade.events.unsubscribe(event_type, listener)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/journey/state")
def journey_state(trip_id: uuid.UUID, current_user: User = Depends(get_current_user)):
    """Polled by frontend/src/pages/TripDetailPage.tsx while a trip is on
    screen - the same map-ready shape start_journey() returns, always with
    every checkpoint included (tagged hit: true/false), not just the hit
    ones. Filtering that down to "only what a normal user should see" is
    the frontend's job (see TripDetailPage.tsx and dev_testing/TRIP_MAP.md's
    ?debug=1 flag), not this endpoint's. A user can have several trips
    going at once now, so trip_id says which one."""
    try:
        return travel_facade.get_map_state(current_user.id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.get("/api/journey/list")
def journey_list(current_user: User = Depends(get_current_user)):
    """Every trip belonging to the logged-in user, active or finished -
    frontend/src/pages/HomePage.tsx's My Journeys screen splits this into
    "Active" (status active/paused) and "Completed" sections client-side."""
    return {"trips": travel_facade.list_trips(current_user.id)}


@app.get("/api/journey/stats")
def journey_stats(current_user: User = Depends(get_current_user)):
    """The Profile screen's one journey-derived stat - kept separate from
    /api/journey/list (which every screen calls) since only Profile needs
    it and it's a different kind of read (one aggregate, not per-trip
    rows)."""
    return {"lifetime_steps": travel_facade.lifetime_steps(current_user.id)}


@app.post("/api/journey/{trip_id}/pause")
def pause_journey(trip_id: uuid.UUID, current_user: User = Depends(get_current_user)):
    try:
        return travel_facade.pause_journey(current_user.id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.post("/api/journey/{trip_id}/resume")
def resume_journey(trip_id: uuid.UUID, current_user: User = Depends(get_current_user)):
    try:
        return travel_facade.resume_journey(current_user.id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)


@app.delete("/api/journey/{trip_id}")
def delete_journey(trip_id: uuid.UUID, current_user: User = Depends(get_current_user)):
    try:
        travel_facade.delete_journey(current_user.id, trip_id)
    except ValueError:
        return JSONResponse({"error": "No such trip."}, status_code=404)
    return Response(status_code=204)


class JourneyDeleteBulkRequest(BaseModel):
    trip_ids: list[uuid.UUID]


@app.post("/api/journey/delete")
def delete_journeys(body: JourneyDeleteBulkRequest, current_user: User = Depends(get_current_user)):
    """Multi-select delete from the trips panel - one request instead of
    the frontend firing a DELETE per selected card."""
    deleted_count = travel_facade.delete_journeys(current_user.id, body.trip_ids)
    return {"deleted": deleted_count}


# Every page route (/, /login, /signup, and anything react-router adds
# later) is this same file - a plain SPA shell with no server-injected
# state. Registered dead last, after every real route/router above (route
# matching is registration order, not specificity) so it only ever
# catches what nothing else claimed; still explicitly excludes the API
# prefixes so a genuinely missing API route 404s instead of silently
# getting HTML back.
#
# On Vercel this route is effectively dead code in production -
# vercel.json's own routes send every non-API path straight to the
# @vercel/static-build output before it ever reaches this Python
# function. Local dev (uvicorn serving this file directly) and the
# single-container Docker/Cloud Run image both have no such routing
# layer in front of this app, so this is the route that actually serves
# react-router's client-side paths there.
@app.get("/{full_path:path}")
def spa(full_path: str):
    if full_path.startswith(API_PREFIXES):
        raise HTTPException(status_code=404)
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=503, detail="Frontend build not found - run `npm run build` in frontend/.")
    return FileResponse(index_file)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
