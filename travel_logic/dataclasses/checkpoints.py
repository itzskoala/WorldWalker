#checkpoints.py

from dataclasses import dataclass
from travel_logic.dataclasses.coordinates import Coordinates


@dataclass(frozen=True)
class Checkpoint:
    name: str  # "" until resolve_checkpoint_name() has run
    coordinates: Coordinates
    checkpoint_number: int  # 1-indexed, in route order
    distance_from_start_m: float
    distance_to_destination_m: float
    description: str = ""  # filled in later by generate_checkpoint_description()


@dataclass(frozen=True)
class CheckpointProgress:
    current_checkpoint_number: int  # 0 - not reached the first checkpoint yet
    distance_to_next_checkpoint_m: float | None  # None - past the last checkpoint
