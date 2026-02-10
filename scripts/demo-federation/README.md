# STOA Federation Demo — Multi-IAM Zero User Storage (ADR-026)

Proves that N organizations with N different IAMs can share APIs through STOA without storing a single user record centrally.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│              Keycloak (single instance)               │
│  ┌───────────────┐ ┌───────────────┐                 │
│  │idp-source-alpha│ │idp-source-beta│  (IdP sources)  │
│  │  OIDC users   │ │  SAML users   │                 │
│  └───────┬───────┘ └───────┬───────┘                 │
│          │ OIDC broker     │ SAML broker              │
│  ┌───────▼───────┐ ┌──────▼────────┐ ┌─────────────┐│
│  │demo-org-alpha │ │demo-org-beta  │ │demo-org-gamma││
│  │(OIDC federated)│ │(SAML federated)│ │(LDAP federated)│
│  └───────────────┘ └───────────────┘ └──────┬──────┘│
└──────────────────────────────────────────────┼───────┘
                                               │
    ┌─────────────────────────────────────┐    │
    │       Mock Gateway (:9000)          │    │
    │  Validates JWT issuer per tenant    │    │
    └─────────────────────────────────────┘    │
                                          ┌────▼─────┐
                                          │ OpenLDAP │
                                          └──────────┘
```

## Prerequisites

- Docker and Docker Compose
- `curl` and `python3` (for scripts)
- `jq` (optional, for manual inspection)

## Quick Start

### Option A: Integrated with main STOA stack (recommended for demo)

```bash
# 1. Start the full platform with federation
cd deploy/docker-compose
docker compose --profile federation up -d

# 2. Seed LDAP + verify realms
./scripts/demo-federation/00-setup-integrated.sh

# 3. Run the isolation test (the money shot)
./scripts/demo-federation/04-test-isolation.sh
```

### Option B: Standalone (for isolated testing)

```bash
# 1. Start the standalone federation stack
./scripts/demo-federation/00-setup.sh

# 2. Run the isolation test
./scripts/demo-federation/04-test-isolation.sh

# 3. Clean up
./scripts/demo-federation/99-cleanup.sh
```

## Step-by-Step Walkthrough (5 min)

### 1. Setup

```bash
./00-setup.sh
```

Starts Keycloak (5 realms), OpenLDAP, mock gateway, and OPA. Triggers LDAP sync for gamma.

### 2. Login as each org

```bash
./01-login.sh alpha demo-alpha demo    # OIDC org
./01-login.sh beta  demo-beta  demo    # SAML org
./01-login.sh gamma eve-gamma  demo    # LDAP org
```

Each returns a JWT with `stoa_realm` claim matching the org's realm.

### 3. Token Exchange (RFC 8693)

```bash
./02-exchange.sh alpha
```

Exchanges user token for a scoped API token with restricted audience. Falls back gracefully if Keycloak's token-exchange preview is not active.

### 4. Call API

```bash
./03-call-api.sh alpha   # → 200 OK, shows claims
./03-call-api.sh beta    # → 200 OK
./03-call-api.sh gamma   # → 200 OK
```

### 5. Prove Isolation (the money shot)

```bash
./04-test-isolation.sh
```

Expected output:
```
Step 2: Positive tests (same-realm → should succeed)
  PASS Alpha token → Alpha API → 200
  PASS Beta token  → Beta API  → 200
  PASS Gamma token → Gamma API → 200

Step 3: Negative tests (cross-realm → must be denied)
  PASS Alpha token → Beta API  (cross-realm) → 403
  PASS Alpha token → Gamma API (cross-realm) → 403
  PASS Beta token  → Alpha API (cross-realm) → 403
  PASS Beta token  → Gamma API (cross-realm) → 403
  PASS Gamma token → Alpha API (cross-realm) → 403
  PASS Gamma token → Beta API  (cross-realm) → 403

Results: 9/9 passed
ISOLATION VERIFIED — Zero User Storage Federation works.
```

### 6. STOA Integration

```bash
./05-stoa-integration.sh
```

Shows OPA policy evaluation, realm inventory, and the STOA value-add beyond raw Keycloak.

### 7. Cleanup

```bash
./99-cleanup.sh
```

## What This Proves

| Claim | Evidence |
|-------|----------|
| 1 Realm = 1 Organization | 3 separate tenant realms, isolated |
| Zero User Storage | Org realms have no local users (alpha/beta use IdP broker, gamma uses LDAP federation) |
| Protocol Diversity | OIDC, SAML 2.0, LDAP — all working |
| Token Exchange (RFC 8693) | User token → scoped API token |
| Cross-Realm Isolation | 6 negative tests all return 403 |

## Browser SSO Flows

The demo scripts use direct-grant (password) for automation. In production, users authenticate via browser SSO:

1. User visits portal
2. Redirected to their org's IdP (Azure AD, Okta, on-prem LDAP via Keycloak login page)
3. Authenticated via SSO
4. Brokered back to STOA realm
5. Same token flow from there

To test manually: visit `http://localhost:8080/realms/demo-org-alpha/account` and click the IdP login button.

## From Federation to API Management (STOA Value)

Raw Keycloak gives you federation. STOA gives you **API-lifecycle-aware federation**:

1. **API Subscriptions** — Org A's token only accesses APIs Org A subscribed to
2. **Metering per Realm** — Usage tracked per organization
3. **OPA Policies** — Formal, auditable isolation (not just gateway code)
4. **MCP-Native** — AI agents inherit the same federation model
5. **GitOps Realms** — Realm configs as code, applied via CI/CD

## Live Demo (2 min — Act 5)

### Pre-Flight Checklist

```bash
# 1. Start the stack (allow ~60s for Keycloak cold start)
make demo-federation-setup

# 2. Verify isolation works before going on stage
make demo-federation-test

# 3. Run the presenter script
make demo-federation-live

# 4. Cleanup after demo
make demo-federation-cleanup
```

### Timing

| Phase | Duration | What happens |
|-------|----------|-------------|
| 1. Auth | ~15s | Silent login for 3 orgs (OIDC, SAML, LDAP) |
| 2. Same-realm | ~20s | 3 green checkmarks (each org accesses its own API) |
| 3. Cross-realm | ~45s | 6 red X with issuer mismatch reasons |
| 4. Verdict | ~10s | ASCII art "ISOLATION VERIFIED" banner |

### Presenter Notes

- Run `make demo-federation-setup` **before** going on stage (Keycloak takes ~45s to start)
- The live demo script (`06-live-demo.sh`) is self-contained: authenticates, tests, and shows verdict
- If a test fails, the script exits with code 1 and shows "ISOLATION BROKEN" — fix before presenting
- Key message: *"Un login, tous vos tenants — souverainete europeenne"*

## Known Issues

| Issue | Symptom | Workaround |
|-------|---------|------------|
| LDAP seed flakiness | `ldapadd` fails on first attempt | Script retries 5 times with 2s delay |
| Token exchange not active | Keycloak preview feature disabled | Script falls back to user token — isolation demo still works |
| Port 8080 conflict | Keycloak fails to start | Stop other services on 8080, or set `KEYCLOAK_URL=http://localhost:8081` |
| OPA AMD64 only | OPA container fails on Apple Silicon | OPA is optional — isolation test works without it (gateway-level validation) |
| Keycloak cold start | First startup imports 5 realms (~45-60s) | Subsequent starts are faster (~15s); just wait |

## Troubleshooting

```bash
# Check all containers are running
docker compose -f deploy/demo-federation/docker-compose.yml ps

# Check Keycloak logs (realm import issues)
docker logs stoa-federation-keycloak 2>&1 | tail -20

# Check gateway logs (JWT validation issues)
docker logs stoa-federation-gateway 2>&1 | tail -20

# Check LDAP is seeded
docker exec stoa-federation-ldap ldapsearch -x -H ldap://localhost:389 \
  -D "cn=admin,dc=demo,dc=stoa" -w "admin-password" -b "ou=users,dc=demo,dc=stoa"

# Manual token test
TOKEN=$(cat scripts/demo-federation/.tokens/alpha.token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:9000/api/alpha/whoami
```

## File Structure

```
deploy/demo-federation/
├── docker-compose.yml
├── .env.example
├── keycloak/
│   ├── idp-source-alpha.json    # OIDC identity source
│   ├── idp-source-beta.json     # SAML identity source
│   ├── demo-org-alpha.json      # Tenant (OIDC federation)
│   ├── demo-org-beta.json       # Tenant (SAML federation)
│   └── demo-org-gamma.json      # Tenant (LDAP federation)
├── openldap/
│   └── seed.ldif                # Test users for gamma
└── gateway/
    ├── server.py                # Mock JWT validator
    └── policy.rego              # OPA isolation policy

scripts/demo-federation/
├── 00-setup.sh                  # Start standalone stack
├── 00-setup-integrated.sh       # Seed LDAP for integrated stack
├── 01-login.sh                  # Get token
├── 02-exchange.sh               # Token exchange
├── 03-call-api.sh               # Call API
├── 04-test-isolation.sh         # Prove isolation
├── 05-stoa-integration.sh       # STOA value-add
├── 06-live-demo.sh              # 2-min presenter script
├── 99-cleanup.sh                # Tear down
└── README.md                    # This file
```

## Reference

- [ADR-026: Multi-IAM Federation Pattern](https://docs.gostoa.dev/architecture/adr/adr-026-multi-iam-federation)
- [RFC 8693: OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693)
- Linear: CAB-1012
