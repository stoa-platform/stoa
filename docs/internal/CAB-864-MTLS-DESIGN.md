# CAB-864: mTLS Certificate Binding — Implementation Design

> **Status**: Design
> **ADR**: [ADR-039](https://docs.gostoa.dev/architecture/adr/adr-039-mtls-cert-bound-tokens) (Rust Gateway mTLS + Certificate-Bound Token Validation)
> **Related ADRs**: [ADR-027](https://docs.gostoa.dev/architecture/adr/adr-027-x509-header-authentication) (X.509 Header Auth), [ADR-028](https://docs.gostoa.dev/architecture/adr/adr-028-rfc8705-certificate-binding) (RFC 8705 Binding), [ADR-029](https://docs.gostoa.dev/architecture/adr/adr-029-mtls-certificate-lifecycle) (Certificate Lifecycle)

## Overview

Enterprise clients connect via mTLS through F5 (load balancer), which terminates TLS and injects client certificate metadata into HTTP headers. The STOA Gateway (Rust/axum) reads these headers, validates the certificate, and verifies RFC 8705 binding between the certificate and the OAuth2 access token.

```
                          mTLS (TLS 1.2+)                  HTTP (internal)
    ┌────────┐      ┌──────────────────┐      ┌──────────────────────┐      ┌────────────┐
    │ Client │─────▶│       F5         │─────▶│    STOA Gateway      │─────▶│ webMethods │
    │ (cert) │ TLS  │ (TLS termination)│  +   │ (header validation)  │  +   │ / Kong     │
    └────────┘      │ extracts cert    │ hdrs │ RFC 8705 binding     │ fwd  │ (upstream) │
                    └──────────────────┘      └──────────────────────┘      └────────────┘
                         │                            │
                         │ Injects X-SSL-* headers    │ Validates:
                         │ Strips from external       │  1. Cert headers present
                         │                            │  2. Verify = SUCCESS
                         │                            │  3. cnf.x5t#S256 = fingerprint
                         │                            │  4. Cert not expired
                         │                            │  5. Issuer allowed
```

## 1. F5 Header Format Specification

F5 BIG-IP (with client SSL profile + iRule) injects these headers after successful mTLS handshake:

| Header | Example Value | Source |
|--------|---------------|--------|
| `X-SSL-Client-Verify` | `SUCCESS` | F5 verify result: `SUCCESS`, `FAILED:reason`, `NONE` |
| `X-SSL-Client-Fingerprint` | `a1b2c3...` (64 hex chars) | SHA-256 of DER-encoded client cert |
| `X-SSL-Client-S-DN` | `CN=api-consumer-1,OU=tenant-acme,O=Acme Corp,C=FR` | Subject Distinguished Name (RFC 2253) |
| `X-SSL-Client-I-DN` | `CN=STOA Intermediate CA,O=STOA Platform,C=FR` | Issuer Distinguished Name |
| `X-SSL-Client-Serial` | `0A1B2C3D` | Certificate serial number (hex) |
| `X-SSL-Client-NotBefore` | `2026-01-15T00:00:00Z` | Certificate validity start (ISO 8601) |
| `X-SSL-Client-NotAfter` | `2027-01-15T00:00:00Z` | Certificate validity end (ISO 8601) |
| `X-SSL-Client-Cert` | `-----BEGIN CERTIFICATE-----\nMIID...` | URL-encoded PEM (optional, large) |

### Trust Model

- **F5 is the sole trusted proxy.** Only F5's IP range may send `X-SSL-*` headers.
- The gateway MUST strip `X-SSL-*` headers from requests not originating from F5 (Kubernetes `NetworkPolicy` + gateway IP check).
- Headers are **unsigned** — security relies on network-level trust (F5 → Gateway path is internal).

### Header Variants by TLS Terminator

| TLS Terminator | Verify Header | Fingerprint Header | DN Header |
|----------------|---------------|--------------------|-----------|
| F5 BIG-IP | `X-SSL-Client-Verify` | `X-SSL-Client-Fingerprint` | `X-SSL-Client-S-DN` |
| nginx | `X-SSL-Client-Verify` | `SSL_CLIENT_FINGERPRINT` | `SSL_CLIENT_S_DN` |
| Envoy | `x-forwarded-client-cert` (XFCC) | Embedded in XFCC `Hash=` | Embedded in XFCC `Subject=` |
| HAProxy | `X-SSL-Client-Verify` | `X-SSL-Client-SHA256` | `X-SSL-Client-DN` |

The gateway config makes header names configurable to support all terminators (per ADR-028 principle).

## 2. Gateway Middleware Chain

### Current Auth Pipeline (pre-mTLS)

```
Request → Rate Limiter → JWT/API Key Auth → RBAC → OPA → Handler
```

### Extended Pipeline (with mTLS)

```
Request
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0: Rate Limiter (existing, unchanged)                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: mTLS Header Extraction [NEW]                           │
│                                                                  │
│   IF mtls_enabled == false → no-op, continue (zero overhead)    │
│                                                                  │
│   1. Read X-SSL-Client-Verify header                            │
│      - Missing → 401 MTLS_CERT_REQUIRED                         │
│      - != "SUCCESS" → 403 MTLS_CERT_INVALID                     │
│                                                                  │
│   2. Read X-SSL-Client-Fingerprint                              │
│      - Normalize: strip colons, lowercase                       │
│      - Compute base64url variant for RFC 8705 comparison        │
│                                                                  │
│   3. Read remaining headers (S-DN, I-DN, Serial, dates)         │
│                                                                  │
│   4. Validate certificate:                                      │
│      - NotAfter < now → 403 MTLS_CERT_EXPIRED                   │
│      - Issuer not in allowed_issuers → 403 MTLS_ISSUER_DENIED   │
│                                                                  │
│   5. Store CertificateInfo in request.extensions()              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: JWT / API Key Auth (existing, extended)                │
│                                                                  │
│   Existing flow (unchanged):                                    │
│   - Extract Authorization: Bearer <token>                       │
│   - Validate JWT signature (JWKS) + expiry + issuer + audience  │
│   - Fallback to API Key if no Bearer token                      │
│   - Build AuthenticatedUser, store in extensions                │
│                                                                  │
│   Extension: Claims struct now deserializes `cnf` field         │
│   (Option<CnfClaim>) — non-breaking, existing tokens work      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: Certificate-Token Binding Verification [NEW]           │
│                                                                  │
│   IF no CertificateInfo in extensions → skip (no cert)          │
│                                                                  │
│   1. Extract claims.cnf.x5t_s256                                │
│      - Missing + require_binding → 403 MTLS_BINDING_REQUIRED    │
│      - Missing + !require_binding → warn, continue              │
│                                                                  │
│   2. Compare fingerprints (timing-safe):                        │
│      cert_fingerprint (hex) → bytes                             │
│      cnf.x5t#S256 (base64url) → decode → bytes                 │
│      subtle::ConstantTimeEq → match/mismatch                   │
│      Mismatch → 403 MTLS_BINDING_MISMATCH                       │
│                                                                  │
│   3. Match → continue (cert bound to token)                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: RBAC Enforcement (existing, unchanged)                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 5: OPA Policy Evaluation (existing, unchanged)            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
  Handler (AuthUser + CertInfo extractors available)
```

**Design rationale**: mTLS extraction (Stage 1) happens **before** JWT validation (Stage 2) to fail fast on invalid certificates. Binding verification (Stage 3) happens **after** because it needs both the certificate info and the JWT claims.

## 3. Configuration Schema

New fields added to `Config` struct (`stoa-gateway/src/config.rs`) via Figment:

```
MtlsConfig (nested in Config)
├── enabled: bool                     STOA_MTLS_ENABLED              default: false
├── require_binding: bool             STOA_MTLS_REQUIRE_BINDING      default: true
├── trusted_proxies: Vec<String>      STOA_MTLS_TRUSTED_PROXIES      default: [] (F5 IPs, CIDR)
├── header_verify: String             STOA_MTLS_HEADER_VERIFY        default: "X-SSL-Client-Verify"
├── header_fingerprint: String        STOA_MTLS_HEADER_FINGERPRINT   default: "X-SSL-Client-Fingerprint"
├── header_subject_dn: String         STOA_MTLS_HEADER_SUBJECT_DN    default: "X-SSL-Client-S-DN"
├── header_issuer_dn: String          STOA_MTLS_HEADER_ISSUER_DN     default: "X-SSL-Client-I-DN"
├── header_serial: String             STOA_MTLS_HEADER_SERIAL        default: "X-SSL-Client-Serial"
├── header_not_before: String         STOA_MTLS_HEADER_NOT_BEFORE    default: "X-SSL-Client-NotBefore"
├── header_not_after: String          STOA_MTLS_HEADER_NOT_AFTER     default: "X-SSL-Client-NotAfter"
├── header_cert: String               STOA_MTLS_HEADER_CERT          default: "X-SSL-Client-Cert"
├── allowed_issuers: Vec<String>      STOA_MTLS_ALLOWED_ISSUERS      default: [] (accept all)
├── required_routes: Vec<String>      STOA_MTLS_REQUIRED_ROUTES      default: [] (per-route opt-in)
└── tenant_from_dn: bool              STOA_MTLS_TENANT_FROM_DN       default: true
```

### Trusted Proxies

```
STOA_MTLS_TRUSTED_PROXIES=10.0.0.0/8,172.16.0.0/12
```

If set, the gateway checks `X-Forwarded-For` or the connection source IP against this list. Requests with `X-SSL-*` headers from outside trusted proxies are rejected with 403 `MTLS_UNTRUSTED_PROXY`.

### Per-Route mTLS Requirement

```
STOA_MTLS_REQUIRED_ROUTES=/api/v1/payments/*,/api/v1/transfers/*
```

Routes matching these patterns require a valid mTLS certificate. Other routes accept mTLS optionally (binding verified if cert present, but not required).

## 4. Error Matrix

| Condition | HTTP | Error Code | Response Body | When |
|-----------|------|------------|---------------|------|
| mTLS disabled, no cert | - | - | (no error, bypass) | `STOA_MTLS_ENABLED=false` |
| No `X-SSL-Client-Verify` header, mTLS enabled | 401 | `MTLS_CERT_REQUIRED` | `{"error":"MTLS_CERT_REQUIRED","detail":"client certificate required"}` | Required route or global |
| `X-SSL-Client-Verify != SUCCESS` | 403 | `MTLS_CERT_INVALID` | `{"error":"MTLS_CERT_INVALID","detail":"client certificate validation failed: {reason}"}` | F5 reports failure |
| Certificate expired (`NotAfter < now`) | 403 | `MTLS_CERT_EXPIRED` | `{"error":"MTLS_CERT_EXPIRED","detail":"client certificate expired on {date}"}` | Date check |
| Issuer not in `allowed_issuers` | 403 | `MTLS_ISSUER_DENIED` | `{"error":"MTLS_ISSUER_DENIED","detail":"certificate issuer not allowed"}` | Issuer allowlist |
| JWT has no `cnf` + cert present + `require_binding=true` | 403 | `MTLS_BINDING_REQUIRED` | `{"error":"MTLS_BINDING_REQUIRED","detail":"certificate-bound token required"}` | Token lacks binding |
| Fingerprint mismatch (`cnf.x5t#S256 != cert SHA-256`) | 403 | `MTLS_BINDING_MISMATCH` | `{"error":"MTLS_BINDING_MISMATCH","detail":"certificate binding mismatch"}` | Stolen/wrong token |
| `X-SSL-*` from untrusted proxy | 403 | `MTLS_UNTRUSTED_PROXY` | `{"error":"MTLS_UNTRUSTED_PROXY","detail":"mTLS headers from untrusted source"}` | IP check |

All errors follow the existing gateway JSON format: `{"error": "...", "detail": "..."}`.

## 5. Certificate Registry Model

Extension to the existing `consumers` table (Alembic migration):

```sql
-- Migration 019: Add mTLS certificate fields to consumers
ALTER TABLE consumers ADD COLUMN certificate_fingerprint         VARCHAR(64);   -- SHA-256 hex, 64 chars
ALTER TABLE consumers ADD COLUMN certificate_fingerprint_previous VARCHAR(64);  -- Grace period rotation
ALTER TABLE consumers ADD COLUMN certificate_subject_dn          VARCHAR(500);
ALTER TABLE consumers ADD COLUMN certificate_issuer_dn           VARCHAR(500);
ALTER TABLE consumers ADD COLUMN certificate_serial              VARCHAR(64);
ALTER TABLE consumers ADD COLUMN certificate_not_before          TIMESTAMPTZ;
ALTER TABLE consumers ADD COLUMN certificate_not_after           TIMESTAMPTZ;
ALTER TABLE consumers ADD COLUMN certificate_pem                 TEXT;          -- Full PEM (optional)
ALTER TABLE consumers ADD COLUMN certificate_status              VARCHAR(20) DEFAULT 'active';
  -- Values: active, rotating, revoked, expired
ALTER TABLE consumers ADD COLUMN previous_cert_expires_at        TIMESTAMPTZ;  -- Grace period end
ALTER TABLE consumers ADD COLUMN last_rotated_at                 TIMESTAMPTZ;
ALTER TABLE consumers ADD COLUMN rotation_count                  INTEGER DEFAULT 0;

-- Index for fingerprint lookups (gateway → API validation)
CREATE INDEX ix_consumers_fingerprint ON consumers (certificate_fingerprint);
CREATE INDEX ix_consumers_fingerprint_prev ON consumers (certificate_fingerprint_previous);
```

### Certificate Status Lifecycle

```
                 rotate
    ┌──────────┐ ────────▶ ┌───────────┐  grace expires  ┌──────────┐
    │  active  │           │ rotating  │ ────────────▶   │  active  │
    │ (cert A) │           │ (A + B)   │                 │ (cert B) │
    └──────────┘           └───────────┘                 └──────────┘
         │                                                     │
         │ revoke                                              │ revoke
         ▼                                                     ▼
    ┌──────────┐                                         ┌──────────┐
    │ revoked  │                                         │ revoked  │
    └──────────┘                                         └──────────┘
```

During `rotating` status, both `certificate_fingerprint` (new) and `certificate_fingerprint_previous` (old) are valid. The grace period is time-based (configurable, default 24h) per ADR-029.

## 6. Bulk Onboarding API

### Endpoint

```
POST /v1/consumers/{tenant_id}/bulk
Content-Type: multipart/form-data
Authorization: Bearer <admin-token>
```

Requires `cpi-admin` or `tenant-admin` role.

### Request

```
--boundary
Content-Disposition: form-data; name="file"; filename="consumers.csv"
Content-Type: text/csv

external_id,name,email,company,certificate_pem
api-consumer-001,Payment Service,payment@acme.com,Acme Corp,"-----BEGIN CERTIFICATE-----
MIID...
-----END CERTIFICATE-----"
api-consumer-002,Billing Service,billing@acme.com,Acme Corp,"-----BEGIN CERTIFICATE-----
MIIE...
-----END CERTIFICATE-----"
--boundary--
```

### Constraints

- Maximum **100 rows** per request
- `certificate_pem` is optional (consumers without certs get client_credentials only)
- Each row is processed **independently** — one failure does not block others
- CSV must be UTF-8 encoded

### Per-Row Processing

For each row with a certificate:
1. Parse PEM, validate it's an X.509 certificate
2. Compute SHA-256 fingerprint (hex lowercase)
3. Compute base64url-encoded thumbprint (`x5t#S256`)
4. Check for duplicate fingerprint within tenant
5. Create Keycloak client with:
   - `client_id`: `consumer-{external_id}`
   - Protocol mapper: `cnf` claim with `{"x5t#S256": "<thumbprint_b64url>"}`
   - `x509.certificate.sha256` client attribute = fingerprint hex
6. Create Consumer record with certificate fields populated
7. Return `client_id` + `client_secret` (one-time)

### Response

```json
{
  "total": 100,
  "success": 98,
  "failed": 2,
  "results": [
    {
      "row": 1,
      "status": "created",
      "external_id": "api-consumer-001",
      "consumer_id": "uuid-...",
      "client_id": "consumer-api-consumer-001",
      "client_secret": "one-time-secret-..."
    },
    {
      "row": 2,
      "status": "error",
      "external_id": "api-consumer-002",
      "error": "Certificate expired: NotAfter 2025-12-31T23:59:59Z"
    }
  ]
}
```

### Error Cases Per Row

| Condition | Row Status | Error Message |
|-----------|-----------|---------------|
| Invalid PEM | `error` | `Invalid PEM certificate` |
| Expired certificate | `error` | `Certificate expired: NotAfter {date}` |
| Duplicate `external_id` | `error` | `Consumer with external_id already exists` |
| Duplicate fingerprint | `error` | `Certificate fingerprint already registered` |
| Keycloak client creation failed | `error` | `Keycloak error: {detail}` |
| Missing required field | `error` | `Missing required field: {field}` |

## 7. Gateway Allowlist Sync Mechanism

The gateway needs to know which certificate fingerprints are valid, without querying the control plane on every request.

### Option A: Token-Based (Chosen)

The fingerprint is embedded in the JWT `cnf` claim by Keycloak. The gateway validates the binding between the presented certificate and the token — **no fingerprint registry needed at the gateway level**.

```
Keycloak (source of truth)
  │
  │ Issues JWT with cnf.x5t#S256 = <thumbprint>
  │ (via protocol mapper configured during consumer creation)
  │
  ▼
Gateway validates: cert_fingerprint == jwt.cnf.x5t#S256
```

This is the simplest and most secure approach:
- No sync lag (fingerprint is in the token itself)
- No additional API calls from the gateway
- Revocation = revoke the Keycloak client (token stops being issued)

### Option B: Push-Based Registry (Future, if needed)

If routes require mTLS without OAuth2 (pure certificate auth):
1. Control Plane API publishes fingerprint changes to Kafka topic `stoa.certificates`
2. Gateway consumes events, maintains in-memory `HashSet<String>` of valid fingerprints
3. Certificate presented → check fingerprint against local set
4. Refresh interval: real-time via Kafka consumer

This is deferred to a future phase — pure cert auth without tokens is not in current scope.

## 8. Migration Strategy

### Backward Compatibility

mTLS is fully opt-in. The feature is controlled by `STOA_MTLS_ENABLED` (default: `false`).

| Scenario | mTLS Config | Behavior |
|----------|-------------|----------|
| Existing deployment, no change | `enabled=false` | Zero overhead, identical to today |
| Enable mTLS globally | `enabled=true` | All routes accept optional mTLS |
| Require mTLS on specific routes | `enabled=true`, `required_routes=/api/v1/payments/*` | Only matching routes require cert |
| Require mTLS everywhere | `enabled=true`, `required_routes=/*` | All routes require cert |

### Rollout Plan

```
Phase 0 (current)
  └── No mTLS support in Rust gateway

Phase 2 (CAB-864 P2): Gateway mTLS Module
  ├── auth/mtls.rs: header extraction + binding verification
  ├── auth/claims.rs: add cnf field (Option, non-breaking)
  ├── auth/middleware.rs: insert stages 1 + 3
  ├── config.rs: MtlsConfig section
  ├── Cargo.toml: +subtle, +base64
  └── Tests: unit + integration

Phase 3 (CAB-864 P3): Bulk Onboarding
  ├── POST /v1/consumers/{tenant_id}/bulk endpoint
  ├── Keycloak cnf protocol mapper auto-config
  ├── Alembic migration 019 (cert fields on consumers)
  └── Tests: bulk endpoint + Keycloak mock

Phase 4 (CAB-864 P4): Production Enablement
  ├── F5 iRule configuration for X-SSL-* headers
  ├── NetworkPolicy: restrict X-SSL-* header sources
  ├── Vault PKI integration (real CA, not mock)
  ├── OCSP/CRL revocation checking (optional)
  └── Monitoring: Grafana dashboard for mTLS metrics
```

### Gateway Config Change (Phase 2 → Phase 4)

```yaml
# Phase 2: Dev/Staging — enabled, optional binding
STOA_MTLS_ENABLED=true
STOA_MTLS_REQUIRE_BINDING=false  # Log mismatches, don't reject

# Phase 3: Staging — enabled, required binding on test routes
STOA_MTLS_ENABLED=true
STOA_MTLS_REQUIRE_BINDING=true
STOA_MTLS_REQUIRED_ROUTES=/api/v1/test-mtls/*

# Phase 4: Production — full enforcement
STOA_MTLS_ENABLED=true
STOA_MTLS_REQUIRE_BINDING=true
STOA_MTLS_REQUIRED_ROUTES=/api/v1/payments/*,/api/v1/transfers/*
STOA_MTLS_TRUSTED_PROXIES=10.0.1.0/24  # F5 subnet
STOA_MTLS_ALLOWED_ISSUERS=CN=STOA Intermediate CA,O=STOA Platform,C=FR
```

## 9. Fingerprint Normalization Algorithm

Consistent with ADR-028 (Python `fingerprint_utils.py`), reimplemented in Rust:

```
Input: raw fingerprint string (from header or JWT claim)

Step 1: Detect format
  - Contains ':' → hex_colons format
  - Matches ^[a-fA-F0-9]{64}$ → hex format
  - Otherwise → base64url format

Step 2: Normalize to hex lowercase
  - hex_colons: strip ':', lowercase
  - hex: lowercase
  - base64url: decode → bytes → hex lowercase

Step 3: For RFC 8705 comparison
  - JWT cnf.x5t#S256 is base64url → decode to bytes
  - Header fingerprint is hex → decode to bytes
  - Compare bytes using subtle::ConstantTimeEq (timing-safe)
```

### Reference Test Vectors

These vectors MUST produce identical results in both Python and Rust implementations:

| Input | Format | Normalized Hex | Base64url |
|-------|--------|---------------|-----------|
| `a1:b2:c3:d4:e5:f6:...` (64 hex + 31 colons) | hex_colons | `a1b2c3d4e5f6...` | `obs...` |
| `A1B2C3D4E5F6...` (64 hex) | hex | `a1b2c3d4e5f6...` | `obs...` |
| `obsz...` (43 base64url chars) | base64url | `a1b2c3d4e5f6...` | `obs...` |

CI should run a shared test that feeds the same vectors to both `fingerprint_utils.py` and `auth/mtls.rs` and asserts identical output.

## 10. Observability

### Metrics (Prometheus)

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `stoa_mtls_requests_total` | Counter | `status={success,no_cert,invalid,expired,mismatch,denied}` | Total mTLS-processed requests |
| `stoa_mtls_binding_verification_duration_seconds` | Histogram | - | Time for fingerprint comparison |
| `stoa_mtls_certificates_seen` | Counter | `issuer`, `tenant` | Unique certificates presented |

### Structured Logs

```json
{
  "level": "info",
  "event": "mtls_binding_verified",
  "tenant": "acme",
  "consumer_external_id": "api-consumer-001",
  "cert_subject": "CN=api-consumer-001,OU=tenant-acme",
  "cert_issuer": "CN=STOA Intermediate CA",
  "cert_serial": "0A1B2C3D",
  "cert_not_after": "2027-01-15T00:00:00Z",
  "binding_match": true
}
```

**Never log**: certificate PEM, private keys, full fingerprint (truncate to first 8 chars in logs).
