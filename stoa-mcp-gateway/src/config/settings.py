"""Application settings using Pydantic Settings."""

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings.

    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "STOA MCP Gateway"
    app_version: str = "0.1.0"
    environment: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    workers: int = 1

    # Base domain for STOA platform
    base_domain: str = "stoa.cab-i.com"

    # Keycloak Authentication
    keycloak_url: str = ""
    keycloak_realm: str = "stoa"
    keycloak_client_id: str = "stoa-mcp-gateway"
    keycloak_client_secret: str = ""

    # Control Plane API
    control_plane_api_url: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Observability
    enable_metrics: bool = True
    enable_tracing: bool = True
    otlp_endpoint: str = ""

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 1000

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Derive URLs from base_domain if not explicitly set
        if not self.keycloak_url:
            self.keycloak_url = f"https://auth.{self.base_domain}"
        if not self.control_plane_api_url:
            self.control_plane_api_url = f"https://api.{self.base_domain}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
