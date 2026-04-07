<p align="center">
  <strong>STOA Platform</strong><br>
  The European Agent Gateway<br>
  <em>Bridge enterprise APIs to AI agents. Define once, expose everywhere.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-api-ci.yml"><img src="https://github.com/stoa-platform/stoa/actions/workflows/control-plane-api-ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/stoa-platform/stoa/stargazers"><img src="https://img.shields.io/github/stars/stoa-platform/stoa?style=social" alt="GitHub Stars"></a>
  <a href="https://discord.gg/j8tHSSes"><img src="https://img.shields.io/badge/Discord-Join%20us-5865F2?logo=discord&logoColor=white" alt="Discord"></a>
</p>
<p align="center">
  <a href="https://gostoa.dev">Website</a> · <a href="https://docs.gostoa.dev">Docs</a> · <a href="https://discord.gg/j8tHSSes">Community</a> · <a href="https://status.gostoa.dev">Status</a>
</p>

---

**STOA** is an open-source MCP gateway that deploys as a **sidecar** next to your existing API gateway. Your REST traffic keeps flowing through Kong, Gravitee, or Apigee — STOA adds an MCP layer so AI agents can discover and call the same APIs, with authentication, rate limiting, and audit built in.

> **Keep your gateway. Add AI.** Define your API once, expose it as REST + MCP.

<p align="center">
  <img src="docs/assets/screenshot-call-flow.png" alt="STOA Console — Call Flow Dashboard with live traces and traffic heatmap" width="800">
</p>

<details>
<summary>More screenshots</summary>

<p align="center">
  <img src="docs/assets/screenshot-gateway.png" alt="STOA Console — Gateway Overview, 3 gateways online" width="800">
</p>

</details>

## Why STOA?

| Problem | STOA Solution |
|---------|--------------|
| AI agents can't use enterprise APIs | MCP sidecar: expose existing APIs as AI tools without changing your gateway |
| 5 days to get API access | Self-service portal, instant credentials |
| API catalog in Excel | Searchable catalog with OpenAPI specs |
| "Rip and replace" to adopt AI | Sidecar deploys next to Kong, Gravitee, Apigee, Azure, AWS, webMethods |
| Multi-org identity is a nightmare | Keycloak federation across organizations |
| No governance for AI API calls | OAuth 2.1, per-consumer rate limits, audit trail for every MCP call |

## Architecture

STOA doesn't replace your existing gateway — it sits alongside it as a **sidecar**, adding MCP/AI capabilities to your current infrastructure.

```
                        STOA Control Plane
┌──────────────────────────────────────────────────────────────────┐
│  Console ──── Control Plane API ──── Keycloak ──── Portal        │
│  (React 19)    (Python/FastAPI)      (OIDC)      (React 19)     │
└──────────────────────────┬───────────────────────────────────────┘
                           │ sync
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
┌─────────────────────┐   ┌─────────────────────────────────────┐
│    STOA Gateway      │   │     Your Existing Gateway            │
│   (Rust · sidecar)   │   │  Kong · Gravitee · Apigee · Azure   │
│                      │   │  AWS API GW · webMethods             │
│  MCP Bridge          │   │                                     │
│  AI Tool Discovery   │   │  ◄── Adapter sync (APIs, policies,  │
│  OAuth 2.1 + PKCE    │   │      consumers, subscriptions)      │
│  mTLS · Rate Limits  │   │                                     │
└──────────┬───────────┘   └──────────────┬──────────────────────┘
           │                              │
           ▼                              ▼
     AI Agents (MCP)              Existing Clients (REST)
```

**Key idea:** your REST traffic keeps flowing through your current gateway. STOA adds an MCP sidecar so AI agents can discover and call the same APIs — with authentication, rate limiting, and audit built in.

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

### MCP Sidecar Gateway (Rust, 93K LOC, 2,300+ tests)
- **Sidecar deployment** — deploys next to your existing gateway, no rip-and-replace
- **Universal API Contract** — define an API once, expose it as REST + MCP tool
- **Tool discovery** — AI agents discover available tools via MCP protocol
- **MCP OAuth 2.1** — RFC 9728 discovery, PKCE, dynamic client registration
- **Per-consumer rate limiting** — plan-based quotas with 429 responses
- **mTLS support** — RFC 8705 certificate-bound tokens
- **Sub-millisecond proxy** — built with Tokio + axum for maximum throughput
- **5 CRDs** — Tools, ToolSets, Skills, Gateways, GatewayBindings (Kubernetes-native)

### Multi-Gateway Adapters
- **7 adapters** — Kong, Gravitee, Apigee, Azure APIM, AWS API Gateway, webMethods, STOA native
- **Bidirectional sync** — APIs, policies, consumers, and subscriptions stay in sync
- **Single control plane** — manage all your gateways from one console

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
| Rust Gateway | Rust (stable), Tokio, axum 0.7 | API proxy + MCP bridge (93K LOC) |
| stoactl | Go 1.25, Cobra | GitOps CLI + VPS connect agent |
| Keycloak | Keycloak 26.5 | Authentication + federation |
| K8s Operator | Python, Kopf | CRD controller for MCP resources |
| Helm Chart | Helm 3 (5 CRDs, 33 templates) | Kubernetes deployment |

## Test Suite

| Component | Framework | Tests | Coverage |
|-----------|-----------|-------|----------|
| Control Plane API | pytest + pytest-asyncio | 7,100+ | 70% min |
| Rust Gateway | cargo test | 2,300+ | Unit + contract + integration + security |
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
├── charts/                # Helm chart (5 CRDs, 33 templates)
├── deploy/docker-compose/ # Quick-start setup
├── e2e/                   # Playwright BDD tests
├── scripts/               # Demo, seed, benchmarks
└── docs/                  # Runbooks + methodology
```

## Related Repositories

| Repository | Purpose |
|------------|---------|
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Documentation site ([docs.gostoa.dev](https://docs.gostoa.dev)) — 57+ ADRs, guides, API ref |
| [stoa-web](https://github.com/stoa-platform/stoa-web) | Landing page ([gostoa.dev](https://gostoa.dev)) |
| [stoa-quickstart](https://github.com/stoa-platform/stoa-quickstart) | Self-hosted quickstart (Docker Compose) |
| [stoactl](https://github.com/stoa-platform/stoactl) | CLI tool (Go) — kubectl-style API management |

## Benchmark

STOA includes **Gateway Arena**, an open benchmark suite comparing API gateways on proxy throughput and AI-native capabilities (MCP, guardrails, governance). See [methodology](docs/BENCHMARK-METHODOLOGY.md) and [latest results](docs/BENCHMARK-RESULTS.md).

## Documentation

- **Docs**: [docs.gostoa.dev](https://docs.gostoa.dev) — 100+ pages
- **Architecture Decisions**: [57+ ADRs](https://docs.gostoa.dev/docs/architecture/adr/)
- **API Reference**: [Control Plane API](https://docs.gostoa.dev/docs/api/control-plane)
- **Guides**: [Quick Start](https://docs.gostoa.dev/docs/guides/quickstart) · [Migration guides](https://docs.gostoa.dev/docs/guides/migration/) (Kong, Apigee, webMethods)

## Security

STOA runs SAST, dependency scanning, container scanning, and SBOM generation on every PR. 4 checks are required for merge: License Compliance, SBOM Generation, Signed Commits, and Regression Test Guard. See [`SECURITY.md`](SECURITY.md) for details.

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
  <em>Built by <a href="https://cabingenierie.com">CAB Ingenierie</a> — Paris, France</em>
</p>
