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
    base_domain: str = "gostoa.dev"

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
    # CAB-950: CORS origins whitelist
    # SECURITY: Never use "*" in production!
    # Comma-separated list of allowed origins
    cors_origins: str = "https://console.stoa.dev,https://portal.stoa.dev,https://console.gostoa.dev,https://portal.gostoa.dev"
    # CAB-950: Additional CORS settings for defense in depth
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
    cors_allow_headers: str = "Authorization,Content-Type,X-Request-ID,X-Tenant-ID"
    cors_expose_headers: str = "X-Request-ID,X-Trace-ID"
    cors_max_age: int = 600  # Preflight cache: 10 minutes

    # CAB-938: JWT Audience validation
    # SECURITY: Set this to your MCP Gateway client ID in Keycloak
    # If empty, audience validation is DISABLED (insecure for production!)
    # Includes 'account' for Keycloak backwards compatibility
    allowed_audiences: str = "stoa-mcp-gateway,account"

    # OPA Policy Engine (RBAC - who can call tools)
    opa_enabled: bool = True
    opa_url: str = "http://127.0.0.1:8181"  # OPA sidecar URL
    opa_embedded: bool = True  # Use embedded evaluator (no sidecar needed)
    opa_policy_path: str = "policies"  # Path to Rego policies

    # Argument Policy Engine (business rules - what argument values are allowed)
    argument_policy_enabled: bool = True
    argument_policy_path: str = "src/policy/rules"  # Path to YAML policy files
    argument_policy_fail_closed: bool = True  # Block all if policy load fails

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

    # Feature Flags (CAB-605)
    enable_demo_tools: bool = False  # Enable RPO Easter egg tools (demo environments only)
    use_tenant_scoped_tools: bool = False  # Phase 2: Tenant-scoped tool naming (removes tenant prefix)

    # External MCP Servers (Linear, GitHub, Slack, etc.)
    external_servers_enabled: bool = True  # Enable external MCP server proxying
    external_server_poll_interval: int = 60  # Seconds between polling Control Plane API
    external_server_api_key: str = ""  # API key for internal endpoint auth (optional)

    # Token Optimization (CAB-881)
    token_counter_enabled: bool = True  # Enable token counting middleware
    token_counter_queue_size: int = 10_000  # Max queue size before dropping
    response_transformer_enabled: bool = True  # Enable response transformer middleware
    semantic_cache_enabled: bool = True  # Enable semantic cache middleware
    semantic_cache_ttl_seconds: int = 300  # Cache TTL (5 minutes)
    semantic_cache_similarity: float = 0.95  # Cosine similarity threshold
    semantic_cache_cleanup_interval: int = 60  # Cleanup interval in seconds
    semantic_cache_gdpr_max_age_hours: int = 24  # GDPR hard-delete age

    # Shadow Mode Configuration (Python → Rust Migration)
    shadow_mode_enabled: bool = False  # Enable shadow traffic to Rust gateway
    shadow_rust_gateway_url: str = "http://mcp-gateway-rust:8080"  # Rust gateway URL
    shadow_timeout_seconds: float = 5.0  # Timeout for shadow requests

    # CAB-939: SSE Connection Limits (Slowloris protection)
    sse_limiter_enabled: bool = True  # Enable SSE rate limiting (set to false for rollback)
    # SECURITY: Set to your ingress controller IPs, e.g., "10.100.0.0/16"
    # Empty = trust nothing (safest default, uses direct client IP)
    sse_trusted_proxies: str = ""

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
        """Return CORS origins as a list.

        CAB-950: Logs warning if wildcard is used (insecure).
        """
        if self.cors_origins == "*":
            # CAB-950: Warn but don't break for dev environments
            import logging
            logging.getLogger(__name__).warning(
                "CAB-950: CORS wildcard '*' is insecure! Set specific origins in production."
            )
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
