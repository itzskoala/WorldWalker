#route_point.py

from dataclasses import dataclass
from travel_logic.dataclasses.coordinates import Coordinates


@dataclass(frozen=True)
class RoutePoint:
    coords: Coordinates
    point_number: int  # 1-indexed, start is 1
    distance_from_start: float
    distance_to_destination: float
    distance_to_previous: float  # 0 for the first point
    distance_to_next: float  # 0 for the last point


@dataclass(frozen=True)
class Route:
    points: list[RoutePoint]
    total_distance: float
    point_count: int
