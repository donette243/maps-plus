import json
from collections.abc import Mapping
from typing import Any

import httpx

from app.config import Settings
from app.exceptions import (
    ConfigurationError,
    InvalidProviderResponseError,
    PlaceNotFoundError,
    ProviderQuotaExceededError,
    ProviderUnavailableError,
)
from app.models import Coordinates, Place
from app.services.metro import MetroCatalogService


class DgisGeocoder:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        metro_catalog: MetroCatalogService,
    ) -> None:
        self.client = client
        self.settings = settings
        self.metro_catalog = metro_catalog

    async def search(
        self,
        query: str,
    ) -> Place:
        normalized_query = query.strip()
        station = await self.metro_catalog.find_by_query(
            normalized_query
        )

        if station is not None:
            return station

        self._validate_api_key()

        items = await self._request_items(
            endpoint="/items",
            params={
                "q": normalized_query,
                "fields": (
                    "items.point,"
                    "items.geometry.centroid,"
                    "items.full_name,"
                    "items.address_name"
                ),
                "locale": "ru_RU",
                "page_size": 10,
            },
        )

        if not items:
            items = await self._request_items(
                endpoint="/items/geocode",
                params={
                    "q": normalized_query,
                    "fields": (
                        "items.point,"
                        "items.geometry.centroid,"
                        "items.full_name,"
                        "items.address_name"
                    ),
                    "locale": "ru_RU",
                },
            )

        for item in items:
            place = self._item_to_place(item)

            if place is not None:
                return place

        raise PlaceNotFoundError(
            f"Адрес или станция не найдены: "
            f"{normalized_query}"
        )

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
                    "items.address_name,"
                    "items.full_name,"
                    "items.geometry.centroid,"
                    "items.type"
                ),
                "locale": "ru_RU",
                "page_size": 10,
            },
        )

        return Place(
            name=self._select_reverse_name(items),
            latitude=point.latitude,
            longitude=point.longitude,
        )

    async def reverse_many(
        self,
        points: list[Coordinates],
    ) -> list[Place]:
        places: list[Place] = []

        for point in points:
            places.append(await self.reverse(point))

        return places

    async def _request_items(
        self,
        endpoint: str,
        params: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        response = await self.client.get(
            (
                f"{self.settings.dgis_catalog_url}"
                f"{endpoint}"
            ),
            params={
                **params,
                "key": self.settings.dgis_key,
            },
        )

        if response.status_code == 404:
            return []

        if response.status_code == 429:
            raise ProviderQuotaExceededError(
                "Лимит запросов 2GIS исчерпан"
            )

        if response.is_error:
            raise ProviderUnavailableError(
                "Сервис геокодирования временно "
                "недоступен"
            )

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise InvalidProviderResponseError(
                "Сервис геокодирования вернул "
                "некорректный ответ"
            ) from exc

        if not isinstance(data, dict):
            raise InvalidProviderResponseError(
                "Сервис геокодирования вернул "
                "некорректный ответ"
            )

        result = data.get("result")

        if not isinstance(result, dict):
            return []

        items = result.get("items", [])

        if not isinstance(items, list):
            raise InvalidProviderResponseError(
                "Некорректный список результатов "
                "геокодирования"
            )

        return [
            item
            for item in items
            if isinstance(item, dict)
        ]

    def _item_to_place(
        self,
        item: Mapping[str, Any],
    ) -> Place | None:
        coordinates = self._extract_coordinates(item)

        if coordinates is None:
            return None

        name = self._first_text(
            item,
            "full_name",
            "address_name",
            "name",
        )

        if name is None:
            return None

        try:
            return Place(
                name=name,
                latitude=coordinates.latitude,
                longitude=coordinates.longitude,
            )
        except ValueError:
            return None

    def _extract_coordinates(
        self,
        item: Mapping[str, Any],
    ) -> Coordinates | None:
        point = item.get("point")

        if isinstance(point, dict):
            coordinates = self._build_coordinates(
                point.get("lat"),
                point.get("lon"),
            )

            if coordinates is not None:
                return coordinates

        geometry = item.get("geometry")

        if not isinstance(geometry, dict):
            return None

        centroid = geometry.get("centroid")

        if not isinstance(centroid, str):
            return None

        values = (
            centroid
            .removeprefix("POINT(")
            .removesuffix(")")
            .split()
        )

        if len(values) != 2:
            return None

        return self._build_coordinates(
            values[1],
            values[0],
        )

    def _build_coordinates(
        self,
        latitude: object,
        longitude: object,
    ) -> Coordinates | None:
        try:
            return Coordinates(
                latitude=float(latitude),
                longitude=float(longitude),
            )
        except (TypeError, ValueError):
            return None

    def _select_reverse_name(
        self,
        items: list[dict[str, Any]],
    ) -> str:
        for fields in (
            ("full_name", "address_name"),
            ("address_name",),
            ("name",),
        ):
            for item in items:
                name = self._first_text(
                    item,
                    *fields,
                )

                if (
                    name is not None
                    and not self._is_unhelpful_name(name)
                ):
                    return name

        return "Точка встречи"

    def _first_text(
        self,
        item: Mapping[str, Any],
        *fields: str,
    ) -> str | None:
        for field in fields:
            value = item.get(field)

            if isinstance(value, str) and value.strip():
                return value.strip()

        return None

    def _is_unhelpful_name(
        self,
        name: str,
    ) -> bool:
        normalized = (
            name
            .casefold()
            .replace("ё", "е")
        )
        unhelpful_fragments = (
            "парковк",
            "автостоянк",
            "банкомат",
            "терминал",
            "платежный терминал",
        )

        return any(
            fragment in normalized
            for fragment in unhelpful_fragments
        )

    def _validate_api_key(self) -> None:
        if not self.settings.dgis_key:
            raise ConfigurationError(
                "API-ключ 2GIS не указан в файле .env"
            )