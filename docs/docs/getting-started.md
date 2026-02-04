---
title: Getting Started
description: From zero to a running STOA platform with MCP tools, multi-tenancy, and observability.
ticket: CAB-611
---

# Getting Started with STOA Platform

This guide takes you from zero to a fully running STOA Platform with AI-native API access.
By the end, you will have:

- A local STOA stack running via Docker Compose
- Your first MCP Tool registered and invocable by AI agents
- Multi-tenant isolation configured with RBAC
- Grafana dashboards showing live metrics and logs

**Prerequisites**: Docker Desktop (4.x+), `curl`, and 8 GB of available RAM.

---

## Part 1 — Installation via Docker Compose

### 1.1 Clone the Repository

```bash
git clone https://github.com/stoa-platform/stoa.git
cd stoa
```

### 1.2 Configure Environment

```bash
cd deploy/docker-compose
cp .env .env.local   # optional: customize ports if needed
```

Default configuration (no changes required):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `stoa` | Database user |
| `POSTGRES_PASSWORD` | `stoa-quickstart-2045` | Database password |
| `KEYCLOAK_ADMIN` | `admin` | Keycloak admin user |
| `KEYCLOAK_ADMIN_PASSWORD` | `admin` | Keycloak admin password |
| `PORT_KEYCLOAK` | `8280` | Keycloak external port |
| `PORT_API` | `8000` | Control Plane API port |
| `PORT_CONSOLE` | `3000` | Console UI port |
| `PORT_GRAFANA` | `3002` | Grafana port |
| `PORT_PROMETHEUS` | `9090` | Prometheus port |

### 1.3 Start the Stack

```bash
docker compose up -d
```

This launches 9 services (~1.5 GB RAM):

| Service | Container | Purpose |
|---------|-----------|---------|
| **PostgreSQL** | `stoa-postgres` | Database |
| **Keycloak** | `stoa-keycloak` | OIDC authentication |
| **db-migrate** | `stoa-db-migrate` | One-shot Alembic migration |
| **Control Plane API** | `stoa-api` | FastAPI backend |
| **Console UI** | `stoa-console` | React admin interface |
| **Prometheus** | `stoa-prometheus` | Metrics collection |
| **Grafana** | `stoa-grafana` | Dashboards |
| **Loki** | `stoa-loki` | Log aggregation |
| **Promtail** | `stoa-promtail` | Log shipping |

### 1.4 Verify All Services Are Healthy

```bash
docker compose ps
```

Wait until all services show `healthy` or `running` (Keycloak can take up to 60s on first start):

```bash
# Quick health check
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected output:

```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### 1.5 Access the Platform

| Service | URL | Credentials |
|---------|-----|-------------|
| **Console UI** | http://localhost:3000 | `halliday` / `readyplayerone` |
| **Keycloak Admin** | http://localhost:8280 | `admin` / `admin` |
| **API Docs (Swagger)** | http://localhost:8000/docs | Bearer token |
| **Grafana** | http://localhost:3002 | `admin` / `admin` |
| **Prometheus** | http://localhost:9090 | — |

### 1.6 Demo Users (OASIS Theme)

The Keycloak realm ships with pre-configured users across 3 tenants:

| User | Password | Role | Tenant |
|------|----------|------|--------|
| `halliday` | `readyplayerone` | cpi-admin | gregarious-games |
| `morrow` | `ogdensmcguffin` | cpi-admin | gregarious-games |
| `parzival` | `copperkeystart` | tenant-admin | oasis-gunters |
| `art3mis` | `samantha2045` | devops | oasis-gunters |
| `aech` | `helen2045` | viewer | oasis-gunters |
| `sorrento` | `ioi101` | tenant-admin | ioi-sixers |
| `sixer42` | `loyalty2045` | viewer | ioi-sixers |

Log in to the Console at http://localhost:3000 with `halliday` / `readyplayerone` to explore the platform as a CPI Admin.

---

## Part 2 — Your First MCP Tool

The MCP (Model Context Protocol) Gateway lets AI agents discover and invoke your APIs as tools. In this section you will register a tool and call it.

### 2.1 Get an Access Token

```bash
# Authenticate as halliday (cpi-admin)
TOKEN=$(curl -s -X POST \
  "http://localhost:8280/realms/stoa/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "client_id=control-plane-ui" \
  -d "username=halliday" \
  -d "password=readyplayerone" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token acquired: ${TOKEN:0:20}..."
```

### 2.2 Understand the Tool CRD

Tools are defined as Kubernetes Custom Resources following the `gostoa.dev/v1alpha1` API:

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: crm-search              # unique name within namespace
  namespace: team-alpha          # tenant isolation boundary
  labels:
    gostoa.dev/tenant: team-alpha
    gostoa.dev/category: sales
spec:
  displayName: "CRM Search"
  description: "Search customers in CRM database"
  version: "1.0.0"
  tags: [crm, customers, search]

  endpoint: "https://httpbin.org/post"   # backend API URL
  method: POST

  inputSchema:                           # JSON Schema for parameters
    type: object
    properties:
      query:
        type: string
        description: "Search query (name, email, or company)"
      limit:
        type: integer
        description: "Max results to return"
        default: 10
    required:
      - query

  authentication:
    type: none            # none | bearer | api-key | oauth2

  timeout: "30s"
  rateLimit:
    requestsPerMinute: 60
    burst: 10

  enabled: true
```

### 2.3 Deploy Demo Tools

The repository includes 4 demo tools across 2 tenants:

| Tool | Tenant | Category |
|------|--------|----------|
| `crm-search` | team-alpha | Sales |
| `billing-invoice` | team-alpha | Finance |
| `inventory-lookup` | team-beta | Operations |
| `notifications-send` | team-beta | Communications |

Deploy them with Kustomize (requires a Kubernetes cluster):

```bash
kubectl apply -k deploy/demo-tools/
```

Or individually:

```bash
kubectl apply -f deploy/demo-tools/crm-search.yaml
```

### 2.4 List Available Tools

Once tools are registered, AI agents (or any MCP client) can discover them:

```bash
# List all tools accessible to the current user
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/mcp/v1/tools | python3 -m json.tool
```

Filter by category or tags:

```bash
# By category
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/mcp/v1/tools?category=sales"

# By tag
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/mcp/v1/tools?tags=crm"

# Search by keyword
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/mcp/v1/tools?search=customer"
```

### 2.5 Invoke a Tool

Call a tool by name using the `invoke` endpoint:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "arguments": {
      "query": "ACME",
      "limit": 5
    }
  }' \
  http://localhost:8001/mcp/v1/tools/team_alpha_crm_search/invoke \
  | python3 -m json.tool
```

> **Naming convention**: Tool names in the MCP API use the pattern `{namespace}_{tool_name}` with dashes replaced by underscores. Example: namespace `team-alpha` + tool `crm-search` = `team_alpha_crm_search`.

### 2.6 MCP Protocol Flow (SSE)

In production, AI agents connect via SSE (Server-Sent Events) for real-time tool discovery:

```
┌─────────────┐     SSE      ┌──────────────────┐     HTTP    ┌──────────┐
│  AI Agent   │◄────────────►│   MCP Gateway     │────────────►│ Backend  │
│  (Claude,   │              │                   │             │  API     │
│   GPT, ...) │              │  ┌─────────────┐  │             └──────────┘
└─────────────┘              │  │ Tool Registry│  │
                             │  │ OPA Engine   │  │
                             │  │ Metering     │  │
                             │  └─────────────┘  │
                             └──────────────────┘
```

**MCP API endpoints summary:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/mcp/v1/tools` | List tools (filtered by tenant) |
| `GET` | `/mcp/v1/tools/{name}` | Get tool details |
| `POST` | `/mcp/v1/tools/{name}/invoke` | Invoke a tool |
| `GET` | `/mcp/v1/tools/categories` | List categories |
| `GET` | `/mcp/v1/tools/tags` | List tags |

---

## Part 3 — Multi-Tenant Basics

STOA is designed for multi-tenancy from the ground up. Each tenant gets isolated resources, RBAC, and namespace-level tool separation.

### 3.1 What Is a Tenant?

A tenant represents an organization or team using the platform. Each tenant has:

- **Isolated namespace** in Kubernetes (tools, policies)
- **Dedicated RBAC roles** (tenant-admin, devops, viewer)
- **Separate API catalog** visible only to tenant members
- **Independent metering and quotas**

### 3.2 Create a Tenant via API

```bash
# Create a new tenant (requires cpi-admin role)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme-corp",
    "display_name": "ACME Corporation",
    "description": "Demo tenant for Getting Started guide",
    "owner_email": "admin@acme-corp.com"
  }' \
  http://localhost:8000/v1/tenants | python3 -m json.tool
```

Or use the Console UI: **Tenants** > **Create Tenant**.

### 3.3 RBAC Roles

STOA uses four roles, enforced via Keycloak scopes and OPA policies:

| Role | Scope | Permissions |
|------|-------|-------------|
| **cpi-admin** | `stoa:admin` | Full platform access: create tenants, manage all APIs and users |
| **tenant-admin** | `stoa:write`, `stoa:read` | Manage APIs, apps, and users within own tenant |
| **devops** | `stoa:write`, `stoa:read` | Deploy and promote APIs, create apps |
| **viewer** | `stoa:read` | Read-only access to own tenant |

**Permission matrix:**

| Action | cpi-admin | tenant-admin | devops | viewer |
|--------|-----------|--------------|--------|--------|
| Create tenants | Yes | — | — | — |
| Create APIs | Yes | Yes | Yes | — |
| Deploy/Promote APIs | Yes | Yes | Yes | — |
| Manage users | Yes | Yes | — | — |
| View APIs & Apps | Yes | Yes | Yes | Yes |
| Approve subscriptions | Yes | Yes | — | — |

### 3.4 Namespace Isolation for Tools

MCP tools are isolated by Kubernetes namespace, one namespace per tenant:

```bash
# team-alpha tools (Sales, Finance)
kubectl get tools -n team-alpha
# NAME              DISPLAY NAME       ENABLED
# crm-search        CRM Search         true
# billing-invoice   Billing Invoice    true

# team-beta tools (Operations, Communications)
kubectl get tools -n team-beta
# NAME                 DISPLAY NAME          ENABLED
# inventory-lookup     Inventory Lookup      true
# notifications-send   Send Notification     true
```

A user from `team-alpha` **cannot** access tools in the `team-beta` namespace. The MCP Gateway enforces this via the user's JWT `tenant` claim and OPA policies:

```rego
package stoa.mcp

default allow = false

# Allow tool access only within the user's tenant namespace
allow {
    input.tenant == input.tool_namespace
}

# Platform admins can access all namespaces
allow {
    input.scope == "stoa:admin"
}
```

### 3.5 Keycloak Integration

STOA uses a dedicated Keycloak realm (`stoa`) with 4 OIDC clients:

| Client | Type | Purpose |
|--------|------|---------|
| `control-plane-api` | Confidential | Backend API authentication |
| `control-plane-ui` | Public | Console UI login |
| `stoa-portal` | Public | Developer Portal login |
| `stoa-mcp-gateway` | Confidential | MCP Gateway service auth |

Users carry their role and tenant in JWT claims:

```json
{
  "sub": "user-uuid",
  "preferred_username": "parzival",
  "email": "parzival@oasis.gg",
  "realm_access": {
    "roles": ["tenant-admin"]
  },
  "attributes": {
    "tenant": "oasis-gunters"
  }
}
```

---

## Part 4 — Observability with Grafana

The Docker Compose stack includes a full observability pipeline: Prometheus (metrics), Loki (logs), and Grafana (dashboards).

### 4.1 Access Grafana

Open http://localhost:3002 and log in with `admin` / `admin`.

The **STOA Platform Overview** dashboard loads automatically as the home dashboard.

### 4.2 Pre-Built Dashboards

Two dashboards are provisioned automatically:

| Dashboard | Description |
|-----------|-------------|
| **STOA Platform Overview** | Request rates, latency percentiles, error rates, service health |
| **STOA Logs** | Log analysis with filters by service, level, and container |

### 4.3 Generate Sample Metrics

Use the seed script to create demo data and generate API traffic that populates Grafana:

```bash
pip install httpx   # one-time dependency

CONTROL_PLANE_URL=http://localhost:8000 \
KEYCLOAK_URL=http://localhost:8280 \
ANORAK_PASSWORD=readyplayerone \
python scripts/seed-demo-data.py
```

This creates:

- 3 APIs: Petstore, Account Management, Payments
- 2 Applications: 1 active subscription, 1 pending approval
- API traffic across multiple endpoints to populate metrics

### 4.4 Explore Metrics in Prometheus

Open http://localhost:9090 and run sample queries:

```promql
# API request rate (5 min window)
sum(rate(http_requests_total[5m])) by (method, endpoint)

# Request latency (p95)
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m]))
  / sum(rate(http_requests_total[5m]))
```

### 4.5 Query Logs in Grafana

Switch to the **STOA Logs** dashboard, or open **Explore** > select **Loki** datasource:

```logql
# All API logs
{job="stoa-api"}

# Error logs only
{job="stoa-api"} |= "level=error"

# Filter by endpoint
{job="stoa-api"} |= "/v1/tenants"

# JSON parsing for structured logs
{container="stoa-api"} | json | level="ERROR"
```

### 4.6 Observability Architecture

```
┌──────────────┐     ┌────────────┐     ┌──────────┐
│ Control      │────►│ Prometheus │────►│ Grafana  │
│ Plane API    │     │ :9090      │     │ :3002    │
│ :8000        │     └────────────┘     │          │
│              │                        │          │
│  /metrics    │     ┌────────────┐     │          │
└──────────────┘     │   Loki     │────►│          │
                     │   :3100    │     └──────────┘
┌──────────────┐     └────────────┘
│  Promtail    │────►      ▲
│ (log shipper)│           │
└──────────────┘     Docker containers
```

Prometheus scrapes `/metrics` from the Control Plane API every 15s. Promtail collects Docker container logs and ships them to Loki. Grafana queries both datasources.

---

## Next Steps

You now have a running STOA platform with MCP tools, multi-tenant RBAC, and observability.

| Topic | Resource |
|-------|----------|
| **Deploy to Kubernetes** | `docs/installation.md` |
| **Full architecture** | `docs/ARCHITECTURE-COMPLETE.md` |
| **GitOps with ArgoCD** | `docs/GITOPS-SETUP.md` |
| **Deep observability** | `docs/OBSERVABILITY.md` |
| **MCP subscriptions** | `docs/MCP-SUBSCRIPTIONS.md` |
| **Security hardening** | `docs/security.md` |

### Cleanup

```bash
# Stop and remove all containers
cd deploy/docker-compose
docker compose down

# Also remove persistent volumes (full reset)
docker compose down -v
```
