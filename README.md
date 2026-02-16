<p align="center">
  <strong>STOA Platform</strong><br>
  The European Agent Gateway
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/security-scan.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/security-scan.yml/badge.svg" alt="Security Scan"></a>
  <a href="https://github.com/stoa-platform/stoa/stargazers"><img src="https://img.shields.io/github/stars/stoa-platform/stoa?style=social" alt="GitHub Stars"></a>
  <a href="https://discord.gg/j8tHSSes"><img src="https://img.shields.io/badge/Discord-Join%20us-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://status.gostoa.dev"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/stoa-platform/status/master/api/stoa-api-gateway/uptime.json" alt="Uptime"></a>
</p>
<p align="center">
  <a href="https://docs.gostoa.dev"><img src="https://img.shields.io/badge/docs-docs.gostoa.dev-green.svg" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/Rust-Gateway-orange.svg" alt="Rust Gateway">
  <img src="https://img.shields.io/badge/MCP-Compatible-purple.svg" alt="MCP Compatible">
  <a href="https://github.com/stoa-platform/stoa/discussions"><img src="https://img.shields.io/github/discussions/stoa-platform/stoa?logo=github" alt="GitHub Discussions"></a>
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
┌──────────────────────────────────────────────────────────────┐
│                     STOA Platform                             │
│                                                               │
│  Console ──── API ──── Keycloak ──── Portal                   │
│  (React)    (Python)   (OIDC)      (React)                    │
│                │                                              │
│         ┌──────┴──────┐                                       │
│         │ Rust Gateway │ ◄── JWT + Rate Limit + MCP Bridge    │
│         └──────┬──────┘                                       │
│                │                                              │
│  Prometheus ── Grafana ── Loki ── OpenSearch                  │
│  (Metrics)    (Dashboards) (Logs) (Error Tracking)            │
└──────────────────────────────────────────────────────────────┘
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

See [deployment docs](https://docs.gostoa.dev/deployment/hybrid-deployment) for production setup with ArgoCD.

## Repository Structure

```
stoa/
├── control-plane-api/     # FastAPI backend
├── control-plane-ui/      # React admin console
├── portal/                # React developer portal
├── stoa-gateway/          # Rust API gateway
├── mcp-gateway/           # Python MCP gateway (legacy, migrating to Rust)
├── e2e/                   # Playwright E2E tests
├── charts/                # Helm charts
├── deploy/                # Docker Compose + configs
│   ├── docker-compose/    # Quick-start setup (17 services)
│   └── grafana/           # Analytics dashboards
└── scripts/               # Demo + seed scripts
```

## Related Repositories

| Repository | Purpose |
|------------|---------|
| [stoa-infra](https://github.com/stoa-platform/stoa-infra) | Terraform + Ansible + Helm |
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Documentation (docs.gostoa.dev) |
| [stoa-web](https://github.com/stoa-platform/stoa-web) | Landing page (gostoa.dev) |
| [stoa-quickstart](https://github.com/stoa-platform/stoa-quickstart) | Self-hosted quickstart |
| [stoactl](https://github.com/stoa-platform/stoactl) | CLI tool (Go) |

## Documentation

- **Docs**: [docs.gostoa.dev](https://docs.gostoa.dev)
- **Architecture Decisions**: [ADRs](https://docs.gostoa.dev/architecture/adr/)
- **API Reference**: [Control Plane API](https://docs.gostoa.dev/api/control-plane/)
- **Guides**: [Quick Start](https://docs.gostoa.dev/guides/quick-start/)

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- **Commits**: `type(scope): description` (commitlint enforced)
- **PRs**: Squash merge to main, < 300 LOC per PR
- **License**: Apache 2.0 with [DCO sign-off](CLA.md)

<a href="https://github.com/stoa-platform/stoa/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=stoa-platform/stoa" alt="Contributors" />
</a>

## Community

- [GitHub Discussions](https://github.com/stoa-platform/stoa/discussions) — questions, ideas, show & tell
- [Discord](https://discord.gg/j8tHSSes) — real-time chat
- [Documentation](https://docs.gostoa.dev) — guides, ADRs, API reference
- [Status Page](https://status.gostoa.dev) — platform uptime monitoring

## License

[Apache License 2.0](LICENSE)

---

<p align="center">
  <em>Built by <a href="https://cabingenierie.com">CAB Ingenierie</a> — Bordeaux, France</em>
</p>
