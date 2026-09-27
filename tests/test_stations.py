from unittest.mock import AsyncMock

import pytest

from app.exceptions import PlaceNotFoundError
from app.models import Coordinates, Place
from app.services.metro import MetroCatalogService
from app.services.stations import StationSearchService


@pytest.mark.asyncio
async def test_respects_candidate_count() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.get_stations.return_value = [
        Place(
            name=f"Метро Станция {index}",
            latitude=55.75,
            longitude=37.40 + index / 100,
        )
        for index in range(20)
    ]
    service = StationSearchService(catalog)

    candidates = await service.find_candidates(
        origin_a=Coordinates(
            latitude=55.75,
            longitude=37.30,
        ),
        origin_b=Coordinates(
            latitude=55.75,
            longitude=37.80,
        ),
        count=5,
    )

    assert len(candidates) == 5
    catalog.get_stations.assert_awaited_once()


@pytest.mark.asyncio
async def test_prefers_balanced_nearby_station(
) -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.get_stations.return_value = [
        Place(
            name="Метро Западная",
            latitude=55.75,
            longitude=37.20,
        ),
        Place(
            name="Метро Центральная",
            latitude=55.75,
            longitude=37.50,
        ),
        Place(
            name="Метро Восточная",
            latitude=55.75,
            longitude=37.80,
        ),
        Place(
            name="Метро Дальняя",
            latitude=56.20,
            longitude=37.50,
        ),
    ]
    service = StationSearchService(catalog)

    candidates = await service.find_candidates(
        origin_a=Coordinates(
            latitude=55.75,
            longitude=37.00,
        ),
        origin_b=Coordinates(
            latitude=55.75,
            longitude=38.00,
        ),
        count=3,
    )

    assert (
        candidates[0].name
        == "Метро Центральная"
    )
    assert "Метро Дальняя" not in {
        candidate.name
        for candidate in candidates
    }


@pytest.mark.asyncio
async def test_rejects_empty_catalog() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.get_stations.return_value = []
    service = StationSearchService(catalog)

    with pytest.raises(PlaceNotFoundError):
        await service.find_candidates(
            origin_a=Coordinates(
                latitude=55.75,
                longitude=37.30,
            ),
            origin_b=Coordinates(
                latitude=55.75,
                longitude=37.80,
            ),
            count=3,
        )


@pytest.mark.asyncio
async def test_rejects_invalid_count() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    service = StationSearchService(catalog)

    with pytest.raises(ValueError):
        await service.find_candidates(
            origin_a=Coordinates(
                latitude=55.75,
                longitude=37.30,
            ),
            origin_b=Coordinates(
                latitude=55.75,
                longitude=37.80,
            ),
            count=0,
        )

    catalog.get_stations.assert_not_awaited()