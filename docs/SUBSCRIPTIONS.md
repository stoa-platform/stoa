# STOA Platform - API Subscriptions System

This document describes the API subscription system for the STOA Platform, enabling developers to subscribe to APIs and obtain API keys for access.

## Overview

The subscription system provides:
- **Developer Portal Integration**: Developers can browse APIs and subscribe
- **API Key Management**: Secure API key generation and validation
- **Approval Workflow**: Tenant admins approve/reject subscription requests
- **Lifecycle Management**: Suspend, revoke, and expire subscriptions

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Developer Portal│────>│ Control-Plane   │────>│   PostgreSQL    │
│    (React)      │     │     API         │     │   (Subscriptions)│
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 │ validate-key
                                 ▼
                        ┌─────────────────┐
                        │   API Gateway   │
                        │  (webMethods)   │
                        └─────────────────┘
```

## Subscription Workflow

### 1. Developer Subscribes (Portal)

```mermaid
sequenceDiagram
    Developer->>Portal: Browse APIs
    Developer->>Portal: Click "Subscribe"
    Portal->>API: POST /v1/subscriptions
    API->>DB: Create subscription (PENDING)
    API->>Developer: Return API Key (shown once!)
    Developer->>Developer: Save API Key securely
```

### 2. Admin Approves (Control Plane)

```mermaid
sequenceDiagram
    Admin->>Console: View pending subscriptions
    Console->>API: GET /v1/subscriptions/tenant/{id}/pending
    Admin->>Console: Click "Approve"
    Console->>API: POST /v1/subscriptions/{id}/approve
    API->>DB: Update status to ACTIVE
    Note over Developer: API Key now works!
```

## API Endpoints

### Subscriber Endpoints (Developer Portal)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/subscriptions` | Create subscription request |
| GET | `/v1/subscriptions/my` | List my subscriptions |
| GET | `/v1/subscriptions/{id}` | Get subscription details |
| DELETE | `/v1/subscriptions/{id}` | Cancel my subscription |

### Admin Endpoints (Control Plane)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/subscriptions/tenant/{tenant_id}` | List tenant subscriptions |
| GET | `/v1/subscriptions/tenant/{tenant_id}/pending` | List pending approvals |
| POST | `/v1/subscriptions/{id}/approve` | Approve subscription |
| POST | `/v1/subscriptions/{id}/revoke` | Revoke subscription |
| POST | `/v1/subscriptions/{id}/suspend` | Suspend subscription |
| POST | `/v1/subscriptions/{id}/reactivate` | Reactivate subscription |

### Gateway Endpoint (Internal)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/subscriptions/validate-key` | Validate API key |

## Subscription States

```
┌─────────┐     approve      ┌─────────┐
│ PENDING │─────────────────>│ ACTIVE  │
└─────────┘                  └────┬────┘
     │                            │
     │ cancel/revoke        suspend│reactivate
     │                            │
     ▼                       ┌────▼────┐
┌─────────┐                  │SUSPENDED│
│ REVOKED │<─────────────────┴─────────┘
└─────────┘      revoke
     │
     │ (or)
     ▼
┌─────────┐
│ EXPIRED │  (automatic on expires_at)
└─────────┘
```

## API Key Format

API keys follow a predictable format for easy identification:

```
stoa_sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
└─────┘ └──────────────────────────────┘
 prefix          32 hex characters
```

- **Prefix**: `stoa_sk_` (STOA Secret Key)
- **Random part**: 32 hex characters (128 bits of entropy)
- **Total length**: 40 characters

### Security

- API keys are **hashed with SHA-256** before storage
- Only the **prefix** (first 12 chars) is stored for display
- Full key is stored encrypted in **HashiCorp Vault** for secure retrieval
- Keys can be revealed later using the **Reveal Key** feature
- Optional **2FA/TOTP protection** for revealing stored keys

## Vault Secure Storage (MCP Gateway)

As of the Secure API Key Management feature, API keys for MCP subscriptions are:

1. **Stored encrypted in Vault** at `secret/data/subscriptions/{subscription_id}`
2. **Retrievable via reveal-key endpoint** with optional 2FA protection
3. **Shown with 30-second visibility window** for security

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Developer Portal│────>│   MCP Gateway   │────>│ HashiCorp Vault │
│    (React)      │     │   (FastAPI)     │     │ (KV v2 Secrets) │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 │ (hash only)
                                 ▼
                        ┌─────────────────┐
                        │   PostgreSQL    │
                        │ (mcp_subscriptions)│
                        └─────────────────┘
```

### Reveal Key Flow

1. User clicks "Reveal Key" in Portal
2. If TOTP required, user enters 6-digit code
3. Portal calls `POST /mcp/v1/subscriptions/{id}/reveal-key`
4. MCP Gateway validates token ACR claim (if TOTP required)
5. MCP Gateway retrieves key from Vault
6. Key shown for 30 seconds with countdown timer
7. Key auto-hides after timer expires

### Enabling 2FA Protection

Users can enable TOTP protection per subscription:

```bash
# Enable TOTP requirement
curl -X PATCH "https://mcp.stoa.cab-i.com/mcp/v1/subscriptions/{id}/totp?enabled=true" \
  -H "Authorization: Bearer $TOKEN"

# Disable TOTP requirement
curl -X PATCH "https://mcp.stoa.cab-i.com/mcp/v1/subscriptions/{id}/totp?enabled=false" \
  -H "Authorization: Bearer $TOKEN"
```

### Reveal Key Endpoint

```bash
# Reveal API key (no TOTP)
curl -X POST "https://mcp.stoa.cab-i.com/mcp/v1/subscriptions/{id}/reveal-key" \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "api_key": "stoa_sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "expires_in": 30
}
```

### Security Considerations

- Vault access uses Kubernetes authentication in-cluster
- All key retrievals are logged for audit trail
- Token must have TOTP ACR claim if subscription has TOTP enabled
- Step-up authentication via Keycloak for sensitive operations

## Database Schema

```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Subscriber info
    application_id VARCHAR(255) NOT NULL,
    application_name VARCHAR(255) NOT NULL,
    subscriber_id VARCHAR(255) NOT NULL,
    subscriber_email VARCHAR(255) NOT NULL,

    -- API info
    api_id VARCHAR(255) NOT NULL,
    api_name VARCHAR(255) NOT NULL,
    api_version VARCHAR(50) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,

    -- Plan
    plan_id VARCHAR(255),
    plan_name VARCHAR(255) DEFAULT 'default',

    -- API Key (hashed)
    api_key_hash VARCHAR(512) NOT NULL UNIQUE,
    api_key_prefix VARCHAR(10) NOT NULL,

    -- Status
    status subscription_status NOT NULL DEFAULT 'pending',
    status_reason TEXT,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMP,
    expires_at TIMESTAMP,
    revoked_at TIMESTAMP,

    -- Audit
    approved_by VARCHAR(255),
    revoked_by VARCHAR(255)
);

-- Indexes
CREATE INDEX ix_subscriptions_application_id ON subscriptions(application_id);
CREATE INDEX ix_subscriptions_subscriber_id ON subscriptions(subscriber_id);
CREATE INDEX ix_subscriptions_api_id ON subscriptions(api_id);
CREATE INDEX ix_subscriptions_tenant_id ON subscriptions(tenant_id);
CREATE INDEX ix_subscriptions_tenant_api ON subscriptions(tenant_id, api_id);
CREATE INDEX ix_subscriptions_subscriber_status ON subscriptions(subscriber_id, status);
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `DATABASE_POOL_SIZE` | `5` | Connection pool size |
| `DATABASE_MAX_OVERFLOW` | `10` | Max overflow connections |

### Example Configuration

```bash
# .env
DATABASE_URL=postgresql+asyncpg://stoa:password@postgres.stoa-system:5432/stoa
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
```

## Setup

### 1. Install Dependencies

```bash
cd control-plane-api
pip install -r requirements.txt
```

### 2. Configure Database URL

```bash
export DATABASE_URL=postgresql+asyncpg://stoa:password@localhost:5432/stoa
```

### 3. Run Migrations

```bash
cd control-plane-api
alembic upgrade head
```

### 4. Verify

```bash
# Check migration status
alembic current

# Should show: 001 (head)
```

## Usage Examples

### Create Subscription (Developer)

```bash
curl -X POST https://api.stoa.cab-i.com/v1/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "application_id": "app-123",
    "application_name": "My Weather App",
    "api_id": "weather-api",
    "api_name": "Weather API",
    "api_version": "1.0",
    "tenant_id": "acme",
    "plan_name": "Basic"
  }'
```

Response:
```json
{
  "subscription_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_key": "stoa_sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "api_key_prefix": "stoa_sk_",
  "expires_at": null
}
```

### Approve Subscription (Admin)

```bash
curl -X POST https://api.stoa.cab-i.com/v1/subscriptions/550e8400-e29b-41d4-a716-446655440000/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_at": "2026-12-31T23:59:59Z"
  }'
```

### Validate API Key (Gateway)

```bash
curl -X POST https://api.stoa.cab-i.com/v1/subscriptions/validate-key \
  -H "Content-Type: application/json" \
  -d '"stoa_sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"'
```

Response:
```json
{
  "valid": true,
  "subscription_id": "550e8400-e29b-41d4-a716-446655440000",
  "application_id": "app-123",
  "application_name": "My Weather App",
  "subscriber_id": "user-456",
  "api_id": "weather-api",
  "api_name": "Weather API",
  "tenant_id": "acme",
  "plan_id": null,
  "plan_name": "Basic"
}
```

## Integration with Gateway

The API Gateway can validate API keys by calling the `/v1/subscriptions/validate-key` endpoint:

1. **Extract API key** from `X-API-Key` header or query parameter
2. **Call validate-key endpoint** with the key
3. **Check response**:
   - `valid: true` → Allow request, set headers from response
   - `valid: false` or error → Reject with 401/403
4. **Set headers** for downstream:
   - `X-Subscription-ID`
   - `X-Application-ID`
   - `X-Tenant-ID`
   - `X-Plan-Name`

## RBAC Permissions

| Role | Permissions |
|------|-------------|
| **Developer** | Create subscription, view own subscriptions, cancel own |
| **Tenant Admin** | View tenant subscriptions, approve/revoke/suspend |
| **CPI Admin** | All tenant admin permissions across all tenants |

## Kubernetes Deployment

### Via Helm Chart

The PostgreSQL database is included in the stoa-platform Helm chart:

```bash
# Deploy with database enabled (default)
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace \
  --set database.enabled=true \
  --set database.password=your-secure-password

# Check database status
kubectl get statefulset control-plane-db -n stoa-system
kubectl get pvc -n stoa-system | grep control-plane-db
```

### Helm Values

```yaml
database:
  enabled: true
  image:
    repository: postgres
    tag: "15-alpine"
  user: stoa
  password: stoa-db-password-2026  # Override in production!
  name: stoa
  persistence:
    size: 10Gi
    storageClass: gp2
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
```

### Manual Deployment

```bash
# Deploy PostgreSQL
kubectl apply -f deploy/database/postgres-statefulset.yaml

# Wait for database
kubectl wait --for=condition=ready pod/control-plane-db-0 -n stoa-system --timeout=120s

# Run migrations
kubectl apply -f deploy/database/alembic-migration-job.yaml

# Check migration status
kubectl logs job/alembic-migration -n stoa-system
```

### Redpanda (Kafka)

```bash
# Add Redpanda Helm repo
helm repo add redpanda https://charts.redpanda.com
helm repo update

# Deploy Redpanda
helm install redpanda redpanda/redpanda \
  -n stoa-system \
  -f deploy/redpanda/values.yaml

# Verify
kubectl get pods -n stoa-system | grep redpanda
```

## Related Documentation

- [Developer Portal Plan](DEVELOPER-PORTAL-PLAN.md)
- [API Architecture](ARCHITECTURE-PRESENTATION.md)
- [SLO/SLA Documentation](SLO-SLA.md)
