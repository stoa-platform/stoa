---
sidebar_position: 5
title: FAQ
description: Frequently asked questions about STOA Platform.
---

# FAQ

## General

### What is STOA?

STOA is a multi-tenant API management platform that combines traditional API governance (publish, subscribe, version, govern) with AI-native access via the MCP Gateway. It enables organizations to manage APIs for both human developers and AI agents through a unified control plane.

### What does "STOA" mean?

STOA (Greek: Στοά) refers to the ancient Greek covered walkway or portico — a place where people gathered to exchange ideas. Similarly, the STOA platform is where APIs, services, and agents come together.

### Is STOA open source?

STOA is source-available. The core platform components are available on GitHub under a permissive license. Enterprise features (advanced RBAC, SLA enforcement, priority support) are available under a commercial license.

### What API gateways does STOA support?

STOA uses a Gateway Adapter pattern that supports multiple gateways:

| Gateway | Status |
|---------|--------|
| webMethods | Production |
| Kong | Planned (Q3 2026) |
| Apigee | Planned (Q4 2026) |
| AWS API Gateway | Planned (Q4 2026) |

The adapter interface is extensible — you can implement your own adapter for any gateway.

### How is STOA different from Apigee / Kong / AWS API Gateway?

STOA is not a replacement for your API gateway — it sits **above** it as a management layer. While gateways handle runtime traffic (routing, rate limiting, TLS), STOA provides:

- Multi-tenant API lifecycle management
- GitOps-driven configuration
- AI-native access via MCP
- Gateway-agnostic control plane

You keep your existing gateway; STOA orchestrates it.

## Architecture

### Why GitOps?

Git as the source of truth provides:

- **Audit trail**: Every change is a commit with author and timestamp
- **Rollback**: `git revert` to undo any configuration change
- **Review**: Pull requests for API and policy changes
- **Automation**: ArgoCD ensures desired state matches actual state

### Why Kafka / Redpanda?

Event streaming decouples components and enables:

- Async workflow processing (subscription approvals, gateway sync)
- Metering and usage tracking for billing
- Audit log aggregation
- Real-time notifications

We recommend Redpanda for simpler operations (no ZooKeeper) and Kafka-API compatibility.

### Can I run STOA without Kubernetes?

Docker Compose is supported for development and small deployments. For production, Kubernetes is recommended for:

- Tenant namespace isolation
- CRD-based tool registration
- Horizontal pod autoscaling
- Network policies

### What's the MCP Gateway's relationship to the Rust gateway?

The current MCP Gateway is written in Python (FastAPI) and handles **edge-mcp** mode — AI agent access via the MCP protocol. A Rust rewrite (`stoa-gateway/`) is planned for Q4 2026, which will implement all four gateway modes (edge-mcp, sidecar, proxy, shadow) with better performance characteristics.

## Operations

### How do I backup the platform?

Key backup targets:

1. **PostgreSQL**: Standard pg_dump or RDS automated backups
2. **GitLab**: Git repositories are inherently backed up; back up GitLab config separately
3. **Keycloak**: Export realm configuration via Keycloak admin
4. **Vault**: Use `vault operator raft snapshot save`

### How do I upgrade STOA?

```bash
# Pull latest chart
helm repo update

# Preview changes
helm diff upgrade stoa-platform ./charts/stoa-platform -f values.yaml

# Apply
helm upgrade stoa-platform ./charts/stoa-platform -f values.yaml
```

Database migrations run automatically on API startup via Alembic.

### What's the recommended monitoring setup?

STOA ships with Prometheus + Grafana + Loki. See the [Observability](../guides/observability) guide. At minimum, monitor:

- API health endpoints (`/health/ready`)
- Error rate (alert if > 5% for 5 minutes)
- Kafka consumer lag (alert if > 10,000)
- Certificate expiration (alert 30 days before)

### How many tenants can STOA support?

STOA has been tested with dozens of tenants. Each tenant maps to a Kubernetes namespace, so the practical limit depends on your cluster capacity and Kubernetes namespace limits (typically thousands).

## Security

### How is tenant data isolated?

Three layers of isolation:

1. **Database**: Tenant ID column on all data, ORM-level query filtering
2. **Kubernetes**: Separate namespaces with RBAC and network policies
3. **Application**: JWT scope validation on every API request

### Does STOA store API keys or secrets?

API consumer credentials are stored in Vault (if configured) or the target API gateway. STOA stores references, not the secrets themselves.

### What security scanning does STOA run?

9 automated checks on every push/PR:

- Commit signature verification
- SAST (Bandit for Python, ESLint Security for JS)
- Dependency scanning (pip-audit, npm audit)
- Secret scanning (Gitleaks)
- License compliance (Trivy)
- SBOM generation (CycloneDX + SPDX)
- Container image scanning (Trivy)

See the [Security](https://github.com/stoa-platform/stoa/blob/main/SECURITY.md) documentation for details.

## Development

### How do I run tests?

```bash
# Python (Control Plane API, MCP Gateway)
cd control-plane-api && pytest --cov=src --cov-fail-under=70
cd mcp-gateway && pytest --cov=src

# TypeScript (Portal, Console)
cd portal && npm run test
cd control-plane-ui && npm run test

# E2E
cd e2e && npx playwright test
```

### What's the minimum test coverage?

70% for Python components, enforced in CI via `pytest --cov-fail-under=70`.

### How do I add a new Gateway Adapter?

1. Create module in `control-plane-api/src/adapters/{gateway}/`
2. Implement the `GatewayAdapterInterface` abstract class
3. Register the adapter in `provisioning_service.py`
4. Optionally update Ansible tasks for reconciliation

See the [Gateway Adapter Spec](https://docs.gostoa.dev/reference/gateway-adapter-spec) for the full interface.
