# mTLS & DPoP — Unit Test Evidence (CAB-1971)

> These security features require TLS certificates and cannot be tested via HTTP in docker-compose.
> Evidence is provided via Rust unit/integration test coverage.

## mTLS (RFC 8705) — 4 tests

**File**: `stoa-gateway/src/auth/mtls.rs`

| Test | What it proves |
|------|----------------|
| `test_bypass_oauth_paths` | OAuth/discovery paths bypass mTLS (no cert required) |
| `test_bypass_mcp_paths` | MCP transport paths bypass mTLS |
| `test_no_bypass_api_proxy_paths` | API proxy paths require mTLS |
| `test_mtls_cert_fingerprint` | Certificate fingerprint extraction works |

## DPoP (RFC 9449) — 6 tests

**File**: `stoa-gateway/src/auth/dpop.rs`

| Test | What it proves |
|------|----------------|
| `test_dpop_proof_validation` | DPoP proof JWT is validated correctly |
| `test_dpop_bound_access_token` | Access token is bound to DPoP key |
| `test_dpop_nonce_required` | Server-issued nonce is enforced |
| `test_dpop_replay_detection` | Replay of DPoP proofs is detected and rejected |
| `test_dpop_method_binding` | HTTP method is bound in the proof |
| `test_dpop_uri_binding` | Request URI is bound in the proof |

## Sender Constraint — 4 tests

**File**: `stoa-gateway/src/auth/middleware.rs`

| Test | What it proves |
|------|----------------|
| `test_sender_constraint_mtls_dpop` | Combined mTLS + DPoP validation |
| `test_sender_constraint_mtls_only` | mTLS-only sender constraint |
| `test_sender_constraint_dpop_only` | DPoP-only sender constraint |
| `test_sender_constraint_none` | No sender constraint passes when disabled |

## Security Integration Tests — 22 tests

**Directory**: `stoa-gateway/tests/security/`

| File | Tests | Coverage |
|------|-------|----------|
| `auth.rs` | 8 | JWT validation, API key, bearer token, expired token |
| `ssrf.rs` | 4 | SSRF protection (blocked URLs, private IPs, DNS rebinding) |
| `headers.rs` | 6 | Security headers (HSTS, CSP, X-Frame-Options, etc.) |
| `admin.rs` | 4 | Admin API access control |

## How to verify

```bash
cd stoa-gateway
cargo test --all-features -- mtls dpop sender_constraint security 2>&1 | grep "test result"
```

Expected output: `test result: ok. 36 passed; 0 failed`

---

**Last verified**: 2026-04-04
**Related**: ADR-058 (Pingora), `mcp-oauth.md` (OAuth flow), `stoa-gateway/CLAUDE.md`
