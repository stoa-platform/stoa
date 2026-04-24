"""Configuration settings for Control-Plane API

All settings can be overridden via environment variables.
For Kubernetes deployments, set these in ConfigMaps/Secrets.
"""

import json
import logging
import os
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings

# Base domain - used to construct default URLs
_BASE_DOMAIN = os.getenv("BASE_DOMAIN", "gostoa.dev")

_logger = logging.getLogger(__name__)

# CAB-2145: flags that emit credential-grade data (raw JWT tokens, decoded
# JWT payload, Authorization/Cookie headers, raw request bodies). They must
# never be `True` in production. Adding a new flag to this list is enough to
# make the startup validator enforce the gate.
SENSITIVE_DEBUG_FLAGS_IN_PROD: tuple[str, ...] = (
    "LOG_DEBUG_AUTH_TOKENS",
    "LOG_DEBUG_AUTH_HEADERS",
    "LOG_DEBUG_AUTH_PAYLOAD",
    "LOG_DEBUG_HTTP_BODY",
    "LOG_DEBUG_HTTP_HEADERS",
)

# CAB-1889 CP-2: startup validation gate. Activated in C.3 once all consumers
# migrated to `settings.git.*` (verified by scripts/check_git_config_access.sh).
_VALIDATE_GIT_CONFIG: bool = True


class GitHubConfig(BaseModel):
    """GitHub provider config — hydrated from flat env vars by Settings validator."""

    token: SecretStr = Field(default=SecretStr(""))
    org: str = "stoa-platform"
    catalog_repo: str = "stoa-catalog"
    webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def catalog_project_id(self) -> str:
        """Provider-agnostic project identifier: 'org/repo'."""
        return f"{self.org}/{self.catalog_repo}"


class GitLabConfig(BaseModel):
    """GitLab provider config — hydrated from flat env vars by Settings validator."""

    url: str = "https://gitlab.com"
    token: SecretStr = Field(default=SecretStr(""))
    project_id: str = ""
    webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def catalog_project_id(self) -> str:
        return self.project_id


class GitProviderConfig(BaseModel):
    """Single entry point for Git provider config.

    Consumers must read from ``settings.git.*`` only. A grep gate in CI
    enforces this (see ``scripts/check_git_config_access.sh``).
    """

    provider: Literal["github", "gitlab"] = "github"
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    gitlab: GitLabConfig = Field(default_factory=GitLabConfig)
    # CP-1 P2 (M.4): catalog repo default branch. Provider-agnostic because
    # the catalog is a single repo regardless of provider. Hydrated from
    # ``GIT_DEFAULT_BRANCH`` env var; keep ``"main"`` as the default so
    # omitted config is a no-op.
    default_branch: str = "main"

    @property
    def active_catalog_project_id(self) -> str:
        """Provider-agnostic ``project_id`` for the currently selected provider."""
        if self.provider == "github":
            return self.github.catalog_project_id
        return self.gitlab.catalog_project_id


class Settings(BaseSettings):
    # Application
    VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # dev, staging, production
    STOA_EDITION: str = "community"  # community, standard, enterprise (Open Core model)

    # Base domain for URL construction
    BASE_DOMAIN: str = _BASE_DOMAIN

    # Keycloak Authentication
    # KEYCLOAK_URL is the PUBLIC URL Keycloak embeds in token `iss` claims
    # (e.g. https://auth.gostoa.dev). Must match what clients see — used for
    # issuer validation and for the `token_endpoint` returned to external
    # consumers. CAB-2094: previously set to the in-cluster svc URL in prod,
    # which broke issuer validation for every user token.
    # KEYCLOAK_INTERNAL_URL is the in-cluster service URL used for backend-to-KC
    # calls (admin API, token exchange, JWKS fetch). Avoids hairpin NAT on
    # OVH MKS and similar cloud providers. Falls back to KEYCLOAK_URL when
    # unset. Mirrors the stoa-gateway STOA_KEYCLOAK_URL / _INTERNAL_URL pattern.
    KEYCLOAK_URL: str = f"https://auth.{_BASE_DOMAIN}"
    KEYCLOAK_INTERNAL_URL: str = ""
    KEYCLOAK_REALM: str = "stoa"
    KEYCLOAK_CLIENT_ID: str = "control-plane-api"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_VERIFY_SSL: bool = True

    @property
    def keycloak_internal_url(self) -> str:
        """Return internal URL for backend-to-KC calls, falling back to public URL."""
        return self.KEYCLOAK_INTERNAL_URL or self.KEYCLOAK_URL

    # Keycloak Admin API (for Service Account management)
    # Uses a dedicated admin client with realm-management roles
    KEYCLOAK_ADMIN_CLIENT_ID: str = "admin-cli"
    # Accepts KEYCLOAK_ADMIN_CLIENT_SECRET or KEYCLOAK_ADMIN_PASSWORD env var
    KEYCLOAK_ADMIN_CLIENT_SECRET: str = os.getenv(
        "KEYCLOAK_ADMIN_CLIENT_SECRET",
        os.getenv("KEYCLOAK_ADMIN_PASSWORD", ""),
    )

    # Slack Notifications (CAB-1413 — deployment event fanout)
    SLACK_WEBHOOK_URL: str = ""  # Incoming webhook URL (fallback)
    SLACK_BOT_TOKEN: str = ""  # Bot API token (preferred, supports threading)
    SLACK_CHANNEL_ID: str = ""  # Target channel ID for Bot API

    # ── Git Provider — legacy flat ingress (CAB-1889 CP-2) ───────────────
    # These 9 fields exist only so Pydantic Settings can hydrate them from
    # env vars, .env and K8s ConfigMap. They are `exclude=True` so they
    # never appear in model_dump() or JSON schema.
    #
    # Consumers MUST read `settings.git.*` instead. A grep gate in CI
    # enforces this (see scripts/check_git_config_access.sh).
    GIT_PROVIDER: Literal["github", "gitlab"] = Field(default="github", exclude=True)
    GITHUB_TOKEN: str = Field(default="", exclude=True)
    GITHUB_ORG: str = Field(default="stoa-platform", exclude=True)
    GITHUB_CATALOG_REPO: str = Field(default="stoa-catalog", exclude=True)
    GITHUB_WEBHOOK_SECRET: str = Field(default="", exclude=True)
    GITLAB_URL: str = Field(default="https://gitlab.com", exclude=True)
    GITLAB_TOKEN: str = Field(default="", exclude=True)
    GITLAB_PROJECT_ID: str = Field(default="", exclude=True)
    GITLAB_WEBHOOK_SECRET: str = Field(default="", exclude=True)
    # CP-1 P2 (M.4): catalog repo default branch, provider-agnostic.
    GIT_DEFAULT_BRANCH: str = Field(default="main", exclude=True)

    # ── Git Provider — single source of truth for consumers ──────────────
    git: GitProviderConfig = Field(default_factory=GitProviderConfig)

    # Kafka/Redpanda Event Streaming
    KAFKA_ENABLED: bool = True  # Set to False to skip Kafka health checks
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda.stoa-system.svc.cluster.local:9092"
    KAFKA_ADMIN_URL: str = "http://redpanda.stoa-system.svc.cluster.local:9644"  # Redpanda Admin API for quotas
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    KAFKA_SASL_MECHANISM: str = ""  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""

    # API Gateway
    GATEWAY_URL: str = f"https://vps-wm.{_BASE_DOMAIN}"
    GATEWAY_ADMIN_USER: str = "Administrator"
    GATEWAY_ADMIN_PASSWORD: str = ""

    # Gateway Admin Proxy API (OIDC secured)
    # Uses the Gateway-Admin-API proxy instead of direct Basic Auth
    GATEWAY_ADMIN_PROXY_URL: str = f"https://apis.{_BASE_DOMAIN}/gateway/Gateway-Admin-API/1.0"
    GATEWAY_USE_OIDC_PROXY: bool = True  # Set to False to use Basic Auth directly

    # MCP Gateway URL (for tools proxy)
    # Default to internal K8s service, can be overridden for external access
    MCP_GATEWAY_URL: str = "http://stoa-gateway.stoa-system.svc.cluster.local:80"

    # ArgoCD (GitOps Observability - CAB-654)
    # Uses static API token (stoa-api service account) for platform status
    ARGOCD_URL: str = f"https://argocd.{_BASE_DOMAIN}"
    ARGOCD_EXTERNAL_URL: str = f"https://argocd.{_BASE_DOMAIN}"
    ARGOCD_TOKEN: str = ""
    ARGOCD_VERIFY_SSL: bool = True
    ARGOCD_PLATFORM_APPS: str = "stoa-gateway,control-plane-api,control-plane-ui,stoa-portal"

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

    # Tempo Internal API (CAB-1984) - for distributed trace queries
    TEMPO_INTERNAL_URL: str = "http://tempo:3200"
    TEMPO_TIMEOUT_SECONDS: int = 30
    TEMPO_ENABLED: bool = True

    # OpenSearch Traces (CAB-1997) - query otel-v1-apm-span-* from Data Prepper
    OPENSEARCH_TRACES_ENABLED: bool = True

    # Git Sync Worker (CAB-2012) — async Git commits on API CRUD
    GIT_SYNC_ON_WRITE: bool = True  # Kill-switch: set False to disable Git sync

    # Gateway Sync Engine (Control Plane Agnostique)
    SYNC_ENGINE_ENABLED: bool = True
    SYNC_ENGINE_INTERVAL_SECONDS: int = 300  # 5 minutes
    SYNC_ENGINE_MAX_CONCURRENT: int = 5
    SYNC_ENGINE_RETRY_MAX: int = 3

    # Drift auto-repair mode (CAB-2016)
    # none: log + Kafka event only (default)
    # commit: auto-commit actual state to Git
    # pr: create a PR with the drift changes
    DRIFT_AUTO_REPAIR: str = "none"

    # ADR-059: Deployment mode — controls how CP notifies gateways of pending deploys
    # sse_only: SSE push only (no SyncEngine, no inline sync)
    # dual: SSE + SyncEngine for drift detection (no push, no inline sync)
    # legacy: original behavior (SyncEngine + inline sync, no SSE)
    DEPLOY_MODE: str = "legacy"

    @property
    def is_sse_enabled(self) -> bool:
        return self.DEPLOY_MODE in ("sse_only", "dual")

    @property
    def is_sync_engine_enabled(self) -> bool:
        return self.DEPLOY_MODE in ("legacy", "dual")

    @property
    def is_inline_sync_enabled(self) -> bool:
        return self.DEPLOY_MODE == "legacy"

    # Gateway Auto-Registration (ADR-028)
    # Comma-separated list of valid API keys for gateway self-registration
    GATEWAY_API_KEYS: str = ""
    # Heartbeat timeout in seconds (gateway marked OFFLINE after this)
    GATEWAY_HEARTBEAT_TIMEOUT_SECONDS: int = 90
    # Health check interval in seconds (how often to check for stale gateways)
    GATEWAY_HEALTH_CHECK_INTERVAL_SECONDS: int = 30
    # Auto-purge stale gateways after N days without heartbeat (CAB-1897)
    GATEWAY_PURGE_AFTER_DAYS: int = 7
    # ArgoCD reconciler interval (how often to sync ArgoCD apps → gateway_instances)
    GATEWAY_RECONCILER_INTERVAL_SECONDS: int = 60

    # Docs Search — Algolia integration (CAB-1327)
    ALGOLIA_APP_ID: str = "GIWP67WK7V"
    ALGOLIA_SEARCH_API_KEY: str = "6f5bb332c047a35c99fd3a151c44cc7f"  # Public search-only key
    ALGOLIA_INDEX_NAME: str = "Stoa Blog"
    DOCS_SEARCH_ENABLED: bool = True
    LLMS_FULL_TXT_URL: str = "https://gostoa.dev/llms-full.txt"

    # Chat Agent — Anthropic integration (CAB-286)
    CHAT_ENABLED: bool = False
    CHAT_PROVIDER_API_KEY: str = ""  # Anthropic key — via Infisical
    # Gateway routing (CAB-1822) — when set, chat routes through Stoa Gateway LLM proxy
    CHAT_GATEWAY_URL: str = ""  # e.g. http://stoa-gateway.stoa-system.svc.cluster.local:80
    CHAT_GATEWAY_API_KEY: str = ""  # STOA consumer API key for gateway auth

    # Docs Search — Semantic / Embedding (CAB-1327 Phase 2)
    EMBEDDING_PROVIDER: str = "openai"  # openai | none
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_API_KEY: str = ""  # via Infisical
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_API_URL: str = "https://api.openai.com/v1/embeddings"
    DOCS_REINDEX_ENABLED: bool = False  # Admin-only reindex endpoint
    OPENSEARCH_URL: str = "http://opensearch.stoa-system.svc.cluster.local:9200"
    OPENSEARCH_DOCS_INDEX: str = "docs-embeddings"

    # Chat Token Budget (CAB-288) — 0 = unlimited
    CHAT_TOKEN_BUDGET_DAILY: int = 0

    # Chat Rate Limiting + Kill Switch (CAB-1655)
    CHAT_KILL_SWITCH: bool = False  # Global kill switch — disables all chat endpoints
    CHAT_RATE_LIMIT_USER_MESSAGES: int = 20  # Max messages per user per minute
    CHAT_RATE_LIMIT_USER_TOOL_CALLS: int = 5  # Max tool calls per user per minute
    CHAT_RATE_LIMIT_TENANT_MESSAGES: int = 100  # Max messages per tenant per minute

    # Multi-environment registry (CAB-1659)
    # JSON array of environment configs. If empty, defaults are generated from BASE_DOMAIN.
    STOA_ENVIRONMENTS: str = ""

    # CORS - comma-separated list of allowed origins
    # Includes all known environment UI origins for multi-backend switching
    CORS_ORIGINS: str = (
        f"https://console.{_BASE_DOMAIN},https://portal.{_BASE_DOMAIN},"
        f"https://staging-console.{_BASE_DOMAIN},https://staging-portal.{_BASE_DOMAIN},"
        f"https://dev-console.{_BASE_DOMAIN},https://dev-portal.{_BASE_DOMAIN},"
        "http://localhost:3000,http://localhost:3002,http://localhost:5173,"
        "http://console.stoa.local,http://portal.stoa.local,http://api.stoa.local"
    )

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Tenant provisioning defaults (CAB-1315)
    TENANT_DEFAULT_RATE_LIMIT_RPM: int = 100

    # Self-service signup (CAB-1541)
    SIGNUP_BLOCKED_EMAIL_DOMAINS: str = ""  # Comma-separated override (empty = use built-in blocklist)
    SIGNUP_INVITE_CODES: str = ""  # Comma-separated valid invite codes (empty = no codes required for trial)

    @property
    def signup_invite_codes_list(self) -> list[str]:
        """Return SIGNUP_INVITE_CODES as a list."""
        if not self.SIGNUP_INVITE_CODES:
            return []
        return [code.strip() for code in self.SIGNUP_INVITE_CODES.split(",") if code.strip()]

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

    # Sender-Constrained Tokens (CAB-438 — RFC 8705 mTLS + RFC 9449 DPoP)
    SENDER_CONSTRAINED_ENABLED: bool = False  # Enable in staging/prod after migration
    SENDER_CONSTRAINED_STRATEGY: str = "auto"  # auto | require-any | mtls-only | dpop-only
    SENDER_CONSTRAINED_DPOP_MAX_CLOCK_SKEW: int = 60  # seconds

    # Logging - Auth Debug
    LOG_DEBUG_AUTH_TOKENS: bool = False
    LOG_DEBUG_AUTH_HEADERS: bool = False
    LOG_DEBUG_AUTH_PAYLOAD: bool = False

    # Logging - External Services Debug
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

    # HashiCorp Vault (runtime secrets — MCP server credentials, OAuth tokens)
    VAULT_ADDR: str = f"https://hcvault.{_BASE_DOMAIN}"
    VAULT_TOKEN: str = ""  # Dev mode token; production uses K8s auth
    VAULT_KUBERNETES_ROLE: str = "control-plane-api"
    VAULT_MOUNT_POINT: str = "secret"
    VAULT_ENABLED: bool = True  # Set to False to skip Vault operations (credentials not stored)

    # Backend API encryption (Fernet key for BYOK credential storage — CAB-1188)
    BACKEND_ENCRYPTION_KEY: str = ""

    # Database (PostgreSQL)
    DATABASE_URL: str = "postgresql+asyncpg://stoa:stoa@localhost:5432/stoa"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 10

    @property
    def database_url_sync(self) -> str:
        """Return sync database URL for Alembic migrations"""
        return self.DATABASE_URL.replace("+asyncpg", "")

    @property
    def argocd_platform_apps_list(self) -> list[str]:
        """Return ARGOCD_PLATFORM_APPS as a list"""
        if isinstance(self.ARGOCD_PLATFORM_APPS, list):
            return self.ARGOCD_PLATFORM_APPS
        return [app.strip() for app in self.ARGOCD_PLATFORM_APPS.split(",") if app.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a list.

        CAB-2142: strip `localhost` and `*.stoa.local` origins when
        `ENVIRONMENT=production`. These are dev-only entries that historically
        leaked into the prod default via the monolithic CORS_ORIGINS string,
        widening the cross-origin attack surface on `api.gostoa.dev`.
        Dev and staging keep the localhost entries so local clusters keep
        working without an explicit override.
        """
        raw = (
            self.CORS_ORIGINS
            if isinstance(self.CORS_ORIGINS, list)
            else [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        )
        if self.ENVIRONMENT == "production":
            return [origin for origin in raw if "localhost" not in origin and ".stoa.local" not in origin]
        return raw

    @property
    def log_components_dict(self) -> dict:
        """Return LOG_COMPONENTS as a dict"""
        try:
            result: dict = json.loads(self.LOG_COMPONENTS)
            return result
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def log_exclude_paths_list(self) -> list[str]:
        """Return LOG_EXCLUDE_PATHS as a list"""
        try:
            result: list[str] = json.loads(self.LOG_EXCLUDE_PATHS)
            return result
        except (json.JSONDecodeError, TypeError):
            return ["/health", "/healthz", "/ready", "/metrics"]

    @property
    def log_masking_patterns_list(self) -> list[str]:
        """Return LOG_MASKING_PATTERNS as a list"""
        try:
            result: list[str] = json.loads(self.LOG_MASKING_PATTERNS)
            return result
        except (json.JSONDecodeError, TypeError):
            return ["password", "secret", "token", "api_key", "authorization"]

    @property
    def gateway_api_keys_list(self) -> list[str]:
        """Return GATEWAY_API_KEYS as a list (ADR-028)"""
        if not self.GATEWAY_API_KEYS:
            return []
        return [key.strip() for key in self.GATEWAY_API_KEYS.split(",") if key.strip()]

    @model_validator(mode="after")
    def _hydrate_and_validate_git(self) -> "Settings":
        """CAB-1889 CP-2: hydrate ``settings.git`` from legacy flat env vars.

        Runs unconditionally so consumers see a coherent ``settings.git.*``
        tree. When ``_VALIDATE_GIT_CONFIG`` is True (flipped in C.3), also
        fails fast in production if the selected provider is misconfigured,
        and warns in dev/staging.
        """
        # Step 1 — hydration (always, wrapping SecretStr at the boundary).
        self.git = GitProviderConfig(
            provider=self.GIT_PROVIDER,
            github=GitHubConfig(
                token=SecretStr(self.GITHUB_TOKEN),
                org=self.GITHUB_ORG,
                catalog_repo=self.GITHUB_CATALOG_REPO,
                webhook_secret=SecretStr(self.GITHUB_WEBHOOK_SECRET),
            ),
            gitlab=GitLabConfig(
                url=self.GITLAB_URL,
                token=SecretStr(self.GITLAB_TOKEN),
                project_id=self.GITLAB_PROJECT_ID,
                webhook_secret=SecretStr(self.GITLAB_WEBHOOK_SECRET),
            ),
            default_branch=self.GIT_DEFAULT_BRANCH or "main",
        )

        # Step 2 — validation (gated; flipped in C.3).
        if not _VALIDATE_GIT_CONFIG:
            return self

        git = self.git
        offender_msgs: list[str] = []

        if git.provider == "github":
            if not git.github.token.get_secret_value():
                offender_msgs.append("GIT_PROVIDER=github but GITHUB_TOKEN is empty")
            if git.gitlab.token.get_secret_value():
                _logger.warning(
                    "GIT_PROVIDER=github but GITLAB_TOKEN is also set. "
                    "Inactive provider credentials should be removed."
                )
        else:  # gitlab
            if not git.gitlab.token.get_secret_value():
                offender_msgs.append("GIT_PROVIDER=gitlab but GITLAB_TOKEN is empty")
            if not git.gitlab.project_id:
                offender_msgs.append("GIT_PROVIDER=gitlab but GITLAB_PROJECT_ID is empty")
            if git.github.token.get_secret_value():
                _logger.warning(
                    "GIT_PROVIDER=gitlab but GITHUB_TOKEN is also set. "
                    "Inactive provider credentials should be removed."
                )

        if not offender_msgs:
            return self

        joined = "; ".join(offender_msgs)
        if self.ENVIRONMENT == "production":
            raise ValueError(
                f"Refusing to boot: Git provider config is incoherent ({joined}). "
                f"Set the required env vars in your Helm override."
            )

        _logger.warning(
            "Git provider config incomplete (ENVIRONMENT=%s): %s. "
            "Catalog operations will fail at request time. Fix before prod.",
            self.ENVIRONMENT,
            joined,
        )
        return self

    @model_validator(mode="after")
    def _gate_sensitive_debug_flags_in_prod(self) -> "Settings":
        """CAB-2145: fail fast if a credential-leaking debug flag is enabled in prod.

        Raises on `ENVIRONMENT=production`; logs a warning in any other env so
        developers still see the foot-gun during local debugging.
        """
        offenders = [flag for flag in SENSITIVE_DEBUG_FLAGS_IN_PROD if getattr(self, flag, False)]
        if not offenders:
            return self

        joined = ", ".join(offenders)
        if self.ENVIRONMENT == "production":
            raise ValueError(
                f"Refusing to boot: sensitive debug flag(s) {joined} are True while "
                f"ENVIRONMENT=production. These flags leak JWT tokens, Authorization "
                f"headers, or request bodies into logs. Unset them in your Helm override."
            )

        _logger.warning(
            "Sensitive debug flag(s) %s are True (ENVIRONMENT=%s). "
            "These MUST be False in production — do not deploy this config.",
            joined,
            self.ENVIRONMENT,
        )
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
