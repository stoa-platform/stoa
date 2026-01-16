"""Application settings using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings.

    All settings can be overridden via environment variables.
    Uses BASE_DOMAIN as the single source of truth for URLs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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

    # Base domain for STOA platform (single source of truth)
    base_domain: str = "stoa.cab-i.com"

    # Keycloak Authentication
    keycloak_url: str = ""
    keycloak_realm: str = "stoa"
    keycloak_client_id: str = "stoa-mcp-gateway"
    keycloak_client_secret: str = ""
    keycloak_verify_ssl: bool = True
    keycloak_admin_password: str = ""  # Admin password for DCR client patching

    # Control Plane API
    control_plane_api_url: str = ""

    # Gateway (webMethods)
    gateway_url: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Observability
    enable_metrics: bool = True
    metrics_prefix: str = "stoa_mcp_gateway"
    enable_tracing: bool = True
    otlp_endpoint: str = ""
    otlp_service_name: str = "stoa-mcp-gateway"

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 1000
    rate_limit_burst: int = 50

    # MCP Configuration
    mcp_max_tools_per_request: int = 100
    mcp_timeout_seconds: int = 30
    mcp_enable_streaming: bool = True

    # Security
    cors_origins: str = "*"
    allowed_audiences: str = ""  # Comma-separated list

    # OPA Policy Engine
    opa_enabled: bool = True
    opa_url: str = "http://127.0.0.1:8181"  # OPA sidecar URL
    opa_embedded: bool = True  # Use embedded evaluator (no sidecar needed)
    opa_policy_path: str = "policies"  # Path to Rego policies

    # Metering & Billing
    metering_enabled: bool = True
    kafka_bootstrap_servers: str = "localhost:9092"
    metering_topic: str = "stoa.metering.events"
    metering_buffer_size: int = 100
    metering_flush_interval: float = 5.0

    # Kubernetes Integration
    k8s_watcher_enabled: bool = False  # Disabled by default (enable in K8s)
    k8s_watch_namespace: str | None = None  # None = all namespaces
    kubeconfig_path: str | None = None  # None = in-cluster config

    @model_validator(mode="after")
    def derive_urls_from_base_domain(self) -> "Settings":
        """Derive service URLs from base_domain if not explicitly set."""
        if not self.keycloak_url:
            object.__setattr__(self, "keycloak_url", f"https://auth.{self.base_domain}")
        if not self.control_plane_api_url:
            object.__setattr__(self, "control_plane_api_url", f"https://api.{self.base_domain}")
        if not self.gateway_url:
            object.__setattr__(self, "gateway_url", f"https://gateway.{self.base_domain}")
        return self

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_audiences_list(self) -> list[str]:
        """Return allowed audiences as a list."""
        if not self.allowed_audiences:
            return []
        return [aud.strip() for aud in self.allowed_audiences.split(",") if aud.strip()]

    @property
    def keycloak_issuer(self) -> str:
        """Return Keycloak issuer URL."""
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_jwks_uri(self) -> str:
        """Return Keycloak JWKS URI."""
        return f"{self.keycloak_issuer}/protocol/openid-connect/certs"

    @property
    def keycloak_token_endpoint(self) -> str:
        """Return Keycloak token endpoint."""
        return f"{self.keycloak_issuer}/protocol/openid-connect/token"

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "prod"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear the settings cache (useful for testing)."""
    get_settings.cache_clear()
