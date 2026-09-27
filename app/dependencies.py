from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.config import get_settings
from app.services.geocoding import DgisGeocoder
from app.services.meeting import MeetingPointService
from app.services.metro import MetroCatalogService
from app.services.routing import Router
from app.services.stations import StationSearchService


def get_http_client(
    request: Request,
) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_metro_catalog(
    request: Request,
) -> MetroCatalogService:
    return request.app.state.metro_catalog


@asynccontextmanager
async def lifespan_http_client() -> AsyncIterator[
    httpx.AsyncClient
]:
    settings = get_settings()

    async with httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers={
            "User-Agent": settings.user_agent,
            "Accept": "application/json",
        },
        follow_redirects=True,
        trust_env=False,
    ) as client:
        yield client


def build_meeting_service(
    client: httpx.AsyncClient,
    metro_catalog: MetroCatalogService,
) -> MeetingPointService:
    settings = get_settings()

    return MeetingPointService(
        geocoder=DgisGeocoder(
            client,
            settings,
            metro_catalog,
        ),
        station_search=StationSearchService(
            metro_catalog,
        ),
        router=Router(
            client,
            settings,
        ),
        default_candidate_count=(
            settings.candidate_count
        ),
        transit_request_delay_seconds=(
            settings.transit_request_delay_seconds
        ),
    )


def get_meeting_service(
    client: Annotated[
        httpx.AsyncClient,
        Depends(get_http_client),
    ],
    metro_catalog: Annotated[
        MetroCatalogService,
        Depends(get_metro_catalog),
    ],
) -> MeetingPointService:
    return build_meeting_service(
        client,
        metro_catalog,
    )