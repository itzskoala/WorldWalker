#route_service.py
# Walking route between two coordinates: ordered points with cumulative
# distance, so progress_calculator can place a user "at mile X" later.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import radians, sin, cos, asin, sqrt
import requests
from travel_logic.coordinates import Coordinates

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(a: Coordinates, b: Coordinates) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (a.lat, a.lng, b.lat, b.lng))
    d_lat, d_lng = lat2 - lat1, lng2 - lng1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(h))


@dataclass(frozen=True)
class RoutePoint:
    coords: Coordinates
    miles_from_start: float


@dataclass(frozen=True)
class Route:
    points: list  # list[RoutePoint], ordered start -> destination
    total_miles: float


class RouteService(ABC):
    @abstractmethod
    def get_walking_route(self, start: Coordinates, end: Coordinates) -> Route:
        """Raises ValueError if no walking route exists between the two points."""


class OSRMWalkingRouteService(RouteService):
    BASE_URL = "https://router.project-osrm.org/route/v1/foot"

    def get_walking_route(self, start: Coordinates, end: Coordinates) -> Route:
        url = f"{self.BASE_URL}/{start.lng},{start.lat};{end.lng},{end.lat}"
        resp = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError(f"No walking route between {start} and {end}")

        # GeoJSON is [lng, lat] - flip to our Coordinates(lat, lng).
        raw_coords = data["routes"][0]["geometry"]["coordinates"]
        coords = [Coordinates(lat=lat, lng=lng) for lng, lat in raw_coords]

        points, cumulative = [], 0.0
        for i, c in enumerate(coords):
            if i > 0:
                cumulative += haversine_miles(coords[i - 1], c)
            points.append(RoutePoint(coords=c, miles_from_start=cumulative))

        return Route(points=points, total_miles=cumulative)
