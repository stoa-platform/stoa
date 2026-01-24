"""Application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="STOA_", env_file=".env", extra="ignore")

    # Application
    app_name: str = "stoa-control-plane"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "stoa"
    db_user: str = "stoa"
    db_password: str = "stoa-quickstart-secret"

    # Invite settings
    invite_expiry_days: int = 7
    invite_base_url: str = "https://demo.gostoa.dev"
    portal_url: str = "https://portal.gostoa.dev"

    # Rate limiting
    rate_limit_invites: str = "10/minute"

    @property
    def database_url(self) -> str:
        """Construct async database URL."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct sync database URL for Alembic migrations."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
