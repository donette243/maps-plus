import asyncio
from math import asin, cos, radians, sin, sqrt

import httpx

from app.exceptions import RoutingUnavailableError
from app.models import (
    CandidateResult,
    Coordinates,
    MeetingRequest,
    MeetingResponse,
    Place,
    RoutingMode,
)
from app.services.geocoding import DgisGeocoder
from app.services.routing import Router
from app.services.stations import StationSearchService


class MeetingPointService:
    def __init__(
        self,
        geocoder: DgisGeocoder,
        station_search: StationSearchService,
        router: Router,
        default_candidate_count: int,
    ) -> None:
        self.geocoder = geocoder
        self.station_search = station_search
        self.router = router
        self.default_candidate_count = default_candidate_count

    async def find(
        self,
        request: MeetingRequest,
    ) -> MeetingResponse:
        origin_a, origin_b = await asyncio.gather(
            self.geocoder.search(
                request.participant_a
            ),
            self.geocoder.search(
                request.participant_b
            ),
        )

        count = (
            request.candidate_count
            or self.default_candidate_count
        )
        estimated = False

        if request.mode == RoutingMode.TRANSIT:
            candidates = (
                await self.station_search.find_candidates(
                    origin_a,
                    origin_b,
                    count,
                )
            )
            evaluated, estimated = (
                await self._evaluate_transit_candidates(
                    origin_a,
                    origin_b,
                    candidates,
                )
            )
        else:
            points = generate_candidates(
                origin_a,
                origin_b,
                count,
            )
            candidates = await self.geocoder.reverse_many(
                points
            )
            evaluated = await asyncio.gather(
                *(
                    self._evaluate(
                        origin_a,
                        origin_b,
                        candidate,
                        request.mode,
                    )
                    for candidate in candidates
                ),
                return_exceptions=True,
            )

        valid = [
            item
            for item in evaluated
            if isinstance(item, CandidateResult)
        ]

        if not valid:
            raise RoutingUnavailableError(
                "Доступные точки встречи не найдены"
            )

        valid.sort(
            key=lambda item: (
                item.difference_minutes,
                item.total_minutes,
            )
        )
        shortlist = valid[: min(3, len(valid))]

        if request.mode == RoutingMode.TRANSIT:
            provider = (
                "Расчётное время по расстоянию"
                if estimated
                else "2GIS"
            )
        else:
            provider = "OSRM + 2GIS"

        return MeetingResponse(
            origin_a=origin_a,
            origin_b=origin_b,
            best_meeting_point=shortlist[0],
            alternatives=shortlist[1:],
            mode=request.mode,
            provider=provider,
        )

    async def _evaluate_transit_candidates(
        self,
        origin_a: Place,
        origin_b: Place,
        candidates: list[Place],
    ) -> tuple[
        list[CandidateResult | Exception],
        bool,
    ]:
        evaluated: list[
            CandidateResult | Exception
        ] = []

        for candidate in candidates[:3]:
            try:
                result = await self._evaluate(
                    origin_a,
                    origin_b,
                    candidate,
                    RoutingMode.TRANSIT,
                )
                evaluated.append(result)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    estimated_results = [
                        self._estimate_candidate(
                            origin_a,
                            origin_b,
                            item,
                        )
                        for item in candidates
                    ]
                    return estimated_results, True

                evaluated.append(
                    RoutingUnavailableError(
                        "Сервис маршрутов временно "
                        "недоступен"
                    )
                )
            except Exception as exc:
                evaluated.append(exc)

            await asyncio.sleep(0.6)

        return evaluated, False

    async def _evaluate(
        self,
        origin_a: Place,
        origin_b: Place,
        candidate: Place,
        mode: RoutingMode,
    ) -> CandidateResult:
        if mode == RoutingMode.TRANSIT:
            duration_a = await self.router.duration_seconds(
                origin_a,
                candidate,
                mode,
            )
            await asyncio.sleep(0.6)
            duration_b = await self.router.duration_seconds(
                origin_b,
                candidate,
                mode,
            )
        else:
            duration_a, duration_b = await asyncio.gather(
                self.router.duration_seconds(
                    origin_a,
                    candidate,
                    mode,
                ),
                self.router.duration_seconds(
                    origin_b,
                    candidate,
                    mode,
                ),
            )

        minutes_a = max(
            1,
            round(duration_a / 60),
        )
        minutes_b = max(
            1,
            round(duration_b / 60),
        )

        return self._candidate_result(
            candidate,
            minutes_a,
            minutes_b,
        )

    def _estimate_candidate(
        self,
        origin_a: Place,
        origin_b: Place,
        candidate: Place,
    ) -> CandidateResult:
        minutes_a = self._estimate_minutes(
            origin_a,
            candidate,
        )
        minutes_b = self._estimate_minutes(
            origin_b,
            candidate,
        )

        return self._candidate_result(
            candidate,
            minutes_a,
            minutes_b,
        )

    def _candidate_result(
        self,
        candidate: Place,
        minutes_a: int,
        minutes_b: int,
    ) -> CandidateResult:
        return CandidateResult(
            place=candidate,
            time_a_minutes=minutes_a,
            time_b_minutes=minutes_b,
            difference_minutes=abs(
                minutes_a - minutes_b
            ),
            total_minutes=(
                minutes_a + minutes_b
            ),
        )

    def _estimate_minutes(
        self,
        origin: Coordinates,
        destination: Coordinates,
    ) -> int:
        distance = self._distance(
            origin,
            destination,
        )

        if distance < 0.3:
            return 1

        return max(
            1,
            round((distance / 22) * 60 + 5),
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


def generate_candidates(
    origin_a: Coordinates,
    origin_b: Coordinates,
    count: int,
) -> list[Coordinates]:
    fractions = [
        0.2 + (0.6 * index / (count - 1))
        for index in range(count)
    ]
    points: list[Coordinates] = []

    mean_latitude = (
        origin_a.latitude + origin_b.latitude
    ) / 2
    longitude_scale = max(
        cos(radians(mean_latitude)),
        0.2,
    )
    perpendicular_latitude = (
        -(origin_b.longitude - origin_a.longitude)
        * longitude_scale
    )
    perpendicular_longitude = (
        (origin_b.latitude - origin_a.latitude)
        / longitude_scale
    )

    for index, fraction in enumerate(fractions):
        latitude = (
            origin_a.latitude
            + fraction
            * (origin_b.latitude - origin_a.latitude)
        )
        longitude = (
            origin_a.longitude
            + fraction
            * (origin_b.longitude - origin_a.longitude)
        )

        if index in {1, count - 2}:
            direction = -1 if index == 1 else 1
            latitude += (
                direction
                * perpendicular_latitude
                * 0.05
            )
            longitude += (
                direction
                * perpendicular_longitude
                * 0.05
            )

        points.append(
            Coordinates(
                latitude=latitude,
                longitude=longitude,
            )
        )

    return points