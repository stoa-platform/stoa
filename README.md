<p align="center">
  <img src="docs/assets/logo.svg" alt="STOA Logo" width="200"/>
</p>

<h1 align="center">STOA Platform</h1>

<p align="center">
  <strong>The Cilium of API Management — MCP Gateway for the AI Era</strong>
</p>

<p align="center">
  <a href="https://github.com/stoa-platform/stoa/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue?style=flat-square" alt="License"></a>
  <a href="https://discord.gg/j8tHSSes"><img src="https://img.shields.io/badge/discord-join-7289da?style=flat-square&logo=discord" alt="Discord"></a>
  <a href="https://docs.gostoa.dev"><img src="https://img.shields.io/badge/docs-gostoa.dev-green?style=flat-square" alt="Documentation"></a>
</p>

---

## What is STOA?

STOA is an **AI-native API Management Platform** that bridges traditional APIs and the new world of AI agents via the Model Context Protocol (MCP).

**Define once, expose everywhere** — STOA's Universal API Contract (UAC) lets you define an API once and automatically expose it as REST, MCP Tools, GraphQL, gRPC, or Kafka events.

### Why STOA?

| Challenge | STOA Solution |
|-----------|---------------|
| AI agents need structured tool access | MCP Gateway with 23+ tools |
| APIs scattered across protocols | Universal API Contract (UAC) |
| Multi-tenant API governance | Built-in RBAC with 6 personas |
| Enterprise security requirements | OAuth2, mTLS, Vault integration |
| Observability at scale | Prometheus + Grafana + Loki stack |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CONTROL PLANE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│   │  Portal  │  │ Console  │  │   MCP    │      UI Layer                │
│   │  (React) │  │  (React) │  │  Server  │      (Optional)              │
│   └────┬─────┘  └────┬─────┘  └────┬─────┘                              │
│        │             │             │                                     │
│        └─────────────┼─────────────┘                                     │
│                      │                                                   │
│               ┌──────▼──────┐                                            │
│               │  STOA Core  │      Hub Central                          │
│               │   (FastAPI) │      Python 3.11+                         │
│               └──────┬──────┘                                            │
│                      │                                                   │
│       ┌──────────────┼──────────────┐                                    │
│       │              │              │                                    │
│   PostgreSQL     Keycloak       Vault                                    │
│   (Runtime)       (IAM)       (Secrets)                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                       │
                       │ GitOps Sync (ArgoCD)
                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA PLANE                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    API Gateway                                   │   │
│   │         (webMethods → Rust/eBPF in 2026)                        │   │
│   │                                                                  │   │
│   │   Routing │ Rate Limit │ Auth │ Transform │ Observability       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Current Stack

| Component | Technology | Status |
|-----------|------------|--------|
| **Control Plane API** | FastAPI (Python 3.11+) | ✅ Production |
| **Developer Portal** | React + TypeScript | ✅ Production |
| **Admin Console** | React + TypeScript | ✅ Production |
| **MCP Server** | Python (23 tools) | ✅ Production |
| **Data Plane** | webMethods Gateway | ✅ Production |
| **Authentication** | Keycloak (OIDC) | ✅ Production |
| **Secrets** | HashiCorp Vault | ✅ Production |
| **Database** | PostgreSQL 15 | ✅ Production |
| **Search** | OpenSearch | ✅ Production |
| **Messaging** | Kafka/Redpanda | ✅ Production |
| **Observability** | Prometheus + Grafana + Loki | ✅ Production |
| **GitOps** | ArgoCD | ✅ Production |

### Roadmap

| Component | Technology | Timeline |
|-----------|------------|----------|
| **Native Gateway** | Rust + eBPF | Q4 2026 |
| **AI Gateway** | Semantic caching, smart routing | Q4 2026 |

---

## Features

### MCP Gateway

- **23 MCP Tools** exposed to AI agents (Claude, GPT, etc.)
- **Multi-tenant** tool isolation with RBAC
- **6 OAuth2 personas**: Admin, Product Owner, Developer, Consumer, Security Officer, AI Agent
- **Error Snapshots** — Flight recorder for debugging failed requests

### API Management

- **Universal API Contract (UAC)** — Define once, expose REST/MCP/GraphQL/gRPC
- **Subscription management** with API keys and quotas
- **Rate limiting** per tenant/consumer
- **Audit logging** for NIS2/DORA compliance

### Enterprise Security

- **OAuth2 + mTLS** support
- **Vault integration** for secrets management
- **RBAC with 12 OAuth2 scopes**
- **Supply chain security** (SBOM, Cosign signatures)

---

## Quick Start

> ⚠️ **Coming Soon** — The open-source release is planned for Q1 2026.
> 
> Join our [Discord](https://discord.gg/j8tHSSes) to get early access or become a design partner.

### Docker Compose (Preview)

```bash
# Clone the repository
git clone https://github.com/stoa-platform/stoa.git
cd stoa

# Start with Docker Compose
docker compose up -d

# Access the Portal
open http://localhost:3000
```

### Helm (Kubernetes)

```bash
helm repo add stoa https://charts.gostoa.dev
helm install stoa stoa/stoa-platform -n stoa --create-namespace
```

---

## Repository Structure

This is the **meta-repository** for STOA Platform documentation and GitOps templates.

| Repository | Description |
|------------|-------------|
| [stoa](https://github.com/stoa-platform/stoa) | Documentation, architecture, GitOps templates |
| [stoa-docs](https://github.com/stoa-platform/stoa-docs) | Docusaurus documentation site |
| [stoa-helm](https://github.com/stoa-platform/stoa-helm) | Helm charts for Kubernetes deployment |
| [stoa-web](https://github.com/stoa-platform/stoa-web) | Landing page (gostoa.dev) |

**Coming Q1 2026:**

| Repository | Description |
|------------|-------------|
| stoa-core | Control Plane API (FastAPI) |
| stoa-portal | Developer Portal (React) |
| stoa-console | Admin Console (React) |
| stoa-mcp | MCP Server (Python) |

---

## Documentation

Full documentation is available at [docs.gostoa.dev](https://docs.gostoa.dev)

- [Architecture Overview](https://docs.gostoa.dev/docs/concepts/architecture)
- [MCP Gateway Concepts](https://docs.gostoa.dev/docs/concepts/mcp-gateway)
- [Multi-Tenant Design](https://docs.gostoa.dev/docs/concepts/multi-tenant)
- [Authentication Guide](https://docs.gostoa.dev/docs/guides/authentication)
- [API Reference](https://docs.gostoa.dev/docs/api/control-plane)

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Good First Issues

Looking for a place to start? Check out issues labeled [`good first issue`](https://github.com/stoa-platform/stoa/labels/good%20first%20issue).

---

## Community

- 💬 [Discord](https://discord.gg/j8tHSSes) — Join our community
- 📖 [Documentation](https://docs.gostoa.dev) — Learn how to use STOA
- 🐛 [Issues](https://github.com/stoa-platform/stoa/issues) — Report bugs or request features
- 📧 [Contact](mailto:hello@gostoa.dev) — Reach out for partnerships

---

## License

STOA Platform is licensed under the [Apache License 2.0](LICENSE).

---

<p align="center">
  <strong>Built with ❤️ by <a href="https://hlfh.dev">HLFH</a></strong>
</p>
