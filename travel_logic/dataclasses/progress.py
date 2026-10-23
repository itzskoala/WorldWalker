#progress.py

from dataclasses import dataclass
from travel_logic.dataclasses.coordinates import Coordinates


@dataclass(frozen=True)
class Progress:
    coords: Coordinates
    distance_walked_m: float
    distance_remaining_m: float
    percent_complete: float
