from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class RoutingMode(StrEnum):
    TRANSIT = "transit"
    DRIVING = "driving"


class RouteProvider(StrEnum):
    DGIS = "2GIS"
    ESTIMATED = "Расчётное время по расстоянию"
    OSRM_DGIS = "OSRM + 2GIS"


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Place(Coordinates):
    name: str = Field(min_length=1, max_length=300)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return value.strip()

        return value


class MeetingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_a: str = Field(
        min_length=2,
        max_length=200,
    )
    participant_b: str = Field(
        min_length=2,
        max_length=200,
    )
    mode: RoutingMode = RoutingMode.TRANSIT
    candidate_count: int | None = Field(
        default=None,
        ge=3,
        le=11,
    )

    @field_validator(
        "participant_a",
        "participant_b",
        mode="before",
    )
    @classmethod
    def clean_address(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @model_validator(mode="after")
    def addresses_must_differ(
        self,
    ) -> "MeetingRequest":
        if (
            self.participant_a.casefold()
            == self.participant_b.casefold()
        ):
            raise ValueError(
                "Адреса участников должны отличаться"
            )

        return self


class CandidateResult(BaseModel):
    place: Place
    time_a_minutes: int = Field(ge=1)
    time_b_minutes: int = Field(ge=1)
    difference_minutes: int = Field(ge=0)
    total_minutes: int = Field(ge=2)

    @model_validator(mode="after")
    def validate_calculated_values(
        self,
    ) -> "CandidateResult":
        expected_difference = abs(
            self.time_a_minutes
            - self.time_b_minutes
        )
        expected_total = (
            self.time_a_minutes
            + self.time_b_minutes
        )

        if self.difference_minutes != expected_difference:
            raise ValueError(
                "Некорректная разница времени"
            )

        if self.total_minutes != expected_total:
            raise ValueError(
                "Некорректное суммарное время"
            )

        return self


class MeetingResponse(BaseModel):
    origin_a: Place
    origin_b: Place
    best_meeting_point: CandidateResult
    alternatives: list[CandidateResult]
    mode: RoutingMode
    provider: RouteProvider