"""Environment-only runtime configuration with safe offline defaults."""

from decimal import Decimal
from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(StrEnum):
    FAKE = "fake"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    model_provider: ProviderName = Field(
        default=ProviderName.FAKE, validation_alias="SLAM_MODEL_PROVIDER"
    )
    model: str = Field(default="fake-structured-v1", validation_alias="SLAM_MODEL")
    api_timeout_seconds: int = Field(
        default=60, ge=1, le=600, validation_alias="SLAM_API_TIMEOUT_SECONDS"
    )
    api_max_retries: int = Field(
        default=2, ge=0, le=2, validation_alias="SLAM_API_MAX_RETRIES"
    )
    api_max_concurrency: int = Field(
        default=4, ge=1, le=32, validation_alias="SLAM_API_MAX_CONCURRENCY"
    )
    api_budget_usd: Decimal = Field(
        default=Decimal("0"), ge=0, validation_alias="SLAM_API_BUDGET_USD"
    )
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")

    @model_validator(mode="after")
    def validate_real_provider_controls(self) -> "Settings":
        if self.model_provider is ProviderName.OPENAI:
            if self.openai_api_key is None or not self.openai_api_key.get_secret_value():
                raise ValueError("OPENAI_API_KEY is required when SLAM_MODEL_PROVIDER=openai")
            if self.api_budget_usd <= 0:
                raise ValueError("a positive SLAM_API_BUDGET_USD is required for API calls")
            if self.model.startswith("fake-"):
                raise ValueError("an explicit non-fake model is required for API calls")
        return self
