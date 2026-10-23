#route_service.py

from math import asin, cos, radians, sin, sqrt

import requests

from travel_logic.dataclasses.coordinates import Coordinates
from travel_logic.dataclasses.route_point import Route, RoutePoint

EARTH_RADIUS_METERS = 6_371_000.0


class NoWalkingRouteError(ValueError):
    """Raised when the routing provider confirms no route exists."""


def haversine_meters(a, b):
    """Straight-line distance between two coordinates, in meters."""
    lat1, lng1, lat2, lng2 = map(radians, (a.lat, a.lng, b.lat, b.lng))

    d_lat = lat2 - lat1
    d_lng = lng2 - lng1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lng / 2) ** 2
    h = max(0.0, min(1.0, h))  # guard tiny float error

    return 2 * EARTH_RADIUS_METERS * asin(sqrt(h))


def build_route(coords):
    """Build a Route from ordered coordinates, no network call."""
    gaps = []
    for i in range(len(coords) - 1):
        gaps.append(haversine_meters(coords[i], coords[i + 1]))
    gaps.append(0.0)  # the last point has no next point

    points = []
    distance_from_start = 0.0
    for i, coords_i in enumerate(coords):
        previous_gap = gaps[i - 1] if i > 0 else 0.0
        points.append(RoutePoint(
            coords=coords_i,
            point_number=i + 1,
            distance_from_start=distance_from_start,
            distance_to_destination=0.0,
            distance_to_previous=previous_gap,
            distance_to_next=gaps[i],
        ))
        distance_from_start += gaps[i]

    total_distance = distance_from_start

    final_points = []
    for point in points:
        final_points.append(RoutePoint(
            coords=point.coords,
            point_number=point.point_number,
            distance_from_start=point.distance_from_start,
            distance_to_destination=total_distance - point.distance_from_start,
            distance_to_previous=point.distance_to_previous,
            distance_to_next=point.distance_to_next,
        ))

    return Route(points=final_points, total_distance=total_distance, point_count=len(final_points))


class OSRMWalkingRouteService:
    """Gets walking routes from the public OSRM routing service."""

    BASE_URL = "https://router.project-osrm.org/route/v1/foot"

    def _fetch_route_data(self, start, end):
        url = f"{self.BASE_URL}/{start.lng},{start.lat};{end.lng},{end.lat}"
        response = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=15)

        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            response.raise_for_status()
            raise RuntimeError(f"OSRM returned an invalid response: {response.text[:200]}")

        if not isinstance(data, dict) or "code" not in data:
            response.raise_for_status()
            raise RuntimeError(f"Unexpected OSRM response: {response.text[:200]}")

        code = data.get("code")

        # OSRM's own "no route" answer - check this before raise_for_status(),
        # since it can arrive as an HTTP 400 with a real, structured body.
        if code in ("NoRoute", "NoSegment"):
            raise NoWalkingRouteError(f"No walking route between {start} and {end}: {data.get('message', code)}")

        if code != "Ok" or not data.get("routes"):
            response.raise_for_status()
            raise RuntimeError(f"OSRM routing failed: {data.get('message', code)}")

        response.raise_for_status()
        return data

    def get_walking_route(self, start, end):
        """Return a walking route, or raise if routing fails."""
        data = self._fetch_route_data(start, end)

        # GeoJSON coordinates use [longitude, latitude].
        raw_coords = data["routes"][0]["geometry"]["coordinates"]
        coords = []
        for lng, lat in raw_coords:
            coords.append(Coordinates(lat=lat, lng=lng))

        if not coords:
            raise RuntimeError("OSRM returned a route with no coordinates.")

        # OSRM can snap an endpoint away from the real requested point -
        # bridge back to it rather than letting the map/marker land there.
        if coords[0] != start:
            coords.insert(0, start)
        if coords[-1] != end:
            coords.append(end)

        return build_route(coords)

    def route_exists(self, start, end):
        """Plain yes/no, without paying for build_route()'s bookkeeping."""
        try:
            self._fetch_route_data(start, end)
        except ValueError:
            return False
        return True
