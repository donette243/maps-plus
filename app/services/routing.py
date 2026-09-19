import asyncio

import httpx

from app.config import Settings
from app.exceptions import RoutingUnavailableError
from app.models import Coordinates, RoutingMode


class Router:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.client = client
        self.settings = settings
        self.duration_cache: dict[
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

        cached = self.duration_cache.get(cache_key)

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

        self.duration_cache[cache_key] = duration
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
        response.raise_for_status()
        data = response.json()

        if (
            data.get("code") != "Ok"
            or not data.get("routes")
        ):
            raise RoutingUnavailableError(
                "Автомобильный маршрут не найден"
            )

        return round(
            float(
                data["routes"][0]["duration"]
            )
        )

    async def _transit_duration(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> int:
        response: httpx.Response | None = None

        for attempt in range(3):
            response = await self.client.post(
                (
                    f"{self.settings.dgis_routing_url}"
                    "/public_transport/2.0"
                ),
                params={
                    "key": self.settings.dgis_api_key,
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

            if response.status_code != 429:
                break

            if attempt < 2:
                await asyncio.sleep(
                    self._retry_delay(
                        response,
                        attempt,
                    )
                )

        if response is None:
            raise RoutingUnavailableError(
                "Не удалось выполнить запрос маршрута"
            )

        response.raise_for_status()
        data = response.json()

        routes = (
            data
            if isinstance(data, list)
            else data.get("routes", [])
        )

        if not routes:
            raise RoutingUnavailableError(
                "Маршрут на общественном "
                "транспорте не найден"
            )

        durations = [
            route.get("total_duration")
            for route in routes
            if (
                isinstance(route, dict)
                and isinstance(
                    route.get("total_duration"),
                    (int, float),
                )
            )
        ]

        if not durations:
            raise RoutingUnavailableError(
                "В ответе 2GIS отсутствует "
                "продолжительность маршрута"
            )

        return round(float(min(durations)))

    def _retry_delay(
        self,
        response: httpx.Response,
        attempt: int,
    ) -> float:
        retry_after = response.headers.get(
            "Retry-After"
        )

        if retry_after is not None:
            try:
                return max(
                    1.0,
                    float(retry_after),
                )
            except ValueError:
                pass

        return float(5 * (attempt + 1))