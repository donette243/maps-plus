from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class RoutingMode(StrEnum):
    TRANSIT = "transit"
    DRIVING = "driving"


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Place(Coordinates):
    name: str


class MeetingRequest(BaseModel):
    participant_a: str = Field(min_length=2, max_length=200)
    participant_b: str = Field(min_length=2, max_length=200)
    mode: RoutingMode = RoutingMode.TRANSIT
    candidate_count: int | None = Field(default=None, ge=3, le=11)

    @model_validator(mode="after")
    def addresses_must_differ(self) -> "MeetingRequest":
        if self.participant_a.strip().casefold() == self.participant_b.strip().casefold():
            raise ValueError("Адреса участников должны отличаться")
        return self


class CandidateResult(BaseModel):
    place: Place
    time_a_minutes: int
    time_b_minutes: int
    difference_minutes: int
    total_minutes: int


class MeetingResponse(BaseModel):
    origin_a: Place
    origin_b: Place
    best_meeting_point: CandidateResult
    alternatives: list[CandidateResult]
    mode: RoutingMode
    provider: str