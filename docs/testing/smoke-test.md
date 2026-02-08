# Smoke Test Gate (Level 1) -- CAB-1043

Autonomous curl-based smoke test that validates the STOA platform is functional
before declaring a cycle Done.

## How to Run

```bash
# Default (gostoa.dev)
npm run test:smoke

# Custom domain
BASE_DOMAIN=staging.gostoa.dev bash scripts/smoke-test.sh

# Local docker-compose
BASE_DOMAIN=localhost:8080 bash scripts/smoke-test.sh
```

## Prerequisites

The script requires only standard Unix tools:

- `curl` -- HTTP requests
- `jq` -- JSON parsing
- `openssl` -- TLS certificate validation
- `dig` -- DNS resolution checks

No npm/node dependency is required. The `npm run test:smoke` script simply delegates
to `bash scripts/smoke-test.sh`.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | `gostoa.dev` | Base domain for all services |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm name |
| `KEYCLOAK_CLIENT` | `stoa-portal` | OIDC client_id for token requests |
| `ALEX_USER` | _(none)_ | Username for alex persona |
| `ALEX_PASSWORD` | _(none)_ | Password for alex persona |
| `PARZIVAL_USER` | _(none)_ | Username for parzival persona |
| `PARZIVAL_PASSWORD` | _(none)_ | Password for parzival persona |
| `SORRENTO_USER` | _(none)_ | Username for sorrento persona |
| `SORRENTO_PASSWORD` | _(none)_ | Password for sorrento persona |
| `MIN_CATALOGUE_APIS` | `12` | Minimum APIs expected in catalogue |

## Audit Checks

| ID | Check | What it Verifies | Blocking |
|----|-------|------------------|----------|
| AUDIT-1 | Portal HTTP 200 | Portal frontend serves the SPA | Yes |
| AUDIT-2 | Keycloak OIDC 200 | Keycloak realm OIDC discovery endpoint responds | Yes |
| AUDIT-3 | MCP Gateway 200 | MCP Gateway /health (or /sse fallback) responds | No |
| AUDIT-4 | Control Plane API 200 | Control Plane API /health responds | No |
| AUDIT-5 | Catalogue >= 12 APIs | Portal catalogue endpoint returns at least 12 APIs | No |
| AUDIT-6 | Tokens (alex/parzival/sorrento) | Token acquisition via password grant for all 3 personas | Yes |
| AUDIT-7 | DNS 4/4 | DNS resolution for portal/api/mcp/auth subdomains | No |
| AUDIT-8 | TLS certificates valid | TLS certificates for all 4 subdomains are not expired | No |

## Gate Verdict

- **GATE PASSED**: All 8/8 checks pass.
- **GATE FAILED**: Any check fails.
- **Blocking checks** (AUDIT-1, AUDIT-2, AUDIT-6): These represent fundamental platform
  functionality. If any blocking check fails, the gate fails regardless of score.

## Output Format

```
AUDIT-1  Portal HTTP 200 .............. PASS (234ms)
AUDIT-2  Keycloak OIDC ................ PASS (156ms)
AUDIT-3  MCP Gateway .................. FAIL (HTTP 503)
...
SCORE: 7/8 -- GATE FAILED (minimum 8/8)
```

## Threshold for Cycle Done

A cycle can only be declared Done when the smoke test gate passes with 8/8.
Blocking checks (AUDIT-1, AUDIT-2, AUDIT-6) are auto-fail: even if the numeric
score were to reach 8/8 through some other means, a blocking failure still
causes GATE FAILED.

## Local vs Cluster Mode

- **Cluster mode** (default): Uses `https://` and subdomains of `BASE_DOMAIN`.
  DNS and TLS checks run against real infrastructure.
- **Local mode**: Set `BASE_DOMAIN=localhost:8080` (or similar). The script
  automatically switches to `http://` and skips TLS checks (AUDIT-8 will FAIL
  with "skipped (non-https)").
