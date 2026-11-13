# intake.py

import uuid
from typing import Optional, Literal
from pydantic import BaseModel
from backend.facade import travel_facade
from backend.travel_logic.dataclasses.coordinates import Coordinates


class IntakeRequest(BaseModel):
    from_place: str
    to_place: str
    gender: Optional[Literal["male", "female"]] = None
    stride_length_m: Optional[float] = None
    user_id: uuid.UUID

    from_lat: Optional[float] = None
    from_lng: Optional[float] = None
    to_lat: Optional[float] = None
    to_lng: Optional[float] = None


def start_journey_from_intake(intake: IntakeRequest) -> dict:
    from_coords = Coordinates(lat=intake.from_lat, lng=intake.from_lng) if intake.from_lat is not None and intake.from_lng is not None else None
    to_coords = Coordinates(lat=intake.to_lat, lng=intake.to_lng) if intake.to_lat is not None and intake.to_lng is not None else None
    return travel_facade.start_journey(
        user_id=intake.user_id,
        from_place=intake.from_place,
        to_place=intake.to_place,
        gender=intake.gender,
        stride_length_m=intake.stride_length_m,
        from_coords=from_coords,
        to_coords=to_coords,
    )
