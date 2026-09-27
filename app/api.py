from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_meeting_service
from app.models import MeetingRequest, MeetingResponse
from app.services.meeting import MeetingPointService

router = APIRouter(
    prefix="/api",
    tags=["Точки встречи"],
)

MeetingServiceDependency = Annotated[
    MeetingPointService,
    Depends(get_meeting_service),
]


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
    responses={
        404: {
            "description": "Адрес или станция не найдены",
        },
        422: {
            "description": "Некорректные входные данные",
        },
        503: {
            "description": (
                "Внешний сервис временно недоступен"
            ),
        },
    },
)
async def find_meeting_point(
    payload: MeetingRequest,
    service: MeetingServiceDependency,
) -> MeetingResponse:
    return await service.find(payload)