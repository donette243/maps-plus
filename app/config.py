from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Я.Карты++"
    app_version: str = "1.0.0"
    contact_email: str = "portfolio@example.com"
    dgis_api_key: str = ""
    dgis_catalog_url: str = "https://catalog.api.2gis.com/3.0"
    dgis_routing_url: str = "https://routing.api.2gis.com"
    osrm_url: str = "https://router.project-osrm.org"
    request_timeout_seconds: float = 30.0
    candidate_count: int = 7
    default_routing_mode: str = "transit"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def user_agent(self) -> str:
        return f"yandex-maps-plus/{self.app_version} ({self.contact_email})"


@lru_cache
def get_settings() -> Settings:
    return Settings()