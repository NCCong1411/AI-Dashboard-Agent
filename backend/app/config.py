"""Typed runtime configuration for the local backend."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime settings. Database URLs remain optional for the health-only app."""

    app_env: Literal["development", "test", "production"]
    app_name: str = "AI Dashboard Agent API"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    frontend_origin: str = "http://localhost:3000"
    session_cookie_name: str = "dashboard_session"
    session_ttl_seconds: int = Field(default=28800, ge=300, le=604800)
    runtime_database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None
    reader_all_database_url: SecretStr | None = None
    reader_ca_database_url: SecretStr | None = None
    reader_tx_database_url: SecretStr | None = None
    seed_builder_all_password: SecretStr | None = None
    seed_viewer_all_password: SecretStr | None = None
    seed_viewer_ca_password: SecretStr | None = None
    seed_builder_tx_password: SecretStr | None = None
    migration_backup_verified: bool = False

    @field_validator(
        "runtime_database_url",
        "migration_database_url",
        "reader_all_database_url",
        "reader_ca_database_url",
        "reader_tx_database_url",
        "seed_builder_all_password",
        "seed_viewer_all_password",
        "seed_viewer_ca_password",
        "seed_builder_tx_password",
        mode="before",
    )
    @classmethod
    def blank_database_url_is_unset(cls, value: object) -> object:
        """Treat blank example-file values as absent credentials."""
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value
        if isinstance(value, str) and not value.strip():
            return None
        return value

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Load and validate configuration once per process."""

    return Settings()

