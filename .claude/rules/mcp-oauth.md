---
globs:
  - "stoa-gateway/src/oauth/**"
  - "stoa-gateway/src/auth/**"
---

# MCP OAuth 2.1 Flow — Critical Patterns

> Lessons from PRs #528, #532, #541 (Feb 2026). Regression tests in `src/oauth/proxy.rs`.

## Discovery Chain (RFC 9728 + RFC 8414)

The MCP OAuth discovery uses a 3-step chain:

```
Claude.ai → GET /.well-known/oauth-protected-resource (RFC 9728)
         → reads authorization_servers[0] → GET /.well-known/oauth-authorization-server (RFC 8414)
         → reads registration_endpoint → POST /oauth/register (DCR)
         → reads token_endpoint → POST /oauth/token
```

### authorization_servers MUST point to gateway (PR #532)

`authorization_servers` in `/.well-known/oauth-protected-resource` MUST point to the gateway URL (not Keycloak). Why:
- Gateway serves curated metadata with `token_endpoint_auth_methods: ["none"]` for public clients
- Keycloak's native metadata doesn't advertise `"none"` auth method — breaks Claude.ai PKCE flow
- Gateway proxies token/register endpoints (adding PKCE patch, scope stripping, etc.)

**Regression test**: `tests/contract/oauth.rs` — snapshot validates `authorization_servers` field.

## DCR Scope Stripping (PR #541)

When Claude.ai sends `scope: "openid profile email stoa:read stoa:write"` in the DCR payload:
- Keycloak REPLACES all realm default scopes with ONLY the requested ones
- Client loses `profile`, `email`, `roles` → authorization fails with `invalid_scope`
- **Fix**: Strip `scope` field before forwarding to Keycloak → all realm defaults + optionals remain available

**Code**: `src/oauth/proxy.rs:128-139`
**Regression tests**: `test_register_proxy_strips_scope_from_dcr_payload` + `test_register_proxy_preserves_payload_without_scope`

## mTLS Bypass (PR #528)

OAuth/MCP/discovery paths MUST bypass mTLS Stage 1 middleware. Without bypass:
- `MTLS_CERT_REQUIRED` (401) is returned before the OAuth challenge (`WWW-Authenticate: Bearer`)
- Claude.ai never sees the OAuth discovery — connection fails silently

**Bypass list** (`src/auth/mtls.rs:is_mtls_bypass_path`): hardcoded intentionally — a config mistake must not break the OAuth flow.

Bypassed paths:
- `/.well-known/*` (discovery)
- `/oauth/*` (token, register)
- `/mcp/sse`, `/mcp/tools/*`, `/mcp/v1/*` (MCP transport)
- `/health`, `/ready`, `/metrics` (infra)

**Regression tests**: `test_bypass_oauth_paths`, `test_bypass_mcp_paths`, `test_no_bypass_api_proxy_paths`

## Public Client PKCE Patch

After DCR registration, the gateway patches the Keycloak client to:
1. `publicClient: true` (removes client_secret requirement)
2. `pkce.code.challenge.method: S256` (enables PKCE)

This requires `KEYCLOAK_ADMIN_PASSWORD` env var. Without it, clients require client_secret (unusable by Claude.ai).

## Known Gotchas

| Issue | Symptom | Root Cause | Fix |
|-------|---------|------------|-----|
| `invalid_scope` during authorization | User sees "scope not available" error | DCR payload contains `scope` field → Keycloak replaces defaults | Strip scope (PR #541) |
| `MTLS_CERT_REQUIRED` on OAuth endpoints | Claude.ai can't discover OAuth metadata | mTLS middleware blocks before OAuth challenge | Bypass list (PR #528) |
| `token_endpoint_auth_method: none` not supported | Client registration fails with "unsupported auth method" | Keycloak metadata doesn't advertise `none` | Gateway serves curated metadata (PR #532) |
| Protocol version mismatch | Claude.ai sends MCP 2025-11-25 | Gateway must negotiate down to 2025-03-26 | Protocol negotiation in MCP handler |
| `Allowed Client Scopes` policy blocks scopes | Custom scopes (stoa:read/write/admin) rejected | Keycloak DCR policy restricts scope list | Add scopes to "Allowed Client Scopes" policy |

## CI Coverage Map

| Layer | What | Coverage |
|-------|------|----------|
| Unit tests (`src/oauth/proxy.rs`) | Token proxy, DCR proxy, scope stripping, error cases | 15 tests |
| Unit tests (`src/auth/mtls.rs`) | mTLS bypass paths | 4 tests |
| Unit tests (`src/oauth/discovery.rs`) | Discovery metadata fields, URLs | 7 tests |
| Contract tests (`tests/contract/oauth.rs`) | Snapshot: authorization_servers, metadata shape | 3 tests |
| Integration tests (`tests/integration/mcp.rs`) | OAuth discovery endpoints, metadata validation | 12 tests |
| E2E bash (`tests/e2e/test-mcp-oauth-flow.sh`) | Full flow: discovery → DCR → token (manual only) | 9 steps |
| E2E Playwright | Not covered | 0 tests |

**Gap**: E2E bash script not in CI (requires live Keycloak). Run manually after OAuth changes.
