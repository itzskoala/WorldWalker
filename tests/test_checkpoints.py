# tests/test_checkpoints.py
# Pure logic for travel_logic/checkpoints.py's three independent stages -
# position generation (sample-count curve, interpolated placement), name/
# description resolution, reveal-radius generation - plus the checkpoint-
# progress/filtering helpers. No real network calls anywhere here; that's
# core/facade.py's job to wire up against the real Geocoder/
# DescriptionGenerator (see tests/test_facade.py).

import pytest
from travel_logic.checkpoints import (
    Checkpoint,
    CheckpointProgress,
    _sample_count,
    generate_checkpoint_positions,
    resolve_checkpoint_name,
    generate_checkpoint_description,
    generate_reveal_radius_m,
    checkpoints_viewed,
    checkpoints_not_seen,
    checkpoint_progress,
    CHECKPOINT_DENSITY_K,
    CHECKPOINT_GROWTH_ALPHA,
    CHECKPOINT_MIN_COUNT,
    CHECKPOINT_REVEAL_RADIUS_MIN_M,
    CHECKPOINT_REVEAL_RADIUS_MAX_M,
)
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint


class FakeGeocoder:
    def __init__(self, city_by_key=None, fallback_by_key=None):
        self._city_by_key = city_by_key or {}
        self._fallback_by_key = fallback_by_key or {}

    def _key(self, coords):
        return (round(coords.lat, 4), round(coords.lng, 4))

    def reverse_geocode_city(self, coords):
        return self._city_by_key.get(self._key(coords))

    def reverse_geocode(self, coords):
        return self._fallback_by_key.get(self._key(coords), "Unknown")


class FakeDescriptionGenerator:
    def __init__(self, raises=False):
        self._raises = raises

    def generate(self, prompt):
        if self._raises:
            raise RuntimeError("model is down")
        return "A lovely little stop."


def _route(distances):
    total_distance = distances[-1]
    points = [
        RoutePoint(
            Coordinates(40.0 + i, -90.0 - i), point_number=i + 1, distance_from_start=d,
            distance_to_destination=total_distance - d, distance_to_previous=0.0, distance_to_next=0.0,
        )
        for i, d in enumerate(distances)
    ]
    return Route(points=points, total_distance=total_distance, point_count=len(points))


# --- _sample_count ---

def _expected_sample_count(total_distance_m):
    """Mirrors _sample_count's own formula - N = max(N_min, floor(k * L^alpha))
    - so these tests check the real curve, not a hardcoded table of
    distance -> count pairs."""
    if total_distance_m <= 0:
        return 0
    length_km = total_distance_m / 1000
    return max(CHECKPOINT_MIN_COUNT, int(CHECKPOINT_DENSITY_K * length_km ** CHECKPOINT_GROWTH_ALPHA))


def test_sample_count_zero_length_route_has_no_samples():
    assert _sample_count(0.0) == 0


def test_sample_count_matches_the_power_curve_formula_for_short_medium_and_long_routes():
    for total_distance_m in (800.0, 10_000.0, 1_000_000.0):  # short, medium, long
        assert _sample_count(total_distance_m) == _expected_sample_count(total_distance_m)


def test_sample_count_very_short_route_still_gets_the_floor_minimum():
    # 800m is short enough that k * L^alpha rounds below 1 - N_min still
    # guarantees at least one checkpoint rather than zero.
    assert _sample_count(800.0) == CHECKPOINT_MIN_COUNT


def test_sample_count_grows_sublinearly_as_routes_get_longer():
    short = _sample_count(10_000.0)  # 10km
    medium = _sample_count(100_000.0)  # 100km
    long = _sample_count(1_000_000.0)  # 1,000km

    # Longer routes get more checkpoints...
    assert short < medium < long
    # ...but growth is gradual: a 10x increase in distance never comes
    # close to a 10x increase in checkpoint count.
    assert medium < short * 10
    assert long < medium * 10


def test_sample_count_has_no_upper_cap_for_a_very_long_route():
    # A transcontinental-scale route used to be clamped to MAX_SAMPLES
    # (60) because the old pipeline paid one blocking Nominatim round
    # trip per sample before the trip could even appear. Position
    # generation is pure geometry now - name/description resolution
    # happens lazily, long after the trip exists - so nothing caps N any
    # more; it just keeps growing, sublinearly, with route length.
    very_long = _sample_count(10_000_000.0)  # 10,000km
    extremely_long = _sample_count(100_000_000.0)  # 100,000km
    assert very_long > 60
    assert extremely_long > very_long


# --- generate_checkpoint_positions ---

def test_generate_checkpoint_positions_covers_short_medium_and_long_routes():
    for total_distance_m in (800.0, 25_000.0, 1_000_000.0):
        route = _route([0.0, total_distance_m])
        positions = generate_checkpoint_positions(route)

        assert len(positions) == _sample_count(total_distance_m)
        assert [p.checkpoint_number for p in positions] == list(range(1, len(positions) + 1))
        # Every position is blank, ready for lazy resolution - never
        # geocoded up front.
        assert all(p.name == "" and p.description == "" for p in positions)
        # Strictly increasing and strictly inside the route (never at the
        # start or destination itself).
        distances = [p.distance_from_start_m for p in positions]
        assert distances == sorted(distances)
        assert all(0 < d < total_distance_m for d in distances)
        for p in positions:
            assert p.distance_to_destination_m == pytest.approx(total_distance_m - p.distance_from_start_m, abs=0.1)


def test_generate_checkpoint_positions_zero_length_route_has_none():
    route = _route([0.0, 0.0])
    assert generate_checkpoint_positions(route) == []


def test_generate_checkpoint_positions_interpolates_between_route_points_rather_than_snapping():
    # Only two route points, 1000m apart - the one sample this route
    # scores (sample_count=1, landing at the midpoint) has no existing
    # vertex to snap to, so it must be computed by interpolating between
    # the two real vertices, and it must still land exactly on the route.
    start, end = Coordinates(40.0, -90.0), Coordinates(40.01, -90.0)
    route = Route(
        points=[
            RoutePoint(start, point_number=1, distance_from_start=0.0, distance_to_destination=1000.0,
                       distance_to_previous=0.0, distance_to_next=1000.0),
            RoutePoint(end, point_number=2, distance_from_start=1000.0, distance_to_destination=0.0,
                       distance_to_previous=1000.0, distance_to_next=0.0),
        ],
        total_distance=1000.0,
        point_count=2,
    )

    positions = generate_checkpoint_positions(route)

    assert len(positions) == 1
    position = positions[0]
    assert position.distance_from_start_m == pytest.approx(500.0)
    # Exact midpoint of start/end - true interpolation, not a snap to
    # either existing vertex.
    assert position.coordinates.lat == pytest.approx((start.lat + end.lat) / 2)
    assert position.coordinates.lng == pytest.approx((start.lng + end.lng) / 2)


# --- resolve_checkpoint_name ---

def test_resolve_checkpoint_name_prefers_the_city_tier_name():
    coords = Coordinates(41.8781, -87.6298)
    geocoder = FakeGeocoder(city_by_key={(41.8781, -87.6298): "Chicago"})
    assert resolve_checkpoint_name(coords, geocoder) == "Chicago"


def test_resolve_checkpoint_name_falls_back_when_not_in_a_recognized_city():
    # Unlike the old sampling loop (which simply dropped a sample that
    # wasn't in a recognized city), a position here can never go
    # nameless - checkpoint count/position is fixed before any name is
    # known, so every one of them needs *some* real label.
    coords = Coordinates(44.0, -100.0)
    geocoder = FakeGeocoder(fallback_by_key={(44.0, -100.0): "Faulk County, South Dakota"})
    assert resolve_checkpoint_name(coords, geocoder) == "Faulk County, South Dakota"


# --- generate_checkpoint_description ---

def test_generate_checkpoint_description_uses_the_resolved_name():
    description = generate_checkpoint_description("Chicago", Coordinates(41.8781, -87.6298), FakeDescriptionGenerator())
    assert description == "A lovely little stop."


def test_generate_checkpoint_description_falls_back_on_a_model_failure():
    description = generate_checkpoint_description("Chicago", Coordinates(41.8781, -87.6298), FakeDescriptionGenerator(raises=True))
    assert description == "A stop along the way in Chicago."


# --- generate_reveal_radius_m ---

def test_generate_reveal_radius_m_stays_within_the_configured_range():
    for _ in range(200):
        radius = generate_reveal_radius_m()
        assert CHECKPOINT_REVEAL_RADIUS_MIN_M <= radius <= CHECKPOINT_REVEAL_RADIUS_MAX_M


def test_generate_reveal_radius_m_is_not_a_single_fixed_value():
    radii = {generate_reveal_radius_m() for _ in range(50)}
    assert len(radii) > 1


# --- checkpoints_viewed / checkpoints_not_seen ---

def _checkpoint(number, distance_from_start_m):
    return Checkpoint(
        name=f"Stop {number}",
        coordinates=Coordinates(0.0, 0.0),
        checkpoint_number=number,
        distance_from_start_m=distance_from_start_m,
        distance_to_destination_m=0.0,
    )


def test_checkpoints_viewed_and_not_seen_split_on_distance_walked():
    checkpoints = [_checkpoint(1, 1000.0), _checkpoint(2, 2000.0), _checkpoint(3, 3000.0)]

    assert checkpoints_viewed(checkpoints, 2000.0) == [checkpoints[0], checkpoints[1]]
    assert checkpoints_not_seen(checkpoints, 2000.0) == [checkpoints[2]]


# --- checkpoint_progress ---

def test_checkpoint_progress_before_the_first_checkpoint():
    checkpoints = [_checkpoint(1, 1000.0), _checkpoint(2, 2000.0)]
    progress = checkpoint_progress(checkpoints, 500.0)
    assert progress == CheckpointProgress(current_checkpoint_number=0, distance_to_next_checkpoint_m=500.0)


def test_checkpoint_progress_between_two_checkpoints():
    checkpoints = [_checkpoint(1, 1000.0), _checkpoint(2, 2000.0), _checkpoint(3, 3000.0)]
    progress = checkpoint_progress(checkpoints, 1500.0)
    assert progress == CheckpointProgress(current_checkpoint_number=1, distance_to_next_checkpoint_m=500.0)


def test_checkpoint_progress_past_the_last_checkpoint_has_no_next():
    checkpoints = [_checkpoint(1, 1000.0), _checkpoint(2, 2000.0)]
    progress = checkpoint_progress(checkpoints, 5000.0)
    assert progress == CheckpointProgress(current_checkpoint_number=2, distance_to_next_checkpoint_m=None)


def test_checkpoint_progress_exact_hit_on_a_checkpoint_counts_as_reached():
    checkpoints = [_checkpoint(1, 1000.0), _checkpoint(2, 2000.0)]
    progress = checkpoint_progress(checkpoints, 1000.0)
    assert progress == CheckpointProgress(current_checkpoint_number=1, distance_to_next_checkpoint_m=1000.0)
