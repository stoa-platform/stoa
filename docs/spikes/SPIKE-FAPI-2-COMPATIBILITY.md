# Spike: FAPI 2.0 Compatibility Assessment

| Field | Value |
|-------|-------|
| **Ticket** | CAB-1733 |
| **Date** | 2026-03-06 |
| **Duration** | 3 j/h (spike) |
| **Result** | STOA is ~65% FAPI 2.0 compliant. 3 critical gaps: PAR, private_key_jwt, confidential-only clients. |

## 1. Gateway Capability Matrix

### FAPI 2.0 Security Profile Requirements

| # | Requirement | RFC | Status | LOC | File(s) |
|---|-----------|-----|--------|-----|---------|
| 1 | Sender-constrained tokens | FAPI 2.0 | ✅ Implemented | 621 | `auth/sender_constraint.rs` |
| 2 | DPoP proof validation | RFC 9449 | ✅ Implemented | 843 | `auth/dpop.rs` |
| 3 | mTLS certificate binding | RFC 8705 | ✅ Implemented | 1,122 | `auth/mtls.rs` |
| 4 | PKCE S256 | RFC 7636 | ✅ Implemented | — | `oauth/proxy.rs` (DCR patch) |
| 5 | OAuth discovery (protected resource) | RFC 9728 | ✅ Implemented | 264 | `oauth/discovery.rs` |
| 6 | OAuth discovery (auth server) | RFC 8414 | ✅ Implemented | — | `oauth/discovery.rs` |
| 7 | DCR (Dynamic Client Registration) | RFC 7591 | ✅ Implemented | ~200 | `oauth/proxy.rs` |
| 8 | PAR (Pushed Authorization Requests) | RFC 9126 | ❌ Missing | 0 | — |
| 9 | private_key_jwt client auth | RFC 7523 | ❌ Missing | 0 | — |
| 10 | Confidential clients only | FAPI 2.0 | ⚠️ Breaking | — | Current: public clients for MCP |
| 11 | JARM (JWT auth response) | OIDC JARM | ❌ Missing | 0 | Optional |
| 12 | Token revocation proxy | RFC 7009 | ❌ Missing | 0 | KC handles natively |

### Agentic Governance Capabilities

| # | Capability | Status | LOC | File(s) |
|---|-----------|--------|-----|---------|
| 1 | Agent identity extraction | ✅ Implemented | 389 | `auth/agent.rs` |
| 2 | Supervision tiers | ✅ Implemented | — | `supervision/mod.rs` |
| 3 | OPA policy engine (regorus) | 🔶 Partial (disabled) | ~320 | `policy/opa.rs` |
| 4 | Guardrails AI pipeline | ✅ Implemented | — | `guardrails/mod.rs` |
| 5 | Skills cascade (CSS model) | ✅ Implemented | — | `skills/resolver.rs` |
| 6 | MCP Federation | ✅ Implemented | — | `federation/mod.rs` |
| 7 | Token exchange in gateway | ❌ Missing | 0 | Only in CP API |
| 8 | Agent delegation (on_behalf_of) | ❌ Missing | 0 | — |
| 9 | Resource-level RBAC | ❌ Missing | 0 | Only role-based |
| 10 | Agent audit trail | 🔶 Partial | — | CP API `audit_event.py` |

### Sovereign Deployment

| # | Capability | Status | Notes |
|---|-----------|--------|-------|
| 1 | On-premise deployment | ✅ | Helm chart, K8s manifests |
| 2 | Air-gapped operation | 🔶 | Needs offline container registry |
| 3 | EU data residency | ✅ | OVH FR + Hetzner DE |
| 4 | DORA compliance tooling | 🔶 | Audit trail exists, gaps in reporting |
| 5 | eIDAS 2.0 integration | ❌ | Phase 4 |
| 6 | Multi-tenancy | ✅ | Tenant isolation via KC realms |

## 2. Keycloak FAPI 2.0 Readiness

### Version Analysis

| Environment | Version | FAPI 2.0 Client Profiles | DPoP Feature | Token Exchange |
|---|---|---|---|---|
| **Production** | 26.5.3 | ✅ Available | ✅ Enabled | ✅ Enabled |
| **Quick-start** | 23.0 | ❌ Too old | ❌ Not available | ✅ Available |
| **E2E tests** | 23.0 | ❌ Too old | ❌ Not available | ✅ Available |

**Decision**: No KC upgrade needed for production. Unify quickstart/E2E to 26.5.3.

### FAPI 2.0 Client Profiles in KC 26.5.3

| Profile | What It Enforces |
|---------|-----------------|
| `fapi-2-security-profile` | Confidential client, PKCE S256, PAR required, short token lifetime |
| `fapi-2-dpop-security-profile` | Above + DPoP header required on token requests |

Activation: Admin Console → Realm Settings → Client Policies → Add profile.

### Keycloak Dockerfile

```dockerfile
# Current: keycloak/Dockerfile
FROM quay.io/keycloak/keycloak:26.5.3
ENV KC_FEATURES=token-exchange,dpop
```

**Recommended addition**: `KC_FEATURES=token-exchange,dpop,par` (PAR support).

## 3. Breaking Change Analysis: Public → Confidential Clients

### Current MCP OAuth Flow (Claude.ai)

```
1. Claude.ai → GET /.well-known/oauth-protected-resource
2. Claude.ai → POST /oauth/register (DCR)
   → Gateway strips scope, forwards to KC
   → Gateway patches client: publicClient=true, PKCE=S256
3. Claude.ai → POST /oauth/token (authorization_code + code_verifier)
   → No client_secret needed (public client)
4. Claude.ai → API calls with Bearer token
```

### FAPI 2.0 Required Flow

```
1. Client → GET /.well-known/oauth-protected-resource
2. Client → POST /oauth/register (DCR)
   → Client provides JWKS URI or embedded JWK
   → KC creates confidential client with private_key_jwt auth
3. Client → POST /oauth/par (PAR)
   → Client signs request with private key (client_assertion)
   → Returns request_uri (60s TTL)
4. Client → GET /authorize?request_uri=...&client_id=...
5. Client → POST /oauth/token
   → client_assertion (JWT signed by client private key)
   → code_verifier (PKCE)
   → DPoP proof header
6. Client → API calls with Bearer token + DPoP proof
```

### Impact on Existing Clients

| Client | Current Auth | FAPI Impact | Mitigation |
|--------|-------------|-------------|------------|
| Claude.ai (MCP) | Public PKCE | ❌ Would break | Dual-mode: keep Standard profile |
| Console UI | Confidential (client_secret) | ⚠️ Needs private_key_jwt | Phase 2 migration |
| Portal | Confidential (client_secret) | ⚠️ Needs private_key_jwt | Phase 2 migration |
| Consumer apps | Confidential (client_secret) | ⚠️ Needs private_key_jwt | Phase 2 migration |
| Service accounts | Confidential (client_credentials) | ⚠️ Needs private_key_jwt | Phase 2 migration |

### Dual-Mode Strategy

Gateway supports two client security profiles via per-client KC configuration:

| Profile | Detection | Enforcement |
|---------|-----------|-------------|
| **Standard** | `publicClient: true` OR no FAPI profile assigned | Current behavior (PKCE, no PAR, no DPoP required) |
| **FAPI 2.0** | FAPI client profile assigned in KC | PAR required, private_key_jwt, DPoP/mTLS enforced |

No code change needed for profile routing — Keycloak handles it. Gateway just needs to support PAR proxy and client assertion validation.

## 4. Competitive Position

| Capability | STOA | Kong OSS | Gravitee 4.8 | agentgateway | WSO2 |
|-----------|------|----------|--------------|--------------|------|
| DPoP (RFC 9449) | ✅ Full | ❌ Enterprise | ❌ | ❌ | ❌ |
| mTLS binding | ✅ Full | ✅ Plugin | ✅ | ❌ | ✅ |
| Sender constraint | ✅ Unified | ❌ | 🔶 mTLS only | ❌ | 🔶 |
| PAR | ❌ Missing | ❌ | ❌ | ❌ | ❌ |
| private_key_jwt | ❌ Missing | ❌ | ❌ | ❌ | 🔶 |
| FAPI 2.0 certified | ❌ | ❌ | ❌ | ❌ | FAPI 1.0 only |
| MCP Protocol | ✅ Native | 🔶 Enterprise | ✅ A2A | ✅ Basic | ❌ |
| Agent Identity | ✅ JWT-based | ❌ | ❌ | ❌ | ❌ |
| OPA Policy | ✅ Embedded | ✅ Plugin | ✅ Plugin | ❌ | ❌ |
| Token Exchange | ✅ CP API | ❌ | ❌ | ❌ | ❌ |

**STOA would be the first open-source API gateway with FAPI 2.0 conformance + native MCP support.**

## 5. Recommendations

### Phase 1 Priority (this ticket scope)
1. ✅ Spike completed (this document)
2. ✅ ADR-056 created
3. ✅ KC version audit done (26.5.3 is sufficient)
4. ✅ Breaking change analysis documented
5. Next: Decompose into sub-tickets via `/decompose`

### Implementation Effort Estimate

| Item | Effort | Complexity |
|------|--------|------------|
| PAR proxy endpoint | 5 pts | Medium — new endpoint + KC PAR config |
| private_key_jwt validation | 8 pts | High — JWT assertion parsing, JWKS cache |
| OTel runtime toggle | 3 pts | Low — env var check, config change |
| KC quickstart upgrade | 2 pts | Low — Dockerfile version bump |
| Docs update (docs.gostoa.dev) | 3 pts | Low — security guide, capability page |
| Token exchange in gateway | 5 pts | Medium — RFC 8693 proxy |
| Agent delegation model | 8 pts | High — new claim, OPA policy, audit |
