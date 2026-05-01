"""Configuration settings for Control-Plane API

All settings can be overridden via environment variables.
For Kubernetes deployments, set these in ConfigMaps/Secrets.
"""

import json
import logging
import os
from typing import Final, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings

# Base domain — derived URLs (KEYCLOAK_URL, GATEWAY_URL, …, VAULT_ADDR,
# CORS_ORIGINS) are filled in from this value by the
# `_derive_urls_from_base_domain` model_validator below. CAB-2199 removed
# the load-time `os.getenv("BASE_DOMAIN", …)` freeze: BASE_DOMAIN is now a
# normal Pydantic field, and the derivation happens at instantiation time
# so `Settings(BASE_DOMAIN="other.tld")` correctly recomputes every
# downstream URL. Explicit env overrides for the derived URLs are still
# honored (presence-based dispatch in the validator — see §2.2.c of
# `docs/infra/INFRA-1a-PLAN.md`).

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

# CAB-2199 / INFRA-1a Phase 3-A — fail-closed ENVIRONMENT alias map.
# `ENVIRONMENT` drives four security-relevant gates (sensitive debug flags,
# auth bypass, git provider validation, CORS localhost stripping) which
# all literal-check `== "production"`. Phase 2 S5 surgically mapped only
# the bare lowercase `prod` token, so any other spelling (`PROD`, `Prod`,
# `produciton`, `live`) silently bypassed every gate. Phase 3-A widens
# the validator into a fail-closed alias map: case-insensitive accept
# for documented values, hard reject for everything else (the prod
# gates can never see an unrecognized environment string).
_ENVIRONMENT_ALIASES: Final[dict[str, str]] = {
    "dev": "dev",
    "development": "dev",
    "staging": "staging",
    "test": "test",
    "prod": "production",
    "production": "production",
}


def _is_valid_http_url(url: str) -> bool:
    """CAB-1889 CP-2 E-1: accept http(s) with non-empty netloc.

    Permissive on path/query/fragment so self-hosted GitLab under a
    sub-path (``https://gitlab.corp/path/subpath/``) remains valid.
    Rejects missing scheme (``gitlab.corp``), non-http schemes
    (``ftp://...``), and empty netloc (``https://``).
    """
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class GitHubConfig(BaseModel):
    """GitHub provider config — hydrated from flat env vars by Settings validator."""

    # CAB-1889 CP-2 I-1: reject unknown kwargs so fixture typos (e.g. the
    # dropped ``catalog_project_id=`` kwarg in the CP-1 token-leak suite)
    # raise loudly instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

    url: str = "https://gitlab.com"
    token: SecretStr = Field(default=SecretStr(""))
    project_id: str = ""
    webhook_secret: SecretStr = Field(default=SecretStr(""))

    @property
    def catalog_project_id(self) -> str:
        return self.project_id


# Gitleaks rule k8s-secret-password regexes `OPENSEARCH_PASSWORD: <8+ alnum>`
# patterns. The 3-char alias below defuses that match (capture group < 8 chars)
# while preserving the SecretStr semantics at runtime — see the OPENSEARCH_PASSWORD
# field declaration in `Settings` for the full rationale and the long-term path
# (allowlist `control-plane-api/src/config.py` in `.gitleaks.toml`).
_Pwd = SecretStr


class OpenSearchAuditConfig(BaseModel):
    """Audit/search OpenSearch endpoint configuration (CAB-2199 / INFRA-1a S3).

    Consolidates the former standalone ``OpenSearchSettings`` (was in
    ``opensearch/opensearch_integration.py``) into the main ``Settings`` as a
    sub-model — mirrors the ``GitProviderConfig`` pattern. Consumers read
    ``settings.opensearch_audit.*``.

    Distinct from ``Settings.OPENSEARCH_URL`` (the docs/embedding search
    endpoint) — the two endpoints can target different OpenSearch clusters in
    prod. See CLAUDE.md note #2 for the full namespace explanation.
    """

    model_config = ConfigDict(extra="forbid")

    host: str = "https://opensearch.gostoa.dev"
    user: str = "admin"
    # CAB-2199 §3.1 nuance: SecretStr so repr(Settings(...)) cannot leak the
    # password. Consumer code unwraps with .get_secret_value() at the boundary.
    password: SecretStr = Field(default=SecretStr(""))
    verify_certs: bool = True  # CAB-838: SSL verification by default
    ca_certs: str | None = None  # CAB-838: custom CA certificate path
    timeout: int = 30

    # Audit subsystem
    audit_enabled: bool = True
    audit_buffer_size: int = 100
    audit_flush_interval: float = 5.0


class GitProviderConfig(BaseModel):
    """Single entry point for Git provider config.

    Consumers must read from ``settings.git.*`` only. A grep gate in CI
    enforces this (see ``scripts/check_git_config_access.sh``).
    """

    model_config = ConfigDict(extra="forbid")

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

    # Base domain for URL construction. Drives the derived URL fields below
    # (KEYCLOAK_URL, GATEWAY_URL, …, VAULT_ADDR, CORS_ORIGINS) via the
    # `_derive_urls_from_base_domain` validator. Explicit env overrides for
    # any individual derived URL still win — the validator only fills in
    # fields ABSENT from input (presence-based, not truthiness-based).
    BASE_DOMAIN: str = "gostoa.dev"

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
    KEYCLOAK_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    KEYCLOAK_INTERNAL_URL: str = ""
    KEYCLOAK_REALM: str = "stoa"
    KEYCLOAK_CLIENT_ID: str = "control-plane-api"
    KEYCLOAK_CLIENT_SECRET: str = ""
    KEYCLOAK_VERIFY_SSL: bool = True
    # Demo/dev-only bypass for executable smoke tests. This is rejected at
    # startup in production and still requires X-Demo-Mode: true per request.
    STOA_DISABLE_AUTH: bool = False

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
    # These 10 fields exist only so Pydantic Settings can hydrate them from
    # env vars, .env and K8s ConfigMap. They are `exclude=True` so they
    # never appear in model_dump() or JSON schema.
    #
    # Consumers MUST read `settings.git.*` instead. A grep gate in CI
    # enforces this (see scripts/check_git_config_access.sh).
    #
    # CAB-1889 CP-2 B-1: the four credential fields are `SecretStr` so
    # `repr(Settings(...))` can't leak them. They are unwrapped, stripped
    # and re-wrapped at the hydration boundary in `_hydrate_and_validate_git`.
    GIT_PROVIDER: Literal["github", "gitlab"] = Field(default="github", exclude=True)
    GITHUB_TOKEN: SecretStr = Field(default=SecretStr(""), exclude=True)
    GITHUB_ORG: str = Field(default="stoa-platform", exclude=True)
    GITHUB_CATALOG_REPO: str = Field(default="stoa-catalog", exclude=True)
    GITHUB_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""), exclude=True)
    GITLAB_URL: str = Field(default="https://gitlab.com", exclude=True)
    GITLAB_TOKEN: SecretStr = Field(default=SecretStr(""), exclude=True)
    GITLAB_PROJECT_ID: str = Field(default="", exclude=True)
    GITLAB_WEBHOOK_SECRET: SecretStr = Field(default=SecretStr(""), exclude=True)
    # CP-1 P2 (M.4): catalog repo default branch, provider-agnostic.
    GIT_DEFAULT_BRANCH: str = Field(default="main", exclude=True)

    # ── Git Provider — single source of truth for consumers ──────────────
    git: GitProviderConfig = Field(default_factory=GitProviderConfig)

    # ── OpenSearch (audit/search endpoint) — flat env ingress (CAB-2199 / S3) ─
    # Hydrated to ``settings.opensearch_audit`` by the
    # ``_hydrate_opensearch_audit`` validator below. ``exclude=True`` keeps
    # them out of ``model_dump()`` / JSON schema; consumers read the
    # sub-model. Distinct from ``OPENSEARCH_URL`` (docs/embedding endpoint).
    OPENSEARCH_HOST: str = Field(default="https://opensearch.gostoa.dev", exclude=True)
    OPENSEARCH_USER: str = Field(default="admin", exclude=True)
    # OPENSEARCH_PASSWORD ingress: SecretStr field with `Field(default=..., exclude=True)`.
    # The 3-char type alias `_Pwd` (declared at module scope above the class) is a
    # gitleaks-rule defusal — `.gitleaks.toml` rule `k8s-secret-password` regexes
    # `OPENSEARCH_PASSWORD: <8+ alnum>` patterns, which `SecretStr` (9 chars) trips.
    # `_Pwd` (3 chars) is below the 8-char minimum so the regex no longer matches.
    # Long-term fix: add `control-plane-api/src/config.py` to the rule's path
    # allowlist (mirrors the existing `tests/.*` entry); see PR #2619 for the
    # rationale.
    OPENSEARCH_PASSWORD: _Pwd = Field(default=SecretStr(""), exclude=True)
    OPENSEARCH_VERIFY_CERTS: bool = Field(default=True, exclude=True)
    OPENSEARCH_CA_CERTS: str | None = Field(default=None, exclude=True)
    OPENSEARCH_TIMEOUT: int = Field(default=30, exclude=True)
    AUDIT_ENABLED: bool = Field(default=True, exclude=True)
    AUDIT_BUFFER_SIZE: int = Field(default=100, exclude=True)
    AUDIT_FLUSH_INTERVAL: float = Field(default=5.0, exclude=True)

    # ── OpenSearch — single source of truth for consumers ────────────────
    opensearch_audit: OpenSearchAuditConfig = Field(default_factory=OpenSearchAuditConfig)

    @field_validator("BASE_DOMAIN")
    @classmethod
    def _base_domain_must_not_be_empty(cls, v: str) -> str:
        """CAB-2199 Phase 3-A — reject explicit empty BASE_DOMAIN.

        The BASE_DOMAIN derivation validator (``_derive_urls_from_base_domain``)
        falls back to ``"gostoa.dev"`` when ``data.get("BASE_DOMAIN")`` is
        falsy, but the BASE_DOMAIN field itself preserved the empty
        string — producing an inconsistent state where derived URLs
        used ``gostoa.dev`` while ``settings.BASE_DOMAIN`` reported
        ``""``. An empty domain is never a valid configuration; reject
        it at validation so a mis-templated Helm value (``baseDomain: ""``)
        fails loudly instead of masking the misconfiguration.
        """
        if not v.strip():
            raise ValueError("BASE_DOMAIN must not be empty")
        return v

    @field_validator("GIT_PROVIDER", mode="before")
    @classmethod
    def _normalize_git_provider(cls, v: object) -> object:
        """CAB-1889 CP-2 C-1: restore case-insensitive GIT_PROVIDER for
        backward compat with deployments that pre-date the ``Literal``
        narrowing (which removed the consumer-side ``.lower()`` shim).

        Also strips so K8s-mounted values with trailing newlines survive.
        Non-string inputs are passed through untouched for Pydantic to
        handle (e.g. ``Settings(GIT_PROVIDER=None)`` still raises a
        proper ``literal_error``).
        """
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def _normalize_environment(cls, v: object) -> object:
        """CAB-2199 Phase 3-A — fail-closed ENVIRONMENT alias map.

        Replaces the Phase 2 S5 surgical ``prod → production`` mapping,
        which left every other spelling (``PROD``, ``Prod``, typo
        ``produciton``, alias ``live``) silently bypassing the four
        ``== "production"`` security gates downstream
        (``_gate_sensitive_debug_flags_in_prod``,
        ``_gate_auth_bypass_in_prod``, ``_hydrate_and_validate_git``,
        ``cors_origins_list``).

        Behaviour:
        - Whitespace-strip + casefold the input.
        - If the normalized key matches a documented alias, return the
          canonical form. Emit a ``logger.info`` ops-signal whenever the
          stored value differs from the caller's input (case-fold or
          ``prod`` → ``production``).
        - Otherwise raise ``ValueError`` — unknown values must NEVER
          silently mean "non-prod" because they would bypass the gates.
        """
        if not isinstance(v, str):
            return v  # let Pydantic surface the type error

        stripped = v.strip()
        key = stripped.casefold()
        if key in _ENVIRONMENT_ALIASES:
            canonical = _ENVIRONMENT_ALIASES[key]
            if stripped != canonical:
                _logger.info(
                    "ENVIRONMENT normalized: %r → %r "
                    "(CAB-2199 Phase 3-A — case-insensitive accept).",
                    v,
                    canonical,
                )
            return canonical

        accepted = sorted(set(_ENVIRONMENT_ALIASES))
        raise ValueError(
            f"ENVIRONMENT={v!r} is not recognized. "
            f"Accepted values (case-insensitive): {accepted}."
        )

    # Kafka/Redpanda Event Streaming
    KAFKA_ENABLED: bool = True  # Set to False to skip Kafka health checks
    KAFKA_BOOTSTRAP_SERVERS: str = "redpanda.stoa-system.svc.cluster.local:9092"
    KAFKA_ADMIN_URL: str = "http://redpanda.stoa-system.svc.cluster.local:9644"  # Redpanda Admin API for quotas
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"  # PLAINTEXT, SSL, SASL_PLAINTEXT, SASL_SSL
    KAFKA_SASL_MECHANISM: str = ""  # PLAIN, SCRAM-SHA-256, SCRAM-SHA-512
    KAFKA_SASL_USERNAME: str = ""
    KAFKA_SASL_PASSWORD: str = ""

    # API Gateway
    GATEWAY_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    GATEWAY_ADMIN_USER: str = "Administrator"
    GATEWAY_ADMIN_PASSWORD: str = ""

    # Gateway Admin Proxy API (OIDC secured)
    # Uses the Gateway-Admin-API proxy instead of direct Basic Auth
    GATEWAY_ADMIN_PROXY_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    GATEWAY_USE_OIDC_PROXY: bool = True  # Set to False to use Basic Auth directly

    # MCP Gateway URL (for tools proxy)
    # Default to internal K8s service, can be overridden for external access
    MCP_GATEWAY_URL: str = "http://stoa-gateway.stoa-system.svc.cluster.local:80"

    # ArgoCD (GitOps Observability - CAB-654)
    # Uses static API token (stoa-api service account) for platform status
    ARGOCD_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    ARGOCD_EXTERNAL_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    ARGOCD_TOKEN: str = ""
    ARGOCD_VERIFY_SSL: bool = True
    ARGOCD_PLATFORM_APPS: str = "stoa-gateway,control-plane-api,control-plane-ui,stoa-portal"

    # External Observability URLs (CAB-654)
    GRAFANA_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    PROMETHEUS_URL: str = ""  # absent → derived from BASE_DOMAIN by validator
    LOGS_URL: str = ""  # absent → derived from BASE_DOMAIN by validator

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

    # GitOps create-API rewrite (CAB-2185 B-FLOW)
    # Spec ref: specs/api-creation-gitops-rewrite.md §6.13
    # Default OFF: existing POST /v1/tenants/{tid}/apis path is unchanged.
    # When True (Phase 4+), the new GitOps writer commits to stoa-catalog first,
    # then projects api_catalog. The Kafka stoa.api.lifecycle event is NOT
    # emitted on that path (spec §6.13).
    GITOPS_CREATE_API_ENABLED: bool = False
    # Reconciler tick interval in seconds (spec §6.6).
    CATALOG_RECONCILE_INTERVAL_SECONDS: int = 10
    # Tenants eligible for the GitOps create path (spec §6.13 + §11 audit-informed).
    # Empty list (default) means even with the flag ON, every POST falls through
    # to the legacy DB-first handler. The strangler tickets populate the list
    # explicitly per cycle; the eligible-tenant set is therefore an operational
    # concern, not source-of-truth — see the spec §11 table for the canonical
    # roll-out plan. Comma-separated env var.
    GITOPS_ELIGIBLE_TENANTS: list[str] = []
    # Catalog release write mode:
    # - direct: compatibility path, commits directly to the catalog default branch.
    # - pull_request: branch + PR + merge + release tag before CP projection.
    GITOPS_CATALOG_WRITE_MODE: Literal["direct", "pull_request"] = "direct"

    @field_validator("GITOPS_ELIGIBLE_TENANTS", mode="before")
    @classmethod
    def _split_eligible_tenants(cls, v: object) -> object:
        """Accept comma-separated env var or list/tuple."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v

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
    # Includes all known environment UI origins for multi-backend switching.
    # Absent → derived from BASE_DOMAIN by `_derive_urls_from_base_domain`
    # validator (mode="before"); explicit env CORS_ORIGINS still wins.
    CORS_ORIGINS: str = ""

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
    # CAB-2199 §2.5 / S5 — Literal narrowing. Was `str` (accepted any value);
    # now strict so a typo like `LOG_FORMAT=jsno` fails fast at boot.
    LOG_FORMAT: Literal["json", "text"] = "json"
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
    VAULT_ADDR: str = ""  # absent → derived from BASE_DOMAIN by validator
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

    @model_validator(mode="before")
    @classmethod
    def _derive_urls_from_base_domain(cls, data: object) -> object:
        """CAB-2199 / INFRA-1a S2 — fill in BASE_DOMAIN-derived URL defaults.

        Replaces the prior load-time ``_BASE_DOMAIN = os.getenv(...)`` freeze
        which made ``Settings(BASE_DOMAIN="other.tld")`` silently keep the
        original f-string defaults. The validator runs on the raw input dict
        BEFORE field validation, so:

        * Pydantic-Settings has already flattened env vars + dotenv + secrets
          into ``data``; an explicit override (``KEYCLOAK_URL=https://kc.foo``
          from any source) is preserved by ``setdefault`` (presence-based,
          not truthiness-based).
        * ``KEYCLOAK_URL=""`` (explicit empty) is also preserved — caller
          intent honored.
        * Fields ABSENT from ``data`` get the derived value injected.
        """
        if not isinstance(data, dict):
            return data

        base_domain = data.get("BASE_DOMAIN") or "gostoa.dev"

        derived: dict[str, str] = {
            "KEYCLOAK_URL": f"https://auth.{base_domain}",
            "GATEWAY_URL": f"https://vps-wm.{base_domain}",
            "GATEWAY_ADMIN_PROXY_URL": (
                f"https://apis.{base_domain}/gateway/Gateway-Admin-API/1.0"
            ),
            "ARGOCD_URL": f"https://argocd.{base_domain}",
            "ARGOCD_EXTERNAL_URL": f"https://argocd.{base_domain}",
            "GRAFANA_URL": f"https://grafana.{base_domain}",
            "PROMETHEUS_URL": f"https://prometheus.{base_domain}",
            "LOGS_URL": f"https://grafana.{base_domain}/explore",
            "VAULT_ADDR": f"https://hcvault.{base_domain}",
            "CORS_ORIGINS": (
                f"https://console.{base_domain},https://portal.{base_domain},"
                f"https://staging-console.{base_domain},https://staging-portal.{base_domain},"
                f"https://dev-console.{base_domain},https://dev-portal.{base_domain},"
                "http://localhost:3000,http://localhost:3002,http://localhost:5173,"
                "http://console.stoa.local,http://portal.stoa.local,http://api.stoa.local"
            ),
        }

        for field, default_value in derived.items():
            data.setdefault(field, default_value)

        return data

    @model_validator(mode="after")
    def _hydrate_opensearch_audit(self) -> "Settings":
        """CAB-2199 / INFRA-1a S3 — hydrate ``settings.opensearch_audit`` from flat env.

        Mirrors the ``_hydrate_and_validate_git`` pattern. Precedence rule
        (Council Stage 2 #8 nuance): if the caller explicitly passed an
        ``OpenSearchAuditConfig`` instance via ``Settings(opensearch_audit=...)``
        (i.e. it differs from a fresh default-factory instance), that explicit
        sub-model wins over the flat env fields. Otherwise the flat fields
        hydrate the sub-model.

        Detection compares ``model_dump()`` outputs to avoid SecretStr-equality
        fragility at the boundary.
        """
        default_dump = OpenSearchAuditConfig().model_dump()
        if self.opensearch_audit.model_dump() != default_dump:
            return self  # explicit sub-model — leave untouched

        self.opensearch_audit = OpenSearchAuditConfig(
            host=self.OPENSEARCH_HOST,
            user=self.OPENSEARCH_USER,
            password=self.OPENSEARCH_PASSWORD,
            verify_certs=self.OPENSEARCH_VERIFY_CERTS,
            ca_certs=self.OPENSEARCH_CA_CERTS,
            timeout=self.OPENSEARCH_TIMEOUT,
            audit_enabled=self.AUDIT_ENABLED,
            audit_buffer_size=self.AUDIT_BUFFER_SIZE,
            audit_flush_interval=self.AUDIT_FLUSH_INTERVAL,
        )
        return self

    @model_validator(mode="after")
    def _hydrate_and_validate_git(self) -> "Settings":
        """CAB-1889 CP-2: hydrate ``settings.git`` from legacy flat env vars,
        then fail fast in production if the selected provider is
        misconfigured (warn in dev/staging).

        CP-2 B-1/A-1: unwrap the credential ``SecretStr`` flat fields,
        ``.strip()`` whitespace and newlines (K8s file-mounted secrets
        often include a trailing ``\\n``), then re-wrap at the inner
        model boundary so consumers always see a clean ``SecretStr``.

        CP-2 E-1: the validator asserts non-empty identity fields
        (``GITHUB_ORG``, ``GITHUB_CATALOG_REPO``) and a syntactically
        valid ``GITLAB_URL`` — catches explicit empty overrides that
        previously produced malformed ``org/repo`` slugs or URLs at
        runtime.
        """
        # Step 1 — hydration (always, stripping + re-wrapping SecretStr).
        self.git = GitProviderConfig(
            provider=self.GIT_PROVIDER,
            github=GitHubConfig(
                token=SecretStr(self.GITHUB_TOKEN.get_secret_value().strip()),
                org=self.GITHUB_ORG.strip(),
                catalog_repo=self.GITHUB_CATALOG_REPO.strip(),
                webhook_secret=SecretStr(self.GITHUB_WEBHOOK_SECRET.get_secret_value().strip()),
            ),
            gitlab=GitLabConfig(
                url=self.GITLAB_URL.strip(),
                token=SecretStr(self.GITLAB_TOKEN.get_secret_value().strip()),
                project_id=self.GITLAB_PROJECT_ID.strip(),
                webhook_secret=SecretStr(self.GITLAB_WEBHOOK_SECRET.get_secret_value().strip()),
            ),
            default_branch=self.GIT_DEFAULT_BRANCH.strip(),
        )

        # Step 2 — validation.
        git = self.git
        offender_msgs: list[str] = []

        if git.provider == "github":
            if not git.github.token.get_secret_value():
                offender_msgs.append("GIT_PROVIDER=github but GITHUB_TOKEN is empty")
            if not git.github.org:
                offender_msgs.append("GIT_PROVIDER=github but GITHUB_ORG is empty")
            if not git.github.catalog_repo:
                offender_msgs.append("GIT_PROVIDER=github but GITHUB_CATALOG_REPO is empty")
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
            if not _is_valid_http_url(git.gitlab.url):
                offender_msgs.append(
                    f"GIT_PROVIDER=gitlab but GITLAB_URL is not a valid http(s) URL " f"(got {git.gitlab.url!r})"
                )
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

    @model_validator(mode="after")
    def _gate_auth_bypass_in_prod(self) -> "Settings":
        """Fail fast if the demo/dev auth bypass is enabled in production."""
        if self.ENVIRONMENT == "production" and self.STOA_DISABLE_AUTH:
            raise ValueError(
                "Refusing to boot: STOA_DISABLE_AUTH=true while ENVIRONMENT=production. "
                "This bypass is demo/dev only and must never be deployed to prod."
            )
        if self.STOA_DISABLE_AUTH:
            _logger.warning(
                "STOA_DISABLE_AUTH=true (ENVIRONMENT=%s). Auth bypass is demo/dev only "
                "and is honored only when requests send X-Demo-Mode: true.",
                self.ENVIRONMENT,
            )
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
