---
sidebar_position: 1
title: API Reference
description: Control Plane API endpoints and usage.
---

# API Reference

The Control Plane API is a RESTful service built with FastAPI. All endpoints require authentication via Keycloak JWT unless noted otherwise.

**Base URL**: `https://api.gostoa.dev`

## Health

Public endpoints — no authentication required.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/ready` | Readiness check (dependencies reachable) |
| `GET` | `/health/live` | Liveness check (process alive) |
| `GET` | `/health/startup` | Startup check (initialization complete) |

```bash
curl https://api.gostoa.dev/health/ready
# {"status": "ok"}
```

## Tenants

Requires `stoa:admin` scope unless noted.

| Method | Path | Description | Scope |
|--------|------|-------------|-------|
| `GET` | `/v1/tenants` | List all tenants | `stoa:read` |
| `POST` | `/v1/tenants` | Create a tenant | `stoa:admin` |
| `GET` | `/v1/tenants/{id}` | Get tenant details | `stoa:read` |
| `PUT` | `/v1/tenants/{id}` | Update a tenant | `stoa:write` |
| `DELETE` | `/v1/tenants/{id}` | Delete a tenant | `stoa:admin` |

### Create Tenant

```bash
curl -X POST https://api.gostoa.dev/v1/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme",
    "displayName": "ACME Corp",
    "contactEmail": "admin@acme.com"
  }'
```

**Response** (201):

```json
{
  "id": "tenant-uuid",
  "name": "acme",
  "displayName": "ACME Corp",
  "contactEmail": "admin@acme.com",
  "createdAt": "2026-02-04T10:00:00Z"
}
```

## APIs

Scoped to a tenant. Requires `stoa:write` for mutations, `stoa:read` for reads.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/tenants/{tenant}/apis` | List APIs for a tenant |
| `POST` | `/v1/tenants/{tenant}/apis` | Create/publish an API |
| `GET` | `/v1/tenants/{tenant}/apis/{id}` | Get API details |
| `PUT` | `/v1/tenants/{tenant}/apis/{id}` | Update an API |
| `DELETE` | `/v1/tenants/{tenant}/apis/{id}` | Delete an API |

### Create API

```bash
curl -X POST https://api.gostoa.dev/v1/tenants/acme/apis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "petstore",
    "version": "1.0.0",
    "displayName": "Petstore API",
    "description": "Manage pets",
    "specUrl": "https://petstore3.swagger.io/api/v3/openapi.json"
  }'
```

## Portal APIs

Public-facing catalog endpoints for the Developer Portal.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/portal/apis` | List published APIs (with search) |
| `GET` | `/v1/portal/apis/{id}` | Get API details for portal |

### Search APIs

```bash
curl "https://api.gostoa.dev/v1/portal/apis?search=pet&category=demo" \
  -H "Authorization: Bearer $TOKEN"
```

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `search` | string | Full-text search across name, description |
| `category` | string | Filter by category |
| `page` | integer | Page number (default: 1) |
| `per_page` | integer | Results per page (default: 20, max: 100) |

## Subscriptions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/tenants/{tenant}/apis/{api}/subscriptions` | List subscriptions |
| `POST` | `/v1/subscriptions` | Create a subscription |
| `PATCH` | `/v1/subscriptions/{id}/approve` | Approve a subscription |
| `PATCH` | `/v1/subscriptions/{id}/reject` | Reject a subscription |
| `PATCH` | `/v1/subscriptions/{id}/suspend` | Suspend a subscription |
| `DELETE` | `/v1/subscriptions/{id}` | Revoke a subscription |

## Applications

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/applications` | List user's applications |
| `POST` | `/v1/applications` | Create an application |
| `GET` | `/v1/applications/{id}` | Get application details |
| `DELETE` | `/v1/applications/{id}` | Delete an application |

## MCP Gateway

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/mcp/tools` | List available MCP tools |
| `POST` | `/v1/mcp/tools/call` | Invoke an MCP tool |
| `GET` | `/v1/mcp/health` | MCP Gateway health check |

## Error Responses

All errors follow a consistent format:

```json
{
  "detail": "Tenant not found",
  "status_code": 404
}
```

| Status | Meaning |
|--------|---------|
| `400` | Bad request — invalid input |
| `401` | Unauthorized — missing or invalid token |
| `403` | Forbidden — insufficient permissions |
| `404` | Not found — resource doesn't exist |
| `409` | Conflict — resource already exists |
| `422` | Validation error — schema mismatch |
| `500` | Internal server error |

## Rate Limiting

API endpoints are rate-limited per client:

| Tier | Requests/min |
|------|-------------|
| Authenticated | 600 |
| Service account | 6000 |

Rate limit headers are included in responses:

```
X-RateLimit-Limit: 600
X-RateLimit-Remaining: 595
X-RateLimit-Reset: 1706954460
```

## OpenAPI Specification

The full OpenAPI spec is available at:

```
https://api.gostoa.dev/openapi.json
```

Interactive documentation (Swagger UI) is available at:

```
https://api.gostoa.dev/docs
```
