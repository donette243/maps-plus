import json
from math import isfinite
from typing import Any

import httpx

from app.config import Settings
from app.exceptions import (
    ConfigurationError,
    InvalidProviderResponseError,
    ProviderQuotaExceededError,
    ProviderUnavailableError,
    RouteNotFoundError,
)
from app.models import Coordinates, RoutingMode


class Router:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.client = client
        self.settings = settings
        self._duration_cache: dict[
            tuple[float, float, float, float, str],
            int,
        ] = {}

    async def duration_seconds(
        self,
        origin: Coordinates,
        destination: Coordinates,
        mode: RoutingMode,
    ) -> int:
        cache_key = (
            round(origin.latitude, 5),
            round(origin.longitude, 5),
            round(destination.latitude, 5),
            round(destination.longitude, 5),
            mode.value,
        )
        cached = self._duration_cache.get(cache_key)

        if cached is not None:
            return cached

        if mode == RoutingMode.TRANSIT:
            duration = await self._transit_duration(
                origin,
                destination,
            )
        else:
            duration = await self._driving_duration(
                origin,
                destination,
            )

        self._duration_cache[cache_key] = duration
        return duration

    async def _driving_duration(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> int:
        coordinates = (
            f"{origin.longitude},{origin.latitude};"
            f"{destination.longitude},"
            f"{destination.latitude}"
        )
        response = await self.client.get(
            (
                f"{self.settings.osrm_url}"
                f"/route/v1/driving/{coordinates}"
            ),
            params={
                "overview": "false",
                "steps": "false",
            },
        )

        if response.is_error:
            raise ProviderUnavailableError(
                "Сервис автомобильных маршрутов "
                "временно недоступен"
            )

        data = self._read_json(
            response,
            "Сервис автомобильных маршрутов",
        )

        if not isinstance(data, dict):
            raise InvalidProviderResponseError(
                "Сервис автомобильных маршрутов "
                "вернул некорректный ответ"
            )

        routes = data.get("routes")

        if (
            data.get("code") != "Ok"
            or not isinstance(routes, list)
            or not routes
        ):
            raise RouteNotFoundError(
                "Автомобильный маршрут не найден"
            )

        first_route = routes[0]

        if not isinstance(first_route, dict):
            raise InvalidProviderResponseError(
                "В ответе отсутствуют данные маршрута"
            )

        return self._validate_duration(
            first_route.get("duration"),
            "OSRM",
        )

    async def _transit_duration(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> int:
        self._validate_api_key()

        response = await self.client.post(
            (
                f"{self.settings.dgis_routing_url}"
                "/public_transport/2.0"
            ),
            params={
                "key": self.settings.dgis_key,
            },
            json={
                "source": {
                    "point": {
                        "lat": origin.latitude,
                        "lon": origin.longitude,
                    }
                },
                "target": {
                    "point": {
                        "lat": destination.latitude,
                        "lon": destination.longitude,
                    }
                },
                "transport": [
                    "bus",
                    "trolleybus",
                    "tram",
                    "shuttle_bus",
                    "metro",
                    "suburban_train",
                ],
            },
        )

        if response.status_code == 429:
            raise ProviderQuotaExceededError(
                "Лимит запросов 2GIS исчерпан"
            )

        if response.status_code in {401, 403}:
            raise ConfigurationError(
                "API-ключ 2GIS недействителен "
                "или не имеет доступа к маршрутам"
            )

        if response.is_error:
            raise ProviderUnavailableError(
                "Сервис общественного транспорта "
                "временно недоступен"
            )

        data = self._read_json(
            response,
            "Сервис общественного транспорта",
        )

        if isinstance(data, list):
            routes = data
        elif isinstance(data, dict):
            routes = data.get("routes", [])
        else:
            raise InvalidProviderResponseError(
                "Сервис общественного транспорта "
                "вернул некорректный ответ"
            )

        if not isinstance(routes, list) or not routes:
            raise RouteNotFoundError(
                "Маршрут на общественном "
                "транспорте не найден"
            )

        durations: list[int] = []

        for route in routes:
            if not isinstance(route, dict):
                continue

            try:
                duration = self._validate_duration(
                    route.get("total_duration"),
                    "2GIS",
                )
            except InvalidProviderResponseError:
                continue

            durations.append(duration)

        if not durations:
            raise InvalidProviderResponseError(
                "В ответе 2GIS отсутствует "
                "корректная продолжительность маршрута"
            )

        return min(durations)

    def _read_json(
        self,
        response: httpx.Response,
        provider_name: str,
    ) -> Any:
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise InvalidProviderResponseError(
                f"{provider_name} вернул "
                f"некорректный JSON"
            ) from exc

    def _validate_duration(
        self,
        value: object,
        provider_name: str,
    ) -> int:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            raise InvalidProviderResponseError(
                f"{provider_name} вернул "
                f"некорректную продолжительность"
            )

        duration = float(value)

        if not isfinite(duration) or duration <= 0:
            raise InvalidProviderResponseError(
                f"{provider_name} вернул "
                f"некорректную продолжительность"
            )

        return round(duration)

    def _validate_api_key(self) -> None:
        if not self.settings.dgis_key:
            raise ConfigurationError(
                "API-ключ 2GIS не указан в файле .env"
            )