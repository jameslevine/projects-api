"""Runtime configuration, sourced from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings are injected by Terraform as Lambda environment variables.

    Locally, they can be set via the shell or a `.env` file.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Literal["local", "dev", "prod"] = "local"
    service_name: str = "projects-api"
    table_name: str = "projects-local"
    aws_region: str = "eu-west-2"
    dynamodb_endpoint: str | None = None
    log_level: str = "INFO"

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
