from unittest.mock import AsyncMock

import pytest

from app.models import (
    MeetingRequest,
    Place,
    RoutingMode,
)
from app.services.meeting import MeetingPointService


@pytest.mark.asyncio
async def test_finds_station_with_smallest_time_difference(
) -> None:
    origin_a = Place(
        name="Метро Пятницкое шоссе",
        latitude=55.8563,
        longitude=37.3544,
    )

    origin_b = Place(
        name="МЦД Ипподром",
        latitude=55.5814,
        longitude=38.2467,
    )

    stations = [
        Place(
            name="Станция 1",
            latitude=55.75,
            longitude=37.60,
        ),
        Place(
            name="Станция 2",
            latitude=55.72,
            longitude=37.75,
        ),
        Place(
            name="Станция 3",
            latitude=55.70,
            longitude=37.85,
        ),
    ]

    geocoder = AsyncMock()

    geocoder.search.side_effect = [
        origin_a,
        origin_b,
    ]

    station_search = AsyncMock()

    station_search.find_candidates.return_value = (
        stations
    )

    router = AsyncMock()

    durations = {
        ("Метро Пятницкое шоссе", "Станция 1"): 2400,
        ("МЦД Ипподром", "Станция 1"): 3600,
        ("Метро Пятницкое шоссе", "Станция 2"): 3000,
        ("МЦД Ипподром", "Станция 2"): 3060,
        ("Метро Пятницкое шоссе", "Станция 3"): 3600,
        ("МЦД Ипподром", "Станция 3"): 2400,
    }

    async def duration_seconds(
        origin: Place,
        destination: Place,
        mode: RoutingMode,
    ) -> int:
        return durations[
            (
                origin.name,
                destination.name,
            )
        ]

    router.duration_seconds.side_effect = (
        duration_seconds
    )

    service = MeetingPointService(
        geocoder=geocoder,
        station_search=station_search,
        router=router,
        default_candidate_count=7,
    )

    result = await service.find(
        MeetingRequest(
            participant_a=(
                "метро Пятницкое шоссе, Москва"
            ),
            participant_b=(
                "МЦД Ипподром, Московская область"
            ),
        )
    )

    assert (
        result.best_meeting_point.place.name
        == "Станция 2"
    )

    assert (
        result
        .best_meeting_point
        .difference_minutes
        == 1
    )

    assert result.mode == RoutingMode.TRANSIT
    assert result.provider == "2GIS"
    assert len(result.alternatives) == 2