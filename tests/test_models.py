import pytest
from pydantic import ValidationError

from app.models import (
    CandidateResult,
    MeetingRequest,
    Place,
    RoutingMode,
)


def test_meeting_request_cleans_addresses() -> None:
    request = MeetingRequest(
        participant_a="  Москва,   Арбат, 10  ",
        participant_b=" Москва, Тверская, 15 ",
    )

    assert request.participant_a == (
        "Москва, Арбат, 10"
    )
    assert request.participant_b == (
        "Москва, Тверская, 15"
    )
    assert request.mode == RoutingMode.TRANSIT


@pytest.mark.parametrize(
    ("participant_a", "participant_b"),
    [
        ("  ", "Москва, Арбат, 10"),
        ("Москва", "  Москва  "),
        ("A", "Москва, Арбат, 10"),
    ],
)
def test_meeting_request_rejects_invalid_addresses(
    participant_a: str,
    participant_b: str,
) -> None:
    with pytest.raises(ValidationError):
        MeetingRequest(
            participant_a=participant_a,
            participant_b=participant_b,
        )


@pytest.mark.parametrize(
    "candidate_count",
    [2, 12],
)
def test_meeting_request_rejects_candidate_count(
    candidate_count: int,
) -> None:
    with pytest.raises(ValidationError):
        MeetingRequest(
            participant_a="Москва, Арбат, 10",
            participant_b="Москва, Тверская, 15",
            candidate_count=candidate_count,
        )


def test_meeting_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MeetingRequest.model_validate(
            {
                "participant_a": "Москва, Арбат, 10",
                "participant_b": (
                    "Москва, Тверская, 15"
                ),
                "unknown": "value",
            }
        )


def test_place_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        Place(
            name="   ",
            latitude=55.75,
            longitude=37.61,
        )


def test_candidate_result_validates_calculations(
) -> None:
    place = Place(
        name="Метро Арбатская",
        latitude=55.752,
        longitude=37.604,
    )

    with pytest.raises(ValidationError):
        CandidateResult(
            place=place,
            time_a_minutes=10,
            time_b_minutes=20,
            difference_minutes=5,
            total_minutes=30,
        )

    with pytest.raises(ValidationError):
        CandidateResult(
            place=place,
            time_a_minutes=10,
            time_b_minutes=20,
            difference_minutes=10,
            total_minutes=25,
        )