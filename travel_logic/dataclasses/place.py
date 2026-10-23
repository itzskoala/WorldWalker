#place.py

from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    """One geocoded search candidate - value/primary/secondary are
    already split into a bold/muted two-line row for the frontend."""
    value: str
    primary: str
    secondary: str
    lat: float
    lng: float
