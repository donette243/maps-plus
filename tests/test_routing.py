import httpx
import pytest
import respx

from app.config import Settings
from app.exceptions import (
    ConfigurationError,
    InvalidProviderResponseError,
    ProviderQuotaExceededError,
    ProviderUnavailableError,
    RouteNotFoundError,
)
from app.models import Coordinates, RoutingMode
from app.services.routing import Router

ORIGIN = Coordinates(
    latitude=55.8563,
    longitude=37.3544,
)
DESTINATION = Coordinates(
    latitude=55.7512,
    longitude=37.6184,
)


def build_settings() -> Settings:
    return Settings(
        dgis_api_key="test-key",
        dgis_routing_url=(
            "https://routing.api.2gis.test"
        ),
        osrm_url="https://osrm.test",
    )


@pytest.mark.asyncio
@respx.mock
async def test_dgis_chooses_fastest_route() -> None:
    route = respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=[
                {"total_duration": 2400},
                {"total_duration": 1800},
                {"total_duration": 2100},
            ],
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )
        seconds = await router.duration_seconds(
            ORIGIN,
            DESTINATION,
            RoutingMode.TRANSIT,
        )

    assert route.called
    assert seconds == 1800


@pytest.mark.asyncio
@respx.mock
async def test_osrm_driving_duration() -> None:
    route = respx.get(
        url__startswith=(
            "https://osrm.test/route/v1/driving/"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "duration": 900.4,
                    }
                ],
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )
        seconds = await router.duration_seconds(
            ORIGIN,
            DESTINATION,
            RoutingMode.DRIVING,
        )

    assert route.called
    assert seconds == 900


@pytest.mark.asyncio
@respx.mock
async def test_duration_is_cached() -> None:
    route = respx.get(
        url__startswith=(
            "https://osrm.test/route/v1/driving/"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "duration": 600,
                    }
                ],
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        first = await router.duration_seconds(
            ORIGIN,
            DESTINATION,
            RoutingMode.DRIVING,
        )
        second = await router.duration_seconds(
            ORIGIN,
            DESTINATION,
            RoutingMode.DRIVING,
        )

    assert first == second == 600
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_dgis_quota_error_hides_key() -> None:
    respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=429,
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(
            ProviderQuotaExceededError
        ) as error:
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.TRANSIT,
            )

    assert "test-key" not in str(error.value)


@pytest.mark.asyncio
@respx.mock
async def test_dgis_rejects_invalid_key() -> None:
    respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=403,
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(ConfigurationError):
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.TRANSIT,
            )


@pytest.mark.asyncio
@respx.mock
async def test_dgis_rejects_invalid_json() -> None:
    respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            text="not-json",
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(
            InvalidProviderResponseError
        ):
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.TRANSIT,
            )


@pytest.mark.asyncio
@respx.mock
async def test_dgis_rejects_empty_routes() -> None:
    respx.post(
        url__startswith=(
            "https://routing.api.2gis.test/"
            "public_transport/2.0"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=[],
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(RouteNotFoundError):
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.TRANSIT,
            )


@pytest.mark.asyncio
@respx.mock
async def test_osrm_rejects_invalid_duration(
) -> None:
    respx.get(
        url__startswith=(
            "https://osrm.test/route/v1/driving/"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "duration": -10,
                    }
                ],
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(
            InvalidProviderResponseError
        ):
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.DRIVING,
            )


@pytest.mark.asyncio
@respx.mock
async def test_provider_server_error() -> None:
    respx.get(
        url__startswith=(
            "https://osrm.test/route/v1/driving/"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=500,
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        router = Router(
            client,
            build_settings(),
        )

        with pytest.raises(
            ProviderUnavailableError
        ):
            await router.duration_seconds(
                ORIGIN,
                DESTINATION,
                RoutingMode.DRIVING,
            )