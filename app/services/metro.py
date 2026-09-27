import asyncio
import json
from typing import Any

import httpx

from app.config import Settings
from app.exceptions import (
    InvalidProviderResponseError,
    PlaceNotFoundError,
    ProviderUnavailableError,
)
from app.models import Place


class MetroCatalogService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.client = client
        self.settings = settings
        self._stations: list[Place] | None = None
        self._lock = asyncio.Lock()

    async def get_stations(self) -> list[Place]:
        if self._stations is not None:
            return list(self._stations)

        async with self._lock:
            if self._stations is None:
                self._stations = await self._load_stations()

        return list(self._stations)

    async def find_by_query(
        self,
        query: str,
    ) -> Place | None:
        target = self._extract_station_name(query)

        if target is None:
            return None

        stations = await self.get_stations()
        exact_matches = [
            station
            for station in stations
            if self._normalize_station_name(
                station.name
            )
            == target
        ]

        if exact_matches:
            return exact_matches[0]

        partial_matches = [
            station
            for station in stations
            if (
                target
                in self._normalize_station_name(
                    station.name
                )
                or self._normalize_station_name(
                    station.name
                )
                in target
            )
        ]
        unique_matches = self._remove_duplicates(
            partial_matches
        )

        if len(unique_matches) == 1:
            return unique_matches[0]

        raise PlaceNotFoundError(
            f"Станция не найдена или указана "
            f"неоднозначно: {query}"
        )

    async def _load_stations(self) -> list[Place]:
        data = await self._request_catalog()
        lines = data.get("lines")

        if not isinstance(lines, list):
            raise InvalidProviderResponseError(
                "В ответе сервиса отсутствует список линий"
            )

        stations: list[Place] = []

        for line in lines:
            if not isinstance(line, dict):
                continue

            line_name = line.get("name")
            line_stations = line.get("stations")

            if (
                not isinstance(line_name, str)
                or not isinstance(line_stations, list)
            ):
                continue

            for item in line_stations:
                station = self._item_to_place(
                    item,
                    line_name,
                )

                if station is not None:
                    stations.append(station)

        unique_stations = self._remove_duplicates(
            stations
        )

        if not unique_stations:
            raise InvalidProviderResponseError(
                "Сервис станций не вернул станции"
            )

        return unique_stations

    async def _request_catalog(
        self,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(2):
            try:
                response = await self.client.get(
                    self.settings.hh_metro_url,
                    headers={
                        "Accept": "application/json",
                    },
                )
            except httpx.RequestError as exc:
                last_error = exc

                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue

                raise ProviderUnavailableError(
                    "Сервис станций временно недоступен"
                ) from exc

            if response.status_code >= 500:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue

                raise ProviderUnavailableError(
                    "Сервис станций временно недоступен"
                )

            if response.is_error:
                raise ProviderUnavailableError(
                    "Сервис станций временно недоступен"
                )

            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                raise InvalidProviderResponseError(
                    "Сервис станций вернул "
                    "некорректный ответ"
                ) from exc

            if not isinstance(data, dict):
                raise InvalidProviderResponseError(
                    "Сервис станций вернул "
                    "некорректный ответ"
                )

            return data

        raise ProviderUnavailableError(
            "Сервис станций временно недоступен"
        ) from last_error

    def _item_to_place(
        self,
        item: object,
        line_name: str,
    ) -> Place | None:
        if not isinstance(item, dict):
            return None

        name = item.get("name")
        latitude = item.get("lat")
        longitude = item.get("lng")

        if not isinstance(name, str) or not name.strip():
            return None

        if not isinstance(latitude, (int, float)):
            return None

        if not isinstance(longitude, (int, float)):
            return None

        try:
            return Place(
                name=(
                    f"{self._station_type(line_name)} "
                    f"{name.strip()}"
                ),
                latitude=float(latitude),
                longitude=float(longitude),
            )
        except ValueError:
            return None

    def _extract_station_name(
        self,
        query: str,
    ) -> str | None:
        normalized = self._normalize(query)
        markers = (
            "станция метро",
            "метро",
            "мцд",
            "мцк",
        )

        for marker in markers:
            if not normalized.startswith(marker):
                continue

            station_name = normalized[
                len(marker):
            ].split(",", maxsplit=1)[0].strip(" -")

            if station_name:
                return station_name

        return None

    def _normalize_station_name(
        self,
        value: str,
    ) -> str:
        normalized = self._normalize(value)

        for prefix in (
            "метро ",
            "мцд ",
            "мцк ",
        ):
            if normalized.startswith(prefix):
                return normalized[len(prefix):]

        return normalized

    def _station_type(self, line_name: str) -> str:
        normalized = self._normalize(line_name)

        if normalized.startswith("мцд"):
            return "МЦД"

        if normalized == "мцк":
            return "МЦК"

        return "Метро"

    def _remove_duplicates(
        self,
        stations: list[Place],
    ) -> list[Place]:
        unique: dict[tuple[str, str], Place] = {}

        for station in stations:
            parts = station.name.split(maxsplit=1)

            if len(parts) == 2:
                station_type, station_name = parts
            else:
                station_type = ""
                station_name = station.name

            key = (
                self._normalize(station_type),
                self._normalize(station_name),
            )
            unique.setdefault(key, station)

        return list(unique.values())

    def _normalize(self, value: str) -> str:
        return (
            value
            .strip()
            .casefold()
            .replace("ё", "е")
        )