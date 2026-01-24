# STOA Platform v2 - Complete Architecture

> **Version:** 2.0 | **Date:** Janvier 2026 | **Phase actuelle:** Phase 12 (MCP Gateway)

---

## Table of Contents

1. [Overview](#1-vue-densemble)
2. [Composants Principaux](#2-composants-principaux)
3. [Data Flow](#3-data-flow)
4. [Architecture Kubernetes](#4-architecture-kubernetes)
5. [Authentification & Autorisation](#5-authentification--autorisation)
6. [Event-Driven Architecture](#6-event-driven-architecture)
7. [MCP Gateway](#7-mcp-gateway)
8. [GitOps & CI/CD](#8-gitops--cicd)
9. [Database](#9-database)
10. [Integrations](#10-integrations)
11. [Endpoints API](#11-endpoints-api)
12. [Observability](#12-observability)
13. [Security](#13-security)
14. [Stack Technologique](#14-stack-technologique)

---

## 1. Overview

### 1.1 Description

**STOA Platform v2** is a multi-tenant and event-driven API management platform designed for enterprise environments. It combines:

- **Control-Plane UI** - Console d'administration pour les API Providers
- **Developer Portal** - Portal for API Consumers
- **MCP Gateway** - AI-native gateway via Model Context Protocol
- **GitOps Architecture** - GitLab as source of truth
- **Event-Driven Pipeline** - Kafka/Redpanda for asynchronous processing

### 1.2 High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              STOA Platform v2                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  Control-Plane  │    │    Developer    │    │   Claude.ai /   │         │
│  │       UI        │    │     Portal      │    │   MCP Clients   │         │
│  │  (API Provider) │    │  (API Consumer) │    │                 │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           │ OIDC                 │ OIDC                 │ MCP/SSE          │
│           ▼                      ▼                      ▼                   │
│  ┌────────────────────────────────────────────────────────────────┐        │
│  │                         Keycloak                                │        │
│  │                    (auth.gostoa.dev)                       │        │
│  └────────────────────────────────────────────────────────────────┘        │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────────────────────────┐    ┌─────────────────────┐        │
│  │        Control-Plane API            │    │    MCP Gateway      │        │
│  │        (FastAPI Backend)            │◄───┤   (AI-Native API)   │        │
│  │   apis.gostoa.dev/gateway/...   │    │ mcp.gostoa.dev  │        │
│  └──────────────┬──────────────────────┘    └──────────┬──────────┘        │
│                 │                                      │                    │
│      ┌──────────┼──────────┬───────────────────────────┤                   │
│      │          │          │                           │                    │
│      ▼          ▼          ▼                           ▼                    │
│  ┌───────┐  ┌───────┐  ┌───────────┐           ┌─────────────┐             │
│  │GitLab │  │ AWX   │  │  Kafka/   │           │ Kubernetes  │             │
│  │       │  │       │  │ Redpanda  │           │   (CRDs)    │             │
│  └───┬───┘  └───┬───┘  └─────┬─────┘           └──────┬──────┘             │
│      │          │            │                        │                     │
│      │          ▼            │                        │                     │
│      │    ┌───────────┐      │                        │                     │
│      │    │ webMethods│◄─────┴────────────────────────┘                     │
│      │    │  Gateway  │                                                     │
│      │    └─────┬─────┘                                                     │
│      │          │                                                           │
│      ▼          ▼                                                           │
│  ┌──────────────────────────────────────┐                                  │
│  │           PostgreSQL (RDS)           │                                  │
│  │    Subscriptions, Tenants, APIs      │                                  │
│  └──────────────────────────────────────┘                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Production URLs

| Service | URL | Description |
|---------|-----|-------------|
| Console UI | `https://console.gostoa.dev` | API Provider Interface |
| Developer Portal | `https://portal.gostoa.dev` | API Consumer Interface |
| API Gateway Runtime | `https://apis.gostoa.dev` | Runtime des APIs (OIDC) |
| Control-Plane API | `https://apis.gostoa.dev/gateway/Control-Plane-API/2.0` | Backend API |
| MCP Gateway | `https://mcp.gostoa.dev` | AI-Native API Gateway |
| Keycloak | `https://auth.gostoa.dev` | Identity Provider |
| Gateway Admin | `https://gateway.gostoa.dev` | webMethods Admin |
| AWX | `https://awx.gostoa.dev` | Automation |
| ArgoCD | `https://argocd.gostoa.dev` | GitOps |
| Vault | `https://vault.gostoa.dev` | Secrets Management |

---

## 2. Composants Principaux

### 2.1 Control-Plane API (Backend FastAPI)

**Emplacement:** `control-plane-api/`
**Technology:** Python 3.11, FastAPI, SQLAlchemy, Alembic

```
control-plane-api/
├── src/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Configuration (BASE_DOMAIN)
│   ├── routers/
│   │   ├── apis.py             # CRUD APIs (GitOps)
│   │   ├── tenants.py          # Multi-tenant management
│   │   ├── subscriptions.py    # Souscriptions & API keys
│   │   ├── applications.py     # Applications consumer
│   │   ├── deployments.py      # Deployments (Kafka)
│   │   ├── gateway.py          # Proxy webMethods
│   │   ├── mcp.py              # MCP servers
│   │   ├── mcp_admin.py        # MCP administration
│   │   ├── portal.py           # Developer Portal endpoints
│   │   └── webhooks.py         # Event webhooks
│   ├── services/
│   │   ├── git_service.py      # GitLab integration
│   │   ├── kafka_service.py    # Producer Kafka
│   │   ├── awx_service.py      # Orchestration AWX
│   │   ├── keycloak_service.py # IAM Keycloak
│   │   ├── gateway_service.py  # webMethods API client
│   │   └── webhook_service.py  # Delivery webhooks
│   └── models/
│       ├── subscription.py     # Subscription model
│       ├── mcp_server.py       # MCP models
│       └── webhook.py          # Webhook models
├── alembic/                    # DB migrations
└── tests/
```

**Responsibilities:**
- API lifecycle management (CRUD via GitOps)
- Subscription and API key management
- Deployment orchestration via Kafka/AWX
- Proxy vers webMethods Gateway
- Keycloak integration for authentication

### 2.2 Control-Plane UI (Console React)

**Emplacement:** `control-plane-ui/`
**Technology:** React 18, TypeScript, TailwindCSS, Keycloak-js

```
control-plane-ui/
├── src/
│   ├── pages/
│   │   ├── Dashboard.tsx       # Overview
│   │   ├── Tenants.tsx         # Tenant management
│   │   ├── APIs.tsx            # API management
│   │   ├── Applications.tsx    # Applications
│   │   ├── Deployments.tsx     # Deployment history
│   │   ├── AITools.tsx         # AI tools catalog
│   │   └── ErrorSnapshots.tsx  # Snapshots d'erreurs (CAB-397)
│   ├── components/
│   ├── services/
│   │   └── api.ts              # Control-Plane API client
│   └── auth/
│       └── keycloak.ts         # Config Keycloak
└── public/
```

**Features:**
- Dashboard with metrics
- CRUD complet des APIs par tenant
- Application and subscription management
- Deployment monitoring
- AI tools catalog

### 2.3 Developer Portal (React + Vite)

**Emplacement:** `portal/`
**Technology:** React 18, TypeScript, Vite, TailwindCSS, React Query

```
portal/
├── src/
│   ├── pages/
│   │   ├── ApiCatalog.tsx      # Browse APIs
│   │   ├── ApiDetails.tsx      # API details
│   │   ├── Subscriptions.tsx   # Mes souscriptions
│   │   ├── Applications.tsx    # Mes applications
│   │   ├── MCPTools.tsx        # MCP Tools
│   │   ├── MCPServers.tsx      # MCP Servers
│   │   ├── ApiTesting.tsx      # Test sandbox
│   │   └── UsageMetrics.tsx    # Usage metrics
│   ├── components/
│   │   ├── ApiCard.tsx
│   │   ├── SubscriptionForm.tsx
│   │   └── MCPToolCard.tsx
│   ├── services/
│   │   └── api.ts              # API client (React Query)
│   └── config.ts               # Runtime configuration
├── k8s/
│   └── configmap.yaml          # Config Kubernetes
└── Dockerfile
```

**Features:**
- API catalog with filters
- Souscription et gestion des API keys
- Consumer application creation
- API testing in sandbox
- Consumption metrics
- MCP tools discovery

### 2.4 MCP Gateway (AI-Native Gateway)

**Emplacement:** `mcp-gateway/`
**Technology:** Python 3.11, FastAPI, OPA, Kubernetes-asyncio

```
mcp-gateway/
├── src/
│   ├── main.py                 # Entry point
│   ├── handlers/
│   │   ├── mcp.py              # MCP Protocol (tools, resources)
│   │   ├── mcp_sse.py          # Bidirectional SSE transport
│   │   ├── subscriptions.py    # Souscriptions MCP
│   │   └── servers.py          # Cycle de vie serveurs
│   ├── auth/
│   │   ├── keycloak.py         # JWT validation
│   │   └── opa.py              # Moteur de politiques OPA
│   ├── registry/
│   │   ├── tool_registry.py    # Registre des outils
│   │   └── k8s_watcher.py      # Watcher CRDs Kubernetes
│   ├── metering/
│   │   └── kafka_metering.py   # Kafka metrics pipeline
│   └── adapters/
│       ├── rest_adapter.py     # Convertisseur REST/OpenAPI
│       ├── graphql_adapter.py  # Support GraphQL
│       └── grpc_adapter.py     # Support gRPC
├── policies/                   # OPA policies (Rego)
│   ├── rbac.rego
│   └── rate_limit.rego
└── tests/                      # 196 tests, 79% coverage
```

**Architecture en couches:**

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Protocol Layer                          │
│  - Tools discovery & invocation                                 │
│  - Resources & prompts endpoints                                │
│  - SSE (Server-Sent Events) transport                          │
│  - JSON-RPC 2.0 messaging                                       │
├─────────────────────────────────────────────────────────────────┤
│                   Security & Policy Layer                       │
│  - Keycloak OIDC authentication                                │
│  - OPA policy engine (fine-grained RBAC)                       │
│  - Rate limiting (role-based)                                  │
│  - Metering via Kafka                                          │
├─────────────────────────────────────────────────────────────────┤
│                  Kubernetes Integration                         │
│  - Tool CRD watcher                                            │
│  - ToolSet CRD (OpenAPI-to-MCP)                               │
│  - Dynamic tool registration                                   │
├─────────────────────────────────────────────────────────────────┤
│                    Backend Adapters                             │
│  - REST/OpenAPI converter                                      │
│  - GraphQL, gRPC support                                       │
│  - Kafka event streaming                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow

### 3.1 API Creation and Publication

```
┌──────────────┐
│  Developer   │
│ (Provider)   │
└──────┬───────┘
       │ 1. Create/Update API
       ▼
┌──────────────┐     2. Write YAML      ┌──────────────┐
│ Control-Plane├────────────────────────►│    GitLab    │
│      UI      │                         │  Repository  │
└──────────────┘                         └──────┬───────┘
                                                │
                         3. Watch              │
                    ┌───────────────────────────┘
                    ▼
            ┌──────────────┐
            │   ArgoCD     │
            │  (GitOps)    │
            └──────┬───────┘
                   │ 4. Publish event
                   ▼
            ┌──────────────┐
            │    Kafka     │
            │ api-created  │
            └──────┬───────┘
                   │
         ┌─────────┼─────────┐
         │         │         │
         ▼         ▼         ▼
    ┌────────┐ ┌────────┐ ┌────────┐
    │ Portal │ │ Audit  │ │ Notif  │
    │Catalog │ │  Log   │ │ Email  │
    └────────┘ └────────┘ └────────┘
```

### 3.2 Deployment Pipeline (Event-Driven)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Deployment Pipeline                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. GitLab Webhook ────► Control-Plane API                              │
│                          │                                               │
│                          │ < 100ms                                       │
│                          ▼                                               │
│                     ✅ 200 OK (async processing)                         │
│                          │                                               │
│  2. Publish ────────────►│                                               │
│                          ▼                                               │
│                    ┌───────────────┐                                     │
│                    │ deploy-requests│                                    │
│                    │    (Kafka)     │                                    │
│                    └───────┬───────┘                                     │
│                            │                                             │
│  3. Consume ──────────────►│                                             │
│                            ▼                                             │
│                    ┌───────────────┐                                     │
│                    │  AWX Consumer │                                     │
│                    │               │                                     │
│                    │ • Get spec from GitLab                             │
│                    │ • Validate OpenAPI                                 │
│                    │ • Convert 3.1→3.0                                  │
│                    │ • Execute Ansible                                  │
│                    │ • Configure webMethods                             │
│                    └───────┬───────┘                                     │
│                            │                                             │
│  4. Publish ──────────────►│                                             │
│                            ▼                                             │
│                    ┌───────────────┐                                     │
│                    │ deploy-results │                                    │
│                    │    (Kafka)     │                                    │
│                    └───────┬───────┘                                     │
│                            │                                             │
│         ┌──────────────────┼──────────────────┐                         │
│         │                  │                  │                          │
│         ▼                  ▼                  ▼                          │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                    │
│  │Control-Plane│   │ OpenSearch  │   │Notifications│                    │
│  │    API      │   │ (Analytics) │   │(Email/Slack)│                    │
│  └─────────────┘   └─────────────┘   └─────────────┘                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Workflow de Souscription API

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Subscription Workflow                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐                                                        │
│  │  Developer  │                                                        │
│  │  (Consumer) │                                                        │
│  └──────┬──────┘                                                        │
│         │                                                                │
│         │ 1. Browse APIs                                                │
│         ▼                                                                │
│  ┌─────────────┐     2. Subscribe      ┌─────────────┐                  │
│  │  Developer  │ ──────────────────────► Control-Plane                  │
│  │   Portal    │                        │     API     │                  │
│  └─────────────┘                        └──────┬──────┘                  │
│                                                │                         │
│                                                │ 3. Generate API Key     │
│                                                │    (stoa_sk_XXXX)       │
│                                                │                         │
│                                                │ 4. Store hash + prefix  │
│                                                ▼                         │
│                                         ┌─────────────┐                  │
│                                         │ PostgreSQL  │                  │
│                                         │ (PENDING)   │                  │
│                                         └─────────────┘                  │
│                                                                          │
│  ────────────────────── APPROVAL ──────────────────────                 │
│                                                                          │
│  ┌─────────────┐     5. View Pending   ┌─────────────┐                  │
│  │   Admin     │ ◄──────────────────── │Control-Plane│                  │
│  │  (Console)  │                        │     UI      │                  │
│  └──────┬──────┘                        └─────────────┘                  │
│         │                                                                │
│         │ 6. Approve                                                     │
│         ▼                                                                │
│  ┌─────────────┐     7. Update Status  ┌─────────────┐                  │
│  │Control-Plane│ ──────────────────────► PostgreSQL  │                  │
│  │     API     │      (ACTIVE)          │             │                  │
│  └──────┬──────┘                        └─────────────┘                  │
│         │                                                                │
│         │ 8. Publish event                                              │
│         ▼                                                                │
│  ┌─────────────┐                                                        │
│  │   Kafka     │                                                        │
│  │subscription-│                                                        │
│  │  approved   │                                                        │
│  └─────────────┘                                                        │
│                                                                          │
│  ────────────────────── RUNTIME ───────────────────────                 │
│                                                                          │
│  ┌─────────────┐     9. API Call       ┌─────────────┐                  │
│  │  Consumer   │ ──────────────────────► webMethods  │                  │
│  │    App      │     (+ API Key)        │  Gateway    │                  │
│  └─────────────┘                        └──────┬──────┘                  │
│                                                │                         │
│                                    10. Validate│                         │
│                                                ▼                         │
│                                         ┌─────────────┐                  │
│                                         │Control-Plane│                  │
│                                         │     API     │                  │
│                                         └──────┬──────┘                  │
│                                                │                         │
│                                    11. Check   │                         │
│                                                ▼                         │
│                                         ┌─────────────┐                  │
│                                         │ PostgreSQL  │                  │
│                                         │(status/rate)│                  │
│                                         └─────────────┘                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.4 MCP Tool Registration & Invocation

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      MCP Tool Flow                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐                                                        │
│  │Tenant Admin │                                                        │
│  └──────┬──────┘                                                        │
│         │                                                                │
│         │ 1. Create Tool CRD                                            │
│         ▼                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ apiVersion: gostoa.dev/v1alpha1                             │    │
│  │ kind: Tool                                                       │    │
│  │ metadata:                                                        │    │
│  │   name: payment-search                                          │    │
│  │   namespace: tenant-acme                                        │    │
│  │ spec:                                                            │    │
│  │   displayName: Search Payments                                  │    │
│  │   endpoint: https://api.example.com/v1/payments/search          │    │
│  │   method: GET                                                    │    │
│  │   inputSchema: {...}                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│         │                                                                │
│         │ 2. kubectl apply                                              │
│         ▼                                                                │
│  ┌─────────────┐     3. Watch CRDs    ┌─────────────┐                   │
│  │ Kubernetes  │ ────────────────────► MCP Gateway  │                   │
│  │   API       │                       │  K8s Watcher│                   │
│  └─────────────┘                       └──────┬──────┘                   │
│                                               │                          │
│                                 4. Register   │                          │
│                                               ▼                          │
│                                        ┌─────────────┐                   │
│                                        │Tool Registry│                   │
│                                        │ (in-memory) │                   │
│                                        └─────────────┘                   │
│                                                                          │
│  ────────────────────── INVOCATION ────────────────────                 │
│                                                                          │
│  ┌─────────────┐                                                        │
│  │ Claude.ai   │                                                        │
│  │ (MCP Client)│                                                        │
│  └──────┬──────┘                                                        │
│         │                                                                │
│         │ 5. POST /mcp/sse (establish SSE)                              │
│         │ 6. GET /mcp/v1/tools (list tools)                             │
│         │ 7. POST /mcp/v1/tools/{name}/invoke                           │
│         ▼                                                                │
│  ┌─────────────┐                                                        │
│  │ MCP Gateway │                                                        │
│  │             │◄───────────────────────────────────────┐               │
│  │ • Extract JWT claims                                 │               │
│  │ • OPA policy evaluation                              │               │
│  │ • Rate limit check                                   │               │
│  │ • Forward to tool endpoint                           │               │
│  │ • Capture metrics                                    │               │
│  └──────┬──────┘                                        │               │
│         │                                               │               │
│         │ 8. Publish metrics            9. Response     │               │
│         ▼                                               │               │
│  ┌─────────────┐                               ┌────────┴────┐          │
│  │   Kafka     │                               │ Tool Backend│          │
│  │mcp-metering │                               │   (REST)    │          │
│  └─────────────┘                               └─────────────┘          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Architecture Kubernetes

### 4.1 Namespaces

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Kubernetes Namespaces                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      stoa-system                                 │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │Control-  │ │  MCP     │ │ Keycloak │ │ Redpanda │            │    │
│  │  │Plane API │ │ Gateway  │ │          │ │ (Kafka)  │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │    │
│  │  │  Portal  │ │ Console  │ │ ArgoCD   │                         │    │
│  │  │          │ │   UI     │ │          │                         │    │
│  │  └──────────┘ └──────────┘ └──────────┘                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────┐    │
│  │      stoa-acme-dev              │ │     stoa-acme-staging       │    │
│  │  ┌──────────┐ ┌──────────┐      │ │  ┌──────────┐ ┌──────────┐  │    │
│  │  │ CRM API  │ │Inventory │      │ │  │ CRM API  │ │Inventory │  │    │
│  │  │   Pod    │ │ API Pod  │      │ │  │   Pod    │ │ API Pod  │  │    │
│  │  └──────────┘ └──────────┘      │ │  └──────────┘ └──────────┘  │    │
│  │  ┌──────────┐                   │ │  ┌──────────┐               │    │
│  │  │ Billing  │                   │ │  │ Billing  │               │    │
│  │  │ API Pod  │                   │ │  │ API Pod  │               │    │
│  │  └──────────┘                   │ │  └──────────┘               │    │
│  └─────────────────────────────────┘ └─────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────┐    │
│  │      stoa-demo-dev              │ │     stoa-demo-staging       │    │
│  │  ┌──────────┐ ┌──────────┐      │ │  ┌──────────┐ ┌──────────┐  │    │
│  │  │ Weather  │ │  User    │      │ │  │ Weather  │ │  User    │  │    │
│  │  │ API Pod  │ │ Svc Pod  │      │ │  │ API Pod  │ │ Svc Pod  │  │    │
│  │  └──────────┘ └──────────┘      │ │  └──────────┘ └──────────┘  │    │
│  └─────────────────────────────────┘ └─────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Custom Resource Definitions (CRDs)

```yaml
# Tool CRD - MCP tool registration
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: payment-search
  namespace: tenant-acme
spec:
  displayName: Search Payments
  description: Search payments by criteria
  endpoint: https://api.example.com/v1/payments/search
  method: GET
  inputSchema:
    type: object
    properties:
      startDate:
        type: string
        format: date
      endDate:
        type: string
        format: date
      status:
        type: string
        enum: [pending, completed, failed]
  outputSchema:
    type: array
    items:
      type: object

---
# ToolSet CRD - Conversion OpenAPI vers MCP
apiVersion: gostoa.dev/v1alpha1
kind: ToolSet
metadata:
  name: crm-api-tools
  namespace: tenant-acme
spec:
  openApiUrl: https://api.acme.com/crm/openapi.json
  prefix: crm_
  includeOperations:
    - getCustomer
    - searchCustomers
    - createOrder
```

### 4.3 Helm Chart Structure

```
charts/stoa-platform/
├── Chart.yaml
├── values.yaml
├── crds/
│   ├── tool-crd.yaml
│   └── toolset-crd.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── control-plane-api/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── configmap.yaml
│   │   └── ingress.yaml
│   ├── mcp-gateway/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   ├── portal/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── configmap.yaml
│   ├── console-ui/
│   │   ├── deployment.yaml
│   │   └── service.yaml
│   └── common/
│       ├── namespace.yaml
│       └── networkpolicy.yaml
└── values/
    ├── dev.yaml
    ├── staging.yaml
    └── prod.yaml
```

---

## 5. Authentification & Autorisation

### 5.1 Keycloak Configuration

**Realm:** `stoa`

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Keycloak Realm: stoa                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Clients:                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ control-plane-api    │ Confidential │ Client Credentials (M2M) │    │
│  │ control-plane-ui     │ Public       │ PKCE + Authorization Code│    │
│  │ stoa-portal          │ Public       │ PKCE + Authorization Code│    │
│  │ api-gateway          │ Confidential │ Token Validation         │    │
│  │ mcp-gateway          │ Confidential │ JWT Validation           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Realm Roles:                                                            │
│  ┌──────────────┬──────────────────────────────────────────────────┐    │
│  │ cpi-admin    │ Full platform access (stoa:admin scope)          │    │
│  │ tenant-admin │ Manage own tenant (stoa:write, stoa:read)        │    │
│  │ devops       │ Deploy and promote APIs (stoa:write, stoa:read)  │    │
│  │ viewer       │ Read-only access (stoa:read)                     │    │
│  └──────────────┴──────────────────────────────────────────────────┘    │
│                                                                          │
│  Client Scopes:                                                          │
│  ┌──────────────┬──────────────────────────────────────────────────┐    │
│  │ stoa:admin   │ Full administrative access                       │    │
│  │ stoa:write   │ Create/Update/Delete resources                   │    │
│  │ stoa:read    │ Read-only access                                 │    │
│  │ openid       │ OIDC standard                                    │    │
│  │ profile      │ User profile info                                │    │
│  │ email        │ User email                                       │    │
│  └──────────────┴──────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Matrice RBAC

| Role | Tenants | APIs | Applications | Deploy | Users |
|------|---------|------|--------------|--------|-------|
| **CPI Admin** | CRUD (tous) | CRUD (tous) | CRUD (tous) | Tous envs | Tous |
| **Tenant Admin** | Read (own) | CRUD (own) | CRUD (own) | Tous envs | Own tenant |
| **DevOps** | Read (own) | CRU (own) | CRU (own) | Tous envs | - |
| **Viewer** | Read (own) | Read (own) | Read (own) | - | - |

### 5.3 MCP Gateway Authorization (OPA)

```rego
# policies/rbac.rego

package stoa.mcp

default allow = false

# Admin peut tout faire
allow {
    input.user.roles[_] == "cpi-admin"
}

# Tenant admin can access tools in their tenant
allow {
    input.user.roles[_] == "tenant-admin"
    input.tool.namespace == input.user.tenant_id
}

# Rate limit verification
rate_limit_exceeded {
    input.user.request_count > get_rate_limit(input.user.roles)
}

get_rate_limit(roles) = limit {
    roles[_] == "cpi-admin"
    limit := 10000
} else = limit {
    roles[_] == "tenant-admin"
    limit := 1000
} else = limit {
    limit := 100
}
```

---

## 6. Event-Driven Architecture

### 6.1 Topics Kafka/Redpanda

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Kafka Topics                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┬──────────────────┬──────────────────────────────┐  │
│  │     Topic       │    Producers     │         Consumers            │  │
│  ├─────────────────┼──────────────────┼──────────────────────────────┤  │
│  │ api-created     │ Control-Plane    │ ArgoCD, Audit, Notifications │  │
│  │ api-updated     │ Control-Plane    │ ArgoCD, Audit, Notifications │  │
│  │ api-deleted     │ Control-Plane    │ Audit, Cleanup               │  │
│  │ deploy-requests │ Control-Plane    │ AWX Consumer                 │  │
│  │ deploy-results  │ AWX Worker       │ Control-Plane, OpenSearch    │  │
│  │ audit-log       │ All Services     │ OpenSearch, Compliance       │  │
│  │ notifications   │ All Services     │ Email/Slack                  │  │
│  │ mcp-metering    │ MCP Gateway      │ Billing, Analytics           │  │
│  │ mcp-errors      │ MCP Gateway      │ Control-Plane, OpenSearch    │  │
│  │ subscriptions   │ Control-Plane    │ Portal, Notifications        │  │
│  │ webhooks        │ Control-Plane    │ Webhook Delivery             │  │
│  └─────────────────┴──────────────────┴──────────────────────────────┘  │
│                                                                          │
│  Configuration:                                                          │
│  - Retention: 7 jours                                                   │
│  - Partitions: 3 (default)                                           │
│  - Replication Factor: 2                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Event Schema

```json
// api-created event
{
  "event_type": "api-created",
  "timestamp": "2026-01-18T10:30:00Z",
  "correlation_id": "uuid-xxx",
  "tenant_id": "acme-corp",
  "payload": {
    "api_id": "crm-api",
    "api_name": "CRM API",
    "version": "1.0.0",
    "status": "draft",
    "created_by": "user@acme.com"
  }
}

// deploy-request event
{
  "event_type": "deploy-request",
  "timestamp": "2026-01-18T11:00:00Z",
  "correlation_id": "uuid-yyy",
  "tenant_id": "acme-corp",
  "payload": {
    "api_id": "crm-api",
    "environment": "dev",
    "version": "1.0.0",
    "git_commit": "abc123",
    "requested_by": "devops@acme.com"
  }
}

// subscription-approved event
{
  "event_type": "subscription-approved",
  "timestamp": "2026-01-18T12:00:00Z",
  "correlation_id": "uuid-zzz",
  "tenant_id": "acme-corp",
  "payload": {
    "subscription_id": "sub-123",
    "api_id": "crm-api",
    "application_id": "app-456",
    "subscriber_id": "consumer@company.com",
    "approved_by": "admin@acme.com"
  }
}
```

---

## 7. MCP Gateway

### 7.1 MCP Protocol

The **Model Context Protocol (MCP)** allows LLMs (like Claude) to interact with APIs in a standardized way.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MCP Protocol Stack                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     Transport Layer                              │    │
│  │  - SSE (Server-Sent Events) bidirectionnel                      │    │
│  │  - JSON-RPC 2.0 messaging                                       │    │
│  │  - WebSocket (optionnel)                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     Protocol Layer                               │    │
│  │  Methods:                                                        │    │
│  │  - tools/list       → List of available tools              │    │
│  │  - tools/call       → Invocation d'un outil                     │    │
│  │  - resources/list   → List of resources                      │    │
│  │  - resources/read   → Read a resource                   │    │
│  │  - prompts/list     → List of prompts                         │    │
│  │  - prompts/get      → Get a prompt                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     Security Layer                               │    │
│  │  - OAuth 2.0 / OIDC authentication                              │    │
│  │  - JWT token validation (Keycloak)                              │    │
│  │  - OPA policy evaluation                                        │    │
│  │  - Rate limiting per role/user                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Endpoints MCP Gateway

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness probe |
| `/metrics` | GET | Prometheus metrics |
| `/mcp/sse` | POST | SSE bidirectionnel (MCP 2.0) |
| `/mcp/v1/tools` | GET | List of tools |
| `/mcp/v1/tools/{name}` | GET | Tool details |
| `/mcp/v1/tools/{name}/invoke` | POST | Invocation |
| `/api/tools` | GET | Alias REST |
| `/api/apis` | GET | List of APIs |
| `/.well-known/oauth-protected-resource/mcp/sse` | GET | OAuth metadata |

### 7.3 MCP Gateway Environment Variables

| Variable | Default | Description |
|----------|--------|-------------|
| `OPA_ENABLED` | `true` | Activer OPA |
| `OPA_EMBEDDED` | `true` | Embedded evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metrics |
| `K8S_WATCHER_ENABLED` | `false` | Watcher CRDs K8s |
| `KEYCLOAK_URL` | - | URL Keycloak |
| `KEYCLOAK_REALM` | `stoa` | Realm |
| `KAFKA_BOOTSTRAP_SERVERS` | - | Kafka servers |

---

## 8. GitOps & CI/CD

### 8.1 GitLab Repository Structure

```
stoa-gitops/
├── tenants/
│   ├── acme-corp/
│   │   ├── tenant.yaml           # Tenant definition
│   │   └── apis/
│   │       ├── crm-api/
│   │       │   ├── api.yaml      # API metadata
│   │       │   └── openapi.yaml  # Spec OpenAPI
│   │       └── inventory-api/
│   │           ├── api.yaml
│   │           └── openapi.yaml
│   └── demo-tenant/
│       ├── tenant.yaml
│       └── apis/
│           └── weather-api/
│               ├── api.yaml
│               └── openapi.yaml
│
├── webmethods/
│   ├── apis/
│   │   └── control-plane-api.yaml    # Config Gateway
│   ├── policies/
│   │   ├── jwt-validation.yaml
│   │   ├── rate-limit-standard.yaml
│   │   ├── cors-platform.yaml
│   │   └── logging-standard.yaml
│   └── aliases/
│       └── dev.yaml
│
├── argocd/
│   ├── applications/
│   │   ├── stoa-system.yaml
│   │   ├── tenant-acme-dev.yaml
│   │   └── tenant-acme-staging.yaml
│   └── projects/
│       └── stoa-platform.yaml
│
└── .gitlab-ci.yml                    # Pipeline CI/CD
```

### 8.2 Exemple tenant.yaml

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: Tenant
metadata:
  name: acme-corp
  labels:
    environment: production
spec:
  displayName: ACME Corporation
  description: Enterprise APIs for ACME Corp

  owner:
    email: admin@acme.com
    name: ACME Admin Team

  portalVisibility: public    # public | private

  settings:
    maxApis: 50
    maxApplications: 100
    supportedEnvironments:
      - dev
      - staging
      - production

  defaultPolicies:
    - jwt-validation
    - rate-limit-standard
    - cors-platform
    - logging-standard

  tags:
    - enterprise
    - finance
    - retail
```

### 8.3 Pipeline GitLab CI/CD

```yaml
# .gitlab-ci.yml
stages:
  - validate
  - reconcile
  - deploy
  - e2e-test

validate-openapi:
  stage: validate
  script:
    - openapi-lint tenants/*/apis/*/openapi.yaml
  rules:
    - changes:
        - tenants/*/apis/**/*

reconcile-webmethods:
  stage: reconcile
  script:
    - >
      curl -X POST $AWX_URL/api/v2/job_templates/reconcile-apis/launch/
      -H "Authorization: Bearer $AWX_TOKEN"
  rules:
    - changes:
        - webmethods/**/*
        - tenants/*/apis/**/*

deploy-to-argocd:
  stage: deploy
  script:
    - argocd app sync stoa-platform --prune
  environment:
    name: $CI_ENVIRONMENT_NAME

e2e-tests:
  stage: e2e-test
  script:
    - pytest tests/e2e/ -v
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

---

## 9. Database

### 9.1 Schema PostgreSQL

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL Schema                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       subscriptions                              │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ application_id  UUID NOT NULL                                   │    │
│  │ api_id          VARCHAR(255) NOT NULL                           │    │
│  │ tenant_id       VARCHAR(255) NOT NULL                           │    │
│  │ subscriber_id   VARCHAR(255) NOT NULL                           │    │
│  │ api_key_hash    VARCHAR(64)                                     │    │
│  │ api_key_prefix  VARCHAR(12)   -- stoa_sk_XXXX                   │    │
│  │ status          VARCHAR(20)   -- pending/active/suspended/...   │    │
│  │ created_at      TIMESTAMP                                       │    │
│  │ expires_at      TIMESTAMP                                       │    │
│  │ approved_at     TIMESTAMP                                       │    │
│  │ approved_by     VARCHAR(255)                                    │    │
│  │ rate_limit      INTEGER       -- requests per minute            │    │
│  │                                                                 │    │
│  │ INDEX idx_sub_tenant (tenant_id)                                │    │
│  │ INDEX idx_sub_api (api_id)                                      │    │
│  │ INDEX idx_sub_app (application_id)                              │    │
│  │ INDEX idx_sub_status (status)                                   │    │
│  └─────────────────────────────────────────────────────────────────��    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       mcp_servers                                │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ tenant_id       VARCHAR(255) NOT NULL                           │    │
│  │ name            VARCHAR(255) NOT NULL                           │    │
│  │ description     TEXT                                            │    │
│  │ endpoint        VARCHAR(512)                                    │    │
│  │ auth_type       VARCHAR(50)   -- oauth2/apikey/none            │    │
│  │ status          VARCHAR(20)   -- active/inactive                │    │
│  │ created_at      TIMESTAMP                                       │    │
│  │ updated_at      TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     mcp_server_tools                             │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ server_id       UUID REFERENCES mcp_servers(id)                 │    │
│  │ name            VARCHAR(255) NOT NULL                           │    │
│  │ description     TEXT                                            │    │
│  │ input_schema    JSONB                                           │    │
│  │ output_schema   JSONB                                           │    │
│  │ endpoint        VARCHAR(512)                                    │    │
│  │ method          VARCHAR(10)   -- GET/POST/PUT/DELETE            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    mcp_subscriptions                             │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ server_id       UUID REFERENCES mcp_servers(id)                 │    │
│  │ subscriber_id   VARCHAR(255) NOT NULL                           │    │
│  │ status          VARCHAR(20)                                     │    │
│  │ created_at      TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     tenant_webhooks                              │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ tenant_id       VARCHAR(255) NOT NULL                           │    │
│  │ url             VARCHAR(512) NOT NULL                           │    │
│  │ events          JSONB         -- ["api-created", "deploy-*"]    │    │
│  │ secret          VARCHAR(255)  -- HMAC signing                   │    │
│  │ status          VARCHAR(20)                                     │    │
│  │ created_at      TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    webhook_deliveries                            │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ webhook_id      UUID REFERENCES tenant_webhooks(id)             │    │
│  │ event_type      VARCHAR(100)                                    │    │
│  │ payload         JSONB                                           │    │
│  │ response_code   INTEGER                                         │    │
│  │ response_body   TEXT                                            │    │
│  │ attempts        INTEGER                                         │    │
│  │ delivered_at    TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    mcp_error_snapshots                           │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ tenant_id       VARCHAR(255)                                    │    │
│  │ tool_name       VARCHAR(255)                                    │    │
│  │ error_type      VARCHAR(100)                                    │    │
│  │ error_message   TEXT                                            │    │
│  │ request_data    JSONB         -- masked sensitive data          │    │
│  │ response_data   JSONB                                           │    │
│  │ stack_trace     TEXT                                            │    │
│  │ created_at      TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                     pipeline_traces                              │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ correlation_id  UUID                                            │    │
│  │ tenant_id       VARCHAR(255)                                    │    │
│  │ api_id          VARCHAR(255)                                    │    │
│  │ environment     VARCHAR(50)                                     │    │
│  │ status          VARCHAR(20)   -- running/success/failed         │    │
│  │ started_at      TIMESTAMP                                       │    │
│  │ completed_at    TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       trace_steps                                │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │ id              UUID PRIMARY KEY                                │    │
│  │ trace_id        UUID REFERENCES pipeline_traces(id)             │    │
│  │ step_name       VARCHAR(100)                                    │    │
│  │ status          VARCHAR(20)                                     │    │
│  │ message         TEXT                                            │    │
│  │ metadata        JSONB                                           │    │
│  │ started_at      TIMESTAMP                                       │    │
│  │ completed_at    TIMESTAMP                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Migrations Alembic

```
control-plane-api/alembic/versions/
├── 001_initial_schema.py
├── 002_add_subscriptions.py
├── 003_add_mcp_tables.py
├── 004_add_webhooks.py
├── 005_add_key_rotation.py      # CAB-314
├── 006_add_error_snapshots.py   # CAB-485
└── 007_add_pipeline_traces.py
```

---

## 10. Integrations

### 10.1 webMethods Gateway

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      webMethods Integration                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Version: 10.15 (lean image)                                            │
│  URL: https://gateway.gostoa.dev                                    │
│                                                                          │
│  Configuration:                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Policies Applied:                                                │    │
│  │ • jwt-validation      → Keycloak token validation               │    │
│  │ • rate-limit-standard → Rate limiting (configurable)            │    │
│  │ • cors-platform       → CORS headers                            │    │
│  │ • logging-standard    → Access logs                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  API Registration Flow:                                                  │
│  1. GitLab commit → webmethods/apis/*.yaml                              │
│  2. GitLab CI → Trigger AWX reconciliation                              │
│  3. AWX playbook:                                                        │
│     a. Import API into Gateway                                          │
│     b. Configure OIDC authentication                                    │
│     c. Apply policies                                                   │
│     d. Activate API                                                     │
│  4. Publish result to Kafka                                             │
│                                                                          │
│  OpenAPI Compatibility:                                                  │
│  • Accepts: 3.0.x, 3.1.x (converts to 3.0.0 internally)                │
│  • Stores: Swagger 2.0 (GitOps format)                                  │
│  • Elasticsearch 8 required for 10.15                                   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.2 AWX (Ansible Automation)

```yaml
# Playbook: deploy-api.yaml
---
- name: Deploy API to webMethods Gateway
  hosts: localhost
  vars:
    tenant_id: "{{ awx_tenant_id }}"
    api_id: "{{ awx_api_id }}"
    environment: "{{ awx_environment }}"

  tasks:
    - name: Fetch API spec from GitLab
      uri:
        url: "{{ gitlab_url }}/api/v4/projects/{{ project_id }}/repository/files/{{ path }}"
        headers:
          PRIVATE-TOKEN: "{{ gitlab_token }}"
      register: api_spec

    - name: Validate OpenAPI spec
      command: openapi-lint {{ api_spec.content }}

    - name: Convert OpenAPI 3.1 to 3.0
      command: openapi-downgrade {{ api_spec.content }}
      when: api_spec.content | regex_search('openapi.*3\\.1')

    - name: Import API to webMethods
      uri:
        url: "{{ gateway_url }}/rest/apigateway/apis"
        method: POST
        body_format: json
        body: "{{ api_spec.content }}"
        headers:
          Authorization: "Bearer {{ gateway_token }}"

    - name: Configure OIDC authentication
      uri:
        url: "{{ gateway_url }}/rest/apigateway/policies"
        method: POST
        body:
          policyName: jwt-validation
          apiId: "{{ api_id }}"

    - name: Activate API
      uri:
        url: "{{ gateway_url }}/rest/apigateway/apis/{{ api_id }}/activate"
        method: PUT

    - name: Publish success event
      kafka_publish:
        topic: deploy-results
        message:
          status: success
          api_id: "{{ api_id }}"
          environment: "{{ environment }}"
```

### 10.3 ArgoCD (GitOps)

```yaml
# argocd/applications/stoa-system.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: stoa-system
  namespace: argocd
spec:
  project: stoa-platform

  source:
    repoURL: https://gitlab.cab-i.com/stoa/gitops.git
    targetRevision: HEAD
    path: charts/stoa-platform
    helm:
      valueFiles:
        - values/prod.yaml

  destination:
    server: https://kubernetes.default.svc
    namespace: stoa-system

  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### 10.4 Vault (Secrets Management)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      HashiCorp Vault                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  URL: https://vault.gostoa.dev                                      │
│                                                                          │
│  Secret Paths:                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ secret/stoa/database                                            │    │
│  │   └── connection_string, username, password                     │    │
│  │                                                                 │    │
│  │ secret/stoa/keycloak                                            │    │
│  │   └── client_id, client_secret                                  │    │
│  │                                                                 │    │
│  │ secret/stoa/kafka                                               │    │
│  │   └── bootstrap_servers, sasl_username, sasl_password           │    │
│  │                                                                 │    │
│  │ secret/stoa/gitlab                                              │    │
│  │   └── token, project_ids                                        │    │
│  │                                                                 │    │
│  │ secret/stoa/awx                                                 │    │
│  │   └── url, token                                                │    │
│  │                                                                 │    │
│  │ secret/stoa/gateway                                             │    │
│  │   └── admin_url, admin_token                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Kubernetes Integration:                                                 │
│  - Vault Agent Sidecar Injector                                         │
│  - External Secrets Operator                                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 11. Endpoints API

### 11.1 Control-Plane API

#### Tenants
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/tenants` | GET | Liste des tenants |
| `/v1/tenants` | POST | Create a tenant |
| `/v1/tenants/{id}` | GET | Tenant details |
| `/v1/tenants/{id}` | PUT | Update |
| `/v1/tenants/{id}` | DELETE | Supprimer |

#### APIs
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/tenants/{tenant_id}/apis` | GET | List of APIs |
| `/v1/tenants/{tenant_id}/apis` | POST | Create an API |
| `/v1/tenants/{tenant_id}/apis/{api_id}` | GET | Details |
| `/v1/tenants/{tenant_id}/apis/{api_id}` | PUT | Update |
| `/v1/tenants/{tenant_id}/apis/{api_id}` | DELETE | Supprimer |

#### Subscriptions
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/subscriptions` | POST | Create subscription |
| `/v1/subscriptions/my` | GET | Mes souscriptions |
| `/v1/subscriptions/{id}` | GET | Details |
| `/v1/subscriptions/{id}` | DELETE | Annuler |
| `/v1/subscriptions/{id}/approve` | POST | Approuver |
| `/v1/subscriptions/{id}/revoke` | POST | Revoke |
| `/v1/subscriptions/{id}/rotate-key` | POST | Key rotation |
| `/v1/subscriptions/validate-key` | POST | Validate API key |
| `/v1/subscriptions/tenant/{tenant_id}/pending` | GET | Pending approvals |

#### Deployments
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/deployments` | POST | Trigger deployment |
| `/v1/deployments/{id}` | GET | Statut |
| `/v1/deployments/history` | GET | Historique |

#### MCP
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/mcp/servers` | GET | Liste serveurs MCP |
| `/v1/mcp/servers` | POST | Enregistrer serveur |
| `/v1/mcp/servers/{id}` | GET | Details |
| `/v1/mcp/servers/{id}/tools` | GET | Outils du serveur |
| `/v1/mcp/servers/{id}/subscriptions` | GET | Souscriptions |

#### Portal
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/portal/apis` | GET | Catalogue APIs (public) |
| `/v1/portal/apis/{id}` | GET | Details API |
| `/v1/portal/tools` | GET | MCP Tools disponibles |
| `/v1/portal/subscriptions` | GET | Mes souscriptions |

### 11.2 MCP Gateway

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/health` | GET | Health check |
| `/ready` | GET | Readiness |
| `/live` | GET | Liveness |
| `/metrics` | GET | Prometheus metrics |
| `/mcp/sse` | POST | SSE bidirectionnel |
| `/mcp/v1/tools` | GET | Liste outils |
| `/mcp/v1/tools/{name}` | GET | Details outil |
| `/mcp/v1/tools/{name}/invoke` | POST | Invoquer outil |
| `/api/tools` | GET | Alias REST tools |
| `/api/apis` | GET | Liste APIs |
| `/.well-known/oauth-protected-resource/mcp/sse` | GET | OAuth metadata |
| `/oauth/token` | POST | Token exchange |
| `/oauth/register` | POST | Dynamic client registration |

---

## 12. Observability

### 12.1 Stack de Monitoring

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Observability Stack                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        Logging                                   │    │
│  │  • Structured JSON (structlog)                                  │    │
│  │  • OpenSearch aggregation                                       │    │
│  │  • Log levels per environment                                   │    │
│  │  • X-Request-ID correlation                                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        Metrics                                   │    │
│  │  • Prometheus /metrics endpoint                                 │    │
│  │  • Grafana dashboards                                           │    │
│  │  • Rate limit tracking                                          │    │
│  │  • Request latency histograms                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        Tracing                                   │    │
│  │  • Pipeline traces (deploy tracking)                            │    │
│  │  • Error snapshots (forensics)                                  │    │
│  │  • Request tracing with correlation IDs                         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        Alerting                                  │    │
│  │  • Webhook notifications (Slack, Email)                         │    │
│  │  • Deployment success/failure                                   │    │
│  │  • Error threshold alerts                                       │    │
│  │  • Rate limit violations                                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 12.2 Prometheus Metrics

```
# Control-Plane API
stoa_api_requests_total{endpoint, method, status}
stoa_api_request_duration_seconds{endpoint}
stoa_subscriptions_total{tenant, status}
stoa_deployments_total{tenant, environment, status}

# MCP Gateway
mcp_tool_invocations_total{tool_name, tenant, status}
mcp_tool_latency_seconds{tool_name}
mcp_opa_evaluations_total{decision}
mcp_rate_limit_exceeded_total{tenant, user}
mcp_active_sse_connections{tenant}

# Kafka
kafka_messages_produced_total{topic}
kafka_messages_consumed_total{topic, consumer_group}
kafka_consumer_lag{topic, partition}
```

---

## 13. Security

### 13.1 Mesures de Security

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Security Measures                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Authentication:                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • JWT validation (Keycloak RS256)                               │    │
│  │ • API Key authentication (SHA-256 hashed)                       │    │
│  │ • OIDC authorization code + PKCE                                │    │
│  │ • Service account tokens (M2M)                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Authorization:                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • OPA policies (fine-grained RBAC)                              │    │
│  │ • Tenant isolation (namespace-based)                            │    │
│  │ • Role-based rate limiting                                      │    │
│  │ • Resource-level permissions                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Data Protection:                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • API key hashing (never stored plain)                          │    │
│  │ • Key rotation with grace period (CAB-314)                      │    │
│  │ • Sensitive data masking in error snapshots                     │    │
│  │ • TLS everywhere (cert-manager)                                 │    │
│  │ • Vault for secrets management                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Network Security:                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • Kubernetes Network Policies                                   │    │
│  │ • WAF (AWS WAF)                                                 │    │
│  │ • Private subnets for databases                                 │    │
│  │ • VPC peering for internal services                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Compliance & Audit:                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ • Complete audit trail via Kafka                                │    │
│  │ • Event sourcing for traceability                               │    │
│  │ • 7-day event retention                                         │    │
│  │ • GDPR-compliant data handling                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 13.2 API Key Format

```
Format: stoa_sk_{random_32_chars}
Exemple: stoa_sk_aB3cD4eF5gH6iJ7kL8mN9oP0qR1sT2uV

Storage:
- Hash: SHA-256(api_key) → stored in DB
- Prefix: stoa_sk_aB3c → stored for identification
- Plain key: shown ONCE at creation, never stored
```

---

## 14. Stack Technologique

### 14.1 Summary

| Layer | Technology | Details |
|--------|-------------|---------|
| **Frontend** | React 18 | TypeScript, TailwindCSS, React Router |
| **Backend API** | FastAPI | Python 3.11, async/await, OpenAPI |
| **MCP Gateway** | FastAPI | OPA, Kubernetes-asyncio, SSE |
| **Database** | PostgreSQL | RDS, SQLAlchemy, Alembic |
| **Cache/Streaming** | Redpanda | Kafka-compatible |
| **Auth** | Keycloak | OIDC, JWT, multi-realm |
| **Git/GitOps** | GitLab + ArgoCD | Source of truth, CD |
| **Automation** | AWX | Ansible playbooks |
| **API Gateway** | webMethods | 10.15 lean, OIDC |
| **Search** | OpenSearch | Analytics, logs |
| **Infrastructure** | EKS + Helm | Kubernetes |
| **Secrets** | Vault | Encrypted storage |
| **Monitoring** | Prometheus + Grafana | Metrics |

### 14.2 Versions

```yaml
# Runtime
python: "3.11"
node: "20.x"
react: "18.2"

# Infrastructure
kubernetes: "1.28"
helm: "3.14"
terraform: "1.7"

# Databases
postgresql: "15"
redpanda: "23.3"
opensearch: "2.11"
elasticsearch: "8.11"  # webMethods

# Tools
argocd: "2.10"
vault: "1.15"
keycloak: "23.0"
webmethods-gateway: "10.15"
```

---

## Annexe A: Configuration Environment

### Variables d'environnement principales

```bash
# Base configuration
BASE_DOMAIN=gostoa.dev

# Keycloak
KEYCLOAK_URL=https://auth.${BASE_DOMAIN}
KEYCLOAK_REALM=stoa
KEYCLOAK_CLIENT_ID=control-plane-api
KEYCLOAK_CLIENT_SECRET=${VAULT_SECRET}

# Database
DATABASE_URL=postgresql://user:pass@rds.amazonaws.com:5432/stoa

# Kafka
KAFKA_BOOTSTRAP_SERVERS=redpanda.stoa-system:9092

# GitLab
GITLAB_URL=https://gitlab.cab-i.com
GITLAB_TOKEN=${VAULT_SECRET}
GITLAB_PROJECT_ID=123

# AWX
AWX_URL=https://awx.${BASE_DOMAIN}
AWX_TOKEN=${VAULT_SECRET}

# webMethods Gateway
GATEWAY_URL=https://gateway.${BASE_DOMAIN}
GATEWAY_ADMIN_TOKEN=${VAULT_SECRET}

# MCP Gateway specific
OPA_ENABLED=true
OPA_EMBEDDED=true
METERING_ENABLED=true
K8S_WATCHER_ENABLED=true
```

---

## Annexe B: Commandes Utiles

```bash
# Development
cd control-plane-ui && npm start          # Console UI
cd portal && npm run dev                   # Developer Portal
cd control-plane-api && uvicorn src.main:app --reload  # API
cd mcp-gateway && python -m src.main      # MCP Gateway

# Testing
cd mcp-gateway && pytest --cov=src        # MCP tests (196 tests)
cd portal && npm run test                  # Portal tests

# Deployment
terraform -chdir=terraform/environments/dev plan
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system
kubectl apply -f charts/stoa-platform/crds/

# MCP Tool management
kubectl apply -f tool.yaml                 # Create tool
kubectl get tools -n tenant-acme           # List tools
kubectl describe tool payment-search -n tenant-acme

# Debugging
kubectl logs -f deployment/control-plane-api -n stoa-system
kubectl logs -f deployment/mcp-gateway -n stoa-system
kubectl exec -it deployment/control-plane-api -n stoa-system -- /bin/sh
```

---

*Document generated on January 18, 2026 - STOA Platform v2*
