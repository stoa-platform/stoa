<p align="center">
  <strong>STOA Platform</strong><br>
  The European Agent Gateway
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
  <img src="https://img.shields.io/badge/Rust-Gateway-orange.svg" alt="Rust Gateway">
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

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       STOA Platform                         │
│                                                             │
│  Console ──── API ──── Keycloak ──── Portal                 │
│  (React)    (Python)    (OIDC)      (React)                 │
│                │                                            │
│         ┌──────┴──────┐                                     │
│         │ Rust Gateway │ ◄── JWT + Rate Limit + MCP Bridge  │
│         └──────┬──────┘                                     │
│                │                                            │
│  Prometheus ── Grafana ── Loki ── OpenSearch                │
│  (Metrics)   (Dashboards) (Logs) (Error Tracking)           │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/stoa-platform/stoa.git
cd stoa/deploy/docker-compose

# Start (17 services, ~3GB RAM)
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

### Rust Gateway
- **Sub-millisecond proxy** — built with Tokio + axum for maximum throughput
- **JWT validation** — Keycloak OIDC integration with JWKS caching
- **Per-consumer rate limiting** — plan-based quotas with 429 responses
- **mTLS support** — RFC 8705 certificate-bound tokens

### MCP Bridge (AI-Native)
- **Universal API Contract** — define an API once, expose it as REST + MCP tool
- **Tool discovery** — AI agents discover available tools via MCP protocol
- **SSE transport** — real-time streaming for agent communication
- **Governance** — authentication, rate limiting, and audit trail for AI calls

### Observability
- **12 Grafana dashboards** — gateway metrics, tenant analytics, error tracking
- **OpenSearch integration** — error snapshots with trace ID correlation
- **Loki log aggregation** — centralized logs from all components
- **Prometheus metrics** — p50/p90/p99 latency, request rates, error rates

### Identity Federation
- **Multi-org Keycloak** — federate Active Directory, LDAP, SAML, OIDC
- **Cross-realm token isolation** — zero-trust between organizations
- **Self-registration** — developers onboard without admin intervention

## Components

| Component | Tech | Purpose |
|-----------|------|---------|
| Control Plane API | Python 3.11, FastAPI | Backend API with RBAC |
| Console UI | React 18, TypeScript | Admin interface |
| Developer Portal | React, Vite, TypeScript | Developer self-service |
| Rust Gateway | Rust, Tokio, axum | API proxy + MCP bridge |
| Keycloak | Keycloak 23.0 | Authentication + federation |
| Helm Chart | Helm 3 | Kubernetes deployment |

## Deployment

### Docker Compose (Development)

See [deploy/docker-compose/README.md](deploy/docker-compose/README.md) for the full quick-start guide.

### Kubernetes (Production)

```bash
helm install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace \
  -f charts/stoa-platform/values.yaml
```

See [deployment docs](https://docs.gostoa.dev/docs/deployment/hybrid) for production setup with ArgoCD.

## Repository Structure

```
stoa/
├── control-plane-api/     # FastAPI backend
├── control-plane-ui/      # React admin console
├── portal/                # React developer portal
├── stoa-gateway/          # Rust API gateway + MCP bridge
├── cli/                   # Python CLI (Typer + Rich)
├── e2e/                   # Playwright E2E tests (BDD)
├── charts/                # Helm charts
├── deploy/                # Docker Compose + configs
│   ├── docker-compose/    # Quick-start setup (17 services)
│   └── grafana/           # Analytics dashboards
├── scripts/               # Demo, seed, migration scripts
└── docs/                  # Runbooks + benchmark methodology
```

## Related Repositories

| Repository | Purpose |
|------------|---------|
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Documentation ([docs.gostoa.dev](https://docs.gostoa.dev)) |
| [stoa-web](https://github.com/stoa-platform/stoa-web) | Landing page ([gostoa.dev](https://gostoa.dev)) |
| [stoa-quickstart](https://github.com/stoa-platform/stoa-quickstart) | Self-hosted quickstart |
| [stoactl](https://github.com/stoa-platform/stoactl) | CLI tool (Go) |

## Benchmark

STOA includes an open benchmark suite (**Gateway Arena**) that continuously measures gateway performance across proxy throughput and AI-native capabilities (MCP, guardrails, governance).

- **Methodology**: [docs/BENCHMARK-METHODOLOGY.md](docs/BENCHMARK-METHODOLOGY.md) — scoring formula, scenarios, statistical method
- **Latest Results**: [docs/BENCHMARK-RESULTS.md](docs/BENCHMARK-RESULTS.md) — scores for STOA, Kong, and Gravitee

Quick local run (requires [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) + Docker):

```bash
./scripts/traffic/arena/run-local.sh http://localhost:8080
```

## Documentation

- **Docs**: [docs.gostoa.dev](https://docs.gostoa.dev)
- **Architecture Decisions**: [ADRs](https://docs.gostoa.dev/docs/architecture/adr/)
- **API Reference**: [Control Plane API](https://docs.gostoa.dev/docs/api/control-plane)
- **Guides**: [Quick Start](https://docs.gostoa.dev/docs/guides/quickstart)

## Security

STOA runs a 9-job security pipeline on every PR and daily on `main`:

| Tool | Scope | What It Catches |
|------|-------|-----------------|
| **Gitleaks** | Entire repo | Hardcoded secrets, API keys, tokens |
| **Bandit** | Python (API, MCP GW) | SQL injection, eval(), insecure crypto |
| **ESLint Security** | TypeScript (Console, Portal) | XSS, unsafe regex, eval |
| **Clippy SAST** | Rust (Gateway) | `todo!()`, `dbg!()`, `unwrap()`, `panic()` |
| **Trivy** | Container images | CVEs (CRITICAL + HIGH) |
| **Cargo Audit** | Rust dependencies | Known vulnerability advisories |
| **pip-audit / npm audit** | Python + Node deps | Dependency vulnerabilities |
| **CycloneDX + SPDX** | All components | SBOM generation |
| **Trivy License** | All components | License compliance (Apache 2.0 compatibility) |

3 checks are **required** on every PR (branch protection): License Compliance, SBOM Generation, Verify Signed Commits.

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
