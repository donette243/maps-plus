from math import asin, cos, radians, sin, sqrt

import httpx

from app.config import Settings
from app.exceptions import PlaceNotFoundError
from app.models import Coordinates, Place


class StationSearchService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.client = client
        self.settings = settings
        self.metro_url = "https://api.hh.ru/metro/1"

    async def find_candidates(
        self,
        origin_a: Coordinates,
        origin_b: Coordinates,
        count: int,
    ) -> list[Place]:
        stations = await self._load_stations()

        stations.sort(
            key=lambda station: self._station_score(
                station=station,
                origin_a=origin_a,
                origin_b=origin_b,
            )
        )

        candidates = stations[: max(count, 30)]

        if not candidates:
            raise PlaceNotFoundError(
                "Станции метро, МЦД или МЦК не найдены"
            )

        return candidates

    async def _load_stations(self) -> list[Place]:
        response = await self.client.get(
            self.metro_url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()

        data = response.json()
        lines = data.get("lines", [])

        if not isinstance(lines, list):
            return []

        stations: list[Place] = []

        for line in lines:
            if not isinstance(line, dict):
                continue

            line_name = line.get("name", "")
            line_stations = line.get("stations", [])

            if not isinstance(line_stations, list):
                continue

            for item in line_stations:
                station = self._item_to_place(
                    item=item,
                    line_name=line_name,
                )

                if station is not None:
                    stations.append(station)

        return self._remove_duplicates(stations)

    def _item_to_place(
        self,
        item: dict,
        line_name: str,
    ) -> Place | None:
        name = item.get("name")
        latitude = item.get("lat")
        longitude = item.get("lng")

        if not isinstance(name, str) or not name:
            return None

        if not isinstance(latitude, (int, float)):
            return None

        if not isinstance(longitude, (int, float)):
            return None

        station_type = self._station_type(line_name)

        return Place(
            name=f"{station_type} {name}",
            latitude=float(latitude),
            longitude=float(longitude),
        )

    def _station_type(self, line_name: str) -> str:
        normalized = line_name.casefold()

        if normalized.startswith("мцд"):
            return "МЦД"

        if normalized == "мцк":
            return "МЦК"

        return "Метро"

    def _remove_duplicates(
        self,
        stations: list[Place],
    ) -> list[Place]:
        unique: dict[
            tuple[str, float, float],
            Place,
        ] = {}

        for station in stations:
            key = (
                station.name.casefold(),
                round(station.latitude, 4),
                round(station.longitude, 4),
            )
            unique[key] = station

        return list(unique.values())

    def _station_score(
        self,
        station: Place,
        origin_a: Coordinates,
        origin_b: Coordinates,
    ) -> tuple[float, float]:
        midpoint = Coordinates(
            latitude=(
                origin_a.latitude
                + origin_b.latitude
            )
            / 2,
            longitude=(
                origin_a.longitude
                + origin_b.longitude
            )
            / 2,
        )

        distance_to_midpoint = self._distance(
            midpoint,
            station,
        )
        distance_a = self._distance(
            origin_a,
            station,
        )
        distance_b = self._distance(
            origin_b,
            station,
        )

        return (
            distance_to_midpoint,
            distance_a + distance_b,
        )

    def _distance(
        self,
        first: Coordinates,
        second: Coordinates,
    ) -> float:
        earth_radius_km = 6371.0

        latitude_difference = radians(
            second.latitude - first.latitude
        )
        longitude_difference = radians(
            second.longitude - first.longitude
        )
        first_latitude = radians(first.latitude)
        second_latitude = radians(second.latitude)

        value = (
            sin(latitude_difference / 2) ** 2
            + cos(first_latitude)
            * cos(second_latitude)
            * sin(longitude_difference / 2) ** 2
        )

        return (
            2
            * earth_radius_km
            * asin(sqrt(value))
        )