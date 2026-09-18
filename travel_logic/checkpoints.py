#checkpoints.py
# "Important" landmarks along a route = real city-tier places (Nominatim's
# `address.city`, not town/village/hamlet), found by sampling the route
# and reverse-geocoding each sample, then collapsing consecutive samples
# that land in the same city into one landmark.
#
# Sample count scales with route length on a square-root curve, not a
# fixed spacing - checkpoint density should taper off as a route grows,
# the same way a map doesn't label 100x more towns on a cross-country
# view just because it covers 100x the distance. A 10-minute walk (<1mi)
# rounds down to 0 samples/API calls; a coast-to-coast route approaches
# but doesn't blow past MAX_SAMPLES.
#
# Nominatim's usage policy caps reverse lookups at ~1/sec, so this is a
# real one-time cost at journey-start (sample_count seconds) - not
# something to run per-sync.

import time
from dataclasses import dataclass, replace
from math import sqrt
from typing import List
from travel_logic.coordinates import Coordinates
from travel_logic.description_generator import DescriptionGenerator
from travel_logic.geocoder import Geocoder
from travel_logic.route_service import Route

CHECKPOINTS_PER_SQRT_KM = 1.0  # tune density without touching the curve's shape
NOMINATIM_RATE_LIMIT_SECONDS = 1.0
MAX_LATENCY_SECONDS = 60  # journey-start is a one-time wait; keep it under a minute
MAX_SAMPLES = int(MAX_LATENCY_SECONDS / NOMINATIM_RATE_LIMIT_SECONDS)


@dataclass(frozen=True)
class Checkpoint:
    name: str
    coordinates: Coordinates  # for the map UI to actually place a pin
    checkpoint_number: int  # 1-indexed position among checkpoints, in route order
    distance_from_start_m: float
    distance_to_destination_m: float
    description: str = ""  # filled in later by generate_description()


def _sample_count(total_distance_m: float):
    return min(MAX_SAMPLES, int(CHECKPOINTS_PER_SQRT_KM * sqrt(total_distance_m / 1000)))


def generate_checkpoints(route: Route, geocoder: Geocoder, describer: DescriptionGenerator):
    sample_count = _sample_count(route.total_distance)
    if sample_count < 1:
        return []  # too short a route to have any landmarks in between start/destination

    checkpoints = []
    last_city = None
    for i in range(1, sample_count + 1):
        target_distance_m = route.total_distance * i / (sample_count + 1)
        point = min(route.points, key=lambda p: abs(p.distance_from_start - target_distance_m))

        city = geocoder.reverse_geocode_city(point.coords)
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)

        if city and city != last_city:
            checkpoint = Checkpoint(
                name=city,
                coordinates=point.coords,
                checkpoint_number=len(checkpoints) + 1,
                distance_from_start_m=point.distance_from_start,
                distance_to_destination_m=round(route.total_distance - point.distance_from_start, 1),
            )
            checkpoints.append(generate_description(checkpoint, describer))
        if city:
            last_city = city

    return checkpoints


def checkpoints_viewed(checkpoints: List[Checkpoint], distance_walked_m: float):
    """Checkpoints the user has already walked past."""
    viewed = []
    for c in checkpoints:
        if c.distance_from_start_m <= distance_walked_m:
            viewed.append(c)
    return viewed


def checkpoints_not_seen(checkpoints: List[Checkpoint], distance_walked_m: float):
    """Checkpoints still ahead of the user - shrinks as checkpoints_viewed grows."""
    not_seen = []
    for c in checkpoints:
        if c.distance_from_start_m > distance_walked_m:
            not_seen.append(c)
    return not_seen


@dataclass(frozen=True)
class CheckpointProgress:
    current_checkpoint_number: int  # 0 - the user hasn't reached the first checkpoint yet
    distance_to_next_checkpoint_m: float  # None - the user is past the last checkpoint


def checkpoint_progress(checkpoints: List[Checkpoint], distance_walked_m: float):
    """Which checkpoint the user is at/past, and how far to the next one.
    checkpoints must be in route order (as generate_checkpoints returns
    them). Once the user is past the last checkpoint, there is no "next"
    one left - distance_to_next_checkpoint_m is None, not a stand-in
    value; the real distance to the destination comes from
    progress_calculator.locate_on_route separately."""
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


def generate_description(checkpoint: Checkpoint, describer: DescriptionGenerator):
    """Asks the model for one short, fun, tourist-facing line about this
    checkpoint's location and returns a copy of it with `description` filled
    in. Best-effort: a model/network failure degrades to a plain fallback
    line rather than breaking journey creation over flavor text."""

    prompt = (
        f"In one short, fun phrase (10 words or fewer), tell a tourist something "
        f"interesting about {checkpoint.name}, located at "
        f"{checkpoint.coordinates.lat}, {checkpoint.coordinates.lng}. "
        )
    try:
        description = describer.generate(prompt)
    except Exception:
        description = f"A stop along the way in {checkpoint.name}."

    return replace(checkpoint, description=description)
