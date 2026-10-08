"""Environment-based configuration; credentials are never embedded in code."""

from pathlib import Path

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[1] / ".env",
        ),
        extra="ignore",
    )

    llm_api_key: str | None = None
    llm_provider: str = "demo"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    orchestrator_mode: Literal["mock", "staging", "production"] | None = None
    orchestrator_url: str | None = None
    careos_api_url: str | None = None
    orchestrator_timeout_seconds: float = 10.0
    orchestrator_token: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: float = 20.0
    live_voice_model: str = "gemini-3.8-live"
    log_level: str = "INFO"
    emergency_escalation_workflow: str | None = None

    @field_validator("app_env", "orchestrator_mode", mode="before")
    @classmethod
    def normalize_environment_names(cls, value: object) -> object:
        return value.casefold() if isinstance(value, str) else value

    @field_validator("orchestrator_timeout_seconds")
    @classmethod
    def validate_orchestrator_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ORCHESTRATOR_TIMEOUT_SECONDS must be positive")
        return value

settings = Settings()