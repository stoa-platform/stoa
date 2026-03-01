# Upgrade Guide — STOA Platform vX.Y.W to vX.Y.Z

> Estimated downtime: ~2 min per component (rolling update)
> Risk level: Low | Medium | High
> Rollback: Supported (see bottom of this guide)

## Prerequisites

| Requirement | Minimum | Check Command |
|-------------|---------|---------------|
| Kubernetes | 1.28+ | `kubectl version --short` |
| Helm | 3.14+ | `helm version --short` |
| kubectl access | stoa-system namespace | `kubectl get pods -n stoa-system` |
| Backup | Database snapshot taken | `pg_dump` or RDS snapshot |

## Pre-Upgrade Checklist

- [ ] Read [Breaking Changes](./breaking-changes.md) for this version
- [ ] Database backup completed
- [ ] Current version confirmed: `helm list -n stoa-system`
- [ ] All pods healthy: `kubectl get pods -n stoa-system` (no CrashLoopBackOff)
- [ ] Monitoring dashboard open (Grafana)

## Step 1 — Update Helm Values (if needed)

Check [Breaking Changes](./breaking-changes.md) for any values changes.

```bash
# Compare your current values with new defaults
helm get values stoa-platform -n stoa-system > /tmp/current-values.yaml
helm show values ./charts/stoa-platform > /tmp/new-defaults.yaml
diff /tmp/current-values.yaml /tmp/new-defaults.yaml
```

## Step 2 — Apply Database Migrations (if needed)

```bash
# Check if migrations are pending
kubectl exec -n stoa-system deploy/control-plane-api -- alembic current
kubectl exec -n stoa-system deploy/control-plane-api -- alembic heads

# Apply migrations (if heads != current)
kubectl exec -n stoa-system deploy/control-plane-api -- alembic upgrade head
```

## Step 3 — Upgrade

### Option A: Helm Upgrade (recommended)

```bash
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values-prod.yaml \
  --wait --timeout 5m
```

### Option B: Image-Only Update (hotfix)

```bash
# Per-component image update
kubectl set image deployment/control-plane-api \
  control-plane-api=ghcr.io/stoa-platform/control-plane-api:vX.Y.Z \
  -n stoa-system

kubectl set image deployment/stoa-gateway \
  stoa-gateway=ghcr.io/stoa-platform/stoa-gateway:vX.Y.Z \
  -n stoa-system
```

## Step 4 — Verify Upgrade

Run the automated verification:

```bash
./scripts/release/verify-upgrade.sh
```

Or verify manually — **all checks must pass**:

### Verification Matrix

| # | Component | What to Test | Command | Pass Criteria |
|---|-----------|-------------|---------|---------------|
| 1 | API Health | Service responds | `curl -sf ${STOA_API_URL}/v1/health` | HTTP 200, `{"status":"healthy"}` |
| 2 | Gateway Health | Service responds | `curl -sf ${STOA_GATEWAY_URL}/health` | HTTP 200 |
| 3 | Auth Chain | Token endpoint works | `curl -sf -X POST ${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token -d 'grant_type=client_credentials&client_id=...'` | HTTP 200, `access_token` present |
| 4 | MCP Discovery | MCP capabilities | `curl -sf ${STOA_GATEWAY_URL}/mcp/capabilities` | HTTP 200, valid JSON |
| 5 | Console UI | Frontend loads | `curl -sf ${STOA_CONSOLE_URL} -o /dev/null -w '%{http_code}'` | HTTP 200 |
| 6 | Portal | Frontend loads | `curl -sf ${STOA_PORTAL_URL} -o /dev/null -w '%{http_code}'` | HTTP 200 |
| 7 | Pod Status | No restarts | `kubectl get pods -n stoa-system --no-headers \| grep -v Running` | Empty output |
| 8 | ArgoCD Sync | Apps synced | `kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.metadata.name}: {.status.sync.status}\n{end}'` | All "Synced" |
| 9 | Logs Clean | No errors post-upgrade | `kubectl logs -n stoa-system deploy/control-plane-api --since=5m \| grep -c ERROR` | 0 |

### New Features to Test (vX.Y.Z specific)

<!-- Add version-specific tests here. Example: -->

| Feature | Test | Pass Criteria |
|---------|------|---------------|
| New endpoint `/v1/example` | `curl ${STOA_API_URL}/v1/example` | HTTP 200, returns expected schema |

## Step 5 — Post-Upgrade

- [ ] Verify Grafana dashboards show normal metrics
- [ ] Check error rate in the last 15 minutes
- [ ] Confirm no alerts fired
- [ ] Update deployment documentation if config changed

## Rollback Procedure

If any verification check fails:

```bash
# Option A: Helm rollback
helm rollback stoa-platform -n stoa-system

# Option B: Image rollback (per-component)
kubectl set image deployment/control-plane-api \
  control-plane-api=ghcr.io/stoa-platform/control-plane-api:vPREVIOUS \
  -n stoa-system

# If database migration was applied, rollback:
kubectl exec -n stoa-system deploy/control-plane-api -- alembic downgrade -1
```

Verify rollback succeeded using the same verification matrix above.

## Known Issues in This Release

See [Known Issues](../known-issues.md) for current known issues and workarounds.
