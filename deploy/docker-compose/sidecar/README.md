# STOA Gateway — Sidecar Mode Demo

Demonstrates the STOA Gateway running as a **sidecar** alongside an existing API gateway (NGINX), providing policy enforcement via the `ext_authz` pattern.

## Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │              Docker Network                 │
  Client                  │                                             │
    │                     │  ┌────────────┐       ┌─────────────────┐  │
    │  GET /api/customers │  │            │ POST  │  stoa-gateway   │  │
    ├─────────────────────▸  │  nginx     │──────▸│  :8081          │  │
    │                     │  │  proxy     │ /authz│                 │  │
    │                     │  │  :8080     │◂──────│  Mode: sidecar  │  │
    │                     │  │            │200/401│  DecisionFormat:│  │
    │                     │  │            │       │    StatusCode   │  │
    │                     │  │            │       └─────────────────┘  │
    │                     │  │            │                            │
    │                     │  │            │       ┌─────────────────┐  │
    │                     │  │   if 200   │       │ fake-webmethods │  │
    │  ◂──── response ────│  │   ───────▸ │──────▸│  :8080          │  │
    │                     │  │ proxy_pass │       │                 │  │
    │                     │  └────────────┘       │  Mock backend   │  │
                          │                       └─────────────────┘  │
                          └─────────────────────────────────────────────┘
```

### Flow

1. **Client** sends `GET /api/customers` with `Authorization: Bearer <token>`
2. **nginx-proxy** intercepts and issues an `auth_request` subrequest to `/_authz`
3. `/_authz` constructs a JSON body from request metadata and POSTs to **stoa-gateway** `/authz`
4. **stoa-gateway** evaluates the authorization request:
   - No user info → `401 Unauthorized`
   - No tenant ID → `403 Forbidden`
   - User + tenant present → `200 OK` (allowed)
5. nginx acts on the response:
   - `200` → proxy the request to **fake-webmethods** backend
   - `401/403` → return error to client

## Quick Start

```bash
cd deploy/docker-compose

# Run the full demo (start, test, cleanup)
./sidecar/demo.sh

# Or start manually
docker compose -f docker-compose.sidecar.yml up -d --build

# Test without token (expect 401)
curl -i http://localhost:8080/api/customers

# Test with token (expect 200)
curl -i -H "Authorization: Bearer my-token" http://localhost:8080/api/customers

# Direct authz call
curl -X POST http://localhost:8081/authz \
  -H "Content-Type: application/json" \
  -d '{
    "method": "GET",
    "path": "/api/customers",
    "headers": {},
    "tenant_id": "demo-tenant",
    "user": {"id": "user-1", "roles": ["admin"], "scopes": ["read"]}
  }'

# Gateway metrics
curl http://localhost:8081/metrics

# Stop
docker compose -f docker-compose.sidecar.yml down
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| nginx-proxy | 8080 | Entry point, auth_request to gateway |
| stoa-gateway | 8081 | Sidecar policy enforcement (POST /authz) |
| fake-webmethods | internal | Mock backend (customers, orders APIs) |

## Endpoints

### Through nginx-proxy (:8080)

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| GET | `/api/customers` | Yes | List customers |
| GET | `/api/orders` | Yes | List orders |
| POST | `/api/orders` | Yes | Create order |
| GET | `/health` | No | Proxy health |
| GET | `/gateway/health` | No | Gateway health (proxied) |
| GET | `/gateway/metrics` | No | Gateway metrics (proxied) |

### Direct to stoa-gateway (:8081)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/authz` | Authorization decision endpoint |
| GET | `/health` | Gateway health |
| GET | `/metrics` | Prometheus metrics |

## AuthzRequest / AuthzResponse

The `/authz` endpoint accepts:

```json
{
  "method": "GET",
  "path": "/api/customers",
  "headers": {"Authorization": "Bearer ..."},
  "tenant_id": "demo-tenant",
  "user": {
    "id": "user-123",
    "email": "user@example.com",
    "roles": ["admin"],
    "scopes": ["read", "write"]
  }
}
```

Responses:
- **200 OK** — request allowed (with `StatusCode` decision format)
- **401 Unauthorized** — missing user information
- **403 Forbidden** — missing tenant ID or policy violation
- **429 Too Many Requests** — rate limit exceeded

## Environment Variables

Copy `sidecar/.env.example` to `.env` to customize ports:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT_PROXY` | 8080 | nginx-proxy listen port |
| `PORT_GATEWAY` | 8081 | stoa-gateway listen port |

## Keep Services Running

To keep services running after the demo script finishes:

```bash
KEEP_RUNNING=true ./sidecar/demo.sh
```

## Production Considerations

This demo uses simplified authentication simulation. In production:

- The **upstream gateway** (Kong, Envoy, Apigee) validates JWTs and extracts claims
- User info and tenant ID are passed to STOA via headers configured in `SidecarSettings`
- The `DecisionFormat` can be set to `EnvoyExtAuthz` or `KongPlugin` for native integration
- OPA policies provide fine-grained access control
- Kafka metering captures all authorization decisions
