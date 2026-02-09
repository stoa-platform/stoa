# STOA Platform — Admin Guide

> Operational documentation for STOA Platform administrators.
> For user-facing docs, see [docs.gostoa.dev](https://docs.gostoa.dev).

## Architecture Overview

```
CONTROL PLANE (Cloud)                        DATA PLANE (On-Premise)
┌──────────────────────────────────┐         ┌──────────────────────────┐
│  Console   Portal   API   Auth   │  ←sync→ │  MCP Gateway   Legacy GW │
│  (React)   (React)  (Py)  (KC)   │         │  (Python)      Kong/Envoy│
│  :443      :443     :8000 :8080  │         │  :8080         :8443     │
└──────────────────────────────────┘         └──────────────────────────┘
         │                                            │
         ▼                                            ▼
┌──────────────────────────────────┐         ┌──────────────────────────┐
│  PostgreSQL 15  │  MinIO (S3)    │         │  OPA   │  Prometheus     │
│  OpenSearch     │  Kafka         │         │  Vault │  Grafana        │
└──────────────────────────────────┘         └──────────────────────────┘
```

## Components

| Component | Technology | Default Port | Health Endpoint |
|-----------|-----------|-------------|-----------------|
| Control Plane API | Python 3.11, FastAPI, SQLAlchemy | 8000 | `/health/ready` |
| Console UI | React 18, TypeScript, Keycloak-js | 443 | `/` |
| Developer Portal | React, Vite, TypeScript | 443 | `/` |
| MCP Gateway | Python 3.11, FastAPI, OPA | 8080 | `/health` |
| STOA Gateway | Rust, Tokio, axum | 8443 | `/health` |
| Auth (Keycloak) | Keycloak 24 | 8080 | `/health/ready` |

## Prerequisites

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| Kubernetes | 1.28+ | EKS recommended |
| Helm | 3.x | Chart in `charts/stoa-platform/` |
| PostgreSQL | 15 | Control Plane state store |
| Keycloak | 24 | Identity & access management |
| HashiCorp Vault | 1.15+ | Secrets management |
| MinIO / S3 | Latest | Object storage (specs, artifacts) |

## Key URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Console | `https://console.<BASE_DOMAIN>` | Admin UI |
| Portal | `https://portal.<BASE_DOMAIN>` | Developer self-service |
| API | `https://api.<BASE_DOMAIN>` | Control Plane REST API |
| MCP Gateway | `https://mcp.<BASE_DOMAIN>` | AI agent gateway |
| Auth | `https://auth.<BASE_DOMAIN>` | Keycloak SSO |
| Docs | `https://docs.<BASE_DOMAIN>` | Documentation site |
| Vault | `https://vault.<BASE_DOMAIN>` | Secrets UI |

> `BASE_DOMAIN` is the single source of truth for all URLs. Set it once in your configuration.

## Guide Index

| Page | Description |
|------|-------------|
| [Installation](installation.md) | Helm install, CRDs, post-install checks |
| [Configuration](configuration.md) | Environment variables, secrets, ESO |
| [RBAC](rbac.md) | Roles, permissions, Keycloak setup |
| [Secrets Rotation](secrets-rotation.md) | Vault + ESO rotation procedure |
| [Monitoring](monitoring.md) | Prometheus, Grafana, OpenSearch |
| [Backup & Restore](backup-restore.md) | PostgreSQL, Keycloak, MinIO |
| [Troubleshooting](troubleshooting.md) | Common issues and fixes |
| [Upgrade](upgrade.md) | Helm upgrade, Alembic migrations |
| [OpenShift Delta](openshift-delta.md) | OpenShift-specific differences |

## Quick Commands

```bash
# Check all pods
kubectl get pods -n stoa-system

# Health check
curl -s https://api.<BASE_DOMAIN>/health/ready

# Logs for a component
kubectl logs -f deploy/control-plane-api -n stoa-system

# Helm status
helm status stoa-platform -n stoa-system
```
