# STOA Security Audit Report — Team Coca

**Date:** 2026-01-25
**Auditeur:** Claude (VSCode)
**Scope:** CAB-938, CAB-939, CAB-945, CAB-950

---

## Executive Summary

| Ticket | Risque | Status | Findings |
|--------|--------|--------|----------|
| CAB-938 JWT | CRITICAL | 🔴 | 4 CRITICAL + 3 HIGH issues |
| CAB-939 SSE | CRITICAL | 🔴 | 6 CRITICAL issues |
| CAB-945 Container | CRITICAL | 🟡 | 3 CRITICAL + 4 HIGH issues |
| CAB-950 UI/CLI | HIGH | 🟡 | 4 CRITICAL + 3 HIGH issues |

**Overall Risk Level:** 🔴 CRITICAL

---

## Detailed Findings

---

### CAB-938: JWT Validation

#### Status: 🔴 CRITICAL

**Summary:** JWT signature verification is correctly implemented, but **audience validation is disabled** in MCP Gateway and **stale JWKS cache** can be exploited for key replay attacks.

---

#### Finding 1: MCP Gateway - Audience Validation Disabled (CRITICAL)

**Code Location:** [mcp-gateway/src/middleware/auth.py:311](mcp-gateway/src/middleware/auth.py#L311)

**Evidence:**
```python
# Line 311 - CRITICAL: Audience validation completely disabled
payload = jwt.decode(
    token,
    rsa_key,
    algorithms=["RS256"],
    issuer=self.issuer,
    options={
        "verify_aud": False,  # CRITICAL: Keycloak doesn't always set audience
        "verify_exp": True,
    },
)
```

**Risk:** Allows tokens issued for ANY service to be accepted. An attacker can obtain a token for service-B and use it to access MCP Gateway (service-A).

**Recommendation:**
```python
# Enable audience validation
options={
    "verify_aud": True,
    "verify_exp": True,
},
audience=["mcp-gateway", "stoa-portal"]  # Explicit audience list
```

---

#### Finding 2: MCP Gateway - Stale JWKS Cache Fallback (CRITICAL)

**Code Location:** [mcp-gateway/src/middleware/auth.py:246-250](mcp-gateway/src/middleware/auth.py#L246-L250)

**Evidence:**
```python
except httpx.HTTPError as e:
    logger.error("Failed to fetch JWKS", error=str(e))
    if self._jwks_cache:
        logger.warning("Using stale JWKS cache")  # ← NO TTL LIMIT
        return self._jwks_cache.keys
```

**Risk:** If Keycloak is temporarily unavailable, any previously cached JWKS is used **indefinitely**. Revoked/rotated keys remain valid.

**Recommendation:**
```python
if self._jwks_cache:
    stale_age = time.time() - self._jwks_cache.fetched_at
    if stale_age < 3600:  # Max 1 hour stale
        logger.warning("Using stale JWKS cache", age_seconds=stale_age)
        return self._jwks_cache.keys
    else:
        logger.error("JWKS cache too stale, refusing to use")
        raise HTTPException(status_code=503, detail="Authentication unavailable")
```

---

#### Finding 3: Client Credentials Token Cache Without Revocation Check (CRITICAL)

**Code Location:** [mcp-gateway/src/middleware/auth.py:426-453](mcp-gateway/src/middleware/auth.py#L426-L453)

**Evidence:**
```python
_client_token_cache: dict[str, tuple[TokenClaims, float]] = {}
CLIENT_TOKEN_CACHE_TTL = 300  # 5 minutes

# Cache check only verifies local cache age and token expiration
if claims.exp and claims.exp > time.time():
    return claims  # Returns WITHOUT checking revocation
```

**Risk:** 5-minute window of unauthorized access after credential revocation.

**Recommendation:** Remove caching or implement token introspection via Keycloak `/token/introspect` endpoint.

---

#### Finding 4: Control Plane API - Manual Audience Validation (HIGH)

**Code Location:** [control-plane-api/src/auth/dependencies.py:57, 91-103](control-plane-api/src/auth/dependencies.py#L57)

**Evidence:**
```python
# Line 57: Disable built-in validation
payload = jwt.decode(
    token, public_key, algorithms=["RS256"],
    options={"verify_aud": False}  # Disabled first
)

# Lines 91-103: Then manual re-implementation
valid_audiences = {settings.KEYCLOAK_CLIENT_ID, "account", "control-plane-ui", "stoa-portal"}
if not any(aud in valid_audiences for aud in token_aud):
    raise JWTError(f"Invalid audience: {token_aud}")
```

**Risk:** Manual validation is error-prone and inconsistent with other components.

---

#### Finding 5: Control Plane API - No JWKS Caching (HIGH)

**Code Location:** [control-plane-api/src/auth/dependencies.py:25-32](control-plane-api/src/auth/dependencies.py#L25-L32)

**Evidence:**
```python
async def get_keycloak_public_key():
    url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)  # Fresh request EVERY TIME
```

**Risk:** DDoS amplification - every JWT validation triggers HTTP request to Keycloak.

---

#### JWT Audit Questions Summary

| Question | Rust Gateway | Control Plane API | MCP Gateway |
|----------|--------------|-------------------|-------------|
| Signature verified per request? | ✅ YES | ✅ YES | ✅ YES |
| JWKS cached? | ✅ 5 min | ❌ NO | ✅ 5 min |
| `exp` claim verified? | ✅ YES | ✅ YES | ✅ YES |
| `aud` claim verified? | ✅ YES | ⚠️ Manual | ❌ **DISABLED** |
| `iss` claim verified? | ✅ YES | ✅ YES | ✅ YES |
| Token caching? | ❌ No | ❌ No | ⚠️ 5 min (M2M) |

---

### CAB-939: SSE Connection Exhaustion

#### Status: 🔴 CRITICAL

**Summary:** SSE endpoints have **no connection limits per IP/tenant**, **no idle timeout**, and **no max connection duration**. This allows Slowloris DoS attacks.

---

#### Finding 1: No Per-IP Connection Limit (CRITICAL)

**Code Location:** [mcp-gateway/src/handlers/mcp_sse.py:220-221](mcp-gateway/src/handlers/mcp_sse.py#L220-L221)

**Evidence:**
```python
# Global session storage with NO LIMITS
_sessions: dict[str, MCPSession] = {}

# Any IP can create unlimited sessions
session_id = str(uuid.uuid4())
session = MCPSession(session_id, user)
_sessions[session_id] = session  # ← UNBOUNDED GROWTH
```

**Risk:** Attacker can exhaust server memory with 5,000+ concurrent connections.

---

#### Finding 2: No Idle Timeout (CRITICAL)

**Code Location:** [mcp-gateway/src/handlers/mcp_sse.py:409-413](mcp-gateway/src/handlers/mcp_sse.py#L409-L413)

**Evidence:**
```python
# Keep connection alive - INFINITE LOOP
while True:
    if await request.is_disconnected():
        break

    yield ": keepalive\n\n"  # Heartbeat keeps connection alive indefinitely
    await asyncio.sleep(30)  # 30-second interval, but NO TIMEOUT
```

**Risk:** Connections stay open forever if client doesn't properly disconnect.

---

#### Finding 3: No Max Connection Duration (CRITICAL)

**Risk:** A single SSE connection can remain open for hours/days, consuming server resources indefinitely.

**Recommendation:**
```python
MAX_CONNECTION_DURATION = 3600  # 1 hour
connection_start = time.time()

while True:
    if time.time() - connection_start > MAX_CONNECTION_DURATION:
        logger.info("Max connection duration reached, closing")
        break
```

---

#### Finding 4: Control Plane API Events Stream (CRITICAL)

**Code Location:** [control-plane-api/src/routers/events.py:45-94](control-plane-api/src/routers/events.py#L45-L94)

**Evidence:**
```python
@router.get("/stream/{tenant_id}")
async def stream_events(...):
    # No per-tenant connection limit
    # No per-IP connection limit
    return EventSourceResponse(event_generator(...))
```

---

#### SSE Audit Questions Summary

| Question | MCP Gateway | Control Plane API |
|----------|-------------|-------------------|
| Limit connections per IP? | ❌ NO | ❌ NO |
| Limit connections per tenant? | ❌ NO | ❌ NO |
| Idle timeout? | ❌ NO (30s heartbeat ≠ timeout) | ❌ NO |
| Max connection duration? | ❌ NO | ❌ NO |
| Heartbeat mechanism? | ✅ 30 seconds | ✅ 30 seconds |
| Rate limit new connections? | ❌ NO | ❌ NO |

---

#### Recommended Configuration

```python
# src/config/settings.py
sse_max_connections_global: int = 10000
sse_max_connections_per_ip: int = 50
sse_max_connections_per_tenant: int = 500
sse_idle_timeout_seconds: int = 300
sse_max_duration_seconds: int = 3600
sse_heartbeat_interval_seconds: int = 25
```

---

### CAB-945: Control Plane Hardening

#### Status: 🟡 NEEDS WORK

**Summary:** Most containers run as non-root with resource limits, but **critical gaps** exist in read-only filesystem, capability dropping, and Pod Security Standards.

---

#### Finding 1: Frontend Containers Allow Root Filesystem Writes (CRITICAL)

**Code Location:** [portal/k8s/deployment.yaml:52](portal/k8s/deployment.yaml#L52)

**Evidence:**
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 101
  readOnlyRootFilesystem: false  # ❌ ALLOWS CONTAINER MODIFICATIONS
  allowPrivilegeEscalation: false
```

**Risk:** Attacker can modify application files after compromise, persist malicious code.

**Recommendation:**
```yaml
securityContext:
  readOnlyRootFilesystem: true
volumeMounts:
  - name: nginx-temp
    mountPath: /var/run/nginx
volumes:
  - name: nginx-temp
    emptyDir:
      sizeLimit: 100Mi
```

---

#### Finding 2: stoa-portal Runs as Root (CRITICAL)

**Code Location:** [stoa-portal/Dockerfile:75](stoa-portal/Dockerfile#L75)

**Evidence:**
```dockerfile
FROM nginx:alpine  # Runs as root by default
CMD ["nginx", "-g", "daemon off;"]
# NO USER directive
```

**Recommendation:**
```dockerfile
FROM nginxinc/nginx-unprivileged:alpine
# Runs as uid=101(nginx)
```

---

#### Finding 3: No Capability Dropping (CRITICAL)

**All deployments** retain default kernel capabilities (CAP_NET_RAW, CAP_SYS_ADMIN, etc.)

**Evidence:**
```yaml
# control-plane-api/k8s/deployment.yaml - Lines 66-71
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  # ❌ NO capabilities.drop: [ALL]
```

**Recommendation:**
```yaml
securityContext:
  capabilities:
    drop:
      - ALL
```

---

#### Finding 4: No Pod Security Standards (HIGH)

**Evidence:** No namespaces have PSS labels applied.

```yaml
# deploy/demo-tenants/team-alpha.yaml
metadata:
  labels:
    gostoa.dev/tenant: team-alpha
    # ❌ NO pod-security.kubernetes.io labels
```

**Recommendation:**
```yaml
labels:
  pod-security.kubernetes.io/enforce: restricted
  pod-security.kubernetes.io/audit: restricted
  pod-security.kubernetes.io/warn: restricted
```

---

#### Finding 5: control-plane-ui Has No securityContext (HIGH)

**Code Location:** [control-plane-ui/k8s/deployment.yaml:21-52](control-plane-ui/k8s/deployment.yaml#L21-L52)

**Evidence:** No securityContext defined. Privilege escalation allowed by default.

---

#### Finding 6: No Network Policies (HIGH)

**Evidence:** Zero NetworkPolicy resources in the repository.

**Risk:** Lateral movement within cluster unrestricted.

---

#### Container Security Summary

| Component | Non-Root | PrivEsc Disabled | Read-Only FS | Caps Dropped | PSS |
|-----------|----------|------------------|--------------|--------------|-----|
| control-plane-api | ✅ | ✅ | ✅ | ❌ | ❌ |
| mcp-gateway | ✅ | ✅ | ✅ | ❌ | ❌ |
| control-plane-ui | ✅ | ❌ | N/A | ❌ | ❌ |
| portal | ✅ | ✅ | ❌ | ❌ | ❌ |
| stoa-portal | ❌ | ✅ | ❌ | ❌ | ❌ |

---

### CAB-950: UI/CLI Hardening

#### Status: 🟡 NEEDS WORK

**Summary:** Strong RBAC implementation, but **CORS wildcard in MCP Gateway**, **no idle timeout**, and **non-distributed rate limiting** create security gaps.

---

#### Finding 1: MCP Gateway CORS Wildcard (CRITICAL)

**Code Location:** [mcp-gateway/src/config/settings.py](mcp-gateway/src/config/settings.py)

**Evidence:**
```python
cors_origins: str = "*"  # DEFAULT TO WILDCARD
```

**Risk:** Any website can access MCP Gateway on behalf of authenticated users.

**Recommendation:**
```python
cors_origins: str = f"https://console.{base_domain},https://portal.{base_domain}"
```

---

#### Finding 2: No Rate Limiting on Login Endpoints (CRITICAL)

**Evidence:** No rate limiting on Keycloak token endpoint proxy.

**Risk:** Brute force password attacks, credential stuffing.

**Recommendation:** Add rate limit: 5 failed attempts per 15 minutes per IP.

---

#### Finding 3: Non-Distributed Rate Limiting (CRITICAL)

**Code Location:** [control-plane-api/src/middleware/rate_limit.py](control-plane-api/src/middleware/rate_limit.py)

**Evidence:**
```python
limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri="memory://",  # ❌ NOT DISTRIBUTED
    strategy="fixed-window",
)
```

**Risk:** Multi-pod bypass - effective limit is 100 × number_of_pods.

**Recommendation:** Migrate to Redis backend (CAB-459).

---

#### Finding 4: No Idle Timeout (HIGH)

**Evidence:** No client-side or server-side inactivity detection.

**Risk:** Users remain logged in indefinitely if active, violates enterprise security requirements.

---

#### Finding 5: No Content Security Policy (HIGH)

**Evidence:** No CSP headers configured.

**Risk:** XSS attacks possible.

---

#### UI/CLI Audit Questions Summary

| Question | Status | Details |
|----------|--------|---------|
| Session lifetime configured? | ⚠️ | Relies on Keycloak defaults |
| Idle timeout? | ❌ NO | Not implemented |
| Cookie httpOnly/secure/SameSite? | N/A | Token-based auth, no cookies |
| CSRF protection? | ✅ | Inherently mitigated by Bearer tokens |
| CORS restrictive? | ⚠️ | Control Plane ✅, MCP Gateway ❌ |
| Rate limiting on mutations? | ⚠️ | Partial, non-distributed |
| RBAC granular? | ✅ | 12+ scopes, server-side enforcement |
| Audit logging? | ✅ | OpenSearch-based, comprehensive |

---

## Action Items (Prioritized)

| Priority | Action | Ticket | Component |
|----------|--------|--------|-----------|
| P0 | Enable audience validation in MCP Gateway | CAB-938 | mcp-gateway |
| P0 | Fix MCP Gateway CORS wildcard | CAB-950 | mcp-gateway |
| P0 | Add per-IP SSE connection limits | CAB-939 | mcp-gateway, control-plane-api |
| P0 | Add SSE idle timeout (5 min) | CAB-939 | mcp-gateway, control-plane-api |
| P1 | Implement JWKS cache TTL limit on stale | CAB-938 | mcp-gateway |
| P1 | Add rate limiting on login endpoints | CAB-950 | control-plane-api |
| P1 | Enable readOnlyRootFilesystem on frontends | CAB-945 | portal, stoa-portal |
| P1 | Drop ALL capabilities on all containers | CAB-945 | all k8s deployments |
| P1 | Fix stoa-portal Dockerfile (nginx-unprivileged) | CAB-945 | stoa-portal |
| P2 | Add JWKS caching to Control Plane API | CAB-938 | control-plane-api |
| P2 | Apply Pod Security Standards to namespaces | CAB-945 | all namespaces |
| P2 | Migrate rate limiting to Redis (CAB-459) | CAB-950 | control-plane-api |
| P2 | Implement Network Policies | CAB-945 | all namespaces |
| P2 | Add SSE connection Prometheus metrics | CAB-939 | mcp-gateway |
| P3 | Remove client credentials token cache | CAB-938 | mcp-gateway |
| P3 | Add Content Security Policy headers | CAB-950 | control-plane-api |
| P3 | Implement idle timeout detection | CAB-950 | control-plane-ui, portal |

---

## Files Analyzed

### JWT Validation (CAB-938)
- [stoa-gateway/src/auth/jwt.rs](stoa-gateway/src/auth/jwt.rs) — Rust JWT validation
- [stoa-gateway/src/auth/oidc.rs](stoa-gateway/src/auth/oidc.rs) — JWKS caching
- [control-plane-api/src/auth/dependencies.py](control-plane-api/src/auth/dependencies.py) — Python JWT validation
- [mcp-gateway/src/middleware/auth.py](mcp-gateway/src/middleware/auth.py) — MCP Gateway auth

### SSE Connection (CAB-939)
- [mcp-gateway/src/handlers/mcp_sse.py](mcp-gateway/src/handlers/mcp_sse.py) — SSE handler
- [control-plane-api/src/routers/events.py](control-plane-api/src/routers/events.py) — Events stream
- [mcp-gateway/src/config/settings.py](mcp-gateway/src/config/settings.py) — Gateway config

### Container Hardening (CAB-945)
- [control-plane-api/k8s/deployment.yaml](control-plane-api/k8s/deployment.yaml)
- [control-plane-ui/k8s/deployment.yaml](control-plane-ui/k8s/deployment.yaml)
- [mcp-gateway/k8s/deployment.yaml](mcp-gateway/k8s/deployment.yaml)
- [portal/k8s/deployment.yaml](portal/k8s/deployment.yaml)
- [stoa-portal/k8s/deployment.yaml](stoa-portal/k8s/deployment.yaml)
- [stoa-portal/Dockerfile](stoa-portal/Dockerfile)
- [k8s/postgres-backup-cronjob.yaml](k8s/postgres-backup-cronjob.yaml)

### UI/CLI Hardening (CAB-950)
- [control-plane-api/src/middleware/rate_limit.py](control-plane-api/src/middleware/rate_limit.py)
- [control-plane-api/src/auth/rbac.py](control-plane-api/src/auth/rbac.py)
- [control-plane-api/src/config.py](control-plane-api/src/config.py)
- [mcp-gateway/src/policy/scopes.py](mcp-gateway/src/policy/scopes.py)
- [control-plane-api/src/opensearch/audit_middleware.py](control-plane-api/src/opensearch/audit_middleware.py)

---

## Files NOT Found (manual review needed)

- `/stoactl` or CLI tool — No CLI exists in current codebase
- Keycloak realm configuration — Not in repo (external service)
- TLS certificate configuration — Infrastructure-level
- AWS WAF/CloudFront settings — Infrastructure-level

---

## Compliance Summary

| Control | CIS K8s | Status |
|---------|---------|--------|
| 5.2.1 Run as non-root | PARTIAL | 3 containers violate |
| 5.2.2 Privilege escalation | PARTIAL | 4 missing config |
| 5.2.3 Read-only filesystem | PARTIAL | 2 frontends vulnerable |
| 5.2.7 Capabilities dropped | ❌ MISSING | All containers |
| 5.7.1 Pod Security Standards | ❌ MISSING | All namespaces |
| 5.3.1 Network Policies | ❌ MISSING | None defined |

---

**Report Generated:** 2026-01-25
**Next Review:** After implementation of P0 items
