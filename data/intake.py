#intake.py
# Validated shape of the website's "where from? / where to?" form ->
# hands straight to the facade to start a journey.

import uuid
from typing import Optional, Literal
from pydantic import BaseModel
from core.facade import travel_facade


class IntakeRequest(BaseModel):
    from_place: str
    to_place: str
    gender: Optional[Literal["male", "female"]] = None  # stride fallback if no real stride is on file
    stride_length_m: Optional[float] = None  # real per-user value, e.g. from Fitbit, if we have one
    round_trip: bool = False  # UI's trip-type toggle - see TravelFacade.start_journey's docstring
    user_id: uuid.UUID  # the logged-in WorldWalker user - see accounts.dependencies.get_current_user


def start_journey_from_intake(intake: IntakeRequest) -> dict:
    return travel_facade.start_journey(
        user_id=intake.user_id,
        from_place=intake.from_place,
        to_place=intake.to_place,
        gender=intake.gender,
        stride_length_m=intake.stride_length_m,
        round_trip=intake.round_trip,
    )
