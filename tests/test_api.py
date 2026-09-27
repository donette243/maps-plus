from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_meeting_service
from app.exceptions import (
    PlaceNotFoundError,
    ProviderUnavailableError,
)
from app.main import app
from app.models import (
    CandidateResult,
    MeetingResponse,
    Place,
    RouteProvider,
    RoutingMode,
)
from app.services.meeting import MeetingPointService


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Я.Карты++" in response.text


def test_meeting_point_success() -> None:
    origin_a = Place(
        name="Москва, Арбат, 10",
        latitude=55.752,
        longitude=37.604,
    )
    origin_b = Place(
        name="Москва, Тверская, 15",
        latitude=55.768,
        longitude=37.605,
    )
    meeting_place = Place(
        name="Метро Тверская",
        latitude=55.765,
        longitude=37.606,
    )
    service = AsyncMock(
        spec=MeetingPointService
    )
    service.find.return_value = MeetingResponse(
        origin_a=origin_a,
        origin_b=origin_b,
        best_meeting_point=CandidateResult(
            place=meeting_place,
            time_a_minutes=12,
            time_b_minutes=11,
            difference_minutes=1,
            total_minutes=23,
        ),
        alternatives=[],
        mode=RoutingMode.TRANSIT,
        provider=RouteProvider.DGIS,
    )
    app.dependency_overrides[
        get_meeting_service
    ] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/meeting-points",
            json={
                "participant_a": (
                    "Москва, Арбат, 10"
                ),
                "participant_b": (
                    "Москва, Тверская, 15"
                ),
                "mode": "transit",
            },
        )

    assert response.status_code == 200
    assert (
        response.json()["best_meeting_point"]
        ["place"]["name"]
        == "Метро Тверская"
    )
    service.find.assert_awaited_once()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "participant_a": " ",
            "participant_b": "Москва, Арбат, 10",
        },
        {
            "participant_a": "Москва",
            "participant_b": "  Москва  ",
        },
        {
            "participant_a": "Москва, Арбат, 10",
            "participant_b": "Москва, Тверская, 15",
            "mode": "plane",
        },
        {
            "participant_a": "Москва, Арбат, 10",
            "participant_b": "Москва, Тверская, 15",
            "candidate_count": 2,
        },
        {
            "participant_a": "Москва, Арбат, 10",
            "participant_b": "Москва, Тверская, 15",
            "unknown": "value",
        },
    ],
)
def test_meeting_point_validation_error(
    payload: dict[str, object],
) -> None:
    service = AsyncMock(
        spec=MeetingPointService
    )
    app.dependency_overrides[
        get_meeting_service
    ] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/meeting-points",
            json=payload,
        )

    assert response.status_code == 422
    service.find.assert_not_awaited()


def test_place_not_found_error() -> None:
    service = AsyncMock(
        spec=MeetingPointService
    )
    service.find.side_effect = PlaceNotFoundError(
        "Адрес не найден"
    )
    app.dependency_overrides[
        get_meeting_service
    ] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/meeting-points",
            json={
                "participant_a": "Неизвестный адрес 1",
                "participant_b": "Неизвестный адрес 2",
            },
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Адрес не найден"
    }


def test_provider_error_hides_sensitive_data(
) -> None:
    service = AsyncMock(
        spec=MeetingPointService
    )
    service.find.side_effect = (
        ProviderUnavailableError(
            "key=secret-test-key"
        )
    )
    app.dependency_overrides[
        get_meeting_service
    ] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/api/meeting-points",
            json={
                "participant_a": "Москва, Арбат, 10",
                "participant_b": (
                    "Москва, Тверская, 15"
                ),
            },
        )

    assert response.status_code == 503
    assert "secret-test-key" not in response.text


def test_http_error_hides_sensitive_data() -> None:
    service = AsyncMock(
        spec=MeetingPointService
    )
    request = httpx.Request(
        "GET",
        "https://provider.test/?key=secret-test-key",
    )
    response = httpx.Response(
        status_code=500,
        request=request,
    )
    service.find.side_effect = httpx.HTTPStatusError(
        "key=secret-test-key",
        request=request,
        response=response,
    )
    app.dependency_overrides[
        get_meeting_service
    ] = lambda: service

    with TestClient(app) as client:
        api_response = client.post(
            "/api/meeting-points",
            json={
                "participant_a": "Москва, Арбат, 10",
                "participant_b": (
                    "Москва, Тверская, 15"
                ),
            },
        )

    assert api_response.status_code == 502
    assert "secret-test-key" not in api_response.text