#checkpoints.py
# "Important" landmarks along a route = real city-tier places (Nominatim's
# `address.city`, not town/village/hamlet), found by sampling the route
# and reverse-geocoding each sample, then collapsing consecutive samples
# that land in the same city into one landmark.
#
# Sample count scales with route length, not a fixed number - a 10-minute
# walk has no room for in-between landmarks (0 samples, 0 API calls); a
# cross-country route gets one sample roughly every SPACING_MILES, capped
# so a very long route doesn't cost unbounded latency.
#
# Nominatim's usage policy caps reverse lookups at ~1/sec, so this is a
# real one-time cost at journey-start (sample_count seconds) - not
# something to run per-sync.

import time
from dataclasses import dataclass
from travel_logic.coordinates import Coordinates
from travel_logic.geocoder import Geocoder
from travel_logic.route_service import Route

SPACING_MILES = 20  # aim for roughly one sample every this many miles
MAX_SAMPLES = 60  # latency cap (~1 min of reverse-geocode calls) even for a coast-to-coast route
NOMINATIM_RATE_LIMIT_SECONDS = 1.0


@dataclass(frozen=True)
class Checkpoint:
    name: str
    coords: Coordinates  # for the map UI to actually place a pin
    miles_from_start: float
    percent: float


def pick_checkpoints(route: Route, geocoder: Geocoder) -> list:
    sample_count = min(MAX_SAMPLES, int(route.total_miles // SPACING_MILES))
    if sample_count < 1:
        return []  # too short a route to have any landmarks in between start/destination

    checkpoints = []
    last_city = None
    for i in range(1, sample_count + 1):
        target_miles = route.total_miles * i / (sample_count + 1)
        point = min(route.points, key=lambda p: abs(p.miles_from_start - target_miles))

        city = geocoder.reverse_geocode_city(point.coords)
        time.sleep(NOMINATIM_RATE_LIMIT_SECONDS)

        if city and city != last_city:
            checkpoints.append(
                Checkpoint(
                    name=city,
                    coords=point.coords,
                    miles_from_start=point.miles_from_start,
                    percent=round(point.miles_from_start / route.total_miles * 100, 1),
                )
            )
        if city:
            last_city = city

    return checkpoints
