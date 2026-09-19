import httpx
import pytest
import respx

from app.config import Settings
from app.models import Coordinates, RoutingMode
from app.services.routing import Router


@pytest.mark.asyncio
@respx.mock
async def test_dgis_transit_duration() -> None:
    settings = Settings(
        dgis_api_key="test-key",
        dgis_routing_url=(
            "https://routing.api.2gis.test"
        ),
    )

    route = respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=[
                {
                    "total_duration": 1800,
                    "total_distance": 15000,
                    "movements": [],
                    "crossing_count": 1,
                    "pedestrian": False,
                    "transfer_count": 1,
                    "total_walkway_distance": (
                        "пешком 8 мин"
                    ),
                }
            ],
        )
    )

    origin = Coordinates(
        latitude=55.8563,
        longitude=37.3544,
    )

    destination = Coordinates(
        latitude=55.7512,
        longitude=37.6184,
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client=client,
            settings=settings,
        )

        seconds = await router.duration_seconds(
            origin=origin,
            destination=destination,
            mode=RoutingMode.TRANSIT,
        )

    assert route.called
    assert seconds == 1800


@pytest.mark.asyncio
@respx.mock
async def test_dgis_chooses_fastest_route() -> None:
    settings = Settings(
        dgis_api_key="test-key",
        dgis_routing_url=(
            "https://routing.api.2gis.test"
        ),
    )

    respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=[
                {
                    "total_duration": 2400,
                },
                {
                    "total_duration": 1800,
                },
                {
                    "total_duration": 2100,
                },
            ],
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client=client,
            settings=settings,
        )

        seconds = await router.duration_seconds(
            origin=Coordinates(
                latitude=55.8563,
                longitude=37.3544,
            ),
            destination=Coordinates(
                latitude=55.7512,
                longitude=37.6184,
            ),
            mode=RoutingMode.TRANSIT,
        )

    assert seconds == 1800