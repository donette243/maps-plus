import asyncio
from math import asin, cos, radians, sin, sqrt

import httpx

from app.exceptions import (
    ProviderQuotaExceededError,
    ProviderUnavailableError,
    RouteNotFoundError,
    RoutingUnavailableError,
)
from app.models import (
    CandidateResult,
    Coordinates,
    MeetingRequest,
    MeetingResponse,
    Place,
    RouteProvider,
    RoutingMode,
)
from app.services.geocoding import DgisGeocoder
from app.services.routing import Router
from app.services.stations import StationSearchService

ESTIMATED_TRANSIT_SPEED_KMH = 22.0
ESTIMATED_TRANSIT_WAIT_MINUTES = 5
MAX_TRANSIT_DIFFERENCE_MINUTES = 10
MAX_TRANSIT_DIFFERENCE_RATIO = 0.25


class MeetingPointService:
    def __init__(
        self,
        geocoder: DgisGeocoder,
        station_search: StationSearchService,
        router: Router,
        default_candidate_count: int,
        transit_request_delay_seconds: float,
    ) -> None:
        self.geocoder = geocoder
        self.station_search = station_search
        self.router = router
        self.default_candidate_count = (
            default_candidate_count
        )
        self.transit_request_delay_seconds = (
            transit_request_delay_seconds
        )

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
            evaluated = await self._evaluate_candidates(
                origin_a,
                origin_b,
                candidates,
                RoutingMode.DRIVING,
            )
            estimated = False

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

        if request.mode == RoutingMode.TRANSIT:
            valid = [
                item
                for item in valid
                if self._is_transit_result_fair(item)
            ]

            if not valid:
                raise RoutingUnavailableError(
                    "Не удалось найти достаточно "
                    "справедливую станцию встречи "
                    "для указанных адресов"
                )

        shortlist = valid[: min(3, len(valid))]

        if request.mode == RoutingMode.TRANSIT:
            provider = (
                RouteProvider.ESTIMATED
                if estimated
                else RouteProvider.DGIS
            )
        else:
            provider = RouteProvider.OSRM_DGIS

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

        for index, candidate in enumerate(candidates):
            try:
                result = await self._evaluate(
                    origin_a,
                    origin_b,
                    candidate,
                    RoutingMode.TRANSIT,
                )
                evaluated.append(result)
            except (
                ProviderQuotaExceededError,
                ProviderUnavailableError,
                httpx.HTTPError,
            ):
                return (
                    [
                        self._estimate_candidate(
                            origin_a,
                            origin_b,
                            item,
                        )
                        for item in candidates
                    ],
                    True,
                )
            except RouteNotFoundError as exc:
                evaluated.append(exc)

            if index < len(candidates) - 1:
                await self._wait_between_requests()

        return evaluated, False

    async def _evaluate_candidates(
        self,
        origin_a: Place,
        origin_b: Place,
        candidates: list[Place],
        mode: RoutingMode,
    ) -> list[CandidateResult | Exception]:
        results = await asyncio.gather(
            *(
                self._evaluate(
                    origin_a,
                    origin_b,
                    candidate,
                    mode,
                )
                for candidate in candidates
            ),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(
                result,
                (
                    CandidateResult,
                    RouteNotFoundError,
                    ProviderUnavailableError,
                ),
            ):
                continue

            if isinstance(result, BaseException):
                raise result

        return [
            result
            for result in results
            if isinstance(
                result,
                (
                    CandidateResult,
                    RouteNotFoundError,
                    ProviderUnavailableError,
                ),
            )
        ]

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
            await self._wait_between_requests()
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

    def _is_transit_result_fair(
        self,
        result: CandidateResult,
    ) -> bool:
        if (
            result.difference_minutes
            <= MAX_TRANSIT_DIFFERENCE_MINUTES
        ):
            return True

        longest_time = max(
            result.time_a_minutes,
            result.time_b_minutes,
        )

        return (
            result.difference_minutes / longest_time
            <= MAX_TRANSIT_DIFFERENCE_RATIO
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
            round(
                (
                    distance
                    / ESTIMATED_TRANSIT_SPEED_KMH
                )
                * 60
                + ESTIMATED_TRANSIT_WAIT_MINUTES
            ),
        )

    async def _wait_between_requests(self) -> None:
        if self.transit_request_delay_seconds > 0:
            await asyncio.sleep(
                self.transit_request_delay_seconds
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
    if count < 3:
        raise ValueError(
            "Количество кандидатов должно быть "
            "не меньше трёх"
        )

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