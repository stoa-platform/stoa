# MCP Server Subscriptions

This document describes the MCP Server Subscription system, which allows developers to subscribe to MCP servers, receive API keys, and consume tools via the MCP Gateway.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│  Developer      │     │  WebMethods Gateway │     │  Control-Plane   │
│  Portal (React) │────>│  (OIDC Forwarding)  │────>│  API (FastAPI)   │
└─────────────────┘     └─────────────────────┘     └────────┬─────────┘
                                                              │
                                                              │ Persist
                                                              ▼
                                                    ┌──────────────────┐
┌─────────────────┐     ┌─────────────────────┐     │   PostgreSQL     │
│  AI Agent       │────>│  MCP Gateway        │────>│   (Shared DB)    │
│  (Claude/etc)   │     │  (API Key Auth)     │     └──────────────────┘
└─────────────────┘     └─────────────────────┘
        │                         │
        │ stoa_mcp_xxx           │ Validate API Key
        └─────────────────────────┘
```

## Database Schema

### Tables

#### `mcp_servers`
Registry of available MCP servers.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| name | VARCHAR(255) | Unique server name |
| display_name | VARCHAR(255) | Human-readable name |
| description | TEXT | Server description |
| icon | VARCHAR(500) | Icon identifier |
| category | ENUM | 'platform', 'tenant', 'public' |
| tenant_id | VARCHAR(255) | Tenant owner (for tenant servers) |
| visibility | JSON | Role-based visibility config |
| requires_approval | BOOLEAN | Whether subscriptions need approval |
| auto_approve_roles | JSON | Roles that bypass approval |
| status | ENUM | 'active', 'maintenance', 'deprecated' |
| version | VARCHAR(50) | Server version |
| documentation_url | VARCHAR(500) | Link to docs |

#### `mcp_server_tools`
Tools within each server.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| server_id | UUID | FK to mcp_servers |
| name | VARCHAR(255) | Tool name |
| display_name | VARCHAR(255) | Human-readable name |
| description | TEXT | Tool description |
| input_schema | JSON | JSON Schema for inputs |
| enabled | BOOLEAN | Whether tool is available |
| requires_approval | BOOLEAN | Tool-level approval |

#### `mcp_server_subscriptions`
User subscriptions to servers.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| server_id | UUID | FK to mcp_servers |
| subscriber_id | VARCHAR(255) | Keycloak user ID |
| subscriber_email | VARCHAR(255) | User email |
| tenant_id | VARCHAR(255) | User's tenant |
| plan | VARCHAR(100) | Subscription plan |
| api_key_hash | VARCHAR(512) | SHA-256 hash of API key |
| api_key_prefix | VARCHAR(16) | First 12 chars for display |
| vault_path | VARCHAR(500) | Vault path for key storage |
| status | ENUM | 'pending', 'active', 'suspended', 'revoked', 'expired' |
| previous_api_key_hash | VARCHAR(512) | Old key during rotation |
| previous_key_expires_at | DATETIME | Grace period expiry |

#### `mcp_tool_access`
Per-tool access control within subscriptions.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| subscription_id | UUID | FK to subscriptions |
| tool_id | UUID | Tool being accessed |
| tool_name | VARCHAR(255) | Tool name for reference |
| status | ENUM | 'enabled', 'disabled', 'pending_approval' |
| usage_count | INTEGER | Invocation counter |

## API Endpoints

### User Endpoints (Portal)

#### List Servers
```
GET /v1/mcp/servers
Authorization: Bearer {keycloak_token}

Response:
{
  "servers": [...],
  "total_count": 10
}
```

#### Get Server Details
```
GET /v1/mcp/servers/{server_id}
Authorization: Bearer {keycloak_token}
```

#### List My Subscriptions
```
GET /v1/mcp/subscriptions
Authorization: Bearer {keycloak_token}

Response:
{
  "items": [...],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

#### Create Subscription
```
POST /v1/mcp/subscriptions
Authorization: Bearer {keycloak_token}
Content-Type: application/json

{
  "server_id": "uuid",
  "plan": "free",
  "requested_tools": []
}

Response (201):
{
  "id": "uuid",
  "server_id": "uuid",
  "api_key": "stoa_mcp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "api_key_prefix": "stoa_mcp_xxx",
  "status": "active",
  ...
}
```

#### Cancel Subscription
```
DELETE /v1/mcp/subscriptions/{subscription_id}
Authorization: Bearer {keycloak_token}
```

#### Rotate API Key
```
POST /v1/mcp/subscriptions/{subscription_id}/rotate-key
Authorization: Bearer {keycloak_token}
Content-Type: application/json

{
  "grace_period_hours": 24
}

Response:
{
  "new_api_key": "stoa_mcp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "old_key_expires_at": "2026-01-15T12:00:00Z"
}
```

### Admin Endpoints

#### List Pending Approvals
```
GET /v1/admin/mcp/subscriptions/pending
Authorization: Bearer {admin_token}
```

#### Approve Subscription
```
POST /v1/admin/mcp/subscriptions/{id}/approve
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "expires_at": "2026-12-31T23:59:59Z",
  "approved_tools": ["uuid1", "uuid2"]
}
```

#### Revoke Subscription
```
POST /v1/admin/mcp/subscriptions/{id}/revoke
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "reason": "Violation of terms"
}
```

#### Create Server
```
POST /v1/admin/mcp/servers
Authorization: Bearer {admin_token}
Content-Type: application/json

{
  "name": "my-server",
  "display_name": "My Server",
  "description": "Server description",
  "category": "public",
  "visibility": {"public": true},
  "requires_approval": false
}
```

### MCP Gateway Validation Endpoint

Used internally by MCP Gateway to validate API keys:

```
POST /v1/mcp/validate/api-key
Content-Type: application/json

{
  "api_key": "stoa_mcp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}

Response:
{
  "valid": true,
  "subscription_id": "uuid",
  "server_id": "uuid",
  "subscriber_id": "user-id",
  "tenant_id": "tenant",
  "plan": "free",
  "enabled_tools": ["tool1", "tool2"],
  "using_previous_key": false
}
```

## Authentication Flow

### Portal (User Token)

1. User logs into Portal via Keycloak
2. Portal receives JWT access token
3. Portal calls Control-Plane API via WebMethods Gateway
4. WebMethods forwards the OIDC token
5. Control-Plane API validates token with Keycloak
6. User gets subscription with API key

### MCP Gateway (API Key)

1. AI Agent sends request with `X-API-Key: stoa_mcp_xxx`
2. MCP Gateway validates API key against PostgreSQL
3. MCP Gateway retrieves enabled tools for subscription
4. MCP Gateway processes tool invocation
5. Usage is tracked and metered

## Key Rotation

API keys can be rotated with a grace period:

1. User requests key rotation with grace period (1-168 hours)
2. New key is generated and returned
3. Both old and new keys work during grace period
4. After grace period, old key is invalidated
5. User should update their applications during grace period

## Approval Workflow

For servers with `requires_approval = true`:

1. User creates subscription -> status = PENDING
2. Admin sees pending subscription in approval queue
3. Admin approves with optional expiration date
4. API key is generated and subscription is ACTIVE
5. User can now use the API key

For servers with `auto_approve_roles`:
- Users with matching roles bypass approval
- Subscription is immediately ACTIVE with API key

## Database Migrations

Run migrations with Alembic:

```bash
cd control-plane-api
alembic upgrade head
```

Migration `004_create_mcp_subscription_tables.py` creates:
- `mcp_servers` table
- `mcp_server_tools` table
- `mcp_server_subscriptions` table
- `mcp_tool_access` table
- All required enums and indexes

## Configuration

### Control-Plane API

```bash
# Database (shared with other tables)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/stoa
```

### MCP Gateway

```bash
# Database (same as Control-Plane API)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/stoa
# Or individual components:
DB_HOST=control-plane-db.stoa-system.svc.cluster.local
DB_PORT=5432
DB_NAME=stoa
DB_USER=stoa
DB_PASSWORD=xxx
```

### Portal

```bash
# Control-Plane API via WebMethods
VITE_API_URL=https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0
```

## Security Considerations

1. **API Keys**: Stored as SHA-256 hash in PostgreSQL, never in plain text
2. **Vault Integration**: Full keys can be stored in Vault (optional)
3. **Key Rotation**: Grace period prevents service disruption
4. **Role-Based Access**: Servers can be restricted by Keycloak roles
5. **Tenant Isolation**: Subscriptions are scoped to tenant
6. **Usage Tracking**: All invocations are counted and timestamped

## Future Enhancements

- **mTLS**: Certificate-bound tokens (RFC 8705) for M2M
- **Vault PKI**: Client certificate issuance via Vault
- **Rate Limiting**: Per-subscription rate limits
- **Billing Integration**: Usage-based billing
