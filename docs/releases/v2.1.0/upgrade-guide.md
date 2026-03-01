# Upgrade Guide — STOA Platform v1.0.0 to v2.1.0

> Estimated downtime: ~5 min (rolling update, multiple components)
> Risk level: Medium (new services, database migrations)
> Rollback: Supported via Helm rollback + Alembic downgrade

## Prerequisites

| Requirement | Minimum | Check Command |
|-------------|---------|---------------|
| Kubernetes | 1.28+ | `kubectl version --short` |
| Helm | 3.14+ | `helm version --short` |
| Rust toolchain | stable (1.90+) | `rustc --version` (dev only) |
| Python | 3.11 | `python3 --version` (dev only) |
| Node | 20 | `node --version` (dev only) |
| Database backup | PostgreSQL snapshot | `pg_dump` or cloud snapshot |

## Breaking Changes

### Critical

_None._

### High

| Component | Change | Migration |
|-----------|--------|-----------|
| Gateway | mTLS bypass paths expanded for OAuth/MCP | Review mTLS config if custom bypass list was set |
| Gateway | DCR scope stripping (Keycloak PKCE fix) | No action if using standard Keycloak setup |

### Medium

| Component | Change | Migration |
|-----------|--------|-----------|
| API | New `POST /v1/tenants/provision` requires `stoa:admin` role | Ensure admin role configured in Keycloak |
| API | Tenant usage limits table added | Run `alembic upgrade head` |
| Gateway | Skills system requires admin endpoints enabled | Set `ADMIN_ENABLED=true` in gateway config |
| Helm | `stoaGateway.llmProxy` values section added | Add to values if using LLM proxy feature |

### Low

| Component | Change | Migration |
|-----------|--------|-----------|
| Portal | New signup page at `/signup` | No action (additive) |
| Arena | Enterprise benchmark CronJob added | Apply `k8s/arena/cronjob-enterprise.yaml` if using arena |

## Step 1 — Pre-Upgrade Checks

```bash
# Verify current state
kubectl get pods -n stoa-system
helm list -n stoa-system
kubectl exec -n stoa-system deploy/control-plane-api -- alembic current
```

## Step 2 — Database Migrations

```bash
kubectl exec -n stoa-system deploy/control-plane-api -- alembic upgrade head
```

New tables: `tenant_usage_limits`, `contracts`, `system_info`.

## Step 3 — Upgrade

```bash
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values-prod.yaml \
  --wait --timeout 5m
```

## Step 4 — Verify

### Verification Matrix

| # | Component | What to Test | Command | Pass |
|---|-----------|-------------|---------|------|
| 1 | API Health | Service responds | `curl -sf ${STOA_API_URL}/v1/health` | 200 |
| 2 | Gateway Health | Service responds | `curl -sf ${STOA_GATEWAY_URL}/health` | 200 |
| 3 | Auth Chain | Token works | `curl -sf -X POST ${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token -d '...'` | 200 + token |
| 4 | MCP Discovery | Capabilities | `curl -sf ${STOA_GATEWAY_URL}/mcp/capabilities` | 200 + JSON |
| 5 | MCP Tools | Tool listing | `curl -sf -X POST ${STOA_GATEWAY_URL}/mcp/tools/list` | 200 + tools array |
| 6 | Console UI | Loads | `curl -sf ${STOA_CONSOLE_URL} -o /dev/null -w '%{http_code}'` | 200 |
| 7 | Portal | Loads | `curl -sf ${STOA_PORTAL_URL} -o /dev/null -w '%{http_code}'` | 200 |
| 8 | Signup | New page | `curl -sf ${STOA_PORTAL_URL}/signup -o /dev/null -w '%{http_code}'` | 200 |
| 9 | System Info | New endpoint | `curl -sf ${STOA_API_URL}/v1/system/info` | 200 + edition field |
| 10 | Pod Status | No restarts | `kubectl get pods -n stoa-system --no-headers \| grep -v Running` | Empty |

### Automated Verification

```bash
./scripts/release/verify-upgrade.sh
```

## Step 5 — Post-Upgrade

- [ ] Verify Grafana dashboards (new LLM token tracking dashboard)
- [ ] Check Arena benchmark CronJobs (if applicable)
- [ ] Confirm no alerts in last 15 minutes
- [ ] Update tenant admin roles in Keycloak for self-service provisioning

## Rollback

```bash
# Helm rollback
helm rollback stoa-platform -n stoa-system

# Database rollback (if needed)
kubectl exec -n stoa-system deploy/control-plane-api -- alembic downgrade -1
```

## Known Issues

See [Known Issues](../known-issues.md).
