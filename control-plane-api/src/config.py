"""Configuration settings for Control-Plane API

All settings can be overridden via environment variables.
For Kubernetes deployments, set these in ConfigMaps/Secrets.
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import json
import os

# Base domain - used to construct default URLs
_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")

class Settings(BaseSettings):
    # Application
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # dev, staging, production

    # Base domain for URL construction
    BASE_DOMAIN: str = _BASE_DOMAIN

    # Keycloak Authentication
    KEYCLOAK_URL: str = f"https://auth.{_BASE_DOMAIN}"
    KEYCLOAK_REALM: str = "stoa"
    KEYCLOAK_CLIENT_ID: str = "control-plane-api"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_VERIFY_SSL: bool = True

    # Keycloak Admin API (for Service Account management)
    # Uses a dedicated admin client with realm-management roles
    KEYCLOAK_ADMIN_CLIENT_ID: str = "admin-cli"
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = ""

    # GitLab Integration
    GITLAB_URL: str = "https://gitlab.com"
    GITLAB_TOKEN: str = ""
    GITLAB_WEBHOOK_SECRET: str = ""
    GITLAB_DEFAULT_BRANCH: str = "main"

    # GitLab Project ID - primary project for API catalog (stoa-catalog)
    # This is the main project ID used by git_service for tenant/API operations
    # Can be set via GITLAB_PROJECT_ID env var (for backward compatibility)
    # or GITLAB_CATALOG_PROJECT_ID (explicit naming)
    GITLAB_PROJECT_ID: str = ""  # Set via env - defaults to stoa-catalog
    GITLAB_CATALOG_PROJECT_PATH: str = "cab6961310/stoa-catalog"

    # stoa-gitops: Infrastructure configs, policies, Ansible playbooks (secondary)
    GITLAB_GITOPS_PROJECT_ID: str = "77260481"  # cab6961310/stoa-gitops
    GITLAB_GITOPS_PROJECT_PATH: str = "cab6961310/stoa-gitops"

    # Alias for catalog project ID (for code clarity)
    @property
    def GITLAB_CATALOG_PROJECT_ID(self) -> str:
        return self.GITLAB_PROJECT_ID

    @property
    def GITLAB_PROJECT_PATH(self) -> str:
        return self.GITLAB_CATALOG_PROJECT_PATH

    # Kafka/Redpanda Event Streaming
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda.stoa-system.svc.cluster.local:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    KAFKA_SASL_MECHANISM: str = ""  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""

    # AWX Automation
    AWX_URL: str = f"https://awx.{_BASE_DOMAIN}"
    AWX_TOKEN: str = ""
    AWX_VERIFY_SSL: bool = True

    # API Gateway
    GATEWAY_URL: str = f"https://gateway.{_BASE_DOMAIN}"
    GATEWAY_ADMIN_USER: str = "Administrator"
    GATEWAY_ADMIN_PASSWORD: str = ""

    # Gateway Admin Proxy API (OIDC secured)
    # Uses the Gateway-Admin-API proxy instead of direct Basic Auth
    GATEWAY_ADMIN_PROXY_URL: str = f"https://apis.{_BASE_DOMAIN}/gateway/Gateway-Admin-API/1.0"
    GATEWAY_USE_OIDC_PROXY: bool = True  # Set to False to use Basic Auth directly

    # MCP Gateway URL (for tools proxy)
    # Default to internal K8s service, can be overridden for external access
    MCP_GATEWAY_URL: str = "http://mcp-gateway.stoa-system.svc.cluster.local:80"

    # ArgoCD (GitOps Observability - CAB-654)
    # Uses OIDC authentication - forwards user's Keycloak token to ArgoCD
    ARGOCD_URL: str = f"https://argocd.{_BASE_DOMAIN}"
    ARGOCD_VERIFY_SSL: bool = True
    ARGOCD_PLATFORM_APPS: str = "control-plane-api,control-plane-ui,stoa-portal,mcp-gateway,devportal"

    # External Observability URLs (CAB-654)
    GRAFANA_URL: str = f"https://grafana.{_BASE_DOMAIN}"
    PROMETHEUS_URL: str = f"https://prometheus.{_BASE_DOMAIN}"
    LOGS_URL: str = f"https://grafana.{_BASE_DOMAIN}/explore"

    # Prometheus Internal API (CAB-840) - for direct PromQL queries
    PROMETHEUS_INTERNAL_URL: str = "http://prometheus:9090"
    PROMETHEUS_TIMEOUT_SECONDS: int = 30
    PROMETHEUS_ENABLED: bool = True

    # Loki Internal API (CAB-840) - for direct LogQL queries
    LOKI_INTERNAL_URL: str = "http://loki:3100"
    LOKI_TIMEOUT_SECONDS: int = 30
    LOKI_ENABLED: bool = True

    # CORS - comma-separated list of allowed origins
    CORS_ORIGINS: str = f"https://console.{_BASE_DOMAIN},http://localhost:3000,http://localhost:5173"

    # Certificate Provisioning (CAB-865)
    CERTIFICATE_PROVIDER: str = "mock"  # mock | vault
    CERTIFICATE_KEY_SIZE: int = 4096
    CERTIFICATE_VALIDITY_DAYS: int = 365

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Logging - Basic Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json, text
    LOG_COMPONENTS: str = "{}"  # JSON dict of component:level overrides

    # Logging - Middleware Enable/Disable
    LOG_HTTP_MIDDLEWARE_ENABLED: bool = True  # Set to False to disable HTTP logging middleware

    # Logging - HTTP Debug
    LOG_DEBUG_HTTP_REQUESTS: bool = False
    LOG_DEBUG_HTTP_RESPONSES: bool = False
    LOG_DEBUG_HTTP_HEADERS: bool = False
    LOG_DEBUG_HTTP_BODY: bool = False

    # Logging - SSL Debug
    LOG_DEBUG_SSL_HANDSHAKE: bool = False
    LOG_DEBUG_SSL_CERTIFICATES: bool = False

    # Logging - Kafka Debug
    LOG_DEBUG_KAFKA_MESSAGES: bool = False
    LOG_DEBUG_KAFKA_CONSUMER: bool = False
    LOG_DEBUG_KAFKA_PRODUCER: bool = False

    # Logging - SQL Debug
    LOG_DEBUG_SQL_QUERIES: bool = False
    LOG_DEBUG_SQL_RESULTS: bool = False
    LOG_DEBUG_SQL_TRANSACTIONS: bool = False

    # Logging - Auth Debug
    LOG_DEBUG_AUTH_TOKENS: bool = False
    LOG_DEBUG_AUTH_HEADERS: bool = False
    LOG_DEBUG_AUTH_PAYLOAD: bool = False

    # Logging - External Services Debug
    LOG_DEBUG_AWX_API: bool = False
    LOG_DEBUG_GITLAB_API: bool = False
    LOG_DEBUG_KEYCLOAK_API: bool = False
    LOG_DEBUG_GATEWAY_API: bool = False

    # Logging - Tracing
    LOG_TRACE_ENABLED: bool = False
    LOG_TRACE_SAMPLE_RATE: float = 0.1
    LOG_TRACE_EXPORT_ENDPOINT: str = ""

    # Logging - Context
    LOG_CONTEXT_TENANT_ID: bool = True
    LOG_CONTEXT_USER_ID: bool = True
    LOG_CONTEXT_REQUEST_ID: bool = True
    LOG_CONTEXT_TRACE_ID: bool = True

    # Logging - Filtering
    LOG_EXCLUDE_PATHS: str = '["/health", "/healthz", "/ready", "/metrics"]'
    LOG_SLOW_REQUEST_THRESHOLD_MS: int = 1000
    LOG_ACCESS_SAMPLE_RATE: float = 1.0

    # Logging - Masking
    LOG_MASKING_ENABLED: bool = True
    LOG_MASKING_PATTERNS: str = '["password", "secret", "token", "api_key", "authorization"]'

    # Database (PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa"
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 10

    @property
    def database_url_sync(self) -> str:
        """Return sync database URL for Alembic migrations"""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @property
    def argocd_platform_apps_list(self) -> List[str]:
        """Return ARGOCD_PLATFORM_APPS as a list"""
        if isinstance(self.ARGOCD_PLATFORM_APPS, list):
            return self.ARGOCD_PLATFORM_APPS
        return [app.strip() for app in self.ARGOCD_PLATFORM_APPS.split(",") if app.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        """Return CORS origins as a list"""
        if isinstance(self.CORS_ORIGINS, list):
            return self.CORS_ORIGINS
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def log_components_dict(self) -> dict:
        """Return LOG_COMPONENTS as a dict"""
        try:
            return json.loads(self.LOG_COMPONENTS)
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def log_exclude_paths_list(self) -> List[str]:
        """Return LOG_EXCLUDE_PATHS as a list"""
        try:
            return json.loads(self.LOG_EXCLUDE_PATHS)
        except (json.JSONDecodeError, TypeError):
            return ["/health", "/healthz", "/ready", "/metrics"]

    @property
    def log_masking_patterns_list(self) -> List[str]:
        """Return LOG_MASKING_PATTERNS as a list"""
        try:
            return json.loads(self.LOG_MASKING_PATTERNS)
        except (json.JSONDecodeError, TypeError):
            return ["password", "secret", "token", "api_key", "authorization"]

    class Config:
        env_file = ".env"

settings = Settings()
