#route_service.py
# Walking route between two coordinates: ordered points, each carrying its
# distance (in meters) from the start, from the destination, and to its
# immediate neighbors - so progress_calculator can place a user at a given
# distance along the route later.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import radians, sin, cos, asin, sqrt
import requests
from travel_logic.coordinates import Coordinates

EARTH_RADIUS_METERS = 6371000.0


def haversine_meters(a: Coordinates, b: Coordinates) -> float:
    lat1, lng1, lat2, lng2 = map(radians, (a.lat, a.lng, b.lat, b.lng))
    d_lat, d_lng = lat2 - lat1, lng2 - lng1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(h))


@dataclass(frozen=True)
class RoutePoint:
    coords: Coordinates
    point_number: int  # 1-indexed position along the route: start is 1
    distance_from_start: float
    distance_to_destination: float
    distance_to_previous: float  # 0 for the first point - no previous point
    distance_to_next: float  # 0 for the last point - no next point


@dataclass(frozen=True)
class Route:
    points: list  # list[RoutePoint], ordered start -> destination
    total_distance: float
    point_count: int  # how many points make up the route, start through destination


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

        # gaps[i] = distance from coords[i] to coords[i + 1]; the last point
        # has no next point, so its gap is 0.
        gaps = []
        for i in range(len(coords) - 1):
            gaps.append(haversine_meters(coords[i], coords[i + 1]))
        gaps.append(0.0)

        total_distance = sum(gaps)

        points = []
        distance_from_start = 0.0
        for i, c in enumerate(coords):
            distance_to_previous = gaps[i - 1] if i > 0 else 0.0
            distance_to_next = gaps[i]
            points.append(RoutePoint(
                coords=c,
                point_number=i + 1,
                distance_from_start=distance_from_start,
                distance_to_destination=total_distance - distance_from_start,
                distance_to_previous=distance_to_previous,
                distance_to_next=distance_to_next,
            ))
            distance_from_start += distance_to_next

        return Route(points=points, total_distance=total_distance, point_count=len(points))
