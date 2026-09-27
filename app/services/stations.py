from math import asin, cos, radians, sin, sqrt

from app.exceptions import PlaceNotFoundError
from app.models import Coordinates, Place
from app.services.metro import MetroCatalogService


class StationSearchService:
    def __init__(
        self,
        metro_catalog: MetroCatalogService,
    ) -> None:
        self.metro_catalog = metro_catalog

    async def find_candidates(
        self,
        origin_a: Coordinates,
        origin_b: Coordinates,
        count: int,
    ) -> list[Place]:
        if count < 1:
            raise ValueError(
                "Количество кандидатов должно быть "
                "положительным"
            )

        stations = await self.metro_catalog.get_stations()

        if not stations:
            raise PlaceNotFoundError(
                "Станции метро, МЦД или МЦК не найдены"
            )

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
        origin_distance = self._distance(
            origin_a,
            origin_b,
        )
        corridor_radius = max(
            5.0,
            origin_distance * 0.35,
        )
        stations_by_midpoint = sorted(
            stations,
            key=lambda station: self._distance(
                midpoint,
                station,
            ),
        )
        pool_limit = min(
            len(stations_by_midpoint),
            max(count * 4, 30),
        )
        nearby_stations = [
            station
            for station in stations_by_midpoint
            if (
                self._distance(midpoint, station)
                <= corridor_radius
            )
        ][:pool_limit]

        if len(nearby_stations) < count:
            for station in stations_by_midpoint:
                if station in nearby_stations:
                    continue

                nearby_stations.append(station)

                if len(nearby_stations) >= count:
                    break

        nearby_stations.sort(
            key=lambda station: self._station_score(
                station,
                origin_a,
                origin_b,
            )
        )

        return nearby_stations[:count]

    def _station_score(
        self,
        station: Place,
        origin_a: Coordinates,
        origin_b: Coordinates,
    ) -> tuple[float, float]:
        distance_a = self._distance(
            origin_a,
            station,
        )
        distance_b = self._distance(
            origin_b,
            station,
        )
        difference = abs(
            distance_a - distance_b
        )
        total_distance = distance_a + distance_b

        return (
            total_distance * 2 + difference,
            difference,
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