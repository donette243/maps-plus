import httpx
import pytest
import respx

from app.config import Settings
from app.models import Place
from app.services.stations import StationSearchService


@pytest.mark.asyncio
@respx.mock
async def test_finds_station_candidates() -> None:
    settings = Settings(
        dgis_api_key="test-key",
    )

    route = respx.get(
        "https://api.hh.ru/metro/1"
    ).mock(
        return_value=httpx.Response(
            status_code=200,
            json={
                "lines": [
                    {
                        "id": "6",
                        "name": "Калужско-Рижская",
                        "stations": [
                            {
                                "id": "1",
                                "name": "Китай-город",
                                "lat": 55.7565,
                                "lng": 37.6316,
                            }
                        ],
                    },
                    {
                        "id": "131",
                        "name": "МЦД-1",
                        "stations": [
                            {
                                "id": "2",
                                "name": "Москва-Сити",
                                "lat": 55.7472,
                                "lng": 37.5323,
                            }
                        ],
                    },
                    {
                        "id": "95",
                        "name": "МЦК",
                        "stations": [
                            {
                                "id": "3",
                                "name": "Лужники",
                                "lat": 55.7203,
                                "lng": 37.5603,
                            }
                        ],
                    },
                ]
            },
        )
    )

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

    async with httpx.AsyncClient(
        trust_env=False,
    ) as client:
        service = StationSearchService(
            client=client,
            settings=settings,
        )

        stations = await service.find_candidates(
            origin_a=origin_a,
            origin_b=origin_b,
            count=3,
        )

    names = {
        station.name
        for station in stations
    }

    assert route.called
    assert len(stations) == 3
    assert "Метро Китай-город" in names
    assert "МЦД Москва-Сити" in names
    assert "МЦК Лужники" in names