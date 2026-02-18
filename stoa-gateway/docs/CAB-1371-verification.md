# CAB-1371: OAuth2 Scope Stripping Verification

**Issue**: #694
**Council Score**: 8.2/10 — Go
**Status**: ✅ **VERIFIED** — Feature fully implemented and tested

## Summary

The OAuth2 scope stripping feature for gateway discovery has been successfully implemented and verified. All Definition of Done criteria are met.

## Implementation Details

### 1. DCR Scope Stripping (`src/oauth/proxy.rs:128-140`)

The gateway strips the `scope` field from DCR (Dynamic Client Registration) payloads before forwarding to Keycloak:

```rust
// Strip `scope` from DCR payload before forwarding.
// When Keycloak receives `scope` in DCR, it replaces the realm default scopes
// with ONLY the requested ones — losing profile, email, roles, etc.
// By removing it, Keycloak assigns ALL realm defaults + makes optionals available.
// Claude.ai can then request any scope during the authorization step.
let mut cleaned_payload = payload;
if let Some(obj) = cleaned_payload.as_object_mut() {
    if obj.contains_key("scope") {
        debug!("Stripping 'scope' from DCR payload to preserve Keycloak realm defaults");
        obj.remove("scope");
    }
}
```

**Why this matters**: When Claude.ai sends `scope: "openid profile email stoa:read stoa:write"` in DCR, Keycloak would replace ALL realm defaults with only those scopes, causing authorization failures due to missing `roles` scope.

### 2. Discovery Metadata (`src/oauth/discovery.rs:38`)

The `/.well-known/oauth-protected-resource` endpoint correctly returns `authorization_servers` pointing to the gateway (not Keycloak):

```json
{
  "resource": "https://mcp.gostoa.dev",
  "authorization_servers": ["https://mcp.gostoa.dev"],
  "scopes_supported": ["openid", "profile", "email", "stoa:read", "stoa:write", "stoa:admin"],
  "bearer_methods_supported": ["header"]
}
```

**Why this matters**: Per RFC 9728, `authorization_servers` must point to where clients can discover OAuth metadata. Pointing to the gateway (not Keycloak) ensures clients get curated metadata with `token_endpoint_auth_methods: ["none"]` for public clients.

## Definition of Done — Verification Results

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | DCR scope field stripped before Keycloak forward | ✅ **PASS** | Code: `src/oauth/proxy.rs:129-140` |
| 2 | `test_register_proxy_strips_scope_from_dcr_payload` passes | ✅ **PASS** | Test run: 1 passed, 0 failed |
| 3 | Discovery metadata includes correct authorization_servers URL | ✅ **PASS** | Code: `src/oauth/discovery.rs:38`<br>Tests: `test_protected_resource_metadata_*` |
| 4 | CI green: security-scan.yml + component tests | ✅ **PASS** | 815 tests passed<br>clippy clean<br>cargo fmt clean |
| 5 | Regression: old client registrations still work | ✅ **PASS** | Test: `test_register_proxy_preserves_payload_without_scope` |

## Test Coverage

### Unit Tests (`src/oauth/proxy.rs`)
- ✅ `test_register_proxy_strips_scope_from_dcr_payload` — Verifies scope field is removed
- ✅ `test_register_proxy_preserves_payload_without_scope` — Verifies backward compatibility
- ✅ `test_register_proxy_dcr_success` — Full DCR + PKCE patch flow
- ✅ `test_token_proxy_success` — Token endpoint proxy
- ✅ 10 total proxy tests (all passing)

### Unit Tests (`src/oauth/discovery.rs`)
- ✅ `test_protected_resource_metadata_defaults` — Validates authorization_servers field
- ✅ `test_protected_resource_metadata_custom_urls` — Validates with production URLs
- ✅ `test_authorization_server_metadata_has_required_fields` — RFC 8414 compliance
- ✅ 7 total discovery tests (all passing)

### Contract Tests (`tests/contract/oauth.rs`)
- ✅ `test_oauth_protected_resource_shape` — Snapshot validation
- ✅ `test_oauth_authorization_server_shape` — Snapshot validation
- ✅ 3 total contract tests (all passing)

### Integration Tests (`tests/integration/mcp.rs`)
- ✅ `test_oauth_authorization_server_metadata` — End-to-end metadata
- ✅ `test_oauth_protected_resource_metadata` — End-to-end discovery
- ✅ 2 total integration tests (all passing)

## RFC Compliance

| RFC | Section | Requirement | Status |
|-----|---------|-------------|--------|
| RFC 9728 | 3.2 | `authorization_servers` array | ✅ Implemented |
| RFC 8414 | 3 | Authorization server metadata | ✅ Implemented |
| RFC 7591 | 3.2.1 | DCR request handling | ✅ Enhanced (scope stripping) |
| RFC 7636 | 4.2 | PKCE S256 support | ✅ Patched post-DCR |

## Historical Context

This feature was implemented across three PRs:
- **PR #528** (Feb 2026): mTLS bypass for OAuth endpoints
- **PR #532** (Feb 2026): Discovery metadata with gateway-hosted authorization_servers
- **PR #541** (Feb 2026): DCR scope stripping to fix Claude.ai PKCE flow

Documentation: `.claude/rules/mcp-oauth.md`

## Gotchas Fixed

| Issue | Symptom | Root Cause | Fix |
|-------|---------|------------|-----|
| `invalid_scope` during authorization | User sees "scope not available" error | DCR payload contains `scope` field → Keycloak replaces defaults | Strip scope (PR #541) — **THIS PR** |
| `token_endpoint_auth_method: none` not supported | Client registration fails with "unsupported auth method" | Keycloak metadata doesn't advertise `none` | Gateway serves curated metadata (PR #532) |
| `MTLS_CERT_REQUIRED` on OAuth endpoints | Claude.ai can't discover OAuth metadata | mTLS middleware blocks before OAuth challenge | Bypass list (PR #528) |

## Conclusion

✅ **All DoD criteria verified**
✅ **Feature fully functional**
✅ **Test coverage comprehensive (22 tests)**
✅ **RFC compliant**
✅ **Production ready**

This verification confirms that CAB-1371 is complete and closes issue #694.
