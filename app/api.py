from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from app.dependencies import (
    build_meeting_service,
    get_http_client,
)
from app.models import MeetingRequest, MeetingResponse

router = APIRouter(
    prefix="/api",
    tags=["Точки встречи"],
)


@router.get(
    "/health",
    summary="Проверка состояния приложения",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/meeting-points",
    response_model=MeetingResponse,
    summary="Поиск оптимального места встречи",
)
async def find_meeting_point(
    payload: MeetingRequest,
    client: Annotated[
        httpx.AsyncClient,
        Depends(get_http_client),
    ],
) -> MeetingResponse:
    service = build_meeting_service(client)

    return await service.find(payload)
