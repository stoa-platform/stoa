---
sidebar_position: 5
title: Architecture
description: High-level architecture and component overview.
---

# Architecture

STOA follows a modular, event-driven architecture with clear separation between the control plane, data plane, and GitOps pipeline.

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Clients                                 │
│  Console UI        Portal        CLI        AI Agents           │
│  (Provider)      (Consumer)    (stoa)     (MCP clients)         │
└──────┬──────────────┬───────────┬──────────────┬────────────────┘
       │              │           │              │
       ▼              ▼           ▼              ▼
┌──────────────────────────────────┐    ┌────────────────────┐
│       Control Plane API          │    │    MCP Gateway      │
│   FastAPI · Keycloak · RBAC      │    │  Tools · OPA · SSE  │
└──────┬──────┬──────┬─────────────┘    └────────────────────┘
       │      │      │
  ┌────▼──┐ ┌─▼───┐ ┌▼──────────┐
  │  RDS  │ │GitLab│ │  Kafka    │
  │ (PG)  │ │(Git) │ │(Redpanda) │
  └───────┘ └──┬───┘ └───────────┘
               │
          ┌────▼────┐
          │ ArgoCD  │──► Kubernetes (EKS)
          └────┬────┘
               │
          ┌────▼────┐
          │   AWX   │──► API Gateways
          └─────────┘    (webMethods, Kong, ...)
```

## Components

### Control Plane API

The central backend, built with **FastAPI** (Python 3.11). Handles:

- Tenant, API, and subscription CRUD
- RBAC enforcement via Keycloak JWT validation
- Event publishing to Kafka for async workflows
- GitOps synchronization with GitLab

### Console UI (API Provider)

React application for platform administrators and tenant managers. Provides:

- Tenant management (create, configure, delete)
- API lifecycle (publish, version, deprecate)
- User and role management
- Dashboard with platform metrics

### Developer Portal (API Consumer)

React + Vite application for API consumers. Features:

- API catalog with search and filtering
- Subscription management
- API documentation viewer
- Interactive API testing

### MCP Gateway

AI-native API access layer operating in **edge-mcp** mode:

- **Tool Registry**: APIs registered as tools via Kubernetes CRDs
- **OPA Policy Engine**: Fine-grained, policy-based access control
- **Metering Pipeline**: Kafka-based usage tracking and rate limiting
- **SSE Transport**: Server-Sent Events for MCP protocol communication

### GitOps Pipeline

Git serves as the source of truth for all platform configuration:

```
GitHub (code) → GitLab (config) → ArgoCD (sync) → Kubernetes
                                        ↓
                                  AWX (Ansible) → Gateways
```

### Event Streaming

Kafka (via Redpanda) powers async workflows:

- API lifecycle events (publish, deprecate, delete)
- Subscription approval/rejection notifications
- MCP Gateway metering and usage data
- Audit trail for compliance

## Request Flow

### API Provider Flow

1. Admin logs into **Console UI** via Keycloak SSO
2. Creates a tenant → Control Plane API writes to PostgreSQL + publishes to Kafka
3. Publishes an API → API spec stored in GitLab, ArgoCD syncs to cluster
4. AWX reconciles the API definition with the target gateway

### API Consumer Flow

1. Developer visits **Portal**, authenticates via Keycloak
2. Browses API catalog, views documentation
3. Creates a subscription request → pending approval
4. On approval, receives credentials to call the API

### AI Agent Flow

1. Agent connects to **MCP Gateway** via SSE
2. Discovers available tools (registered from CRDs)
3. Calls `tools/call` with parameters
4. OPA evaluates policy → Gateway proxies to backend API
5. Response returned to agent, usage metered via Kafka

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite |
| Backend | FastAPI, Python 3.11 |
| Auth | Keycloak (OIDC) |
| Database | PostgreSQL (RDS) |
| Events | Redpanda (Kafka-compatible) |
| GitOps | GitLab + ArgoCD |
| Automation | AWX (Ansible) |
| Infrastructure | AWS EKS, Terraform |
| Packaging | Helm 3 |
| AI Gateway | MCP Protocol, OPA, Kafka metering |

## Deployment Topology

STOA deploys to Kubernetes with per-tenant namespace isolation:

```
stoa-system/              # Platform services
  ├── control-plane-api
  ├── console-ui
  ├── portal
  ├── mcp-gateway
  └── redpanda

tenant-acme/              # Tenant "acme" resources
  ├── Tool CRDs
  └── ToolSet CRDs

tenant-globex/            # Tenant "globex" resources
  ├── Tool CRDs
  └── ToolSet CRDs
```

Each tenant namespace is isolated by Kubernetes RBAC and network policies.
