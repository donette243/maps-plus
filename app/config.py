from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Я.Карты++"
    app_version: str = "1.0.0"
    contact_email: str = "portfolio@example.com"
    dgis_api_key: SecretStr = SecretStr("")
    dgis_catalog_url: str = (
        "https://catalog.api.2gis.com/3.0"
    )
    dgis_routing_url: str = (
        "https://routing.api.2gis.com"
    )
    osrm_url: str = (
        "https://router.project-osrm.org"
    )
    hh_metro_url: str = "https://api.hh.ru/metro/1"
    request_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        le=120,
    )
    candidate_count: int = Field(
        default=7,
        ge=3,
        le=11,
    )
    transit_request_delay_seconds: float = Field(
        default=0.6,
        ge=0,
        le=5,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "dgis_catalog_url",
        "dgis_routing_url",
        "osrm_url",
        "hh_metro_url",
        mode="before",
    )
    @classmethod
    def validate_service_url(
        cls,
        value: object,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                "Адрес внешнего сервиса должен быть строкой"
            )

        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            raise ValueError(
                "Некорректный адрес внешнего сервиса"
            )

        return normalized

    @property
    def dgis_key(self) -> str:
        return self.dgis_api_key.get_secret_value()

    @property
    def user_agent(self) -> str:
        return (
            f"yandex-maps-plus/{self.app_version} "
            f"({self.contact_email})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()