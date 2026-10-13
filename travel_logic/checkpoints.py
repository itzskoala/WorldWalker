#checkpoints.py
# Checkpoint handling is split into three independent stages now, each
# usable on its own:
#
# 1. Position generation (generate_checkpoint_positions) - pure geometry,
#    zero network calls. Every checkpoint's coordinates for the whole
#    route, computed and returned immediately from the route alone.
#    Sample count scales with route length on a single sublinear power
#    curve - N = max(N_min, floor(k * L^alpha)), L in km - not a fixed
#    spacing and not a set of distance brackets. alpha < 1 means density
#    tapers off as a route grows, the same way a map doesn't label 100x
#    more towns on a cross-country view just because it covers 100x the
#    distance; N_min guarantees even a short route gets at least one.
#    There's no upper cap on N any more - see core/facade.py's checkpoint-
#    metadata pipeline for why a long route's larger N no longer means N
#    blocking Nominatim round trips before the trip can even start.
#
#    Each position is a real point along the route's geometry - linear
#    interpolation between the two route points bracketing its target
#    cumulative distance (same approach as
#    progress_calculator.locate_on_route) - not snapped to whichever
#    existing route vertex happens to be closest. Count and positions are
#    fixed the moment this returns; nothing regenerates them later as the
#    walker moves.
#
# 2. Name/description resolution (resolve_checkpoint_name,
#    generate_checkpoint_description) - the network calls, kept
#    deliberately separate from stage 1 so a long route's checkpoint
#    *positions* are never gated on Nominatim/AI latency. core/facade.py
#    calls these lazily, well after a trip already exists, for whichever
#    checkpoints are coming up next - see its checkpoint-metadata
#    pipeline.
#
#    One behavior change from the old combined pipeline worth knowing:
#    that pipeline discovered samples and resolved their names in the
#    same loop, so it could collapse consecutive samples landing in the
#    same city into a single checkpoint, and silently drop a sample that
#    wasn't in a recognized city at all - both of which shrank the final
#    checkpoint count below N. Positions are now fixed up front, before
#    any name is known, so neither is possible any more: every one of
#    the N positions becomes a real checkpoint, and resolve_checkpoint_name()
#    falls back to the broader town/county/state label (never silently
#    drops a position) instead of leaving it out.
#
# 3. Reveal radius (generate_reveal_radius_m) - the randomized, per-trip
#    proximity distance a checkpoint must be approached within before it
#    shows up on the map at all. Generated once, at trip creation, and
#    persisted on the trip (ActiveTrip.checkpoint_reveal_radius_m) - see
#    core/facade.py's start_journey().

import random
from dataclasses import dataclass
from math import floor
from typing import List, Optional
from travel_logic.coordinates import Coordinates
from travel_logic.description_generator import DescriptionGenerator
from travel_logic.geocoder import Geocoder
from travel_logic.progress_calculator import locate_on_route
from travel_logic.route_service import Route

CHECKPOINT_DENSITY_K = 1.0  # k: scales overall density without touching the curve's shape
CHECKPOINT_GROWTH_ALPHA = 0.55  # alpha: sublinear (<1) growth rate with route length
CHECKPOINT_MIN_COUNT = 1  # N_min: every real route gets at least this many checkpoints

CHECKPOINT_REVEAL_RADIUS_MIN_M = 50.0
CHECKPOINT_REVEAL_RADIUS_MAX_M = 100.0


@dataclass(frozen=True)
class Checkpoint:
    name: str  # "" until resolve_checkpoint_name() has run - see generate_checkpoint_positions()
    coordinates: Coordinates  # for the map UI to actually place a pin
    checkpoint_number: int  # 1-indexed position among checkpoints, in route order
    distance_from_start_m: float
    distance_to_destination_m: float
    description: str = ""  # filled in later by generate_checkpoint_description()


def _sample_count(total_distance_m: float) -> int:
    """N = max(N_min, floor(k * L^alpha)), L = route length in km. One
    smooth power curve - no distance brackets or special-cased ranges. A
    zero-length route is the sole edge case handled outside the formula:
    there's no "in between start and destination" to place a checkpoint
    on, so it gets none regardless of N_min."""
    if total_distance_m <= 0:
        return 0
    length_km = total_distance_m / 1000
    return max(CHECKPOINT_MIN_COUNT, floor(CHECKPOINT_DENSITY_K * length_km ** CHECKPOINT_GROWTH_ALPHA))


def generate_checkpoint_positions(route: Route) -> List[Checkpoint]:
    """Every checkpoint's position for the whole route, computed and
    returned immediately - see this module's docstring, stage 1. name/
    description start blank; callers persist this list exactly once
    (database/trips.py's create_trip()) and never regenerate it."""
    sample_count = _sample_count(route.total_distance)

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


def resolve_checkpoint_name(coordinates: Coordinates, geocoder: Geocoder) -> str:
    """The real-world name for one checkpoint's position - city-tier
    (Nominatim's address.city) when it's actually in one, else the
    broader town/county/state/"Unknown" fallback Geocoder.reverse_geocode
    already provides. See this module's docstring on why every position
    needs a real label now, not just the ones that happen to land in a
    recognized city."""
    return geocoder.reverse_geocode_city(coordinates) or geocoder.reverse_geocode(coordinates)


def generate_checkpoint_description(name: str, coordinates: Coordinates, describer: DescriptionGenerator) -> str:
    """One short, fun, tourist-facing line about this checkpoint -
    generated only once its real name is known (see
    resolve_checkpoint_name()). Best-effort: a model/network failure
    degrades to a plain fallback line rather than leaving metadata
    resolution stuck."""
    prompt = (
        f"In one short, fun phrase (10 words or fewer), tell a tourist something "
        f"interesting about {name}, located at {coordinates.lat}, {coordinates.lng}. "
    )
    try:
        return describer.generate(prompt)
    except Exception:
        return f"A stop along the way in {name}."


def generate_reveal_radius_m() -> float:
    """A fresh random reveal radius for a brand new trip, within the
    product's chosen 50-100m range - generated exactly once per trip
    (core/facade.py's start_journey()) and persisted on the trip itself
    (ActiveTrip.checkpoint_reveal_radius_m), never re-rolled on a later
    refresh/reconnect."""
    return random.uniform(CHECKPOINT_REVEAL_RADIUS_MIN_M, CHECKPOINT_REVEAL_RADIUS_MAX_M)


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
    checkpoints must be in route order. Once the user is past the last
    checkpoint, there is no "next" one left - distance_to_next_checkpoint_m
    is None, not a stand-in value; the real distance to the destination
    comes from progress_calculator.locate_on_route separately."""
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
