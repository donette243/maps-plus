import httpx

from app.config import Settings
from app.exceptions import PlaceNotFoundError
from app.models import Coordinates, Place


class DgisGeocoder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.client = client
        self.settings = settings
        self.metro_url = "https://api.hh.ru/metro/1"

    async def search(
        self,
        query: str,
    ) -> Place:
        station = await self._search_station(query)

        if station is not None:
            return station

        self._validate_api_key()

        items = await self._request_items(
            endpoint="/items",
            params={
                "q": query,
                "fields": (
                    "items.point,"
                    "items.geometry.centroid"
                ),
                "locale": "ru_RU",
                "page_size": 10,
            },
        )

        if not items:
            items = await self._request_items(
                endpoint="/items/geocode",
                params={
                    "q": query,
                    "fields": (
                        "items.point,"
                        "items.geometry.centroid"
                    ),
                    "locale": "ru_RU",
                },
            )

        if not items:
            raise PlaceNotFoundError(
                f"Адрес или станция не найдены: {query}"
            )

        return self._item_to_place(items[0])

    async def reverse(
        self,
        point: Coordinates,
    ) -> Place:
        self._validate_api_key()

        items = await self._request_items(
            endpoint="/items/geocode",
            params={
                "lat": point.latitude,
                "lon": point.longitude,
                "fields": (
                    "items.point,"
                    "items.address,"
                    "items.geometry.centroid"
                ),
                "locale": "ru_RU",
            },
        )

        if not items:
            return Place(
                name="Точка встречи",
                latitude=point.latitude,
                longitude=point.longitude,
            )

        return self._item_to_place(
            items[0],
            fallback=point,
        )

    async def reverse_many(
        self,
        points: list[Coordinates],
    ) -> list[Place]:
        places: list[Place] = []

        for point in points:
            place = await self.reverse(point)
            places.append(place)

        return places

    async def _search_station(
        self,
        query: str,
    ) -> Place | None:
        target = self._extract_station_name(query)

        if target is None:
            return None

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
            return None

        partial_matches: list[Place] = []

        for line in lines:
            if not isinstance(line, dict):
                continue

            line_name = str(line.get("name", ""))
            stations = line.get("stations", [])

            if not isinstance(stations, list):
                continue

            for item in stations:
                if not isinstance(item, dict):
                    continue

                station_name = item.get("name")
                latitude = item.get("lat")
                longitude = item.get("lng")

                if not isinstance(station_name, str):
                    continue

                if not isinstance(
                    latitude,
                    (int, float),
                ):
                    continue

                if not isinstance(
                    longitude,
                    (int, float),
                ):
                    continue

                normalized_name = self._normalize(
                    station_name
                )
                place = Place(
                    name=(
                        f"{self._station_type(line_name)} "
                        f"{station_name}"
                    ),
                    latitude=float(latitude),
                    longitude=float(longitude),
                )

                if normalized_name == target:
                    return place

                if (
                    target in normalized_name
                    or normalized_name in target
                ):
                    partial_matches.append(place)

        if partial_matches:
            partial_matches.sort(
                key=lambda place: len(place.name)
            )
            return partial_matches[0]

        raise PlaceNotFoundError(
            f"Станция не найдена: {query}"
        )

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
            marker_position = normalized.find(marker)

            if marker_position == -1:
                continue

            station_name = normalized[
                marker_position + len(marker):
            ]
            station_name = (
                station_name
                .split(",", maxsplit=1)[0]
                .strip(" -")
            )

            if station_name:
                return station_name

        return None

    def _station_type(self, line_name: str) -> str:
        normalized = self._normalize(line_name)

        if normalized.startswith("мцд"):
            return "МЦД"

        if normalized == "мцк":
            return "МЦК"

        return "Метро"

    def _normalize(self, value: str) -> str:
        return (
            value
            .strip()
            .casefold()
            .replace("ё", "е")
        )

    async def _request_items(
        self,
        endpoint: str,
        params: dict,
    ) -> list[dict]:
        request_params = {
            **params,
            "key": self.settings.dgis_api_key,
        }

        response = await self.client.get(
            (
                f"{self.settings.dgis_catalog_url}"
                f"{endpoint}"
            ),
            params=request_params,
        )

        if response.status_code == 404:
            return []

        response.raise_for_status()
        data = response.json()

        items = (
            data
            .get("result", {})
            .get("items", [])
        )

        if not isinstance(items, list):
            return []

        return items

    def _item_to_place(
        self,
        item: dict,
        fallback: Coordinates | None = None,
    ) -> Place:
        point = item.get("point")

        if isinstance(point, dict):
            latitude = float(point["lat"])
            longitude = float(point["lon"])
        else:
            latitude, longitude = self._parse_centroid(
                item,
                fallback,
            )

        name = (
            item.get("full_name")
            or item.get("address_name")
            or item.get("name")
            or "Неизвестное место"
        )

        return Place(
            name=name,
            latitude=latitude,
            longitude=longitude,
        )

    def _parse_centroid(
        self,
        item: dict,
        fallback: Coordinates | None,
    ) -> tuple[float, float]:
        geometry = item.get("geometry", {})
        centroid = geometry.get("centroid")

        if isinstance(centroid, str):
            values = (
                centroid
                .removeprefix("POINT(")
                .removesuffix(")")
                .split()
            )

            if len(values) == 2:
                longitude = float(values[0])
                latitude = float(values[1])

                return latitude, longitude

        if fallback is not None:
            return (
                fallback.latitude,
                fallback.longitude,
            )

        raise PlaceNotFoundError(
            "Координаты объекта не найдены"
        )

    def _validate_api_key(self) -> None:
        if not self.settings.dgis_api_key:
            raise PlaceNotFoundError(
                "API-ключ 2GIS не указан в файле .env"
            )