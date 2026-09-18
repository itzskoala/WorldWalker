# tests/test_checkpoints.py
# Pure logic (sample-count curve, checkpoint-progress lookup, filtering)
# plus generate_checkpoints wired to fake Geocoder/DescriptionGenerator
# stand-ins - no real network calls.

import pytest
from travel_logic.checkpoints import (
    Checkpoint,
    CheckpointProgress,
    _sample_count,
    generate_checkpoints,
    checkpoints_viewed,
    checkpoints_not_seen,
    checkpoint_progress,
    MAX_SAMPLES,
)
from travel_logic.coordinates import Coordinates
from travel_logic.route_service import Route, RoutePoint


class FakeGeocoder:
    def __init__(self, city_by_index):
        self._city_by_index = city_by_index
        self.calls = 0

    def reverse_geocode_city(self, coords):
        city = self._city_by_index[self.calls]
        self.calls += 1
        return city


class FakeDescriptionGenerator:
    def generate(self, prompt):
        return "A lovely little stop."


def _route_point(point_number, distance_from_start, total_distance):
    return RoutePoint(
        Coordinates(40.0 + point_number, -90.0 - point_number),
        point_number=point_number,
        distance_from_start=distance_from_start,
        distance_to_destination=total_distance - distance_from_start,
        distance_to_previous=0.0,
        distance_to_next=0.0,
    )


def _route(distances):
    total_distance = distances[-1]
    points = [_route_point(i + 1, d, total_distance) for i, d in enumerate(distances)]
    return Route(points=points, total_distance=total_distance, point_count=len(points))


# --- _sample_count ---

def test_sample_count_scales_with_the_square_root_of_kilometers():
    assert _sample_count(0.0) == 0
    assert _sample_count(1_000_000.0) == int(1.0 * (1_000_000.0 / 1000) ** 0.5)


def test_sample_count_never_exceeds_max_samples():
    assert _sample_count(10_000_000_000.0) == MAX_SAMPLES


# --- generate_checkpoints ---

def test_generate_checkpoints_numbers_and_ports_distances_to_meters(monkeypatch):
    monkeypatch.setattr("travel_logic.checkpoints.time.sleep", lambda seconds: None)

    # total_distance=25_000 -> sample_count=5 (sqrt(25_000/1000)=5), landing
    # exactly on the 5 middle points below - each geocode call below maps
    # 1:1 to one of them, in order.
    route = _route([0.0, 4_167.0, 8_333.0, 12_500.0, 16_667.0, 20_833.0, 25_000.0])
    geocoder = FakeGeocoder(["Chicago", "Chicago", "Gary", "Gary", "South Bend"])

    checkpoints = generate_checkpoints(route, geocoder, FakeDescriptionGenerator())

    assert [c.name for c in checkpoints] == ["Chicago", "Gary", "South Bend"]
    assert [c.checkpoint_number for c in checkpoints] == [1, 2, 3]
    assert checkpoints[0].distance_from_start_m < checkpoints[1].distance_from_start_m < checkpoints[2].distance_from_start_m
    for c in checkpoints:
        assert c.distance_to_destination_m == pytest.approx(route.total_distance - c.distance_from_start_m)


def test_generate_checkpoints_too_short_a_route_yields_nothing(monkeypatch):
    monkeypatch.setattr("travel_logic.checkpoints.time.sleep", lambda seconds: None)
    route = _route([0.0, 50.0])
    checkpoints = generate_checkpoints(route, FakeGeocoder([]), FakeDescriptionGenerator())
    assert checkpoints == []


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
