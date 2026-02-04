---
sidebar_position: 2
title: Console
description: Admin workflow — manage tenants, APIs, users, and gateways.
---

# Console

The Console is the API provider's administration interface. Platform admins and tenant managers use it to control the entire API lifecycle.

**URL**: [console.gostoa.dev](https://console.gostoa.dev)

## Getting Started

1. Navigate to the Console URL
2. Sign in via Keycloak (OIDC client: `control-plane-ui`)
3. The dashboard shows an overview of your tenants and APIs

## Dashboard

The Console dashboard provides:

- **Tenant summary**: Number of tenants, active APIs, subscriptions
- **Recent activity**: Latest API publications, subscription requests
- **Health status**: Platform component health checks

## Tenant Management

### Creating a Tenant

1. Navigate to **Tenants → Create Tenant**
2. Enter:
   - **Name**: Unique identifier (lowercase, hyphens allowed)
   - **Display Name**: Human-readable label
   - **Contact Email**: Tenant admin email
3. Click **Create**

This provisions:
- Kubernetes namespace `tenant-{name}`
- GitLab repository for tenant config
- Keycloak group for tenant RBAC

### Tenant Settings

- **Members**: Add/remove users, assign roles
- **Quotas**: Set API and subscription limits
- **Policies**: Default policies applied to all tenant APIs

### Tenant Selector

If you have access to multiple tenants, use the **tenant selector** in the top navigation to switch context. Only resources belonging to the selected tenant are displayed.

## API Management

### Publishing an API

1. Navigate to **APIs → Create API**
2. Fill in:
   - **Name** and **Version**
   - **Description**
   - **OpenAPI Specification** (upload or URL)
3. Configure policies
4. Click **Publish**

The API will appear in the Developer Portal and be synced to the gateway.

### API Lifecycle Actions

| Action | Effect |
|--------|--------|
| **Publish** | Make API live and discoverable |
| **Deprecate** | Mark as deprecated (still functional) |
| **Retire** | Deactivate API, stop traffic |
| **Delete** | Remove API and all subscriptions |

### Monitoring APIs

View per-API metrics:

- Request count and error rate
- Latency percentiles (p50, p95, p99)
- Active subscriptions and consumers
- Gateway sync status

## Subscription Management

### Reviewing Requests

1. Navigate to **Subscriptions → Pending**
2. Review the consumer's application details
3. Click **Approve** or **Reject**

### Managing Active Subscriptions

- **Suspend**: Temporarily disable access
- **Revoke**: Permanently terminate the subscription
- **View usage**: Request count and rate limit utilization

## User Management

Managed through Keycloak integration:

| Role | What They Can Do |
|------|------------------|
| `cpi-admin` | Everything — all tenants, all operations |
| `tenant-admin` | Full access within their tenant |
| `devops` | Deploy and promote APIs |
| `viewer` | Read-only access |

### Adding a User

1. Navigate to **Users → Invite**
2. Enter email address
3. Select tenant and role
4. The user receives an invitation via Keycloak

## Gateway Adapters

The Console shows the sync status between STOA and the target API gateways:

| Status | Meaning |
|--------|---------|
| **Synced** | API is live on the gateway |
| **Pending** | Sync in progress |
| **Error** | Sync failed — check logs |
| **Drift** | Gateway state differs from desired state |

The Gateway Adapter reconciliation can be triggered manually from the Console or automatically via ArgoCD.
