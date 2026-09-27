from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.dependencies import lifespan_http_client
from app.exceptions import (
    ConfigurationError,
    MapsPlusError,
    PlaceNotFoundError,
    ProviderQuotaExceededError,
    ProviderUnavailableError,
    RouteNotFoundError,
)
from app.services.metro import MetroCatalogService

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    settings = get_settings()

    async with lifespan_http_client() as client:
        app.state.http_client = client
        app.state.metro_catalog = (
            MetroCatalogService(
                client,
                settings,
            )
        )
        yield


async def place_not_found_handler(
    _: Request,
    exc: PlaceNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": str(exc),
        },
    )


async def route_not_found_handler(
    _: Request,
    exc: RouteNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        content={
            "detail": str(exc),
        },
    )


async def quota_error_handler(
    _: Request,
    __: ProviderQuotaExceededError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "detail": (
                "Лимит внешнего картографического "
                "сервиса временно исчерпан"
            ),
        },
    )


async def configuration_error_handler(
    _: Request,
    exc: ConfigurationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "detail": str(exc),
        },
    )


async def provider_error_handler(
    _: Request,
    __: ProviderUnavailableError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "detail": (
                "Картографический сервис временно "
                "недоступен"
            ),
        },
    )


async def maps_error_handler(
    _: Request,
    exc: MapsPlusError,
) -> JSONResponse:
    return JSONResponse(
        status_code=(
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        content={
            "detail": str(exc),
        },
    )


async def http_error_handler(
    _: Request,
    __: httpx.HTTPError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "detail": (
                "Ошибка соединения с внешним сервисом"
            ),
        },
    )


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.include_router(router)
    application.add_exception_handler(
        PlaceNotFoundError,
        place_not_found_handler,
    )
    application.add_exception_handler(
        RouteNotFoundError,
        route_not_found_handler,
    )
    application.add_exception_handler(
        ProviderQuotaExceededError,
        quota_error_handler,
    )
    application.add_exception_handler(
        ConfigurationError,
        configuration_error_handler,
    )
    application.add_exception_handler(
        ProviderUnavailableError,
        provider_error_handler,
    )
    application.add_exception_handler(
        MapsPlusError,
        maps_error_handler,
    )
    application.add_exception_handler(
        httpx.HTTPError,
        http_error_handler,
    )
    application.mount(
        "/",
        StaticFiles(
            directory=BASE_DIR / "static",
            html=True,
        ),
        name="static",
    )

    return application


app = create_app()