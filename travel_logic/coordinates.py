#coordinates.py
from dataclasses import dataclass


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lng: float
