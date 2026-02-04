---
sidebar_position: 2
title: Tenants
description: Multi-tenancy model — isolation, namespaces, and RBAC.
---

# Tenants

Tenants are the primary isolation boundary in STOA. Every API, subscription, application, and user belongs to exactly one tenant.

## What is a Tenant?

A tenant represents an organization or team that manages APIs on the platform. Each tenant gets:

- **Kubernetes namespace**: `tenant-{name}` for resource isolation
- **RBAC scope**: Users can only access resources within their tenant
- **API catalog**: Separate set of APIs, visible only within the tenant or published to the portal
- **GitLab project**: Tenant-specific configuration repository

## Creating a Tenant

### Via Console UI

1. Log in as `cpi-admin`
2. Navigate to **Tenants → Create Tenant**
3. Enter tenant name, display name, and contact email
4. Assign initial tenant admin

### Via API

```bash
curl -X POST https://api.gostoa.dev/v1/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "acme",
    "displayName": "ACME Corp",
    "contactEmail": "api-team@acme.com"
  }'
```

## Isolation Model

```
┌────────────────────────────────────────────┐
│               stoa-system                  │
│  Control Plane · Portal · MCP Gateway      │
└──────────────────┬─────────────────────────┘
                   │
       ┌───────────┼───────────┐
       ▼           ▼           ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ tenant-acme│ │tenant-globex│ │ tenant-xyz │
│  APIs      │ │  APIs      │ │  APIs      │
│  Tools     │ │  Tools     │ │  Tools     │
│  CRDs      │ │  CRDs      │ │  CRDs      │
└────────────┘ └────────────┘ └────────────┘
```

### Kubernetes Isolation

- Each tenant has its own namespace (`tenant-{name}`)
- Network policies prevent cross-tenant traffic
- Resource quotas limit compute and storage per tenant
- RBAC restricts kubectl access to tenant resources

### Data Isolation

- Tenant data is scoped in PostgreSQL via tenant ID columns
- API queries are filtered by tenant at the ORM level
- GitLab repositories are per-tenant with separate access tokens

## RBAC Roles

Users are assigned roles within a tenant context:

| Role | Scope | Permissions |
|------|-------|-------------|
| `cpi-admin` | `stoa:admin` | Full platform access across all tenants |
| `tenant-admin` | `stoa:write`, `stoa:read` | Full access within own tenant |
| `devops` | `stoa:write`, `stoa:read` | Deploy and promote APIs within tenant |
| `viewer` | `stoa:read` | Read-only access within tenant |

Role assignment is managed through Keycloak groups and client scopes. See [Authentication](../guides/authentication) for configuration details.

## Tenant Configuration

Tenant-level settings are stored in GitLab and reconciled via ArgoCD:

```
tenants/
├── acme/
│   ├── tenant.yaml       # Tenant metadata
│   ├── policies/          # Default policies
│   ├── aliases/           # Gateway aliases
│   └── oidc/              # OIDC configuration
└── globex/
    ├── tenant.yaml
    ├── policies/
    ├── aliases/
    └── oidc/
```

## Quotas and Limits

Platform administrators can set per-tenant quotas:

| Quota | Description |
|-------|-------------|
| Max APIs | Maximum number of APIs a tenant can publish |
| Max subscriptions | Maximum active subscriptions |
| Max applications | Maximum registered consumer applications |
| Rate limit (global) | Default rate limit applied to all tenant APIs |
