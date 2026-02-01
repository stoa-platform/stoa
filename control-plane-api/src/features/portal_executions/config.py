"""Portal Executions feature configuration.

CAB-432: Configuration loaded from environment variables.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PortalExecutionsSettings(BaseSettings):
    """Configuration for portal executions feature.

    All settings can be overridden via environment variables
    with the STOA_PORTAL_EXECUTIONS_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="STOA_PORTAL_EXECUTIONS_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(
        default=True,
        description="Enable/disable portal executions feature",
    )

    error_window_hours: int = Field(
        default=24,
        description="Hours to look back for recent errors",
    )

    max_errors: int = Field(
        default=50,
        description="Maximum number of recent errors to return",
    )


@lru_cache
def get_portal_executions_settings() -> PortalExecutionsSettings:
    """Get cached portal executions settings instance."""
    return PortalExecutionsSettings()
