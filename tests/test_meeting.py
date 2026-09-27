from unittest.mock import AsyncMock

import pytest

from app.exceptions import (
    ProviderQuotaExceededError,
    RouteNotFoundError,
    RoutingUnavailableError,
)
from app.models import (
    Coordinates,
    MeetingRequest,
    Place,
    RouteProvider,
    RoutingMode,
)
from app.services.geocoding import DgisGeocoder
from app.services.meeting import (
    MeetingPointService,
    generate_candidates,
)
from app.services.routing import Router
from app.services.stations import StationSearchService


def build_service(
    geocoder: AsyncMock,
    station_search: AsyncMock,
    router: AsyncMock,
    candidate_count: int = 7,
) -> MeetingPointService:
    return MeetingPointService(
        geocoder=geocoder,
        station_search=station_search,
        router=router,
        default_candidate_count=candidate_count,
        transit_request_delay_seconds=0,
    )


@pytest.mark.asyncio
async def test_checks_candidates_after_third_position(
) -> None:
    origin_a = Place(
        name="РќР°С‡Р°Р»Рѕ A",
        latitude=55.85,
        longitude=37.35,
    )
    origin_b = Place(
        name="РќР°С‡Р°Р»Рѕ B",
        latitude=55.58,
        longitude=38.24,
    )
    stations = [
        Place(
            name=f"РЎС‚Р°РЅС†РёСЏ {index}",
            latitude=55.70,
            longitude=37.50 + index / 100,
        )
        for index in range(1, 5)
    ]
    geocoder = AsyncMock(spec=DgisGeocoder)
    geocoder.search.side_effect = [
        origin_a,
        origin_b,
    ]
    station_search = AsyncMock(
        spec=StationSearchService
    )
    station_search.find_candidates.return_value = (
        stations
    )
    router = AsyncMock(spec=Router)
    durations = {
        ("РќР°С‡Р°Р»Рѕ A", "РЎС‚Р°РЅС†РёСЏ 1"): 1200,
        ("РќР°С‡Р°Р»Рѕ B", "РЎС‚Р°РЅС†РёСЏ 1"): 3000,
        ("РќР°С‡Р°Р»Рѕ A", "РЎС‚Р°РЅС†РёСЏ 2"): 1800,
        ("РќР°С‡Р°Р»Рѕ B", "РЎС‚Р°РЅС†РёСЏ 2"): 2700,
        ("РќР°С‡Р°Р»Рѕ A", "РЎС‚Р°РЅС†РёСЏ 3"): 2400,
        ("РќР°С‡Р°Р»Рѕ B", "РЎС‚Р°РЅС†РёСЏ 3"): 3000,
        ("РќР°С‡Р°Р»Рѕ A", "РЎС‚Р°РЅС†РёСЏ 4"): 2700,
        ("РќР°С‡Р°Р»Рѕ B", "РЎС‚Р°РЅС†РёСЏ 4"): 2760,
    }

    async def duration_seconds(
        origin: Place,
        destination: Place,
        mode: RoutingMode,
    ) -> int:
        assert mode == RoutingMode.TRANSIT
        return durations[
            origin.name,
            destination.name,
        ]

    router.duration_seconds.side_effect = (
        duration_seconds
    )
    service = build_service(
        geocoder,
        station_search,
        router,
        candidate_count=4,
    )

    result = await service.find(
        MeetingRequest(
            participant_a="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° A",
            participant_b="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° B",
            candidate_count=4,
        )
    )

    assert (
        result.best_meeting_point.place.name
        == "РЎС‚Р°РЅС†РёСЏ 4"
    )
    assert (
        result.best_meeting_point.difference_minutes
        == 1
    )
    assert result.provider == RouteProvider.DGIS
    assert len(result.alternatives) == 1
    assert router.duration_seconds.await_count == 8


@pytest.mark.asyncio
async def test_uses_estimate_when_quota_is_exhausted(
) -> None:
    origin_a = Place(
        name="РќР°С‡Р°Р»Рѕ A",
        latitude=55.85,
        longitude=37.35,
    )
    origin_b = Place(
        name="РќР°С‡Р°Р»Рѕ B",
        latitude=55.58,
        longitude=38.24,
    )
    stations = [
        Place(
            name="РЎС‚Р°РЅС†РёСЏ 1",
            latitude=55.75,
            longitude=37.65,
        ),
        Place(
            name="РЎС‚Р°РЅС†РёСЏ 2",
            latitude=55.70,
            longitude=37.80,
        ),
        Place(
            name="РЎС‚Р°РЅС†РёСЏ 3",
            latitude=55.65,
            longitude=37.95,
        ),
    ]
    geocoder = AsyncMock(spec=DgisGeocoder)
    geocoder.search.side_effect = [
        origin_a,
        origin_b,
    ]
    station_search = AsyncMock(
        spec=StationSearchService
    )
    station_search.find_candidates.return_value = (
        stations
    )
    router = AsyncMock(spec=Router)
    router.duration_seconds.side_effect = (
        ProviderQuotaExceededError(
            "Р›РёРјРёС‚ РёСЃС‡РµСЂРїР°РЅ"
        )
    )
    service = build_service(
        geocoder,
        station_search,
        router,
    )

    result = await service.find(
        MeetingRequest(
            participant_a="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° A",
            participant_b="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° B",
        )
    )

    assert (
        result.provider
        == RouteProvider.ESTIMATED
    )
    assert (
        result.best_meeting_point
        .difference_minutes
        >= 0
    )
    assert router.duration_seconds.await_count == 1


@pytest.mark.asyncio
async def test_finds_driving_meeting_point(
) -> None:
    origin_a = Place(
        name="РќР°С‡Р°Р»Рѕ A",
        latitude=55.70,
        longitude=37.50,
    )
    origin_b = Place(
        name="РќР°С‡Р°Р»Рѕ B",
        latitude=55.80,
        longitude=37.80,
    )
    candidates = [
        Place(
            name="РўРѕС‡РєР° 1",
            latitude=55.73,
            longitude=37.59,
        ),
        Place(
            name="РўРѕС‡РєР° 2",
            latitude=55.75,
            longitude=37.65,
        ),
        Place(
            name="РўРѕС‡РєР° 3",
            latitude=55.77,
            longitude=37.71,
        ),
    ]
    geocoder = AsyncMock(spec=DgisGeocoder)
    geocoder.search.side_effect = [
        origin_a,
        origin_b,
    ]
    geocoder.reverse_many.return_value = candidates
    station_search = AsyncMock(
        spec=StationSearchService
    )
    router = AsyncMock(spec=Router)
    durations = {
        ("РќР°С‡Р°Р»Рѕ A", "РўРѕС‡РєР° 1"): 600,
        ("РќР°С‡Р°Р»Рѕ B", "РўРѕС‡РєР° 1"): 1200,
        ("РќР°С‡Р°Р»Рѕ A", "РўРѕС‡РєР° 2"): 900,
        ("РќР°С‡Р°Р»Рѕ B", "РўРѕС‡РєР° 2"): 960,
        ("РќР°С‡Р°Р»Рѕ A", "РўРѕС‡РєР° 3"): 1200,
        ("РќР°С‡Р°Р»Рѕ B", "РўРѕС‡РєР° 3"): 600,
    }

    async def duration_seconds(
        origin: Place,
        destination: Place,
        mode: RoutingMode,
    ) -> int:
        assert mode == RoutingMode.DRIVING
        return durations[
            origin.name,
            destination.name,
        ]

    router.duration_seconds.side_effect = (
        duration_seconds
    )
    service = build_service(
        geocoder,
        station_search,
        router,
        candidate_count=3,
    )

    result = await service.find(
        MeetingRequest(
            participant_a="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° A",
            participant_b="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° B",
            mode=RoutingMode.DRIVING,
            candidate_count=3,
        )
    )

    assert (
        result.best_meeting_point.place.name
        == "РўРѕС‡РєР° 2"
    )
    assert (
        result.best_meeting_point.difference_minutes
        == 1
    )
    assert (
        result.provider
        == RouteProvider.OSRM_DGIS
    )
    station_search.find_candidates.assert_not_awaited()


@pytest.mark.asyncio
async def test_raises_when_no_route_is_available(
) -> None:
    origin_a = Place(
        name="РќР°С‡Р°Р»Рѕ A",
        latitude=55.70,
        longitude=37.50,
    )
    origin_b = Place(
        name="РќР°С‡Р°Р»Рѕ B",
        latitude=55.80,
        longitude=37.80,
    )
    stations = [
        Place(
            name=f"РЎС‚Р°РЅС†РёСЏ {index}",
            latitude=55.70 + index / 100,
            longitude=37.60,
        )
        for index in range(1, 4)
    ]
    geocoder = AsyncMock(spec=DgisGeocoder)
    geocoder.search.side_effect = [
        origin_a,
        origin_b,
    ]
    station_search = AsyncMock(
        spec=StationSearchService
    )
    station_search.find_candidates.return_value = (
        stations
    )
    router = AsyncMock(spec=Router)
    router.duration_seconds.side_effect = (
        RouteNotFoundError("РњР°СЂС€СЂСѓС‚ РЅРµ РЅР°Р№РґРµРЅ")
    )
    service = build_service(
        geocoder,
        station_search,
        router,
    )

    with pytest.raises(RoutingUnavailableError):
        await service.find(
            MeetingRequest(
                participant_a="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° A",
                participant_b="РђРґСЂРµСЃ СѓС‡Р°СЃС‚РЅРёРєР° B",
            )
        )


def test_generate_candidates() -> None:
    origin_a = Coordinates(
        latitude=55.70,
        longitude=37.50,
    )
    origin_b = Coordinates(
        latitude=55.80,
        longitude=37.80,
    )

    candidates = generate_candidates(
        origin_a,
        origin_b,
        7,
    )

    assert len(candidates) == 7
    assert all(
        55.70 < point.latitude < 55.80
        for point in candidates
    )


def test_generate_candidates_rejects_small_count(
) -> None:
    with pytest.raises(ValueError):
        generate_candidates(
            Coordinates(
                latitude=55.70,
                longitude=37.50,
            ),
            Coordinates(
                latitude=55.80,
                longitude=37.80,
            ),
            2,
        )
