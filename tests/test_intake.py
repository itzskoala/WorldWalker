# tests/test_intake.py
# IntakeRequest validation + start_journey_from_intake's passthrough to
# TravelFacade.start_journey - no network calls, start_journey itself is
# monkeypatched.

from data.intake import IntakeRequest, start_journey_from_intake
from data import intake as intake_module


def test_round_trip_defaults_to_false():
    assert IntakeRequest(from_place="Miami", to_place="Chicago").round_trip is False


def test_start_journey_from_intake_forwards_round_trip(monkeypatch):
    calls = []
    monkeypatch.setattr(
        intake_module.travel_facade, "start_journey",
        lambda **kwargs: calls.append(kwargs) or {"ok": True},
    )
    intake = IntakeRequest(from_place="Miami", to_place="Chicago", round_trip=True)
    result = start_journey_from_intake(intake)

    assert result == {"ok": True}
    assert calls == [{
        "user_id": intake.user_id,
        "from_place": "Miami",
        "to_place": "Chicago",
        "gender": None,
        "stride_length_m": None,
        "round_trip": True,
    }]
