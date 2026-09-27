from unittest.mock import AsyncMock

from app.models import CandidateResult, Place
from app.services.meeting import MeetingPointService


def test_transit_fairness_limit() -> None:
    service = MeetingPointService(
        geocoder=AsyncMock(),
        station_search=AsyncMock(),
        router=AsyncMock(),
        default_candidate_count=7,
        transit_request_delay_seconds=0,
    )

    place = Place(
        name="Тестовая станция",
        latitude=55.75,
        longitude=37.62,
    )
    fair_result = CandidateResult(
        place=place,
        time_a_minutes=47,
        time_b_minutes=47,
        difference_minutes=0,
        total_minutes=94,
    )
    unfair_result = CandidateResult(
        place=place,
        time_a_minutes=127,
        time_b_minutes=179,
        difference_minutes=52,
        total_minutes=306,
    )

    assert service._is_transit_result_fair(
        fair_result
    )
    assert not service._is_transit_result_fair(
        unfair_result
    )