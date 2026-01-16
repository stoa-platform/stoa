# MCP Gateway - Claude.ai Integration

## Overview

This document describes the integration between Claude.ai and the STOA MCP Gateway, including authentication flow, known issues, and solutions.

## Architecture

```
Claude.ai                         STOA MCP Gateway                    Keycloak
   │                                    │                                │
   │  1. POST /mcp/sse (no auth)        │                                │
   │ ─────────────────────────────────> │                                │
   │  401 Unauthorized                  │                                │
   │ <───────────────────────────────── │                                │
   │                                    │                                │
   │  2. GET /.well-known/oauth-protected-resource/mcp/sse               │
   │ ─────────────────────────────────> │                                │
   │  200 { resource, authorization_servers: [...] }                     │
   │ <───────────────────────────────── │                                │
   │                                    │                                │
   │  3. OAuth2 PKCE flow               │                                │
   │ ──────────────────────────────────────────────────────────────────> │
   │  Access Token + Refresh Token      │                                │
   │ <────────────────────────────────────────────────────────────────── │
   │                                    │                                │
   │  4. POST /mcp/sse (Bearer token)   │                                │
   │ ─────────────────────────────────> │                                │
   │  200 + Mcp-Session-Id header       │                                │
   │ <───────────────────────────────── │                                │
   │  Initialize response (SSE)         │                                │
   │ <───────────────────────────────── │                                │
   │                                    │                                │
   │  5. Subsequent requests            │                                │
   │     (Mcp-Session-Id only,          │                                │
   │      no Bearer token)              │                                │
   │ ─────────────────────────────────> │                                │
   │  200 (authenticated via session)   │                                │
   │ <───────────────────────────────── │                                │
```

## MCP Protocol Spec

- **Spec Version**: MCP Streamable HTTP Transport (2025-03-26)
- **Protocol Version**: 2025-11-25
- **Transport**: Server-Sent Events (SSE) over HTTP
- **Message Format**: JSON-RPC 2.0

## Endpoints

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/mcp/sse` | POST | Yes | MCP SSE bidirectional transport |
| `/mcp/sse` | GET | Yes | Receive server-initiated messages |
| `/mcp/sse` | DELETE | Yes | Close session |
| `/.well-known/oauth-protected-resource/mcp/sse` | GET | No | OAuth 2.0 Protected Resource Metadata (RFC 9449) |
| `/.well-known/oauth-authorization-server` | GET | No | OAuth AS metadata (proxied from Keycloak) |
| `/oauth/authorize` | GET | No | OAuth authorization proxy |
| `/oauth/token` | POST | No | Token exchange proxy |
| `/oauth/register` | POST | No | Dynamic client registration proxy |
| `/tools` | GET | No | REST endpoint for tool listing (hybrid mode) |
| `/subscriptions` | GET | No | REST endpoint for subscriptions (hybrid mode) |

## Authentication Methods

### 1. Bearer Token (Initial Request)
Claude.ai sends the OAuth2 access token on the first request:
```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 2. Session-Based (Subsequent Requests)
After successful initialization, Claude.ai uses the `Mcp-Session-Id` header:
```
Mcp-Session-Id: abc123-def456-789xyz
```

### 3. Optional Authentication (Current Solution)
The MCP Gateway uses optional authentication (`get_optional_user`) on all SSE endpoints:

```python
@router.post("/sse")
async def mcp_sse_post_endpoint(
    request: Request,
    user: TokenClaims | None = Depends(get_optional_user),
) -> Response:
    """MCP Streamable HTTP Transport endpoint.

    Uses optional authentication - if Bearer token is provided,
    user identity is captured. Otherwise, requests proceed anonymously.
    """
```

**Note**: This approach allows Claude.ai to connect without requiring Bearer tokens on every request, which matches how other MCP clients work.

## Known Issues and Solutions

### Issue 1: 401 on All MCP Requests (Fixed)

**Symptom**: Claude.ai and other MCP clients receive 401 Unauthorized on all requests.

**Root Cause**: Commit `70ac729a6` changed all endpoints from `get_optional_user` to `get_current_user`, requiring Bearer token on every request.

**Solution**: Reverted to `get_optional_user` (commit `fabc02f3e`) - optional authentication that allows anonymous access while capturing user identity when tokens are provided.

### Issue 2: Claude.ai Not Sending Bearer Token

**Symptom**: Logs show `has_bearer: false` on all requests, even initial ones.

**Root Cause**: OAuth tokens may have expired or Claude.ai cached the connection state.

**Solution**: In Claude.ai settings:
1. Go to **Settings > MCP Servers**
2. Disconnect the STOA MCP server
3. Reconnect to trigger fresh OAuth flow
4. Re-authenticate with Keycloak

### Issue 3: Protocol Version Mismatch (Fixed)

**Symptom**: `PROTOCOL_VERSION_NOT_SUPPORTED` error.

**Root Cause**: MCP Gateway was using old protocol version.

**Solution**: Updated to `protocolVersion: "2025-11-25"`.

### Issue 4: 405 Method Not Allowed (Fixed)

**Symptom**: POST requests to `/mcp/sse` returned 405.

**Root Cause**: Only GET method was configured for SSE endpoint.

**Solution**: Added POST handler for MCP SSE endpoint.

### Issue 5: Missing Return in Initialize Handler (Fixed)

**Symptom**: Initialize response not sent to client.

**Root Cause**: `_handle_initialize()` was missing `return response`.

**Solution**: Added proper return statement.

## Debugging

### Server Logs

Enable debug logging to see authentication details:

```python
# In auth middleware
logger.debug(
    "Auth check",
    has_bearer=has_bearer,
    has_api_key=has_api_key,
    session_id=session_id,
)
```

### Test Commands

```bash
# Test OAuth discovery
curl https://mcp.stoa.cab-i.com/.well-known/oauth-protected-resource/mcp/sse

# Test tools endpoint (no auth required)
curl https://mcp.stoa.cab-i.com/tools

# Test MCP initialize with Bearer token
curl -X POST https://mcp.stoa.cab-i.com/mcp/sse \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}'
```

### Kubernetes Logs

```bash
# Follow MCP Gateway logs
kubectl logs -f deployment/mcp-gateway -n stoa-system

# Check recent events
kubectl get events -n stoa-system --sort-by='.lastTimestamp'
```

## Configuration

### Keycloak Client Settings

| Setting | Value |
|---------|-------|
| Client ID | `mcp-gateway` |
| Protocol | OpenID Connect |
| Access Type | Public |
| Standard Flow Enabled | Yes |
| Direct Access Grants | No |
| Valid Redirect URIs | `https://claude.ai/*` |
| Web Origins | `https://claude.ai` |

### Environment Variables

| Variable | Description |
|----------|-------------|
| `KEYCLOAK_URL` | Keycloak base URL |
| `KEYCLOAK_REALM` | Realm name |
| `KEYCLOAK_CLIENT_ID` | OAuth client ID |
| `AUTH_REQUIRED_PATHS` | Paths requiring authentication |
| `AUTH_EXCLUDED_PATHS` | Paths excluded from auth |

## Related Files

| File | Description |
|------|-------------|
| `mcp-gateway/src/handlers/mcp_sse.py` | MCP SSE handler with session auth |
| `mcp-gateway/src/middleware/auth.py` | Authentication middleware |
| `mcp-gateway/src/main.py` | Main app with REST endpoints |
| `mcp-gateway/src/routes/oauth_discovery.py` | OAuth discovery endpoints |

## Changelog

| Date | Commit | Description |
|------|--------|-------------|
| 2026-01-16 | `fabc02f3e` | Revert MCP SSE to optional auth for Claude.ai compatibility |
| 2026-01-16 | `532b91615` | Add detailed auth logging for debugging |
| 2026-01-16 | `8950e9b6f` | Add OAuth Protected Resource Metadata endpoint (RFC 9449) |
| 2026-01-16 | `43e01a9df` | Add OAuth discovery endpoints for Claude.ai integration |
| 2026-01-15 | `7a97d73c7` | Fix MCP SSE inputSchema attribute and logger bugs |
