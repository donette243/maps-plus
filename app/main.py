from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.dependencies import lifespan_http_client
from app.exceptions import MapsPlusError

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    async for client in lifespan_http_client():
        app.state.http_client = client
        yield


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(router)


@app.exception_handler(MapsPlusError)
async def maps_error_handler(
    _: Request,
    exc: MapsPlusError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(httpx.HTTPStatusError)
async def provider_status_error_handler(
    _: Request,
    exc: httpx.HTTPStatusError,
) -> JSONResponse:
    if exc.response.status_code == 429:
        detail = (
            "Сервис временно ограничил количество "
            "запросов. Подождите и попробуйте снова."
        )
    else:
        detail = (
            "Картографический сервис временно "
            "недоступен"
        )

    return JSONResponse(
        status_code=502,
        content={
            "detail": detail,
        },
    )


@app.exception_handler(httpx.HTTPError)
async def provider_error_handler(
    _: Request,
    __: httpx.HTTPError,
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "detail": (
                "Картографический сервис временно "
                "недоступен"
            ),
        },
    )


app.mount(
    "/",
    StaticFiles(
        directory=BASE_DIR / "static",
        html=True,
    ),
    name="static",
)