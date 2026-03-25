<p align="center">
  <strong>STOA Platform</strong><br>
  The European Agent Gateway<br>
  <a href="https://gostoa.dev">Website</a> · <a href="https://docs.gostoa.dev">Docs</a> · <a href="https://discord.gg/j8tHSSes">Discord</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/security-scan.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/security-scan.yml/badge.svg" alt="Security Scan"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-api-ci.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-api-ci.yml/badge.svg" alt="API CI"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/stoa-gateway-ci.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/stoa-gateway-ci.yml/badge.svg" alt="Gateway CI"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-ui-ci.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-ui-ci.yml/badge.svg" alt="Console CI"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/stoa-portal-ci.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/stoa-portal-ci.yml/badge.svg" alt="Portal CI"></a>
</p>
<p align="center">
  <a href="https://github.com/stoa-platform/stoa/stargazers"><img src="https://img.shields.io/github/stars/stoa-platform/stoa?style=social" alt="GitHub Stars"></a>
  <a href="https://discord.gg/j8tHSSes"><img src="https://img.shields.io/badge/Discord-Join%20us-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://status.gostoa.dev"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/stoa-platform/status/master/api/stoa-api-gateway/uptime.json" alt="Uptime"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/scorecard.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/scorecard.yml/badge.svg" alt="OpenSSF Scorecard"></a>
</p>
<p align="center">
  <a href="https://docs.gostoa.dev"><img src="https://img.shields.io/badge/docs-docs.gostoa.dev-green.svg" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/Rust-Gateway_(90K_LOC)-orange.svg" alt="Rust Gateway">
  <img src="https://img.shields.io/badge/MCP-Compatible-purple.svg" alt="MCP Compatible">
  <a href="https://github.com/stoa-platform/stoa/discussions"><img src="https://img.shields.io/github/discussions/stoa-platform/stoa?logo=github" alt="GitHub Discussions"></a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/SAST-Gitleaks%20%7C%20Bandit%20%7C%20Clippy-brightgreen?logo=shieldsdotio" alt="SAST: Gitleaks, Bandit, Clippy">
  <img src="https://img.shields.io/badge/Container-Trivy-blue?logo=aquasecurity" alt="Container Scan: Trivy">
  <img src="https://img.shields.io/badge/SBOM-CycloneDX%20%7C%20SPDX-blue?logo=dependabot" alt="SBOM: CycloneDX + SPDX">
  <img src="https://img.shields.io/badge/License_Scan-Trivy-blue?logo=opensourceinitiative" alt="License Scan: Trivy">
</p>

---

**STOA** is an open-source API management platform that bridges enterprise APIs to AI agents. Define your API once, expose it everywhere — REST, GraphQL, MCP.

> **Universal API Contract (UAC):** Define Once, Expose Everywhere.

## Why STOA?

| Problem | STOA Solution |
|---------|--------------|
| 5 days to get API access | Self-service portal, instant credentials |
| API catalog in Excel | Searchable catalog with OpenAPI specs |
| Gateway = black box at $500K/year | Open-source, full observability, Rust performance |
| AI agents can't use enterprise APIs | MCP bridge: legacy API → AI agent tool |
| Multi-org identity is a nightmare | Keycloak federation across organizations |
| Locked into one gateway vendor | Multi-gateway adapters: Kong, Gravitee, Apigee, Azure APIM, AWS, webMethods |

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         STOA Platform                            │
│                                                                  │
│  Console ──── Control Plane API ──── Keycloak ──── Portal        │
│  (React 19)    (Python/FastAPI)      (OIDC)      (React 19)     │
│                       │                                          │
│             ┌─────────┴─────────┐                                │
│             │   Rust Gateway    │ ◄── MCP + JWT + mTLS + Quotas  │
│             │  (Tokio + axum)   │                                │
│             └─────────┬─────────┘                                │
│                       │                                          │
│   ┌───────────────────┼───────────────────┐                      │
│   │                   │                   │                      │
│   ▼                   ▼                   ▼                      │
│  Kong            Gravitee            webMethods    ◄── Adapters  │
│  Apigee          Azure APIM         AWS API GW                   │
│                                                                  │
│  Prometheus ── Grafana ── Loki ── OpenSearch                     │
│  (Metrics)   (Dashboards) (Logs) (Error Tracking)                │
└──────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/stoa-platform/stoa.git
cd stoa/deploy/docker-compose

# Start (21 services, ~3GB RAM)
cp .env.example .env
docker compose up -d

# Wait for healthy
../../scripts/demo/check-health.sh --wait

# Seed demo data
../../scripts/demo/seed-all.sh --skip-traffic
```

Open http://localhost — login as `halliday` / `readyplayerone`.

For component-by-component local development (without Docker), see [DEVELOPMENT.md](DEVELOPMENT.md).

| Service | URL |
|---------|-----|
| Console | http://localhost |
| Portal | http://localhost/portal |
| API Docs | http://localhost/api/docs |
| Grafana | http://localhost/grafana |
| Keycloak | http://localhost/auth |
| Gateway | http://localhost/gateway/health |

## Features

### API Management
- **Self-Service Portal** — developers discover, subscribe, and test APIs without tickets
- **Admin Console** — manage tenants, APIs, consumers, and subscriptions
- **Multi-Tenant** — full isolation between organizations with RBAC
- **Multi-Gateway** — 7 adapter integrations (Kong, Gravitee, Apigee, Azure APIM, AWS, webMethods, STOA native)

### Rust Gateway (90K LOC, 1,800+ tests)
- **Sub-millisecond proxy** — built with Tokio + axum for maximum throughput
- **JWT validation** — Keycloak OIDC integration with JWKS caching
- **Per-consumer rate limiting** — plan-based quotas with 429 responses
- **mTLS support** — RFC 8705 certificate-bound tokens
- **MCP OAuth 2.1** — RFC 9728 discovery, PKCE, dynamic client registration
- **4-mode architecture** — edge-mcp (active), sidecar, proxy, shadow

### MCP Bridge (AI-Native)
- **Universal API Contract** — define an API once, expose it as REST + MCP tool
- **Tool discovery** — AI agents discover available tools via MCP protocol
- **SSE transport** — real-time streaming for agent communication
- **Governance** — authentication, rate limiting, and audit trail for AI calls
- **5 CRDs** — Tools, ToolSets, Skills, Gateways, GatewayBindings (Kubernetes-native)

### Observability
- **Grafana dashboards** — gateway metrics, tenant analytics, error tracking, arena benchmarks
- **OpenSearch integration** — error snapshots with trace ID correlation
- **Loki log aggregation** — centralized logs from all components
- **Prometheus metrics** — p50/p90/p99 latency, request rates, error rates

### Identity Federation
- **Multi-org Keycloak 26** — federate Active Directory, LDAP, SAML, OIDC
- **Cross-realm token isolation** — zero-trust between organizations
- **Self-registration** — developers onboard without admin intervention
- **FAPI 2.0 architecture** — financial-grade API security (ADR-056)

## Components

| Component | Tech | Purpose |
|-----------|------|---------|
| Control Plane API | Python 3.11, FastAPI, SQLAlchemy 2.0 | Backend API with RBAC, multi-gateway adapters |
| Console UI | React 19, TypeScript, Vite, TanStack Query | Admin interface |
| Developer Portal | React 19, TypeScript, Vite, TanStack Query | Developer self-service |
| Rust Gateway | Rust (stable), Tokio, axum 0.7 | API proxy + MCP bridge (90K LOC) |
| stoactl | Go 1.25, Cobra | GitOps CLI + VPS connect agent |
| Keycloak | Keycloak 26.5 | Authentication + federation |
| K8s Operator | Python, Kopf | CRD controller for MCP resources |
| Helm Chart | Helm 3 (5 CRDs, 33 templates) | Kubernetes deployment |

## Test Suite

| Component | Framework | Tests | Coverage |
|-----------|-----------|-------|----------|
| Control Plane API | pytest + pytest-asyncio | 7,100+ | 70% min |
| Rust Gateway | cargo test | 1,800+ | Unit + contract + integration + security |
| Console UI | vitest + React Testing Library | Per-component | Persona-based (4 RBAC roles) |
| Portal | vitest + React Testing Library | Per-component | Persona-based (4 RBAC roles) |
| E2E | Playwright + BDD (Gherkin) | 77 feature files | @smoke, @critical, @portal, @console, @gateway |

## Deployment

### Docker Compose (Development)

See [deploy/docker-compose/README.md](deploy/docker-compose/README.md) for the full quick-start guide.

### Kubernetes (Production)

```bash
helm install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace \
  -f charts/stoa-platform/values.yaml
```

Production runs on ArgoCD with GitOps. See [deployment docs](https://docs.gostoa.dev/docs/deployment/hybrid).

## Repository Structure

```
stoa/
├── control-plane-api/     # FastAPI backend (Python 3.11)
├── control-plane-ui/      # React 19 admin console
├── portal/                # React 19 developer portal
├── stoa-gateway/          # Rust API gateway + MCP bridge
├── stoa-go/               # Go CLI (stoactl) + connect agent
├── stoa-operator/         # Kubernetes operator (Python/Kopf)
├── stoa-ebpf/             # eBPF XDP/TC programs (Rust)
├── services/              # Microservices
│   ├── kafka-bridge/      #   Kafka event bridge
│   └── opensearch-sync/   #   OpenSearch synchronization
├── e2e/                   # Playwright BDD tests (77 features)
├── charts/                # Helm chart (5 CRDs, 33 templates)
├── k8s/                   # Standalone K8s manifests + arena
├── deploy/                # Docker Compose + VPS deploys
│   ├── docker-compose/    #   Quick-start setup (21 services)
│   └── vps/               #   VPS gateway deployments
├── scripts/               # Demo, seed, arena benchmarks
├── docs/                  # Runbooks + benchmark methodology
├── keycloak/              # Keycloak theme + realm configs
├── .github/workflows/     # 59 CI/CD workflows
└── .claude/               # AI Factory config (agents, rules, skills)
```

## Related Repositories

| Repository | Purpose |
|------------|---------|
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Documentation site ([docs.gostoa.dev](https://docs.gostoa.dev)) — 57+ ADRs, guides, API ref |
| [stoa-web](https://github.com/stoa-platform/stoa-web) | Landing page ([gostoa.dev](https://gostoa.dev)) |
| [stoa-quickstart](https://github.com/stoa-platform/stoa-quickstart) | Self-hosted quickstart (Docker Compose) |
| [stoactl](https://github.com/stoa-platform/stoactl) | CLI tool (Go) — kubectl-style API management |

## Benchmark

STOA includes an open benchmark suite (**Gateway Arena**) that continuously measures gateway performance across proxy throughput and AI-native capabilities (MCP, guardrails, governance).

- **L0 — Proxy Baseline**: 7 k6 scenarios, median of 5 runs, CI95 confidence intervals
- **L1 — Enterprise AI Readiness**: 20 dimensions across MCP, governance, security, LLM intelligence
- **L2 — Platform CUJs**: 3 critical user journeys every 15 min (health, auth, MCP flow)
- **Methodology**: [docs/BENCHMARK-METHODOLOGY.md](docs/BENCHMARK-METHODOLOGY.md) — scoring formula, scenarios, statistical method
- **Latest Results**: [docs/BENCHMARK-RESULTS.md](docs/BENCHMARK-RESULTS.md) — scores for STOA, Kong, Gravitee, agentgateway

Quick local run (requires [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) + Docker):

```bash
./scripts/traffic/arena/run-local.sh http://localhost:8080
```

## Documentation

- **Docs**: [docs.gostoa.dev](https://docs.gostoa.dev) — 100+ pages
- **Architecture Decisions**: [57+ ADRs](https://docs.gostoa.dev/docs/architecture/adr/)
- **API Reference**: [Control Plane API](https://docs.gostoa.dev/docs/api/control-plane)
- **Guides**: [Quick Start](https://docs.gostoa.dev/docs/guides/quickstart) · [Migration guides](https://docs.gostoa.dev/docs/guides/migration/) (Kong, Apigee, webMethods)

## Security

STOA runs a multi-job security pipeline on every PR and daily on `main`:

| Tool | Scope | What It Catches |
|------|-------|-----------------|
| **Gitleaks** | Entire repo | Hardcoded secrets, API keys, tokens |
| **Bandit** | Python (API, Gateway) | SQL injection, eval(), insecure crypto |
| **ESLint Security** | TypeScript (Console, Portal) | XSS, unsafe regex, eval |
| **Clippy SAST** | Rust (Gateway) | `todo!()`, `dbg!()`, `unwrap()`, `panic()` |
| **CodeQL** | Multi-language | Static analysis (LGTM) |
| **Trivy** | Container images | CVEs (CRITICAL + HIGH) |
| **Cargo Audit** | Rust dependencies | Known vulnerability advisories |
| **pip-audit / npm audit** | Python + Node deps | Dependency vulnerabilities |
| **CycloneDX + SPDX** | All components | SBOM generation |
| **Trivy License** | All components | License compliance (Apache 2.0 compatibility) |

4 checks are **required** on every PR (branch protection): License Compliance, SBOM Generation, Verify Signed Commits, Regression Test Guard.

See [`security-scan.yml`](.github/workflows/security-scan.yml) for the full pipeline.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- **Commits**: `type(scope): description` (commitlint enforced)
- **PRs**: Squash merge to main, < 300 LOC per PR
- **License**: Apache 2.0 with [DCO sign-off](CLA.md)

<a href="https://github.com/stoa-platform/stoa/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=stoa-platform/stoa" alt="Contributors" />
</a>

## Community & Support

- [GitHub Discussions](https://github.com/stoa-platform/stoa/discussions) — questions, ideas, show & tell
- [Discord](https://discord.gg/j8tHSSes) — real-time chat
- [Documentation](https://docs.gostoa.dev) — guides, ADRs, API reference
- [Status Page](https://status.gostoa.dev) — platform uptime monitoring
- [Support](SUPPORT.md) — how to get help and report issues

## License

[Apache License 2.0](LICENSE)

---

<p align="center">
  <em>Built by <a href="https://cabingenierie.com">CAB Ingenierie</a> — Bordeaux, France</em>
</p>
