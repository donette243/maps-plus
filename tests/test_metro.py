import httpx
import pytest
import respx

from app.config import Settings
from app.exceptions import (
    InvalidProviderResponseError,
    PlaceNotFoundError,
)
from app.services.metro import MetroCatalogService


def build_settings() -> Settings:
    return Settings(
        hh_metro_url="https://hh.test/metro/1",
    )


def metro_response() -> dict:
    return {
        "lines": [
            {
                "name": "Калужско-Рижская",
                "stations": [
                    {
                        "name": "Китай-город",
                        "lat": 55.7565,
                        "lng": 37.6316,
                    },
                    {
                        "name": "Китайская",
                        "lat": 55.7600,
                        "lng": 37.6400,
                    },
                ],
            },
            {
                "name": "Таганско-Краснопресненская",
                "stations": [
                    {
                        "name": "Китай-город",
                        "lat": 55.7566,
                        "lng": 37.6317,
                    }
                ],
            },
            {
                "name": "МЦК",
                "stations": [
                    {
                        "name": "Лужники",
                        "lat": 55.7203,
                        "lng": 37.5603,
                    }
                ],
            },
            {
                "name": "МЦД-1",
                "stations": [
                    {
                        "name": "Москва-Сити",
                        "lat": 55.7472,
                        "lng": 37.5323,
                    }
                ],
            },
        ]
    }


@pytest.mark.asyncio
@respx.mock
async def test_loads_and_caches_stations() -> None:
    route = respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=metro_response(),
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )
        first = await catalog.get_stations()
        second = await catalog.get_stations()

    names = {
        station.name
        for station in first
    }

    assert first == second
    assert route.call_count == 1
    assert "Метро Китай-город" in names
    assert "МЦК Лужники" in names
    assert "МЦД Москва-Сити" in names
    assert len(first) == 4


@pytest.mark.asyncio
@respx.mock
async def test_finds_exact_station() -> None:
    respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=metro_response(),
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )
        station = await catalog.find_by_query(
            "метро Китай-город, Москва"
        )

    assert station is not None
    assert station.name == "Метро Китай-город"


@pytest.mark.asyncio
@respx.mock
async def test_regular_address_is_not_station_query(
) -> None:
    route = respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=metro_response(),
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )
        station = await catalog.find_by_query(
            "Москва, улица Метро, 10"
        )

    assert station is None
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_rejects_ambiguous_station_name(
) -> None:
    respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json=metro_response(),
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )

        with pytest.raises(PlaceNotFoundError):
            await catalog.find_by_query(
                "метро Китай"
            )


@pytest.mark.asyncio
@respx.mock
async def test_rejects_invalid_provider_json(
) -> None:
    respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            text="not-json",
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )

        with pytest.raises(
            InvalidProviderResponseError
        ):
            await catalog.get_stations()


@pytest.mark.asyncio
@respx.mock
async def test_rejects_missing_lines() -> None:
    respx.get(
        "https://hh.test/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "unexpected": [],
            },
        )
    )

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        catalog = MetroCatalogService(
            client,
            build_settings(),
        )

        with pytest.raises(
            InvalidProviderResponseError
        ):
            await catalog.get_stations()