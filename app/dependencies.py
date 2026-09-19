from collections.abc import AsyncIterator

import httpx
from fastapi import Request

from app.config import get_settings
from app.services.geocoding import DgisGeocoder
from app.services.meeting import MeetingPointService
from app.services.routing import Router
from app.services.stations import StationSearchService


async def get_http_client(
    request: Request,
) -> httpx.AsyncClient:
    return request.app.state.http_client


async def lifespan_http_client() -> AsyncIterator[
    httpx.AsyncClient
]:
    settings = get_settings()

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={
            "User-Agent": settings.user_agent,
        },
        follow_redirects=True,
        trust_env=False,
    ) as client:
        yield client


def build_meeting_service(
    client: httpx.AsyncClient,
) -> MeetingPointService:
    settings = get_settings()

    return MeetingPointService(
        geocoder=DgisGeocoder(client, settings),
        station_search=StationSearchService(
            client,
            settings,
        ),
        router=Router(client, settings),
        default_candidate_count=settings.candidate_count,
    )