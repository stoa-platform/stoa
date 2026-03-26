#!/usr/bin/env python3
"""populate-db.py — Populate stoa-impact.db with component, contract, scenario, and risk data.

This script is the source of truth for the impact analysis database.
Data extracted from docs/audit/ files (2026-03-26 audit cycle).
Edit the data structures below, then run: python3 docs/scripts/populate-db.py

Auto-generates DEPENDENCIES.md and SCENARIOS.md after populating.
"""

import sqlite3
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "..", "stoa-impact.db")
SCHEMA_PATH = os.path.join(SCRIPT_DIR, "schema.sql")

# ============================================================================
# COMPONENTS — From SYNTHESIS.md section 6 + individual audits
# (id, name, type, tech_stack, repo_path, status, description)
# ============================================================================

COMPONENTS = [
    ("control-plane-api", "Control Plane API", "service",
     "Python 3.11, FastAPI 0.109, SQLAlchemy 2.0", "control-plane-api/", "active",
     "Central hub — 300+ endpoints, 65 tables, 40+ Kafka topics"),
    ("console", "STOA Admin Console", "frontend",
     "React 18, TypeScript, Vite, TanStack Query", "control-plane-ui/", "active",
     "Admin SPA — 200+ API calls, ~150 endpoints consumed"),
    ("portal", "STOA Developer Portal", "frontend",
     "React 19, TypeScript, Vite 7, TanStack Query v5", "portal/", "active",
     "Developer self-service — 100+ API calls, dual client (apiClient + mcpClient)"),
    ("stoa-gateway", "STOA MCP Gateway", "gateway",
     "Rust 2021, Tokio, axum 0.7, 170 source files", "stoa-gateway/", "active",
     "Production gateway — 4 modes: edge-mcp, sidecar, proxy, shadow. 100+ endpoints"),
    ("mcp-gateway-legacy", "MCP Gateway (Python)", "gateway",
     "Python 3.11, FastAPI", "archive/mcp-gateway/", "archived",
     "ARCHIVED Feb 2026 — replaced by stoa-gateway Rust"),
    ("keycloak", "Keycloak IAM", "external",
     "Keycloak 26.5.3, custom STOA theme", "keycloak/", "active",
     "OIDC/OAuth2 — token-exchange, DPoP, PAR. Realm: stoa. 8 clients configured"),
    ("postgresql", "PostgreSQL", "external",
     "PostgreSQL 14+ (asyncpg)", None, "active",
     "65 tables, Alembic migrations, asyncpg pool (2-20)"),
    ("kafka", "Kafka / Redpanda", "external",
     "Redpanda", None, "active",
     "25+ topics, no schema registry — CRITICAL gap"),
    ("opensearch", "OpenSearch", "external",
     "OpenSearch", None, "active",
     "Audit logs, full-text search, traces — OPTIONAL dependency"),
    ("vault", "HashiCorp Vault", "external",
     "Vault KV v2", None, "active",
     "Secrets: API keys, certs, consumer credentials. AppRole auth"),
    ("prometheus", "Prometheus + Grafana", "infra",
     "LGTM stack", None, "active",
     "Metrics scrape from CP API + Gateway, Grafana dashboards"),
    ("argocd", "ArgoCD", "infra",
     "ArgoCD", None, "active",
     "GitOps CD — selfHeal + prune, status API consumed by CP API"),
    ("stoactl", "stoactl CLI", "cli",
     "Go 1.22, Cobra, go-keyring", "stoa-go/cmd/stoactl/", "active",
     "CLI — Device Authorization flow, 20+ commands, OS keyring token storage"),
    ("stoa-connect", "STOA Connect Agent", "service",
     "Go 1.22, Vault SDK, Prometheus", "stoa-go/cmd/stoa-connect/", "active",
     "On-premise agent — bidirectional bridge, policy sync, 3 gateway adapters"),
]

# ============================================================================
# CONTRACTS — From SYNTHESIS.md section 2 + individual audit endpoint lists
# (id, source, target, type, contract_ref, schema_type, schema_path, typed, description)
# ============================================================================

CONTRACTS = [
    # --- Control Plane API → PostgreSQL ---
    ("cp-pg-001", "control-plane-api", "postgresql", "db-write",
     "SQLAlchemy ORM (65 tables)", "pydantic",
     "control-plane-api/src/models/", 1,
     "All CRUD operations via async SQLAlchemy"),
    ("cp-pg-002", "control-plane-api", "postgresql", "db-read",
     "SQLAlchemy ORM queries", "pydantic",
     "control-plane-api/src/repositories/", 1,
     "All read queries via repositories"),

    # --- Control Plane API → Keycloak ---
    ("cp-kc-001", "control-plane-api", "keycloak", "admin-api",
     "Keycloak Admin REST API (python-keycloak)", "none",
     "control-plane-api/src/services/keycloak_service.py", 0,
     "User/client/group/realm CRUD, token exchange, federation setup"),
    ("cp-kc-002", "control-plane-api", "keycloak", "oidc-flow",
     "OIDC JWT validation (RS256, JWKS)", "none",
     "control-plane-api/src/auth/dependencies.py", 1,
     "JWT extraction + JWKS validation for all authenticated requests"),

    # --- Control Plane API → Kafka (PRODUCES) ---
    ("cp-kf-001", "control-plane-api", "kafka", "kafka-event",
     "stoa.api.lifecycle", "none", None, 0,
     "API created/updated/deleted events → gateway sync"),
    ("cp-kf-002", "control-plane-api", "kafka", "kafka-event",
     "stoa.deployment.events", "none", None, 0,
     "Deployment progress events → Slack notification"),
    ("cp-kf-003", "control-plane-api", "kafka", "kafka-event",
     "stoa.tenant.lifecycle", "none", None, 0,
     "Tenant provisioning events → resource allocation"),
    ("cp-kf-004", "control-plane-api", "kafka", "kafka-event",
     "stoa.audit.trail", "none", None, 0,
     "Immutable audit events → OpenSearch indexer"),
    ("cp-kf-005", "control-plane-api", "kafka", "kafka-event",
     "stoa.policy.changes", "none", None, 0,
     "Policy CRUD events → gateway reconciler"),
    ("cp-kf-006", "control-plane-api", "kafka", "kafka-event",
     "stoa.catalog.changes", "none", None, 0,
     "Catalog sync events → git push"),
    ("cp-kf-007", "control-plane-api", "kafka", "kafka-event",
     "stoa.app.lifecycle", "none", None, 0,
     "Application lifecycle events → identity governance"),
    ("cp-kf-008", "control-plane-api", "kafka", "kafka-event",
     "stoa.security.alerts", "none", None, 0,
     "Security violation events → alerting worker"),
    ("cp-kf-009", "control-plane-api", "kafka", "kafka-event",
     "stoa.errors", "none", None, 0,
     "Error snapshot events → S3 archival"),
    ("cp-kf-010", "control-plane-api", "kafka", "kafka-event",
     "stoa.deploy.requests", "none", None, 0,
     "Deploy requests → gateway reconciler"),

    # --- Control Plane API → OpenSearch ---
    ("cp-os-001", "control-plane-api", "opensearch", "rest-api",
     "OpenSearch indexing (stoa-audit-*, stoa-errors-*, stoa-traces-*)", "none",
     "control-plane-api/src/opensearch/", 0,
     "Audit trail, full-text search, telemetry logs — OPTIONAL"),

    # --- Control Plane API → Vault ---
    ("cp-vault-001", "control-plane-api", "vault", "rest-api",
     "Vault KV v2 (hvac)", "none", None, 0,
     "MCP connector credentials, BYOK secrets retrieval"),

    # --- Control Plane API → ArgoCD ---
    ("cp-argo-001", "control-plane-api", "argocd", "rest-api",
     "ArgoCD REST API (sync, diff, status)", "none",
     "control-plane-api/src/services/argocd_service.py", 0,
     "Platform status, GitOps sync, deployment verification"),

    # --- Control Plane API → Prometheus ---
    ("cp-prom-001", "control-plane-api", "prometheus", "metrics",
     "GET /metrics (stoa_control_plane_http_*)", "none",
     "control-plane-api/src/middleware/metrics.py", 1,
     "Prometheus scrape: requests_total, duration_seconds, in_progress"),

    # --- Control Plane API REST endpoints (consumed by frontends/gateway) ---
    ("cp-rest-001", "control-plane-api", "control-plane-api", "rest-api",
     "/v1/tenants CRUD", "pydantic",
     "control-plane-api/src/schemas/tenant.py", 1,
     "Tenant management — consumed by Console + Portal"),
    ("cp-rest-002", "control-plane-api", "control-plane-api", "rest-api",
     "/v1/tenants/{tid}/apis CRUD", "pydantic",
     "control-plane-api/src/schemas/api.py", 1,
     "API catalog — consumed by Console + Portal"),
    ("cp-rest-003", "control-plane-api", "control-plane-api", "rest-api",
     "/v1/subscriptions CRUD", "pydantic",
     "control-plane-api/src/schemas/subscription.py", 1,
     "Subscriptions — consumed by Console + Portal"),
    ("cp-rest-004", "control-plane-api", "control-plane-api", "rest-api",
     "/v1/mcp/servers + /v1/mcp/subscriptions", "pydantic",
     "control-plane-api/src/schemas/mcp.py", 1,
     "MCP server catalog + subscriptions — consumed by Console + Portal"),
    ("cp-rest-005", "control-plane-api", "control-plane-api", "rest-api",
     "/v1/portal/apis (public catalog)", "pydantic",
     "control-plane-api/src/schemas/portal.py", 1,
     "Portal API discovery — consumed by Portal"),
    ("cp-rest-006", "control-plane-api", "control-plane-api", "rest-api",
     "/health", "none", None, 0,
     "Health check — inconsistent format across components"),

    # --- Console → Control Plane API ---
    ("cs-cp-001", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Tenant management (list, create, update, delete, export, import)"),
    ("cs-cp-002", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{t}/apis", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "API management (create, publish, deploy, versions)"),
    ("cs-cp-003", "console", "control-plane-api", "rest-api",
     "CRUD /v1/consumers/{t}", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Consumer management (create, suspend, block, certificates)"),
    ("cs-cp-004", "console", "control-plane-api", "rest-api",
     "CRUD /v1/subscriptions", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Subscription approval workflow (approve, reject, bulk)"),
    ("cs-cp-005", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{t}/deployments", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Deployment management (create, rollback, logs, cancel)"),
    ("cs-cp-006", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{t}/promotions", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "GitOps promotion flow (approve, complete, rollback, diff)"),
    ("cs-cp-007", "console", "control-plane-api", "rest-api",
     "CRUD /v1/admin/gateways", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Gateway instance registry (register, health, metrics, modes)"),
    ("cs-cp-008", "console", "control-plane-api", "rest-api",
     "CRUD /v1/admin/policies", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Policy management + bindings"),
    ("cs-cp-009", "console", "control-plane-api", "rest-api",
     "CRUD /v1/admin/external-mcp-servers", "typescript",
     "control-plane-ui/src/services/externalMcpServersApi.ts", 0,
     "External MCP server management + sync tools"),
    ("cs-cp-010", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{t}/contracts", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "UAC contract management + protocol bindings"),
    ("cs-cp-011", "console", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{t}/federation/accounts", "typescript",
     "control-plane-ui/src/services/federationApi.ts", 0,
     "MCP federation accounts + sub-accounts"),
    ("cs-cp-012", "console", "control-plane-api", "rest-api",
     "GET /v1/platform/status", "typescript",
     "control-plane-ui/src/hooks/usePlatformStatus.ts", 0,
     "Platform GitOps/ArgoCD status dashboard"),
    ("cs-cp-013", "console", "control-plane-api", "rest-api",
     "GET /v1/traces", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Distributed tracing + call flow visualization"),
    ("cs-cp-014", "console", "control-plane-api", "rest-api",
     "GET /v1/business/metrics", "typescript",
     "control-plane-ui/src/services/api.ts", 0,
     "Business KPIs dashboard"),
    ("cs-cp-015", "console", "control-plane-api", "sse",
     "EventSource /v1/events/stream/{tid}", "none",
     "control-plane-ui/src/services/api.ts", 0,
     "Server-Sent Events for real-time updates"),
    ("cs-kc-001", "console", "keycloak", "oidc-flow",
     "OIDC Authorization Code + PKCE (control-plane-ui client)", "none", None, 1,
     "Admin authentication via Keycloak"),
    ("cs-prom-001", "console", "prometheus", "metrics",
     "/prometheus/api/v1/query (same-origin proxy)", "none",
     "control-plane-ui/src/hooks/usePrometheus.ts", 0,
     "Native Prometheus dashboards"),

    # --- Portal → Control Plane API ---
    ("pt-cp-001", "portal", "control-plane-api", "rest-api",
     "GET /v1/portal/apis (catalog)", "typescript",
     "portal/src/services/apiCatalog.ts", 0,
     "API catalog listing, search, filters, categories, universes"),
    ("pt-cp-002", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/subscriptions", "typescript",
     "portal/src/services/apiSubscriptions.ts", 0,
     "Subscription lifecycle (create, cancel, approve, reject)"),
    ("pt-cp-003", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/mcp/servers + /v1/mcp/subscriptions", "typescript",
     "portal/src/services/mcpServers.ts", 0,
     "MCP server catalog + subscription + key rotation"),
    ("pt-cp-004", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/applications", "typescript",
     "portal/src/services/applications.ts", 0,
     "Application management + secret regeneration"),
    ("pt-cp-005", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/consumers/{tenant_id}", "typescript",
     "portal/src/services/consumers.ts", 0,
     "Consumer registration + credentials + token exchange"),
    ("pt-cp-006", "portal", "control-plane-api", "rest-api",
     "GET /v1/usage/me + /v1/dashboard/stats", "typescript",
     "portal/src/services/usage.ts", 0,
     "Usage analytics and dashboard statistics"),
    ("pt-cp-007", "portal", "control-plane-api", "rest-api",
     "POST /v1/self-service/tenants", "typescript",
     "portal/src/services/signup.ts", 0,
     "Self-service tenant creation (unauthenticated, rate-limited)"),
    ("pt-cp-008", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/contracts", "typescript",
     "portal/src/services/contracts.ts", 0,
     "UAC contract management with protocol bindings"),
    ("pt-cp-009", "portal", "control-plane-api", "rest-api",
     "CRUD /v1/tenants/{tid}/mcp-servers", "typescript",
     "portal/src/services/tenantMcpServers.ts", 0,
     "Tenant MCP server management + sync-tools"),
    ("pt-cp-010", "portal", "control-plane-api", "rest-api",
     "CRUD /tenants/{tid}/webhooks", "typescript",
     "portal/src/services/webhooks.ts", 0,
     "Webhook management + test + delivery history"),
    ("pt-cp-011", "portal", "control-plane-api", "rest-api",
     "GET /v1/me + POST /v1/me/tenant", "typescript",
     "portal/src/contexts/AuthContext.tsx", 0,
     "User identity + auto-provision personal tenant"),
    ("pt-kc-001", "portal", "keycloak", "oidc-flow",
     "OIDC Authorization Code + PKCE (stoa-portal client)", "none", None, 1,
     "Developer authentication via Keycloak"),

    # --- Portal → Gateway (DUPLICATE PATH — RISK-003) ---
    ("pt-gw-001", "portal", "stoa-gateway", "rest-api",
     "GET /mcp/v1/tools", "rust-struct",
     "portal/src/services/tools.ts", 1,
     "MCP tool discovery and listing via gateway"),
    ("pt-gw-002", "portal", "stoa-gateway", "rest-api",
     "POST /mcp/v1/tools/{name}/invoke", "rust-struct",
     "portal/src/services/tools.ts", 1,
     "MCP tool invocation from API sandbox"),
    ("pt-gw-003", "portal", "stoa-gateway", "rest-api",
     "CRUD /mcp/v1/subscriptions", "rust-struct",
     "portal/src/services/subscriptions.ts", 1,
     "Legacy MCP subscription management via gateway — DUPLICATE of pt-cp-003"),

    # --- Gateway → Control Plane API ---
    ("gw-cp-001", "stoa-gateway", "control-plane-api", "rest-api",
     "POST /v1/gateway/internal/register", "pydantic",
     "stoa-gateway/src/control_plane/", 1,
     "Gateway self-registration on startup (X-Operator-Key auth)"),
    ("gw-cp-002", "stoa-gateway", "control-plane-api", "rest-api",
     "POST /v1/gateway/internal/heartbeat", "pydantic",
     "stoa-gateway/src/control_plane/", 1,
     "Heartbeat every 30s (X-Operator-Key auth)"),
    ("gw-cp-003", "stoa-gateway", "control-plane-api", "rest-api",
     "GET /v1/mcp/validate", "pydantic",
     "stoa-gateway/src/control_plane/", 1,
     "API key validation for MCP tool calls"),

    # --- Gateway → Keycloak ---
    ("gw-kc-001", "stoa-gateway", "keycloak", "oidc-flow",
     "OIDC JWT validation (JWKS fetch)", "none",
     "stoa-gateway/src/auth/", 1,
     "JWT validation for authenticated requests"),
    ("gw-kc-002", "stoa-gateway", "keycloak", "admin-api",
     "POST /oauth/register proxy → KC DCR + PKCE patch", "none",
     "stoa-gateway/src/oauth/proxy.rs", 0,
     "DCR proxy: scope stripping, public client patching, S256 PKCE"),
    ("gw-kc-003", "stoa-gateway", "keycloak", "oidc-flow",
     "POST /oauth/token proxy → KC token endpoint", "none",
     "stoa-gateway/src/oauth/proxy.rs", 1,
     "Token proxy for AI clients (Claude.ai)"),

    # --- Gateway → Kafka (PRODUCES — cross-language, UNTYPED) ---
    ("gw-kf-001", "stoa-gateway", "kafka", "kafka-event",
     "stoa.metering.events", "none",
     "stoa-gateway/src/metering/", 0,
     "API call metering events — Rust → Python consumer, NO SCHEMA"),
    ("gw-kf-002", "stoa-gateway", "kafka", "kafka-event",
     "stoa.errors", "none",
     "stoa-gateway/src/metering/", 0,
     "Error snapshot events — Rust → Python consumer, NO SCHEMA"),
    ("gw-kf-003", "stoa-gateway", "kafka", "kafka-event",
     "stoa.security.alerts", "none",
     "stoa-gateway/src/metering/", 0,
     "Security alert events — Rust → Python consumer, NO SCHEMA"),
    ("gw-kf-004", "stoa-gateway", "kafka", "kafka-event",
     "stoa.gateway.metrics", "none",
     "stoa-gateway/src/metering/", 0,
     "Telemetry events → OpenSearch, NO SCHEMA"),

    # --- Gateway → Prometheus ---
    ("gw-prom-001", "stoa-gateway", "prometheus", "metrics",
     "GET /metrics (60+ metrics)", "none",
     "stoa-gateway/src/metrics.rs", 1,
     "Prometheus scrape: HTTP, MCP, security, rate-limit, guardrails, upstream, HEGEMON"),

    # --- Gateway MCP Protocol (exposed to AI clients) ---
    ("gw-mcp-001", "stoa-gateway", "stoa-gateway", "rest-api",
     "GET /mcp/capabilities (RFC 9728)", "json-rpc",
     "stoa-gateway/src/mcp/", 1,
     "MCP discovery — consumed by Claude.ai and AI agents"),
    ("gw-mcp-002", "stoa-gateway", "stoa-gateway", "rest-api",
     "POST /mcp/tools/list + /mcp/tools/call (JSON-RPC 2.0)", "json-rpc",
     "stoa-gateway/src/mcp/", 1,
     "MCP tool list + invocation"),
    ("gw-oauth-001", "stoa-gateway", "stoa-gateway", "rest-api",
     "/.well-known/oauth-protected-resource (RFC 9728)", "openapi",
     "stoa-gateway/src/oauth/discovery.rs", 1,
     "OAuth discovery — points to gateway, not Keycloak"),
    ("gw-oauth-002", "stoa-gateway", "stoa-gateway", "rest-api",
     "/.well-known/oauth-authorization-server (RFC 8414)", "openapi",
     "stoa-gateway/src/oauth/discovery.rs", 1,
     "Curated OAuth metadata with token_endpoint_auth_methods: [none]"),
    ("gw-admin-001", "stoa-gateway", "stoa-gateway", "admin-api",
     "/admin/* (70+ endpoints)", "rust-struct",
     "stoa-gateway/src/handlers/admin.rs", 1,
     "Admin API — consumed by CP API adapter (Bearer token)"),

    # --- Gateway → CP API adapter path ---
    ("cp-gw-001", "control-plane-api", "stoa-gateway", "admin-api",
     "StoaGatewayAdapter → /admin/*", "pydantic",
     "control-plane-api/src/adapters/stoa/adapter.py", 1,
     "CP API deploys APIs to gateway via adapter pattern"),

    # --- stoactl → Control Plane API ---
    ("cli-cp-001", "stoactl", "control-plane-api", "rest-api",
     "GET /v1/tenants/{tid}/apis + CRUD", "none",
     "stoa-go/pkg/client/client.go", 0,
     "CLI operations: get, apply, delete, deploy, logs"),
    ("cli-cp-002", "stoactl", "control-plane-api", "rest-api",
     "GET /health", "none",
     "stoa-go/internal/cli/cmd/doctor/doctor.go", 0,
     "stoactl doctor — connectivity + auth check"),
    ("cli-kc-001", "stoactl", "keycloak", "oidc-flow",
     "Device Authorization Grant (stoactl client)", "none", None, 1,
     "CLI login via device code flow → OS keyring"),

    # --- stoa-connect → Control Plane API ---
    ("conn-cp-001", "stoa-connect", "control-plane-api", "rest-api",
     "POST /v1/internal/gateways/register", "none",
     "stoa-go/internal/connect/connect.go", 0,
     "Agent self-registration (X-Gateway-Key auth)"),
    ("conn-cp-002", "stoa-connect", "control-plane-api", "rest-api",
     "POST /v1/internal/gateways/{id}/heartbeat", "none",
     "stoa-go/internal/connect/connect.go", 0,
     "Heartbeat every 30s"),
    ("conn-cp-003", "stoa-connect", "control-plane-api", "rest-api",
     "GET /v1/internal/gateways/{id}/config", "none",
     "stoa-go/internal/connect/connect.go", 0,
     "Fetch pending policies + deployments"),
    ("conn-cp-004", "stoa-connect", "control-plane-api", "rest-api",
     "POST /v1/internal/gateways/{id}/sync-ack", "none",
     "stoa-go/internal/connect/connect.go", 0,
     "Report policy sync results"),
    ("conn-cp-005", "stoa-connect", "control-plane-api", "rest-api",
     "POST /v1/internal/gateways/{id}/discovery", "none",
     "stoa-go/internal/connect/connect.go", 0,
     "Report discovered APIs from third-party gateway"),

    # --- stoa-connect → Vault ---
    ("conn-vault-001", "stoa-connect", "vault", "rest-api",
     "Vault KV v2 stoa/data/consumers/{tid}", "none",
     "stoa-go/internal/connect/vault.go", 0,
     "Consumer credential retrieval for injection"),

    # --- stoa-connect → Prometheus ---
    ("conn-prom-001", "stoa-connect", "prometheus", "metrics",
     "GET /metrics (stoa_connect_*)", "none",
     "stoa-go/internal/connect/metrics.go", 1,
     "Agent metrics: gateway_up, apis_total, sync_status, heartbeats"),
]

# ============================================================================
# SCENARIOS — From SYNTHESIS.md section 3
# (id, name, description, actor, priority, test_level, test_in_ci)
# ============================================================================

SCENARIOS = [
    ("SCEN-001", "Developer Self-Service Subscription",
     "Portal signup → search → subscribe → approve → credentials",
     "api-consumer", "P0", "none", 0),
    ("SCEN-002", "MCP Tool Invocation via AI Client",
     "OAuth discovery → DCR → token → tool list → tool call",
     "ai-client", "P0", "integration", 0),
    ("SCEN-003", "API Deployment to Gateway",
     "Console deploy → adapter → gateway sync → Kafka event → Slack",
     "platform-admin", "P0", "unit", 0),
    ("SCEN-004", "Admin Login + Dashboard",
     "Browser → OIDC → Console → CP API → metrics → SSE events",
     "platform-admin", "P1", "none", 0),
    ("SCEN-005", "Gateway Auto-Registration",
     "Gateway startup → register → heartbeat loop → health worker check",
     "gateway", "P1", "unit", 0),
    ("SCEN-006", "Consumer mTLS Certificate Lifecycle",
     "CSR → sign → configure gateway → mTLS verify → RFC 8705",
     "api-consumer", "P1", "none", 0),
]

# ============================================================================
# SCENARIO STEPS — From SYNTHESIS.md section 3 flow diagrams
# (scenario_id, step_order, component_id, action, contract_id, expected_result)
# ============================================================================

SCENARIO_STEPS = [
    # SCEN-001: Developer Self-Service Subscription
    ("SCEN-001", 1, "portal", "Consumer visits signup page", "pt-cp-007",
     "Tenant created via self-service"),
    ("SCEN-001", 2, "portal", "Consumer logs in via Keycloak OIDC", "pt-kc-001",
     "Authenticated session with JWT"),
    ("SCEN-001", 3, "portal", "Consumer searches API catalog", "pt-cp-001",
     "List of published APIs matching search"),
    ("SCEN-001", 4, "portal", "Consumer creates subscription", "pt-cp-002",
     "Subscription created with pending status"),
    ("SCEN-001", 5, "control-plane-api", "CP emits app.lifecycle Kafka event", "cp-kf-007",
     "Subscription event dispatched"),
    ("SCEN-001", 6, "console", "Admin views pending subscriptions", "cs-cp-004",
     "List of subscriptions awaiting approval"),
    ("SCEN-001", 7, "console", "Admin approves subscription", "cs-cp-004",
     "Subscription activated, API key generated"),
    ("SCEN-001", 8, "control-plane-api", "CP creates Keycloak client for consumer", "cp-kc-001",
     "OAuth client provisioned in Keycloak"),
    ("SCEN-001", 9, "control-plane-api", "CP persists subscription", "cp-pg-001",
     "Subscription + credentials stored"),
    ("SCEN-001", 10, "portal", "Consumer retrieves credentials", "pt-cp-002",
     "API key returned for use"),

    # SCEN-002: MCP Tool Invocation via AI Client
    ("SCEN-002", 1, "stoa-gateway",
     "Claude.ai fetches /.well-known/oauth-protected-resource", "gw-oauth-001",
     "Returns authorization_servers pointing to gateway"),
    ("SCEN-002", 2, "stoa-gateway",
     "Claude.ai fetches /.well-known/oauth-authorization-server", "gw-oauth-002",
     "Returns curated metadata with token_endpoint_auth_methods: [none]"),
    ("SCEN-002", 3, "stoa-gateway",
     "Claude.ai registers client via POST /oauth/register", "gw-kc-002",
     "Client registered in KC, patched to publicClient + PKCE S256"),
    ("SCEN-002", 4, "stoa-gateway",
     "Claude.ai exchanges auth code for token via POST /oauth/token", "gw-kc-003",
     "Access token returned (proxied through gateway)"),
    ("SCEN-002", 5, "stoa-gateway",
     "Claude.ai calls POST /mcp/tools/list", "gw-mcp-002",
     "Tool catalog returned with schemas"),
    ("SCEN-002", 6, "stoa-gateway",
     "Gateway validates API key via CP API", "gw-cp-003",
     "API key validated, subscription confirmed"),
    ("SCEN-002", 7, "stoa-gateway",
     "Claude.ai calls POST /mcp/tools/call with tool invocation", "gw-mcp-002",
     "Tool executed, result returned with credential injection"),
    ("SCEN-002", 8, "stoa-gateway",
     "Gateway emits metering event to Kafka", "gw-kf-001",
     "Call metered for billing/analytics"),

    # SCEN-003: API Deployment to Gateway
    ("SCEN-003", 1, "console", "Admin logs in via Keycloak", "cs-kc-001",
     "Authenticated with stoa:write scope"),
    ("SCEN-003", 2, "console", "Admin creates deployment", "cs-cp-005",
     "Deployment request sent to CP API"),
    ("SCEN-003", 3, "control-plane-api",
     "CP selects adapter via AdapterRegistry.create(gateway_type)", None,
     "Adapter instantiated for target gateway"),
    ("SCEN-003", 4, "control-plane-api",
     "Adapter calls sync_api() on gateway admin API", "cp-gw-001",
     "API definition pushed to gateway"),
    ("SCEN-003", 5, "control-plane-api",
     "CP persists GatewayDeployment record", "cp-pg-001",
     "Deployment state stored in DB"),
    ("SCEN-003", 6, "control-plane-api",
     "CP emits deployment.events Kafka event", "cp-kf-002",
     "Deployment progress event dispatched"),
    ("SCEN-003", 7, "control-plane-api",
     "SyncEngine reconciles DB vs gateway state (every 300s)", None,
     "Drift detected and corrected"),

    # SCEN-004: Admin Login + Dashboard
    ("SCEN-004", 1, "console", "Browser navigates to console.gostoa.dev", None,
     "nginx serves SPA"),
    ("SCEN-004", 2, "console", "Console initiates OIDC login", "cs-kc-001",
     "Authorization Code + PKCE flow with Keycloak"),
    ("SCEN-004", 3, "console", "Console fetches platform data", "cs-cp-001",
     "Tenants, APIs, users loaded"),
    ("SCEN-004", 4, "console", "Console fetches business metrics", "cs-cp-014",
     "KPIs displayed (API calls, subscribers, revenue)"),
    ("SCEN-004", 5, "console", "Console opens SSE stream", "cs-cp-015",
     "Real-time events flowing"),

    # SCEN-005: Gateway Auto-Registration
    ("SCEN-005", 1, "stoa-gateway",
     "Gateway starts and calls POST /v1/gateway/internal/register", "gw-cp-001",
     "Gateway registered with instance ID"),
    ("SCEN-005", 2, "control-plane-api",
     "CP creates GatewayInstance record", "cp-pg-001",
     "Gateway persisted in database"),
    ("SCEN-005", 3, "stoa-gateway",
     "Gateway sends heartbeat every 30s", "gw-cp-002",
     "last_seen updated, status confirmed"),
    ("SCEN-005", 4, "control-plane-api",
     "GatewayHealthWorker checks stale gateways (90s timeout)", None,
     "Stale gateways marked offline"),

    # SCEN-006: Consumer mTLS Certificate Lifecycle
    ("SCEN-006", 1, "console",
     "Admin generates tenant CA via POST /v1/tenants/{tid}/ca", "cs-cp-003",
     "CA keypair generated in-memory"),
    ("SCEN-006", 2, "console",
     "Admin creates consumer", "cs-cp-003",
     "Consumer registered in CP API"),
    ("SCEN-006", 3, "console",
     "Consumer submits CSR, admin signs via POST /v1/tenants/{tid}/ca/sign", "cs-cp-003",
     "Certificate signed with tenant CA"),
    ("SCEN-006", 4, "control-plane-api",
     "CP configures mTLS on gateway via adapter", "cp-gw-001",
     "Gateway updated with cert trust chain"),
    ("SCEN-006", 5, "stoa-gateway",
     "Consumer connects with mTLS, gateway verifies cert", "gw-kc-001",
     "RFC 8705 certificate-bound token validated"),
]

# ============================================================================
# RISKS — From SYNTHESIS.md section 4
# (id, severity, title, description, impacted_components, impacted_contracts,
#  recommendation, status, ticket_ref)
# ============================================================================

RISKS = [
    ("RISK-001", "CRITICAL",
     "No Formal Schema for Kafka Events",
     "All 25+ Kafka topics use untyped Python dicts. Cross-language topics "
     "(Rust gateway → Python consumer) have ZERO contract enforcement. "
     "A gateway metering format change silently breaks Python consumers.",
     "stoa-gateway,control-plane-api,kafka",
     "gw-kf-001,gw-kf-002,gw-kf-003,gw-kf-004,cp-kf-001,cp-kf-002,cp-kf-003,"
     "cp-kf-004,cp-kf-005,cp-kf-006,cp-kf-007,cp-kf-008,cp-kf-009,cp-kf-010",
     "Deploy Redpanda Schema Registry + Avro/Protobuf for cross-language topics. "
     "At minimum, define Pydantic models for all event payloads and validate on consume.",
     "open", None),

    ("RISK-002", "HIGH",
     "Frontend-Backend Contract Drift",
     "Console (150+ endpoints) and Portal (100+ endpoints) call CP API via "
     "hand-written Axios calls. OpenAPI snapshot (shared/api-types/generated.ts) "
     "may be stale. stoactl uses manual Go structs with no shared contract.",
     "console,portal,control-plane-api,stoactl",
     "cs-cp-001,cs-cp-002,cs-cp-003,cs-cp-004,cs-cp-005,cs-cp-006,cs-cp-007,"
     "cs-cp-008,pt-cp-001,pt-cp-002,pt-cp-003,pt-cp-004,pt-cp-005,cli-cp-001",
     "Enforce OpenAPI snapshot regeneration in CI (diff check on PR). "
     "Consider openapi-typescript-codegen for fully generated API clients.",
     "open", None),

    ("RISK-003", "HIGH",
     "Duplicate MCP Subscription Paths",
     "Portal calls MCP subscriptions via TWO different paths: "
     "(1) CP API: /v1/mcp/subscriptions via apiClient, "
     "(2) Gateway: /mcp/v1/subscriptions via mcpClient. "
     "dashboard.ts calls /tools and /subscriptions without /mcp/v1/ prefix — will 404.",
     "portal,stoa-gateway,control-plane-api",
     "pt-cp-003,pt-gw-003",
     "Deprecate the gateway-direct path. Route all MCP subscription management "
     "through CP API.",
     "open", None),

    ("RISK-004", "HIGH",
     "No E2E Integration Tests in CI",
     "All 6 critical scenarios validated by unit tests with mocks only. "
     "MCP OAuth flow has manual bash script (not in CI). "
     "Adapter tests (~250) use mocked httpx, no live gateway tests.",
     "console,portal,stoa-gateway,control-plane-api",
     None,
     "Priority E2E tests for top 3: (1) MCP OAuth discovery → tool call, "
     "(2) API deployment via adapter, (3) subscription lifecycle.",
     "open", None),

    ("RISK-005", "MEDIUM",
     "Gateway-CP API Internal Auth (X-Operator-Key)",
     "Shared secret with no rotation mechanism documented. No mTLS between "
     "gateway and CP API within the cluster. Compromised key = full cpi-admin access.",
     "stoa-gateway,control-plane-api",
     "gw-cp-001,gw-cp-002,gw-cp-003",
     "Migrate to K8s service account JWT or mTLS for internal service-to-service auth.",
     "open", None),

    ("RISK-006", "MEDIUM",
     "Health Check Inconsistency",
     "Different response formats across components: "
     "CP API returns {status, components}, Gateway returns {status}, "
     "Console/Portal return HTML 200 from nginx.",
     "control-plane-api,stoa-gateway,console,portal",
     "cp-rest-006",
     "Standardize on single health response schema: {status, version, components}.",
     "mitigated", "CAB-1916"),

    ("RISK-007", "MEDIUM",
     "OpenSearch Optional Dependency",
     "Audit trail, traces, and docs-embeddings stored in OpenSearch — but listed "
     "as optional. If OpenSearch down: audit trail lost, compliance gap.",
     "opensearch,control-plane-api",
     "cp-os-001",
     "Make audit logging non-optional in prod. Add fallback to PostgreSQL or file.",
     "open", None),

    ("RISK-008", "LOW",
     "Shared Directory Build Context",
     "Console and Portal Dockerfiles require monorepo root as build context "
     "(for shared/ directory). Docker cache invalidation for ANY file change in monorepo.",
     "console,portal",
     None,
     "Consider npm workspace publishing or git submodule for shared components.",
     "accepted", None),
]


# ============================================================================
# Database operations
# ============================================================================

def create_db() -> sqlite3.Connection:
    """Create or recreate the database."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


def populate(conn: sqlite3.Connection) -> None:
    """Insert all data."""
    conn.executemany(
        "INSERT INTO components VALUES (?, ?, ?, ?, ?, ?, ?)", COMPONENTS
    )
    conn.executemany(
        "INSERT INTO contracts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", CONTRACTS
    )
    conn.executemany(
        "INSERT INTO scenarios VALUES (?, ?, ?, ?, ?, ?, ?)", SCENARIOS
    )
    conn.executemany(
        "INSERT INTO scenario_steps (scenario_id, step_order, component_id, action, contract_id, expected_result) VALUES (?, ?, ?, ?, ?, ?)",
        SCENARIO_STEPS,
    )
    conn.executemany(
        "INSERT INTO risks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", RISKS
    )
    conn.commit()


def print_stats(conn: sqlite3.Connection) -> None:
    """Print database statistics."""
    for table in ["components", "contracts", "scenarios", "scenario_steps", "risks"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")

    # View stats
    for view in ["impact_analysis", "untyped_contracts", "untested_scenarios", "component_risk_score"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]
        print(f"  {view} (view): {count} rows")

    # Key stats
    typed = conn.execute("SELECT COUNT(*) FROM contracts WHERE typed = 1").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    print(f"\n  Typed contracts: {typed}/{total} ({100*typed//total}%)")

    open_risks = conn.execute("SELECT COUNT(*) FROM risks WHERE status = 'open'").fetchone()[0]
    print(f"  Open risks: {open_risks}")

    active = conn.execute("SELECT COUNT(*) FROM components WHERE status = 'active'").fetchone()[0]
    print(f"  Active components: {active}")


def main() -> None:
    print(f"Creating database at {DB_PATH}")
    conn = create_db()
    populate(conn)
    print("Database populated:")
    print_stats(conn)
    conn.close()

    # Auto-generate docs
    print("\nRegenerating docs...")
    os.system(f"python3 {os.path.join(SCRIPT_DIR, 'regenerate-docs.py')}")


if __name__ == "__main__":
    main()
