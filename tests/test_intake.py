# tests/test_intake.py
# IntakeRequest validation + start_journey_from_intake's passthrough to
# TravelFacade.start_journey - no network calls, start_journey itself is
# monkeypatched.

import uuid

from data.intake import IntakeRequest, start_journey_from_intake
from data import intake as intake_module
from travel_logic.coordinates import Coordinates

A_USER_ID = uuid.uuid4()


def test_round_trip_defaults_to_false():
    assert IntakeRequest(from_place="Miami", to_place="Chicago", user_id=A_USER_ID).round_trip is False


def test_start_journey_from_intake_forwards_round_trip(monkeypatch):
    calls = []
    monkeypatch.setattr(
        intake_module.travel_facade, "start_journey",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    intake = IntakeRequest(from_place="Miami", to_place="Chicago", round_trip=True, user_id=A_USER_ID)
    result = start_journey_from_intake(intake)

    assert result == {"ok": True}
    assert calls == [{
        "user_id": intake.user_id,
        "from_place": "Miami",
        "to_place": "Chicago",
        "gender": None,
        "stride_length_m": None,
        "round_trip": True,
        "from_coords": None,
        "to_coords": None,
    }]


def test_start_journey_from_intake_forwards_resolved_coordinates(monkeypatch):
    # The Chile Chico fix: when the frontend's autocomplete already
    # resolved from_place/to_place to real coordinates, those are passed
    # straight through as Coordinates instead of being dropped on the
    # floor and re-geocoded from the free-text label (which can fail for
    # a label like "Chile Chico Airport (CCH), Chile Chico, CL" - see
    # TravelFacade.start_journey()'s docstring).
    calls = []
    monkeypatch.setattr(
        intake_module.travel_facade, "start_journey",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    intake = IntakeRequest(
        from_place="Chile Chico Airport (CCH), Chile Chico, CL",
        to_place="Santiago, Chile",
        user_id=A_USER_ID,
        from_lat=-46.5406,
        from_lng=-71.7233,
        to_lat=-33.4489,
        to_lng=-70.6693,
    )
    start_journey_from_intake(intake)

    assert calls[0]["from_coords"] == Coordinates(lat=-46.5406, lng=-71.7233)
    assert calls[0]["to_coords"] == Coordinates(lat=-33.4489, lng=-70.6693)


def test_start_journey_from_intake_leaves_coords_none_when_only_one_axis_is_present(monkeypatch):
    # Defensive: a malformed request with lat but no lng (or vice versa)
    # must not build a half-formed Coordinates - falls back to
    # re-geocoding the text instead.
    calls = []
    monkeypatch.setattr(
        intake_module.travel_facade, "start_journey",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    intake = IntakeRequest(from_place="Miami", to_place="Chicago", user_id=A_USER_ID, from_lat=25.0)
    start_journey_from_intake(intake)

    assert calls[0]["from_coords"] is None
