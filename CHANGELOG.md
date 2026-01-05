# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added (2026-01-05) - Developer Portal Enhancement (CAB-246)

> **Related Ticket**: CAB-246 - STOA Developer Portal Enhancement

- **STOA Developer Portal** - API Consumer features (`portal/`)
  - **API Catalog** (`src/pages/apis/`):
    - `APICatalog.tsx` - Browse all published APIs with search/filter
    - `APIDetail.tsx` - API details with OpenAPI spec viewer
    - `APITestingSandbox.tsx` - Interactive API testing sandbox

  - **Consumer Applications** (`src/pages/apps/`):
    - `MyApplications.tsx` - Create and manage consumer apps
    - `ApplicationDetail.tsx` - App credentials and subscriptions

  - **Subscriptions** (`src/pages/subscriptions/`):
    - `MySubscriptions.tsx` - Manage API and MCP Tool subscriptions
    - Support for both API and MCP Tool subscription types

  - **API Testing Components** (`src/components/testing/`):
    - `EnvironmentSelector.tsx` - Environment dropdown with production warnings
    - `RequestBuilder.tsx` - Request configuration (method, path, headers, body)
    - `ResponseViewer.tsx` - Response display with timing, status codes
    - `SandboxConfirmationModal.tsx` - Production environment confirmation

  - **Configuration** (`src/config.ts`):
    - `portalMode` - production vs non-production portal
    - `enableApplications` - Consumer apps feature flag
    - `enableAPITesting` - Testing sandbox feature flag
    - `testing.requireSandboxConfirmation` - Production safety

  - **Portal Deployment**:
    - URL: https://portal.stoa.cab-i.com
    - Keycloak client: `stoa-portal`
    - CI/CD: `.github/workflows/stoa-portal-ci.yml`

### Added (2026-01-05) - Phase 9.5 Production Readiness (CAB-103)

> **Related Tickets**:
> | Ticket | Title | Status |
> |--------|-------|--------|
> | CAB-103 | Phase 9.5: Production Readiness | ✅ Done |
> | CAB-104 | Backup/Restore AWX | ✅ Done |
> | CAB-105 | Backup/Restore Vault | ✅ Done |
> | CAB-106 | Load Test Pipeline (K6) | ✅ Done |
> | CAB-107 | Operational Runbooks | ✅ Done |
> | CAB-108 | Security Audit (OWASP) | ✅ Done |
> | CAB-109 | Chaos Testing (Litmus) | ✅ Done |
> | CAB-110 | SLO/SLA Definition | ✅ Done |

- **Backup/Restore Infrastructure (CAB-104, CAB-105)**
  - `terraform/modules/backup/` - Terraform module for AWS infrastructure:
    - S3 bucket with versioning and lifecycle (30 days retention)
    - KMS key for backup encryption
    - IAM role and policy for IRSA (OIDC)
    - Region: eu-west-3 (Paris)

  - `scripts/backup/` - Automated backup scripts:
    - `backup-awx.sh` - AWX PostgreSQL backup to S3
    - `backup-vault.sh` - Vault Raft snapshot to S3
    - `restore-awx.sh` - AWX restoration from S3
    - `restore-vault.sh` - Vault restoration from snapshot
    - `common.sh` - Shared functions (S3, logging, Slack)

  - `charts/stoa-platform/templates/backup-*.yaml` - Kubernetes CronJobs:
    - `backup-awx-cronjob.yaml` - Daily AWX backup (2 AM)
    - `backup-vault-cronjob.yaml` - Daily Vault backup (3 AM)
    - `backup-rbac.yaml` - ServiceAccount and RBAC

  - `docs/runbooks/critical/` - Restore procedures (CAB-107):
    - `awx-restore.md` - AWX restoration guide
    - `vault-restore.md` - Vault restoration guide

- **Load Testing K6 (CAB-106)**
  - `tests/load/k6/` - Load testing scenarios:
    - `scenarios/smoke.js` - Minimal test (10 users, 1 min)
    - `scenarios/load.js` - Normal load test (100 users, 5 min)
    - `scenarios/stress.js` - Stress test (500 users, 10 min)
    - `scenarios/spike.js` - Spike test (1000 users spike)
    - `lib/auth.js` - Keycloak authentication helper
    - `lib/config.js` - Endpoint configuration per environment
    - `thresholds.js` - SLO thresholds (p95 < 500ms, errors < 1%)

  - `scripts/run-load-tests.sh` - K6 execution script
  - `tests/load/docker-compose.yml` - K6 + InfluxDB + Grafana

- **SLO/SLA Documentation and Monitoring (CAB-110)**
  - `docs/SLO-SLA.md` - Objectives documentation:
    - Availability: 99.9% (SLO) / 99.5% (SLA)
    - Latency p95: < 500ms (SLO) / < 1000ms (SLA)
    - Error Rate: < 0.1% (SLO) / < 1% (SLA)
    - MTTR P1: < 1h (SLO) / < 4h (SLA)

  - `charts/stoa-platform/templates/prometheus-rules.yaml`:
    - Recording rules: `slo:api_availability:ratio`, `slo:api_latency_p95:seconds`
    - Error budget calculation per period (30 days)

  - `charts/stoa-platform/templates/prometheus-alerts.yaml`:
    - `SLOAvailabilityBreach` - Availability < 99.9%
    - `SLOLatencyP95Breach` - Latency p95 > 500ms
    - `SLOErrorRateBreach` - Error rate > 0.1%
    - `ErrorBudgetLow` - Error budget < 10%

  - `charts/stoa-platform/templates/alertmanager-config.yaml`:
    - Slack configuration (#ops-alerts)
    - Routes by severity (critical, warning)

  - `docker/observability/grafana/dashboards/slo-dashboard.json`:
    - Gauges: Availability, Latency P95, Error Rate, Error Budget
    - Time series: 24h Trends
    - Component SLOs: API, MCP Gateway, Vault, AWX
    - Alert list panel

  - `docker/observability/grafana/provisioning/`:
    - `datasources/prometheus.yml` - Prometheus + Loki
    - `dashboards/default.yml` - Auto-provisioning config

- **Security Scanning (CAB-108)**
  - `tests/security/zap/` - OWASP ZAP configuration:
    - `zap-baseline.yaml` - Passive scan (production-safe)
    - `zap-full.yaml` - Full active scan (staging only)
    - `api-scan-rules.conf` - Rules (FAIL: SQL injection, XSS, HSTS)

  - `scripts/run-security-scan.sh` - Scan script:
    - Modes: baseline, api, full
    - Environments: dev, staging, prod
    - Production protection (blocks active scans)
    - Slack notification

  - `.github/workflows/security-scan.yml`:
    - ZAP baseline scan
    - Trivy container scanning
    - pip-audit + npm audit (dependencies)
    - Gitleaks (secrets detection)
    - Schedule: Sunday 4 AM + PR to main

  - `tests/security/README.md` - Complete documentation

- **Chaos Testing LitmusChaos (CAB-109)**
  - `scripts/install-litmus.sh` - LitmusChaos 3.0 installation:
    - Helm install with CRDs
    - RBAC and pre-installed experiments
    - Commands: install, uninstall, verify

  - `tests/chaos/experiments/` - Chaos scenarios:
    - `pod-delete-api.yaml` - Kill Control-Plane API pods
    - `pod-delete-mcp.yaml` - Kill MCP Gateway pods
    - `pod-delete-vault.yaml` - Kill Vault pod (auto-unseal test)
    - `pod-delete-awx.yaml` - Kill AWX pods
    - `network-latency.yaml` - 500ms latency injection
    - `cpu-stress.yaml` - CPU/Memory stress tests

  - `tests/chaos/workflows/full-chaos-suite.yaml`:
    - Complete workflow executing all scenarios
    - Final platform health validation
    - Schedule: Saturday 2 AM (staging)

  - `tests/chaos/README.md` - Chaos testing documentation

### Changed (2026-01-04) - CAB-237 Rename devops → console subdomain

- **Control Plane UI Subdomain Rename**
  - `devops.stoa.cab-i.com` → `console.stoa.cab-i.com`
  - Reflects UI unification: DevOps + Developers (AI Tools Portal)

- **Configuration files updated**:
  - `deploy/config/dev.env` - CORS_ORIGINS, DOMAIN_UI
  - `deploy/config/staging.env` - CORS_ORIGINS, DOMAIN_UI
  - `deploy/config/prod.env` - CORS_ORIGINS, DOMAIN_UI
  - `control-plane-api/src/config.py` - CORS_ORIGINS default
  - `control-plane-api/Dockerfile` - ENV CORS_ORIGINS
  - `gitops-templates/_defaults.yaml` - CONTROL_PLANE_UI_URL

- **Scripts and playbooks**:
  - `ansible/playbooks/bootstrap-platform.yaml` - URL in final message
  - `scripts/init-gitlab-gitops.sh` - URL in display

- **Documentation**:
  - `CLAUDE.md` - Key URLs section
  - `README.md` - Architecture diagram, URLs, examples
  - `docs/ibm/webmethods-gateway-api.md` - Example URLs
  - `docs/runbooks/README.md` - Service URLs
  - `docs/runbooks/high/certificate-expiration.md` - Check script domains
  - `docs/runbooks/medium/api-rollback.md` - Verification URLs

- **Migration scripts**:
  - `scripts/update-keycloak-console-redirect.sh` - Updates Keycloak redirectURIs
  - `scripts/verify-console-dns.sh` - Verifies/creates Route53 DNS

- **Deployment completed**:
  - Ingress `control-plane-ui` updated to `console.stoa.cab-i.com`
  - TLS Certificate `stoa-console-tls` issued by Let's Encrypt
  - Keycloak client `control-plane-ui` redirectURIs updated

- **Console UI Access**:
  - URL: https://console.stoa.cab-i.com
  - Users: `admin@cab-i.com`, `demo@apim.local` (password: `demo`)

### Added (2026-01-04) - CAB-124 Portal Integration - Tool Catalog

- **Control Plane UI - AI Tools Section**
  - `src/pages/AITools/ToolCatalog.tsx` - MCP Tools catalog:
    - Card grid with filters (search, tag, tenant)
    - Pagination and results counter
    - Inline Subscribe/Unsubscribe button
    - Navigation to tool detail

  - `src/pages/AITools/ToolDetail.tsx` - Tool detail page:
    - Header with name, method, version, tags
    - Tabs: Overview, Schema, Quick Start, Usage
    - Subscribe/Unsubscribe button
    - Usage statistics display

  - `src/pages/AITools/MySubscriptions.tsx` - Subscription management:
    - Table of subscribed tools
    - Status, usage count, subscription date
    - Actions: view detail, unsubscribe

  - `src/pages/AITools/UsageDashboard.tsx` - Metrics dashboard:
    - Stats cards: Total Calls, Success Rate, Avg Latency, Cost
    - Temporal charts (UsageChart)
    - Breakdown table by tool
    - Period selector (day, week, month)

  - `src/components/tools/ToolCard.tsx` - Tool card for catalog:
    - Display: name, description, method, tags, params count
    - API-backed indicator, tenant info
    - Subscribe button

  - `src/components/tools/ToolSchemaViewer.tsx` - JSON Schema viewer:
    - Hierarchical property display
    - Colored types, required badges
    - Enum, default values
    - Expandable mode for objects/arrays

  - `src/components/tools/QuickStartGuide.tsx` - Integration guide:
    - Tabs: Claude Desktop, Python SDK, cURL
    - Code snippets with Copy button
    - Automatic argument example generation

  - `src/components/tools/UsageChart.tsx` - Usage charts:
    - Simple bar chart with hover tooltips
    - Trend indicator
    - UsageStatsCard for key metrics

  - `src/services/mcpGatewayApi.ts` - MCP Gateway API client:
    - Methods: getTools, getTool, getToolTags
    - Subscriptions: getMySubscriptions, subscribeTool, unsubscribeTool
    - Usage: getMyUsage, getToolUsage, getUsageHistory
    - Server info and health check

  - `src/types/index.ts` - Added TypeScript types:
    - MCPTool, ToolInputSchema, ToolPropertySchema
    - ListToolsResponse, ToolUsageStats, ToolUsageSummary
    - ToolSubscription, ToolSubscriptionCreate

  - **Navigation and routes** (`src/App.tsx`, `src/components/Layout.tsx`):
    - "AI Tools" menu with Wrench icon
    - Routes: /ai-tools, /ai-tools/:toolName, /ai-tools/subscriptions, /ai-tools/usage
    - QuickActionCard on Dashboard

  - **Configuration** (`src/config.ts`):
    - `services.mcpGateway.url` (VITE_MCP_GATEWAY_URL)
    - `features.enableAITools` (VITE_ENABLE_AI_TOOLS)

  - **Tests** (vitest + @testing-library/react):
    - `src/components/tools/ToolCard.test.tsx` - 12 tests
    - `src/components/tools/ToolSchemaViewer.test.tsx` - 10 tests
    - `src/services/mcpGatewayApi.test.ts` - 15 tests
    - Setup: vitest.config.ts, test/setup.ts, test/mocks.ts

  - **Added dev dependencies**:
    - vitest, @testing-library/react, @testing-library/jest-dom
    - @testing-library/user-event, jsdom

### Added (2026-01-04) - CAB-121 Tool Registry CRDs Kubernetes

- **STOA MCP Gateway - Kubernetes CRDs for Tool Registry**
  - `charts/stoa-platform/crds/tool-crd.yaml` - Tool CRD:
    - Kind: `Tool`, API Group: `stoa.cab-i.com/v1alpha1`
    - Spec: displayName, description, endpoint, method, inputSchema, tags
    - Authentication: type (none/apiKey/bearer/oauth2), secretRef
    - Status subresource: phase, invocationCount, errorCount, conditions
    - Printer columns for `kubectl get tools`

  - `charts/stoa-platform/crds/toolset-crd.yaml` - ToolSet CRD:
    - Kind: `ToolSet`, generates multiple tools from OpenAPI spec
    - Sources: url, configMapRef, secretRef, inline
    - Selector: filtering by tags, operationIds, methods
    - toolDefaults: default values for all generated tools

  - `src/k8s/models.py` - Pydantic models for CRDs:
    - `ToolCR`, `ToolCRSpec`, `ToolCRStatus`, `ToolCRAuthentication`
    - `ToolSetCR`, `ToolSetCRSpec`, `OpenAPISource`, `ToolSelector`
    - Complete spec validation

  - `src/k8s/watcher.py` - Async Kubernetes Watcher:
    - `ToolWatcher`: watching Tool and ToolSet CRDs
    - Callbacks: on_added, on_removed, on_modified
    - CRD → internal Tool conversion
    - Multi-namespace or single namespace support
    - Graceful degradation if kubernetes-asyncio not installed
    - Automatic watch restart with backoff

  - `charts/stoa-platform/templates/mcp-gateway-rbac.yaml`:
    - ServiceAccount, ClusterRole, RoleBinding
    - Permissions: get, list, watch on tools, toolsets
    - Permissions: patch, update on status subresource

  - `charts/stoa-platform/templates/mcp-gateway-deployment.yaml`:
    - Complete Helm Deployment for MCP Gateway
    - All configurable environment variables
    - Liveness/readiness probes

  - `charts/stoa-platform/values/mcp-gateway.yaml`:
    - Default MCP Gateway configuration
    - Commented example CRDs

  - `tests/test_k8s.py` - 24 tests:
    - Model tests: ToolCR, ToolCRSpec, ToolSetCR
    - Watcher tests: callbacks, tool name generation, event handling
    - Singleton pattern tests
    - OpenAPI converter integration tests

  - **Added configuration** (`src/config/settings.py`):
    - `k8s_watcher_enabled`: bool (default: False)
    - `k8s_watch_namespace`: str | None (default: None = all namespaces)
    - `kubeconfig_path`: str | None (default: None = in-cluster config)

  - **Optional dependency**: `kubernetes-asyncio>=29.0.0`, `pyyaml>=6.0`
    - Installation: `pip install stoa-mcp-gateway[k8s]`

  - **Metrics**: 196 tests, 79% global coverage
    - k8s/models.py: 100% coverage
    - k8s/watcher.py: 45% coverage (async code difficult to test)

### Added (2026-01-04) - CAB-123 Metering Pipeline (Kafka)

- **STOA MCP Gateway - Metering Pipeline**
  - `src/metering/models.py` - Metering event schema:
    - `MeteringEvent`: tenant, project, consumer, user_id, tool, latency_ms, status, cost_units
    - `MeteringStatus`: success, error, timeout, rate_limited, unauthorized
    - `MeteringEventBatch`: Event batch for bulk processing
    - Methods: `to_kafka_message()`, `from_tool_invocation()`, `_compute_cost()`
    - Pricing model: base cost + latency cost + premium tools

  - `src/metering/producer.py` - Async Kafka Producer:
    - `MeteringProducer`: aiokafka client with buffering
    - Dual mode: emit (buffered) vs emit_immediate (direct)
    - Periodic flush (5s) and flush on buffer full (100 events)
    - Graceful degradation if Kafka unavailable
    - Gzip compression, idempotence, partition by tenant

  - **MCP handlers integration** (`src/handlers/mcp.py`):
    - Automatic metering on each tool invocation
    - Capture: latency_ms, status, consumer (X-Consumer-ID header)
    - Emission even for errors (403, timeout, etc.)
    - Fire-and-forget (doesn't block request)

  - `tests/test_metering.py` - 23 tests:
    - MeteringEvent tests: creation, serialization, cost computation
    - MeteringProducer tests: buffering, flush, graceful failure
    - Singleton pattern tests
    - Integration tests with mocked Kafka

  - **Added configuration** (`src/config/settings.py`):
    - `metering_enabled`: bool (default: True)
    - `kafka_bootstrap_servers`: str (default: localhost:9092)
    - `metering_topic`: str (default: stoa.metering.events)
    - `metering_buffer_size`: int (default: 100)
    - `metering_flush_interval`: float (default: 5.0s)

  - **Dependency**: aiokafka>=0.10.0 added to pyproject.toml

  - **Metrics**: 172 tests, 85% global coverage
    - metering/models.py: 100% coverage
    - metering/producer.py: 69% coverage

- **Rename**: `stoa-mcp-gateway/` → `mcp-gateway/`

### Added (2026-01-04) - CAB-122 OPA Policy Engine Integration

- **STOA MCP Gateway - OPA Policy Engine**
  - `src/policy/opa_client.py` - OPA Client with dual mode:
    - Embedded mode (MVP): Python rule evaluation (no sidecar)
    - Sidecar mode (production): HTTP requests to OPA
    - Fail-open for high availability

  - `src/policy/policies/authz.rego` - Rego authorization rules:
    - Tool classification: read_only, write, admin
    - Role → scope mapping (cpi-admin, tenant-admin, devops, viewer)
    - Multi-tenant isolation
    - Dynamic tools management

  - `src/policy/policies/tools.rego` - Tool-specific rules:
    - Rate limiting by role
    - Production environment restrictions
    - Confirmation for destructive actions

  - `tests/test_opa_policy.py` - 31 tests for policy engine:
    - EmbeddedEvaluator tests: scopes, authz, tenant isolation, dynamic tools
    - OPAClient tests: embedded, sidecar, fail-open
    - Singleton pattern tests

  - **MCP handlers integration**:
    - Policy check before tool invocation
    - user_claims construction from TokenClaims
    - 403 error if policy denied

  - **Docker Compose**: OPA sidecar added (openpolicyagent/opa:0.60.0)

  - **Metrics**: 149 tests, 86% global coverage
    - opa_client.py: 93% coverage

### Added (2026-01-04) - CAB-199 MCP Gateway Tests & Tools Implementation

- **STOA MCP Gateway - Complete tests and additional tools**
  - `tests/test_tool_registry.py` - 46 tests for tool registry
    - Basic tests: register, unregister, get, overwrite
    - List tests: filter by tenant, by tag, pagination
    - Lifecycle tests: startup, shutdown, HTTP client
    - Invocation tests: builtin tools, API-backed tools, error handling
    - HTTP methods tests: GET, POST, PUT, DELETE, PATCH
    - Singleton pattern tests
    - New built-in tools tests

  - `tests/test_openapi_converter.py` - 30 tests for OpenAPI conversion
    - Basic tests: empty spec, single/multiple operations
    - Conversion tests: operationId, name generation, description
    - Parameters tests: query, path, enum, required
    - Request body tests: properties extraction
    - Base URL tests: OpenAPI 3.x, Swagger 2.0, override
    - Metadata tests: api_id, tenant_id, version
    - Edge cases tests: $ref, missing schema, non-dict paths

  - `tests/test_mcp.py` - 25 tests for MCP handlers
    - Server info, tools, resources, prompts endpoint tests
    - Pagination and filters tests
    - Authentication tests with dependency override
    - Response format tests (camelCase aliases)

  - `src/services/openapi_converter.py` - OpenAPI → MCP Tools Converter
    - OpenAPI 3.0.x, 3.1.x and Swagger 2.0 support
    - Parameters extraction (path, query, header)
    - Request body extraction (JSON)
    - Automatic name generation if no operationId
    - Name sanitization for MCP compatibility
    - STOA metadata (api_id, tenant_id, base_url)

  - **New built-in tools** added to registry:
    - `stoa_health_check` - Service health check (api, gateway, auth)
    - `stoa_list_tools` - List available tools with tag filtering
    - `stoa_get_tool_schema` - Get tool schema
    - `stoa_search_apis` - API search by keyword (placeholder)

  - **tool_registry.py improvements**:
    - HTTP PATCH method support
    - 7 total built-in tools
    - Helper methods: `_check_health()`, `_get_tools_info()`, `_get_tool_schema()`

  - **Metrics**: 118 tests, 85% global coverage
    - tool_registry.py: 96% coverage
    - openapi_converter.py: 91% coverage
    - mcp.py (handlers): 98% coverage
    - models/mcp.py: 100% coverage

### Added (2026-01-03) - CAB-120 MCP Gateway Auth + MCP Base

- **STOA MCP Gateway - Phase 2** - Auth + MCP Base
  - `stoa-mcp-gateway/src/middleware/auth.py` - Complete Keycloak OIDC Middleware
    - JWT validation with JWKS cache (TTL 5 min)
    - `TokenClaims` model with helpers `has_role()`, `has_scope()`
    - FastAPI dependencies: `get_current_user`, `get_optional_user`
    - Factories: `require_role()`, `require_scope()` for access control
    - Bearer token + API Key (M2M) support

  - `stoa-mcp-gateway/src/handlers/mcp.py` - MCP Protocol Handlers
    - `GET /mcp/v1/` - Server info and capabilities
    - `GET /mcp/v1/tools` - Tool list with pagination
    - `GET /mcp/v1/tools/{name}` - Tool details
    - `POST /mcp/v1/tools/{name}/invoke` - Invocation (auth required)
    - `GET /mcp/v1/resources` - Resource list
    - `GET /mcp/v1/prompts` - Prompt list

  - `stoa-mcp-gateway/src/models/mcp.py` - Pydantic MCP spec models
    - `Tool`, `ToolInvocation`, `ToolResult` with STOA extensions
    - `Resource`, `ResourceReference`, `ResourceContentRead`
    - `Prompt`, `PromptArgument`, `PromptMessage`
    - Responses: `ListToolsResponse`, `InvokeToolResponse`, etc.

  - `stoa-mcp-gateway/src/services/tool_registry.py` - Tool Registry
    - Dynamic tool registration
    - Built-in tools: `stoa_platform_info`, `stoa_list_apis`, `stoa_get_api_details`
    - Invocation with user token forwarding
    - HTTP backend support (GET/POST/PUT/DELETE)

  - `stoa-mcp-gateway/src/middleware/metrics.py` - Prometheus Metrics
    - HTTP: requests total, duration, in-progress
    - MCP: tool invocations, duration per tool
    - Auth: attempts, token validation duration
    - Backend: requests by backend/method/status

  - `stoa-mcp-gateway/docker-compose.yml` - Local development stack
    - MCP Gateway with hot-reload (Dockerfile.dev)
    - Keycloak with pre-configured `stoa` realm
    - Prometheus (port 9090)
    - Grafana (port 3000, admin/admin)

  - `stoa-mcp-gateway/dev/keycloak/stoa-realm.json` - Keycloak Realm
    - Roles: `cpi-admin`, `tenant-admin`, `devops`, `viewer`
    - Clients: `stoa-mcp-gateway`, `stoa-test-client`
    - Test users: admin, tenant-admin, devops, viewer

  - **Tests**: 25 tests, 71% coverage
    - `tests/test_auth.py` - TokenClaims, OIDCAuthenticator
    - `tests/test_mcp.py` - MCP Endpoints
    - `tests/test_health.py` - Health checks

### Changed (2025-01-03) - Rebranding APIM → STOA

- **Complete project renaming** - APIM Platform becomes STOA Platform
  - GitHub Repository: `apim-aws` → `stoa`
  - GitLab Repository: `apim-gitops` → `stoa-gitops` (cab6961310/stoa-gitops)
  - Domain: `apim.cab-i.com` → `stoa.cab-i.com`
  - Kubernetes Namespace: `apim-system` → `stoa-system`
  - Keycloak realm: `apim` → `stoa`
  - Helm chart: `apim-platform` → `stoa-platform`
  - Vault paths: `secret/apim/*` → `secret/stoa/*`
  - AWS resources: `apim-*` → `stoa-*`

- **72 files modified** for rebranding:
  - Documentation (README, CHANGELOG, docs/*)
  - Configuration (deploy/config/*.env)
  - Python API (control-plane-api/)
  - React UI (control-plane-ui/)
  - Ansible playbooks and vars
  - GitOps templates
  - Helm charts and K8s manifests
  - Scripts
  - Terraform modules

- **GitLab stoa-gitops repository initialized**
  - Structure: environments/{dev,staging,prod}, tenants/, argocd/
  - ArgoCD ApplicationSets configured
  - URL: https://gitlab.com/cab6961310/stoa-gitops

- **Complete AWS infrastructure migration**
  - DNS: `*.stoa.cab-i.com` configured (Hostpapa CNAME)
  - TLS Certificates Let's Encrypt generated for all subdomains
  - Kubernetes Ingresses updated (api, devops, auth, gateway, awx)
  - Keycloak: hostname corrected in deployment args
  - AWX: CRD updated with new hostname
  - Control-Plane UI: rebuilt with new URLs

- **URL hardcoding removal**
  - Ansible playbooks: using `{{ base_domain | default('stoa.cab-i.com') }}`
  - Scripts: using environment variables with fallback
  - Centralized configuration in `ansible/vars/platform-config.yaml`

- **Centralized configuration architecture**
  - `BASE_DOMAIN` as single source of truth for domain
  - .env files with derived variables: `${BASE_DOMAIN}` → subdomains
  - Enables client deployment by changing a single variable
  - Structure:
    - `deploy/config/{dev,staging,prod}.env` - Per-environment configuration
    - `control-plane-api/src/config.py` - Python config with BASE_DOMAIN fallback
    - `control-plane-ui/src/config.ts` - TypeScript config with Vite env vars
    - `ansible/vars/platform-config.yaml` - Centralized Ansible config
    - `gitops-templates/_defaults.yaml` - GitOps defaults with interpolation

### Removed (2024-12-23) - webMethods Developer Portal Removal

- **webMethods Developer Portal** - Removed from architecture
  - IBM trial license requested only for Gateway (without Portal)
  - Custom React Developer Portal planned for Phase 8
  - Playbook `promote-portal.yaml` removed
  - Portal references removed from documentation
  - Handler `_handle_promote_request` removed from deployment_worker

### Added (2025-12-23) - Phase 3: Secrets & Gateway Alias - COMPLETED ✅

- **HashiCorp Vault** - Deployed on EKS for centralized secrets management
  - Helm chart `hashicorp/vault` v0.31.0 (Vault 1.20.4)
  - Namespace: `vault`
  - Storage: 5GB PVC (gp2)
  - UI accessible: https://vault.stoa.cab-i.com
  - Unseal keys saved in AWS Secrets Manager (`stoa/vault/keys`)

- **Vault Secrets Engine** - KV v2 for APIM secrets
  - Path: `secret/stoa/{env}/{type}`
  - Structure:
    - `secret/stoa/dev/gateway-admin` - Gateway admin credentials
    - `secret/stoa/dev/keycloak-admin` - Keycloak admin credentials
    - `secret/stoa/dev/awx-automation` - AWX client credentials
    - `secret/stoa/dev/aliases/*` - Backend aliases with credentials

- **Vault Kubernetes Auth** - Native K8s authentication
  - Roles: `stoa-apps` (read), `awx-admin` (read/write)
  - Service accounts: `control-plane-api`, `awx-web`, `awx-task`
  - Policies: `stoa-read`, `stoa-admin`

- **sync-alias.yaml Playbook** - Vault → Gateway alias synchronization
  - Reading aliases from Vault
  - Create/update in webMethods Gateway
  - Authentication support: Basic Auth, API Key, OAuth2
  - Dry-run mode for preview

- **rotate-credentials.yaml Playbook** - Automatic credential rotation
  - Supported types: password, api_key, oauth_client
  - Vault + Gateway Alias update in one operation
  - Keycloak client secret rotation for OAuth
  - Notification callback to Control-Plane API

- **AWX Job Templates** - New Phase 3 templates
  - `Sync Gateway Aliases` (ID: 15) - sync-alias.yaml
  - `Rotate Credentials` (ID: 16) - rotate-credentials.yaml

### Fixed (2024-12-23) - OpenAPI 3.1.0 → 3.0.0 Conversion

- **OpenAPI Version Compatibility** - webMethods Gateway 10.15 doesn't support OpenAPI 3.1.0
  - `deploy-api.yaml`: Automatic OpenAPI version detection
  - 3.1.x → 3.0.0 conversion before Gateway import
  - Native swagger 2.0 and OpenAPI 3.0.x support
  - API type detection (`swagger` vs `openapi`) in playbook

- **Gateway Proxy Response Format** - Handling both response formats
  - Control-Plane API proxy returns `{"api_id": "..."}`
  - Direct Gateway returns `{"apiResponse": {"api": {"id": "..."}}}`
  - Variable `imported_api_id` extracted for compatibility
  - Variable `final_api_id` for unified display

- **POST /v1/gateway/apis** - New endpoint for API import via proxy
  - `control-plane-api/src/routers/gateway.py`: POST /apis route
  - `control-plane-api/src/services/gateway_service.py`: `import_api()` method
  - `apiDefinition` support as JSON object (not string)
  - `type` parameter support (openapi, swagger, raml, wsdl)

- **AWX Job Template Deploy API** - E2E flow validated
  - API import with OpenAPI 3.1.0 spec (converted to 3.0.0)
  - Automatic API activation after import
  - Notification to Control-Plane API
  - Test validated: Control-Plane-API-E2E v2.2 (ID: 4b4045ba-23f3-4a45-ad38-680419d79880)

### Fixed (2024-12-22) - E2E Pipeline Kafka → AWX

- **AWX Token** - Configuration and persistence
  - API Token created and saved in AWS Secrets Manager (`stoa/awx-token`)
  - Variable `AWX_TOKEN` configured on control-plane-api deployment

- **AWX Job Template Names** - Code/AWX alignment
  - `awx_service.py`: `deploy-api` → `Deploy API`, `rollback-api` → `Rollback API`
  - `deployment_worker.py`: `promote-portal` → `Promote Portal`, `sync-gateway` → `Sync Gateway`

- **Missing GitLab Playbooks** - Push to stoa-gitops
  - `deploy-api.yaml` - API deployment to Gateway
  - `rollback.yaml` - API rollback/deactivation
  - `sync-gateway.yaml` - Gateway synchronization
  - `promote-portal.yaml` - API publication to Gateway

- **Kafka Snappy Compression** - snappy codec support
  - Added `python-snappy==0.7.3` to requirements.txt
  - Added `libsnappy-dev` to Dockerfile

- **GitLab Atomic Commits** - Fixed race condition
  - `git_service.py`: Using `commits.create()` API for atomic commits
  - Avoids `reference does not point to expected object` error

- **AWX Project Sync** - Updated job templates
  - All templates (Deploy API, Rollback API, Sync Gateway, Promote Portal)
    point to project 7 "APIM Playbooks" with correct playbooks

- **Deploy API Pipeline** - Working Kafka → AWX → Gateway flow
  - `deploy-api.yaml`: Fixed recursive Ansible variables (`_gateway_url` vs `gw_url`)
  - `deploy-api.yaml`: Added default credentials (avoids missing `vars_files` in AWX)
  - `awx_service.py`: Added `openapi_spec` parameter in `deploy_api()`
  - `deployment_worker.py`: Transmits `openapi_spec` to AWX extra_vars
  - `events.py`: Endpoint `POST /v1/events/deployment-result` for AWX callbacks
  - Test validated: PetstoreAPI v3.0.0 deployed and activated via pipeline

- **OIDC Playbooks** - Migration to OIDC authentication via Gateway-Admin-API proxy
  - All playbooks support 2 modes: OIDC (recommended) and Basic Auth (fallback)
  - External HTTPS URLs: `https://auth.stoa.cab-i.com`, `https://api.stoa.cab-i.com/v1/gateway`
  - Service account client `awx-automation` for AWX
  - Updated playbooks: `deploy-api.yaml`, `rollback.yaml`, `sync-gateway.yaml`, `promote-portal.yaml`
  - `bootstrap-platform.yaml`: Automatic creation of Keycloak client `awx-automation`

### Added (Phase 2.5) - E2E Validation - COMPLETED ✅

- **Gateway OIDC Configuration** - APIs secured via Keycloak
  - External Authorization Server `KeycloakOIDC` configured in Gateway
  - OAuth2 Strategies per application with JWT validation
  - Standardized scope mappings: `{AuthServer}:{Tenant}:{Api}:{Version}:{Scope}`
  - Secured APIs:
    - Control-Plane-API (ID: `7ba67c90-814d-4d2f-a5da-36e9cda77afe`)
    - Gateway-Admin-API (ID: `8f9c7b6c-1bc6-4438-88be-a10e2352bae2`) - Admin proxy

- **Gateway Admin Service** - OIDC Proxy for Gateway administration
  - `control-plane-api/src/services/gateway_service.py` - Dual-mode auth service
  - `control-plane-api/src/routers/gateway.py` - Router `/v1/gateway/*`
  - Token forwarding: User JWT transmitted to Gateway (audit trail)
  - Basic Auth fallback for legacy compatibility
  - Config: `GATEWAY_USE_OIDC_PROXY=True` (default)

- **Secrets Security** - AWS Secrets Manager + K8s
  - `ansible/vars/secrets.yaml` - Centralized configuration (zero hardcoding)
  - `terraform/modules/secrets/main.tf` - AWS Secrets Manager module
  - Documented strategy:
    - **AWS Secrets Manager**: Bootstrap secrets (gateway-admin, keycloak-admin, rds-master, etc.)
    - **K8s Secrets / Vault**: Runtime secrets (OAuth clients, tenant tokens)
  - AWS SM paths: `stoa/{env}/gateway-admin`, `stoa/{env}/keycloak-admin`, etc.
  - All Ansible playbooks updated with `vars_files: ../vars/secrets.yaml`

- **STOA Platform Tenant** - Administrator tenant with cross-tenant access
  - File: `tenants/stoa/` in GitLab stoa-gitops
  - User: `stoaadmin@cab-i.com` (role: cpi-admin)
  - API: Control-Plane configured for Gateway OIDC

- **Ansible Playbooks** - Complete automation
  - `bootstrap-platform.yaml` - **Platform initialization** (KeycloakOIDC + bootstrap APIs)
  - `provision-tenant.yaml` - Creates Keycloak groups, users, K8s namespaces
  - `register-api-gateway.yaml` - OpenAPI import, OIDC, rate limiting, activation
  - `configure-gateway-oidc.yaml` - Complete OIDC configuration
  - `configure-gateway-oidc-tasks.yaml` - Reusable tasks with scope naming
  - `tasks/create-keycloak-user.yaml` - User creation with roles
  - Existing secured playbooks: `deploy-api`, `sync-gateway`, `promote-portal`, `rollback`

- **Gateway-Admin API** - OpenAPI spec for admin proxy
  - `apis/gateway-admin-api/openapi.json` - OpenAPI 3.0.3 spec
  - Endpoints: `/apis`, `/applications`, `/scopes`, `/alias`, `/configure-oidc`, `/health`
  - Secured via Keycloak JWT (BearerAuth)
  - Backend: proxy to `apigateway:5555/rest/apigateway`

- **AWX Job Templates** - New templates
  - `Provision Tenant` (ID: 12) - Complete tenant provisioning
  - `Register API Gateway` (ID: 13) - API registration in Gateway

- **Control-Plane API** - New handlers and services
  - Router `/v1/gateway/*` - Gateway administration via OIDC proxy
  - Endpoints: `GET /apis`, `PUT /apis/{id}/activate`, `POST /configure-oidc`, etc.
  - Event `tenant-provisioning` → AWX Provision Tenant
  - Event `api-registration` → AWX Register API Gateway
  - `gateway_service`: `list_apis()`, `activate_api()`, `configure_api_oidc()`, etc.
  - `awx_service`: `provision_tenant()`, `register_api_gateway()`

- **Clarified architecture**
  - GitHub (stoa): Source code, development, CI/CD
  - GitLab (stoa-gitops): Runtime data, tenants, AWX playbooks

### Added (Phase 2) - COMPLETED
- **GitOps Templates** (`gitops-templates/`) - Templates to initialize GitLab
  - `_defaults.yaml` - Global default variables
  - `environments/{dev,staging,prod}/config.yaml` - Per-environment config
  - `templates/` - API, Application, Tenant templates
  - **Note**: Tenant data is on GitLab, not here

- **Variable Resolver Service** - `${VAR}` and `${VAR:default}` placeholder resolution
  - Vault reference support: `vault:secret/path#key`
  - Config merge: global → env → tenant → inline defaults
  - Required variable validation

- **IAM Sync Service** - GitOps ↔ Keycloak synchronization
  - Per-tenant group/user sync
  - OAuth2 client creation for applications
  - Reconciliation and drift detection
  - Client secret rotation

- **GitOps-Enabled Routers**
  - APIs router: CRUD via GitLab + Kafka events
  - Tenants router: Multi-tenant with RBAC

- **ArgoCD** - GitOps Continuous Delivery
  - Helm Chart with Keycloak SSO
  - ApplicationSets for multi-tenant auto-discovery
  - AppProjects with per-tenant RBAC
  - Installation scripts: `scripts/install-argocd.sh`
  - URL: https://argocd.stoa.cab-i.com

- **Init GitLab Script** - `scripts/init-gitlab-gitops.sh`
  - Initializes GitLab stoa-gitops repo
  - Copies templates and configurations

- **GitLab stoa-gitops** - Configured repository
  - URL: https://gitlab.com/cab6961310/stoa-gitops
  - Structure: `_defaults.yaml`, `environments/`, `tenants/`
  - Connected to ArgoCD for GitOps

---

## [2.0.0] - 2024-12-21

### Phase 1: Event-Driven Architecture - COMPLETED

#### Added
- **Redpanda (Kafka)** - Kafka-compatible event streaming
  - 1 broker on EKS with Redpanda Console
  - Storage: 10GB persistent (EBS gp2)
  - Topics: `api-created`, `api-updated`, `api-deleted`, `deploy-requests`, `deploy-results`, `audit-log`, `notifications`

- **AWX (Ansible Tower)** - Automation
  - AWX 24.6.1 via AWX Operator 2.19.1
  - URL: https://awx.stoa.cab-i.com
  - Job Templates: Deploy API, Sync Gateway, Promote Portal, Rollback API

- **Control-Plane UI** - React Interface
  - Keycloak authentication with PKCE (Keycloak 25+)
  - Pages: Dashboard, Tenants, APIs, Applications, Deployments, Monitoring
  - URL: https://console.stoa.cab-i.com

- **Control-Plane API** - FastAPI Backend
  - Integrated Kafka Producer (events on CRUD)
  - Deployment Worker (consumer `deploy-requests`)
  - GitLab Webhook (Push, MR, Tag Push)
  - Pipeline Traces (in-memory store)
  - URL: https://api.stoa.cab-i.com

- **Variabilized Configuration**
  - UI: `VITE_*` variables for build-time config
  - API: Environment variables via pydantic-settings
  - Dockerfiles with build args for customization

#### Changed
- Infrastructure: 3x t3.large (2 CPU / 8GB RAM) to support Redpanda + AWX
- Keycloak: Realm `stoa`, clients `control-plane-ui` and `control-plane-api`

#### Fixed
- PKCE Authentication - `response_type: 'code'` + `pkce_method: 'S256'`
- Keycloak URLs - `auth.stoa.cab-i.com` instead of `keycloak.dev.stoa.cab-i.com`
- OpenAPI Tags - Case harmonization (`Traces` instead of `traces`)

---

## [1.0.0] - 2024-12-XX

### Initial Infrastructure

#### Added
- **AWS Infrastructure** (Terraform)
  - VPC with public/private subnets
  - EKS Cluster `stoa-dev-cluster`
  - RDS PostgreSQL (db.t3.micro)
  - ECR Repositories

- **Kubernetes**
  - Nginx Ingress Controller
  - Cert-Manager (Let's Encrypt)
  - EBS CSI Driver

- **webMethods**
  - API Gateway (lean trial 10.15)
  - Elasticsearch 8.11 (for Gateway)

- **Keycloak** - Identity Provider
  - URL: https://auth.stoa.cab-i.com
  - Realm: `stoa`

---

## Roadmap

### Phase 2: GitOps + ArgoCD (High Priority) - COMPLETED ✅
- [x] Per-tenant GitOps structure (`gitops-templates/`)
- [x] Variable Resolver (templates with `${VAR}` placeholders)
- [x] IAM Sync Service (Git → Keycloak)
- [x] API/Tenants routers with GitLab integration
- [x] ArgoCD Helm chart with Keycloak SSO
- [x] Multi-tenant ApplicationSets
- [x] ArgoCD installation on EKS
- [x] GitLab `stoa-gitops` repository configured

### Phase 2.5: E2E Validation - COMPLETED ✅
- [x] provision-tenant.yaml playbook (Keycloak + K8s namespaces)
- [x] register-api-gateway.yaml playbook (Gateway OIDC)
- [x] AWX Job Templates (Provision Tenant, Register API Gateway)
- [x] stoa tenant in GitLab with STOAAdmin
- [x] Control-Plane API handlers (tenant-provisioning, api-registration)
- [x] User stoaadmin@cab-i.com created with cpi-admin role
- [x] GitHub/GitLab architecture documented

### Phase 3: Secrets & Gateway Alias - COMPLETED ✅
- [x] HashiCorp Vault deployed on EKS
- [x] Vault KV v2 with APIM secrets structure
- [x] Kubernetes auth configured (roles, policies)
- [x] sync-alias.yaml playbook for Gateway Alias
- [x] rotate-credentials.yaml playbook for secret rotation
- [x] AWX Jobs: Sync Gateway Aliases, Rotate Credentials
- [ ] External Secrets Operator integration (optional - future)
- [ ] Auto-unseal with AWS KMS (optional - future)

### Phase 2.6: Cilium Network Foundation (Medium Priority)
- [ ] Install Cilium on EKS (replaces AWS VPC CNI + kube-proxy)
- [ ] Gateway API CRDs + Cilium GatewayClass
- [ ] Migrate Nginx Ingress → Gateway API (*.stoa.cab-i.com)
- [ ] CiliumNetworkPolicy - Default deny + tenant isolation
- [ ] Hubble - Network observability
- [ ] Cilium migration documentation & runbooks

### Phase 4: Observability (Medium Priority)
- [ ] Amazon OpenSearch
- [ ] FluentBit (log shipping)
- [ ] Prometheus + Grafana
- [ ] OpenSearch Dashboards

### Phase 5: Multi-Environment (Low Priority)
- [ ] STAGING Environment
- [ ] Promotion DEV → STAGING → PROD

### Phase 6: Beta Testing (Low Priority)
- [ ] Demo tenant
- [ ] User documentation (MkDocs)

### Phase 7: Operational Security (Low Priority)
- [ ] Job 1: Certificate Checker (TLS expiration, Vault PKI, endpoints)
- [ ] Job 2: Secret Rotation (API Keys, OAuth, DB passwords via Vault)
- [ ] Job 3: Usage Reporting (per-tenant metrics, PDF, email)
- [ ] Job 4: GitLab Security Scan (Gitleaks, Semgrep, Trivy)
- [ ] NotificationService (Email, Slack, PagerDuty)
- [ ] Kubernetes CronJobs (Helm chart)
- [ ] GitLab CI/CD integration (security-scan stage)
- [ ] Jobs Monitoring (Prometheus, Kafka, OpenSearch, Grafana Dashboard)
- [ ] Alerts (job failed, job not running, critical findings)

### Phase 8: Custom Developer Portal (Low Priority)
- [ ] React + TypeScript + Vite + TailwindCSS frontend
- [ ] Keycloak SSO (client `developer-portal`)
- [ ] API catalog with search/filters
- [ ] API detail + Swagger-UI
- [ ] Applications management (CRUD, credentials, API Key rotation)
- [ ] Subscription management
- [ ] Try-It Console (Monaco Editor, backend proxy)
- [ ] Code Samples (curl, Python, JavaScript)
- [ ] `/portal/*` endpoints in Control-Plane API
- [ ] Kafka events (application-created, subscription-created)
- [ ] Kubernetes deployment
- [ ] Detailed plan: [docs/DEVELOPER-PORTAL-PLAN.md](docs/DEVELOPER-PORTAL-PLAN.md)

### Phase 9: Ticketing - Production Requests (Low Priority)
- [ ] PromotionRequest model (YAML in Git)
- [ ] Workflow: PENDING → APPROVED → DEPLOYING → DEPLOYED
- [ ] RBAC: DevOps creates, CPI approves
- [ ] Anti-self-approval rule
- [ ] CRUD endpoints `/v1/requests/prod`
- [ ] Automatic AWX trigger on approval
- [ ] AWX webhook callback → update status
- [ ] UI: Requests list, form, detail, timeline
- [ ] Kafka events (request-created, approved, rejected, deployed, failed)
- [ ] Email + Slack notifications
- [ ] Detailed plan: [docs/TICKETING-SYSTEM-PLAN.md](docs/TICKETING-SYSTEM-PLAN.md)

### Phase 4.5: Jenkins Orchestration Layer (High Priority - Enterprise)
- [ ] Jenkins deployed on EKS (Helm jenkins/jenkins)
- [ ] JCasC configuration (Jenkins Configuration as Code)
- [ ] Keycloak SSO integration (OIDC)
- [ ] Kafka Consumer Service → Jenkins Trigger
- [ ] Jenkinsfile `deploy-api` with approval gates
- [ ] Jenkinsfile `rollback-api` with emergency bypass
- [ ] Jenkinsfile `promote-api` for env promotion
- [ ] Jenkinsfile `delete-api` with confirmation
- [ ] Shared Library (kafkaPublish, awxLaunch, notifyDeployment)
- [ ] Blue Ocean UI accessible
- [ ] Slack notifications configured
- [ ] Jenkins metrics dashboard
- [ ] AWX/Kafka/Keycloak credentials in Jenkins Credentials Store
- [ ] Jenkins config backup (PVC + S3)

### Phase 9.5: Production Readiness (High Priority - Critical) ✅ COMPLETED

> **Tickets**: CAB-103, CAB-104, CAB-105, CAB-106, CAB-107, CAB-108, CAB-109, CAB-110
> **Completed**: 2026-01-05

- [x] AWX database backup script (PostgreSQL) → S3 (CAB-104)
- [x] Vault snapshot backup script → S3 + KMS (CAB-105)
- [x] Kubernetes CronJob for daily backups (AWX + Vault)
- [x] Documented and tested restore procedures (CAB-107)
- [x] K6 Load Testing Pipeline (CAB-106)
- [x] Performance thresholds defined (p95 < 500ms, p99 < 1s)
- [x] Operational runbooks (docs/runbooks/) (CAB-107)
  - Incident: API Gateway down
  - Incident: AWX job failure
  - Incident: Vault sealed
  - Incident: High Kafka lag
  - Procedure: Emergency rollback
  - Procedure: Horizontal scaling
  - Procedure: Secret rotation
- [x] OWASP ZAP scan on Control Plane API and UI (CAB-108)
- [x] Trivy, pip-audit, npm audit, Gitleaks configuration
- [x] LitmusChaos Testing (CAB-109)
  - Pod kill (API, MCP, AWX, Vault)
  - Network latency injection (500ms)
  - CPU/Memory stress
- [x] Kubernetes auto-healing validation
- [x] SLO/SLA documented (CAB-110)
  - Availability: 99.9%
  - API Latency p95: < 500ms
  - Deployment Success Rate: > 99%
  - MTTR: < 1h for P1
- [x] SLO Dashboard in Grafana
- [x] Prometheus alerts configured → Slack #ops-alerts

### Phase 10: Resource Lifecycle Management (Medium Priority)
- [ ] Terraform `common_tags` module with validations
- [ ] Required tags: environment, owner, project, cost-center, ttl, created_at, auto-teardown, data-class
- [ ] Lambda `resource-cleanup` with EventBridge schedule (cron 2h UTC)
- [ ] Owner notifications (48h → 24h → delete)
- [ ] OPA Gatekeeper policies for Kubernetes admission control
- [ ] GitHub Actions workflow `tag-governance.yaml`
- [ ] Grafana "Resource Lifecycle" dashboard
- [ ] Kafka events (resource-created, resource-expiring, resource-deleted, tag-violation)
- [ ] Guardrails: TTL max 30d, prod exclusion, data-class=restricted exclusion
- [ ] Tagging policy documentation
- [ ] Alternative n8n workflow for multi-cloud (optional)

### Phase 11: Resource Lifecycle Advanced (Low Priority)
- [ ] Per-project quota system (Terraform + AWS Service Quotas)
- [ ] Whitelist configuration (ARN patterns, critical=true tags)
- [ ] Ordered destruction (AWS dependencies: IAM → ASG → EC2 → ELB → S3 → RDS)
- [ ] Self-service TTL extension API (`PATCH /v1/resources/{id}/ttl`)
- [ ] Snooze buttons in emails (7d, 14d)
- [ ] 2 extension max limit (60d total)
- [ ] Avoided cost calculation (AWS pricing per instance_type)
- [ ] Grafana "Cost Savings" dashboard (avoided cost per project)
- [ ] Prometheus metrics (resources_deleted, cost_avoided_usd)
- [ ] Complete n8n workflow with Notion board "Resources to Delete"
- [ ] Hourly cron (instead of daily) for pre-alerts
- [ ] Kafka event `resource-ttl-extended`

### Phase 12: STOA MCP Gateway (High Priority) - COMPLETE ✅
- [x] Gateway Core + Keycloak Auth (CAB-120)
  - FastAPI + OIDC middleware with JWKS caching
  - Pydantic MCP Protocol spec models
  - Tool Registry with built-in tools
  - Prometheus metrics middleware
  - Docker Compose dev stack (Keycloak, Prometheus, Grafana)
- [x] Gateway Tests & Tools Implementation (CAB-199)
  - 118 tests, 85% global coverage
  - OpenAPI → MCP Tools converter (OpenAPI 3.x, Swagger 2.0)
  - 7 built-in tools (platform_info, list_apis, get_api_details, health_check, list_tools, get_tool_schema, search_apis)
  - HTTP PATCH method support
- [x] OPA Policy Engine Integration (CAB-122)
  - Embedded mode (Python) + sidecar (Rego)
  - Policies: authz, tenant isolation, rate limiting
  - 31 tests, 93% opa_client.py coverage
- [x] Kafka Metering Pipeline (CAB-123)
  - MeteringEvent schema, async MeteringProducer
  - MCP handlers integration (fire-and-forget)
  - 23 tests, 100% models coverage
- [x] Kubernetes Tool Registry CRDs (CAB-121)
  - CRDs: Tool, ToolSet (OpenAPI → MCP tools)
  - Async Kubernetes watcher with callbacks
  - Helm templates: RBAC, Deployment
  - 24 tests, 100% models coverage
- [x] Portal Integration - Tool Catalog (CAB-124)
  - AI Tools section in Control Plane UI
  - Pages: ToolCatalog, ToolDetail, MySubscriptions, UsageDashboard
  - Components: ToolCard, ToolSchemaViewer, QuickStartGuide, UsageChart
  - mcpGatewayApi.ts service, vitest tests

### Phase 13: B2B Protocol Binders (Low Priority)
- [ ] EDI X12/EDIFACT support
- [ ] SWIFT messaging integration
- [ ] AS2/AS4 protocol handlers
- [ ] B2B message transformation
- [ ] Partner onboarding automation

### Phase 14: Community & Go-to-Market (Medium Priority)
- [ ] GTM-01: Open Core strategy documented (CAB-201)
- [ ] GTM-02: Licensing choice Apache 2.0 vs dual (CAB-202)
- [ ] GTM-03: Repository structure mono vs multi-repo (CAB-203)
- [ ] GTM-04: Public Docusaurus documentation (CAB-204)
- [ ] GTM-05: STOA landing page (CAB-205)
- [ ] GTM-06: Community channels Discord/GitHub (CAB-206)
- [ ] GTM-07: Public roadmap (CAB-207)
- [ ] GTM-08: IBM Partnership positioning (CAB-208)
- [ ] GTM-09: Pricing tiers definition (CAB-209)
- [ ] GTM-10: Beta program structure (CAB-210)

---

## URLs

| Service | URL | Notes |
|---------|-----|-------|
| Control Plane UI | https://console.stoa.cab-i.com | React + Keycloak |
| Control Plane API (direct) | https://api.stoa.cab-i.com | FastAPI (direct access) |
| **API Gateway Runtime** | https://apis.stoa.cab-i.com | APIs via Gateway (OIDC auth) |
| Keycloak | https://auth.stoa.cab-i.com | Realm: stoa |
| AWX | https://awx.stoa.cab-i.com | admin/demo |
| API Gateway Admin | https://gateway.stoa.cab-i.com | Administrator/manage |
| ArgoCD | https://argocd.stoa.cab-i.com | GitOps CD |
| Vault | https://vault.stoa.cab-i.com | Secrets Management |

> **Architecture**: The UI calls the API via the Gateway (`apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0`) for centralized OIDC authentication.
