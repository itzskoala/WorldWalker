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


def build_route(coords: list[Coordinates]) -> Route:
    """Turns an ordered list of Coordinates into a Route with every point's
    distance bookkeeping filled in. Factored out of OSRMWalkingRouteService
    below so a caller that already has the coordinates - e.g.
    core/facade.py reloading a trip's stored route_geometry from the
    database - can rebuild the exact same Route shape without a network
    call back to OSRM."""
    # gaps[i] = distance from coords[i] to coords[i + 1]; the last point has
    # no next point, so its gap is 0.
    gaps = []
    for i in range(len(coords) - 1):
        gaps.append(haversine_meters(coords[i], coords[i + 1]))
    gaps.append(0.0)

    # distances_from_start[i] is built by the same running accumulator that
    # becomes total_distance below - not a separately-computed sum() - so
    # route.total_distance is guaranteed to exactly equal
    # route.points[-1].distance_from_start (sum() and a manual += loop can
    # round differently over many points otherwise).
    distances_from_start = []
    distance_from_start = 0.0
    for gap in gaps:
        distances_from_start.append(distance_from_start)
        distance_from_start += gap

    total_distance = distance_from_start

    points = []
    for i, c in enumerate(coords):
        distance_to_previous = gaps[i - 1] if i > 0 else 0.0
        distance_to_next = gaps[i]
        points.append(RoutePoint(
            coords=c,
            point_number=i + 1,
            distance_from_start=distances_from_start[i],
            distance_to_destination=total_distance - distances_from_start[i],
            distance_to_previous=distance_to_previous,
            distance_to_next=distance_to_next,
        ))

    return Route(points=points, total_distance=total_distance, point_count=len(points))


class RouteService(ABC):
    @abstractmethod
    def get_walking_route(self, start: Coordinates, end: Coordinates) -> Route:
        """Raises ValueError if no walking route exists between the two points."""

    @abstractmethod
    def route_exists(self, start: Coordinates, end: Coordinates) -> bool:
        """Same provider call and the same "no route"/provider-failure
        distinction as get_walking_route() (ValueError for a real "no",
        whatever get_walking_route() itself raises for a transport
        failure), for a caller that only needs the yes/no answer - e.g.
        travel_logic/route_validation.py - without paying for building
        the full Route's per-point distance bookkeeping, which
        get_walking_route() always does and this caller never uses."""


class OSRMWalkingRouteService(RouteService):
    BASE_URL = "https://router.project-osrm.org/route/v1/foot"

    # No `radiuses` bound - OSRM's own snap search is left unbounded on
    # purpose. Whatever OSRM decides is walkable, including a route that
    # crosses open water (confirmed live: New York -> London comes back
    # "code": "Ok" with a ~2,150km route, snapping the New York end
    # ~5,534km away to make it connect) counts as a real route here - the
    # product's own call, not something this class second-guesses with an
    # invented distance cutoff. If OSRM can place a walking path on real
    # coordinates, that's the answer.
    def _fetch_route_data(self, start: Coordinates, end: Coordinates) -> dict:
        """The OSRM call + response parsing shared by get_walking_route()
        and route_exists() below - everything except turning a real
        answer into a full Route. Raises ValueError for a real "no route"
        answer or an unrecognizable response, same as get_walking_route()
        always has; a transport failure (timeout, DNS, 5xx with no body)
        raises requests.RequestException, letting it propagate."""
        url = f"{self.BASE_URL}/{start.lng},{start.lat};{end.lng},{end.lat}"
        resp = requests.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=15)

        # OSRM reports its own routing failures - "NoSegment" (no
        # snappable point near a coordinate at all) or "NoRoute" (both
        # points snapped fine but nothing connects them, e.g. two real
        # streets on different islands with no path between them) - as
        # HTTP 400 with a structured {"code", "message"} body, confirmed
        # live for both. That's a real, meaningful "no route" answer from
        # OSRM, not a transport failure - so this checks the body's own
        # "code" field before ever consulting the HTTP status. Calling
        # raise_for_status() first (the old code did) would raise a
        # generic HTTPError on every one of those cases, indistinguishable
        # from OSRM actually being down - exactly the "provider failure"
        # vs. "real no-route answer" mixup travel_logic/route_validation.py
        # exists to keep apart (a provider failure must never be treated
        # as a real "no" - see RouteUnavailable there).
        try:
            data = resp.json()
        except ValueError:
            data = None

        if not isinstance(data, dict) or "code" not in data:
            # Not a recognizable OSRM response at all (an outage page, a
            # proxy error, a truncated body, ...) - now the HTTP status is
            # the only signal left, and a non-2xx here is a real provider
            # failure, not a route answer.
            resp.raise_for_status()
            raise ValueError(f"Unexpected OSRM response for {start} -> {end}: {resp.text[:200]!r}")

        if data.get("code") != "Ok" or not data.get("routes"):
            detail = data.get("message", data.get("code", "unknown error"))
            raise ValueError(f"No walking route between {start} and {end}: {detail}")

        return data

    def get_walking_route(self, start: Coordinates, end: Coordinates) -> Route:
        data = self._fetch_route_data(start, end)

        # GeoJSON is [lng, lat] - flip to our Coordinates(lat, lng).
        raw_coords = data["routes"][0]["geometry"]["coordinates"]
        coords = [Coordinates(lat=lat, lng=lng) for lng, lat in raw_coords]

        # OSRM's own path can start/end at whatever point it snapped to,
        # not the coordinates actually requested (observed live: London
        # -> New York snaps the New York end to Portugal, ~5,534km away,
        # rather than reporting failure - see the class docstring above).
        # database/trips.py's create_trip() reads a trip's start/end
        # coordinates straight off route.points[0]/[-1], so leaving that
        # gap unfilled doesn't just cut the drawn line short at the
        # coastline - it puts the destination marker itself at the snap
        # point instead of where the user actually picked. Anchoring both
        # ends to the real request closes that gap unconditionally, no
        # distance check needed: an ordinary snap (a few meters) adds an
        # imperceptible bridging segment; a large one becomes a real,
        # deliberate straight-line segment across the water - exactly
        # what should render there.
        if coords[0] != start:
            coords.insert(0, start)
        if coords[-1] != end:
            coords.append(end)

        return build_route(coords)

    def route_exists(self, start: Coordinates, end: Coordinates) -> bool:
        # _fetch_route_data() raises ValueError for a real "no route"
        # answer - caught here and turned into False, a plain yes/no.
        # requests.RequestException (a real provider/transport failure)
        # is deliberately left to propagate, same as get_walking_route(),
        # so a caller still can't mistake OSRM being down for a real "no".
        #
        # Deliberately never touches the response's geometry/coordinates:
        # parsing thousands of points into Coordinates objects and
        # running them through build_route()'s per-pair haversine_meters()
        # calls (the same cost get_walking_route() pays for a real trip)
        # would be pure waste here, for a Route this caller throws away
        # unused.
        try:
            self._fetch_route_data(start, end)
        except ValueError:
            return False
        return True
