# tests/test_route_service.py
# build_route's distance bookkeeping - in particular the invariant that
# route.total_distance and route.points[-1].distance_from_start must be
# exactly the same value, not just close. Python 3.12+ made sum() use
# compensated summation for floats, which used to drift from a separate
# manual += accumulator over enough points (see build_route's comment in
# travel_logic/route_service.py) and could push locate_on_route's clamp
# past the end of route.points.

from travel_logic.route_service import build_route
from travel_logic.coordinates import Coordinates


def test_build_route_total_distance_exactly_matches_last_point_over_many_points():
    # Enough points, at a granular enough step, for sum()'s compensated
    # summation to diverge from a naive += accumulator if they were ever
    # computed independently again.
    coords = [Coordinates(lat=40.0 + i * 0.0001, lng=-90.0 + i * 0.0001) for i in range(12_000)]
    route = build_route(coords)
    assert route.total_distance == route.points[-1].distance_from_start


def test_build_route_total_distance_matches_last_point_for_a_short_route():
    coords = [Coordinates(41.80, -87.65), Coordinates(41.81, -87.64), Coordinates(41.83, -87.60)]
    route = build_route(coords)
    assert route.total_distance == route.points[-1].distance_from_start


def test_build_route_distance_to_destination_still_reaches_zero_at_the_last_point():
    coords = [Coordinates(41.80, -87.65), Coordinates(41.81, -87.64), Coordinates(41.83, -87.60)]
    route = build_route(coords)
    assert route.points[-1].distance_to_destination == 0.0
    assert route.points[0].distance_to_destination == route.total_distance
