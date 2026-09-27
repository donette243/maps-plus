from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.config import Settings
from app.exceptions import (
    ConfigurationError,
    ProviderQuotaExceededError,
)
from app.models import Coordinates, Place
from app.services.geocoding import DgisGeocoder
from app.services.metro import MetroCatalogService


def build_settings(
    api_key: str = "test-key",
) -> Settings:
    return Settings(
        dgis_api_key=api_key,
        dgis_catalog_url=(
            "https://catalog.api.2gis.test/3.0"
        ),
    )


@pytest.mark.asyncio
@respx.mock
async def test_returns_station_from_catalog() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.find_by_query.return_value = Place(
        name="Метро Арбатская",
        latitude=55.752,
        longitude=37.604,
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )
        place = await geocoder.search(
            "метро Арбатская"
        )

    assert place.name == "Метро Арбатская"
    catalog.find_by_query.assert_awaited_once_with(
        "метро Арбатская"
    )
    assert not respx.calls.called


@pytest.mark.asyncio
@respx.mock
async def test_searches_regular_address() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.find_by_query.return_value = None
    route = respx.get(
        url__startswith=(
            "https://catalog.api.2gis.test/"
            "3.0/items"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "result": {
                    "items": [
                        {
                            "full_name": (
                                "Москва, улица Арбат, 10"
                            ),
                            "point": {
                                "lat": 55.752,
                                "lon": 37.604,
                            },
                        }
                    ]
                }
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )
        place = await geocoder.search(
            "Москва, улица Арбат, 10"
        )

    assert route.called
    assert place.name == "Москва, улица Арбат, 10"
    assert place.latitude == 55.752
    assert place.longitude == 37.604


@pytest.mark.asyncio
@respx.mock
async def test_search_skips_item_without_coordinates(
) -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.find_by_query.return_value = None
    respx.get(
        url__startswith=(
            "https://catalog.api.2gis.test/"
            "3.0/items"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "result": {
                    "items": [
                        {
                            "name": "Некорректный объект",
                        },
                        {
                            "name": "Корректный объект",
                            "point": {
                                "lat": 55.75,
                                "lon": 37.61,
                            },
                        },
                    ]
                }
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )
        place = await geocoder.search(
            "Москва, тестовый адрес"
        )

    assert place.name == "Корректный объект"


@pytest.mark.asyncio
@respx.mock
async def test_reverse_keeps_original_coordinates(
) -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    point = Coordinates(
        latitude=55.75555,
        longitude=37.65555,
    )
    respx.get(
        url__startswith=(
            "https://catalog.api.2gis.test/"
            "3.0/items/geocode"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "result": {
                    "items": [
                        {
                            "full_name": (
                                "Москва, Парковка №0301"
                            ),
                            "point": {
                                "lat": 55.70000,
                                "lon": 37.60000,
                            },
                        },
                        {
                            "full_name": (
                                "Москва, улица Примерная, 5"
                            ),
                            "point": {
                                "lat": 55.70001,
                                "lon": 37.60001,
                            },
                        },
                    ]
                }
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )
        place = await geocoder.reverse(point)

    assert (
        place.name
        == "Москва, улица Примерная, 5"
    )
    assert place.latitude == point.latitude
    assert place.longitude == point.longitude


@pytest.mark.asyncio
@respx.mock
async def test_reverse_uses_fallback_name() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    point = Coordinates(
        latitude=55.75,
        longitude=37.61,
    )
    respx.get(
        url__startswith=(
            "https://catalog.api.2gis.test/"
            "3.0/items/geocode"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "result": {
                    "items": [
                        {
                            "name": "Парковка №1",
                        }
                    ]
                }
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )
        place = await geocoder.reverse(point)

    assert place.name == "Точка встречи"
    assert place.latitude == point.latitude
    assert place.longitude == point.longitude


@pytest.mark.asyncio
@respx.mock
async def test_quota_error_hides_api_key() -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.find_by_query.return_value = None
    respx.get(
        url__startswith=(
            "https://catalog.api.2gis.test/"
            "3.0/items"
        )
    ).mock(
        return_value=httpx.Response(
            status_code=429,
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(),
            catalog,
        )

        with pytest.raises(
            ProviderQuotaExceededError
        ) as error:
            await geocoder.search(
                "Москва, улица Арбат, 10"
            )

    assert "test-key" not in str(error.value)


@pytest.mark.asyncio
async def test_requires_api_key_for_address(
) -> None:
    catalog = AsyncMock(
        spec=MetroCatalogService
    )
    catalog.find_by_query.return_value = None

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        geocoder = DgisGeocoder(
            client,
            build_settings(api_key=""),
            catalog,
        )

        with pytest.raises(ConfigurationError):
            await geocoder.search(
                "Москва, улица Арбат, 10"
            )