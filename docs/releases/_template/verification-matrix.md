# Verification Matrix — STOA Platform vX.Y.Z

> Use this matrix after every upgrade. Every row MUST pass before declaring the upgrade successful.
> Automated version: `./scripts/release/verify-upgrade.sh`

## Environment Variables

```bash
export STOA_API_URL=https://api.<YOUR_DOMAIN>
export STOA_GATEWAY_URL=https://mcp.<YOUR_DOMAIN>
export STOA_AUTH_URL=https://auth.<YOUR_DOMAIN>
export STOA_CONSOLE_URL=https://console.<YOUR_DOMAIN>
export STOA_PORTAL_URL=https://portal.<YOUR_DOMAIN>
```

## Core Health (must pass on every upgrade)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 1 | Control Plane API | HTTP health | `curl -sf ${STOA_API_URL}/v1/health` | HTTP 200, JSON contains `"healthy"` |
| 2 | STOA Gateway | HTTP health | `curl -sf ${STOA_GATEWAY_URL}/health` | HTTP 200 |
| 3 | Keycloak | OIDC discovery | `curl -sf ${STOA_AUTH_URL}/realms/stoa/.well-known/openid-configuration` | HTTP 200, JSON contains `"issuer"` |
| 4 | Console UI | Frontend loads | `curl -sf -o /dev/null -w '%{http_code}' ${STOA_CONSOLE_URL}` | HTTP 200 |
| 5 | Portal | Frontend loads | `curl -sf -o /dev/null -w '%{http_code}' ${STOA_PORTAL_URL}` | HTTP 200 |

## MCP Protocol (must pass if gateway changed)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 6 | MCP Discovery | Capabilities endpoint | `curl -sf ${STOA_GATEWAY_URL}/mcp/capabilities` | HTTP 200, valid JSON |
| 7 | MCP Tools | Tool listing | `curl -sf -X POST ${STOA_GATEWAY_URL}/mcp/tools/list` | HTTP 200, JSON with `tools` array |
| 8 | OAuth Discovery | Protected resource | `curl -sf ${STOA_GATEWAY_URL}/.well-known/oauth-protected-resource` | HTTP 200, JSON with `authorization_servers` |

## Auth Chain (must pass if auth/gateway changed)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 9 | Token Endpoint | Client credentials grant | `curl -sf -X POST ${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token -d 'grant_type=client_credentials&client_id=<CLIENT>&client_secret=<SECRET>'` | HTTP 200, `access_token` in response |
| 10 | Authenticated API | Token-protected endpoint | `curl -sf -H "Authorization: Bearer <TOKEN>" ${STOA_API_URL}/v1/tenants` | HTTP 200 or 403 (not 401) |

## Kubernetes (must pass on every upgrade)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 11 | Pod Status | All pods running | `kubectl get pods -n stoa-system --no-headers \| grep -v Running` | Empty output |
| 12 | No CrashLoops | Zero crash loops | `kubectl get pods -n stoa-system --no-headers \| grep CrashLoopBackOff` | Empty output |
| 13 | Recent Restarts | No excessive restarts | `kubectl get pods -n stoa-system -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount}{"\n"}{end}' \| awk '$2 > 3'` | Empty output |
| 14 | ArgoCD Sync | Apps synced | `kubectl get applications -n argocd -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status'` | All rows show "Synced" |

## Version Confirmation (must pass on every upgrade)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 15 | API Version | Correct image tag | `kubectl get deploy/control-plane-api -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].image}'` | Contains expected version tag |
| 16 | Gateway Version | Correct image tag | `kubectl get deploy/stoa-gateway -n stoa-system -o jsonpath='{.spec.template.spec.containers[0].image}'` | Contains expected version tag |
| 17 | Helm Release | Correct chart version | `helm list -n stoa-system -o json \| jq '.[0].chart'` | Shows expected chart version |

## Error Rate (check 15 min post-upgrade)

| # | Component | Check | Command | Pass Criteria |
|---|-----------|-------|---------|---------------|
| 18 | API Logs | No error spike | `kubectl logs -n stoa-system deploy/control-plane-api --since=15m \| grep -c ERROR` | < 5 errors |
| 19 | Gateway Logs | No error spike | `kubectl logs -n stoa-system deploy/stoa-gateway --since=15m \| grep -c ERROR` | < 5 errors |

## Version-Specific Tests (vX.Y.Z)

<!-- Add rows for features/changes introduced in this specific version. -->
<!-- Copy from the "What's New" document and add verification commands. -->

| # | Feature | Check | Command | Pass Criteria |
|---|---------|-------|---------|---------------|
| — | _Example: New /v1/foo endpoint_ | _Endpoint responds_ | `curl -sf ${STOA_API_URL}/v1/foo` | _HTTP 200_ |

## Quick Automated Check

```bash
# Full verification (HTTP + K8s + ArgoCD)
./scripts/release/verify-upgrade.sh

# HTTP-only (no kubectl required)
./scripts/release/verify-upgrade.sh --skip-k8s

# Custom domain
./scripts/release/verify-upgrade.sh --base-domain example.com

# Specific version check
./scripts/release/verify-upgrade.sh --expected-version v2.1.0
```
