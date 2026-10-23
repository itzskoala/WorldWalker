#route_validation.py
# Validate whether a walking route is possible without creating a trip.

import os

import requests

from travel_logic.dataclasses.route_validation import RouteValidation
from travel_logic.route_service import haversine_meters

MIN_WALKING_ROUTE_METERS = float(os.environ.get("MIN_WALKING_ROUTE_METERS", "1609.344"))


class RouteUnavailable(Exception):
    """Raised when the routing provider fails."""


def validate_walking_route(router, start, end, min_distance_m=MIN_WALKING_ROUTE_METERS):
    """Check whether a walking route exists between two coordinates."""
    if haversine_meters(start, end) < min_distance_m:
        return RouteValidation(valid=False, reason="too_close")

    try:
        exists = router.route_exists(start, end)
    except requests.RequestException as error:
        raise RouteUnavailable(str(error)) from error

    if not exists:
        return RouteValidation(valid=False, reason="no_route")

    return RouteValidation(valid=True)
