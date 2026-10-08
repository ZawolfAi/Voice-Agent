from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BACKEND_ROOT / "careos.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(enable_decoding=False, env_file=BACKEND_ROOT / ".env")
    app_env: str = "development"
    app_name: str = "careos-api"
    deployment_name: str = "careos-local"
    api_prefix: str = "/api/v1"
    app_url: str = "http://localhost:5173"
    log_level: str = "INFO"
    metrics_enabled: bool = True
    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"
    secret_key: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    speech_to_text_provider: str = "unconfigured"
    speech_to_text_api_url: str = ""
    speech_to_text_api_key: str = ""
    speech_to_text_model: str = "gpt-4o-mini-transcribe"
    speech_to_text_language: str = "ar-EG"
    ai_provider: str = "voice_agent"
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    voice_agent_url: str = "http://127.0.0.1:8765"
    voice_agent_api_key: str = ""
    audio_retention_days: int = 30
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_audience: str = ""
    oidc_client_secret: str = ""
    saml_metadata_url: str = ""
    audit_retention_days: int = 2555
    backup_bucket: str = ""
    backup_region: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    email_max_retries: int = 3
    email_retry_backoff_seconds: float = 0.5
    auth_rate_limit_requests: int = 60
    auth_rate_limit_window_seconds: int = 60
    max_upload_bytes: int = 25 * 1024 * 1024
    allowed_upload_content_types: list[str] = ["application/pdf", "audio/webm", "audio/wav", "audio/mpeg", "image/png", "image/jpeg"]
    storage_backend: str = "filesystem"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    storage_prefix: str = "careos"
    sso_allowed_redirect_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "careos.example.com"]
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "testserver"]

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str:
        if not value or not value.strip():
            return f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"
        return value.strip()

    @field_validator("cors_origins", "allowed_hosts", "sso_allowed_redirect_hosts", "allowed_upload_content_types", mode="before")
    @classmethod
    def split_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.is_production and self.secret_key == "development-only-change-this-secret":
            raise ValueError("SECRET_KEY must be configured in production")
        if self.is_production and self.database_url.startswith("sqlite"):
            raise ValueError("Production requires PostgreSQL; SQLite is development-only")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
