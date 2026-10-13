#route_validation.py
# "Can I actually walk from here to there?" - the location-picking UI's
# immediate check (frontend/src/pages/CreatePage.tsx), once both Where
# From/Where To fields have resolved to real coordinates. Deliberately
# separate from core.facade.TravelFacade.start_journey(): that also
# geocodes + calls OSRM, but persists a trip as its very next step -
# nothing here touches the database, so calling this on every location
# selection never creates a trip just to check one (see app.py's
# POST /api/route/validate).

import os
from dataclasses import dataclass
from typing import Literal, Optional

import requests

from travel_logic.coordinates import Coordinates
from travel_logic.route_service import RouteService, haversine_meters

# ~1 mile - below this, "walking a route" isn't really a meaningful trip
# (and OSRM's own foot-routing between two near-identical points is prone
# to degenerate/zero-length results anyway). Overridable per deployment
# without a code change, same pattern as accounts/security.py's token
# lifetimes.
MIN_WALKING_ROUTE_METERS = float(os.environ.get("MIN_WALKING_ROUTE_METERS", "1609.344"))

RouteInvalidReason = Literal["too_close", "no_route"]


@dataclass(frozen=True)
class RouteValidation:
    valid: bool
    reason: Optional[RouteInvalidReason] = None


class RouteUnavailable(Exception):
    """The routing provider itself failed (network error, timeout, 5xx) -
    distinct from RouteValidation(valid=False), which means OSRM was
    reachable and gave a real answer. Callers must not treat the two the
    same way: a UI that clears a field on RouteValidation(valid=False) but
    not on this exception won't wipe out a user's selection just because
    OSRM hiccuped for a moment."""


def validate_walking_route(
    router: RouteService,
    start: Coordinates,
    end: Coordinates,
    min_distance_m: float = MIN_WALKING_ROUTE_METERS,
) -> RouteValidation:
    """Same point (or near enough there's no real walk to take) short-
    circuits before ever calling OSRM - no network round trip needed to
    know two identical/near-identical coordinates aren't a route. Raises
    RouteUnavailable (rather than returning valid=False) when the routing
    provider itself couldn't be reached, so a transient failure can't be
    mistaken for "no walking route exists".

    Calls router.route_exists(), not get_walking_route(): this is a
    yes/no check (CreatePage.tsx's "can I walk from here to there?", see
    app.py's POST /api/route/validate) that never uses the actual route -
    get_walking_route() always builds one anyway (the same per-point
    distance bookkeeping real trip creation needs), which for a long
    candidate pair measurably added to how long this check took for no
    reason; route_exists() skips straight to the same real yes/no OSRM
    already gave without paying for that."""
    if haversine_meters(start, end) < min_distance_m:
        return RouteValidation(valid=False, reason="too_close")

    try:
        exists = router.route_exists(start, end)
    except requests.RequestException as e:
        # route_exists() already turns OSRM's own "no route" answer into
        # a plain False (including requests' own JSONDecodeError on a
        # malformed/truncated response body, which is also technically a
        # ValueError - see its docstring) - whatever reaches here instead
        # is a real transport failure (timeout, DNS, OSRM unreachable).
        raise RouteUnavailable(str(e)) from e

    if not exists:
        return RouteValidation(valid=False, reason="no_route")

    return RouteValidation(valid=True)
