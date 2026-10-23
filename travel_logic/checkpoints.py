#checkpoints.py


# Checkpoint handling, in three independent stages:
# 1. Position generation - pure geometry, no network calls.
# 2. Name resolution - the network call, done lazily (core/facade.py
#    calls this well after a trip already exists). Description
#    resolution is a separate network call, see description_generator.py.
# 3. Reveal radius - the randomized, per-trip proximity distance.

import random
from math import floor

from travel_logic.dataclasses.checkpoints import Checkpoint, CheckpointProgress
from travel_logic.progress_calculator import locate_on_route

CHECKPOINT_DENSITY_K = 1.0  # k: scales overall density
CHECKPOINT_GROWTH_ALPHA = 0.55  # alpha: sublinear growth with route length
CHECKPOINT_MIN_COUNT = 1  # N_min: every real route gets at least this many

CHECKPOINT_REVEAL_RADIUS_MIN_M = 50.0
CHECKPOINT_REVEAL_RADIUS_MAX_M = 100.0


def _checkpoint_formula(total_distance_m):
    """N = max(N_min, floor(k * L^alpha)), L = route length in km."""
    if total_distance_m <= 0:
        return 0
    length_km = total_distance_m / 1000
    return max(CHECKPOINT_MIN_COUNT, floor(CHECKPOINT_DENSITY_K * length_km ** CHECKPOINT_GROWTH_ALPHA))


def generate_checkpoint_positions(route):
    """Every checkpoint's position for the whole route, name/description
    left blank - callers persist this list exactly once."""
    sample_count = _checkpoint_formula(route.total_distance)

    positions = []
    for i in range(1, sample_count + 1):
        target_distance_m = route.total_distance * i / (sample_count + 1)
        coords = locate_on_route(route, target_distance_m).coords
        positions.append(Checkpoint(
            name="",
            coordinates=coords,
            checkpoint_number=i,
            distance_from_start_m=target_distance_m,
            distance_to_destination_m=round(route.total_distance - target_distance_m, 1),
        ))
    return positions


def resolve_checkpoint_name(coordinates, geocoder):
    """City-tier name when it's actually in one, else the broader fallback."""
    return geocoder.reverse_geocode_city(coordinates) or geocoder.reverse_geocode(coordinates)


def generate_reveal_radius_m():
    """A fresh random reveal radius for a brand new trip."""
    return random.uniform(CHECKPOINT_REVEAL_RADIUS_MIN_M, CHECKPOINT_REVEAL_RADIUS_MAX_M)


def checkpoints_viewed(checkpoints, distance_walked_m):
    """Checkpoints the user has already walked past."""
    viewed = []
    for checkpoint in checkpoints:
        if checkpoint.distance_from_start_m <= distance_walked_m:
            viewed.append(checkpoint)
    return viewed


def checkpoints_not_seen(checkpoints, distance_walked_m):
    """Checkpoints still ahead of the user."""
    not_seen = []
    for checkpoint in checkpoints:
        if checkpoint.distance_from_start_m > distance_walked_m:
            not_seen.append(checkpoint)
    return not_seen


def checkpoint_progress(checkpoints, distance_walked_m):
    """Which checkpoint the user is at/past, and how far to the next one.
    checkpoints must be in route order."""
    current_checkpoint_number = 0
    distance_to_next_checkpoint_m = None

    for checkpoint in checkpoints:
        if checkpoint.distance_from_start_m <= distance_walked_m:
            current_checkpoint_number = checkpoint.checkpoint_number
        else:
            distance_to_next_checkpoint_m = checkpoint.distance_from_start_m - distance_walked_m
            break

    return CheckpointProgress(
        current_checkpoint_number=current_checkpoint_number,
        distance_to_next_checkpoint_m=distance_to_next_checkpoint_m,
    )
