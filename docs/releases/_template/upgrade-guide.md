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
# Full verification (HTTP + Kubernetes + ArgoCD)
./scripts/release/verify-upgrade.sh

# HTTP-only (no kubectl required)
./scripts/release/verify-upgrade.sh --skip-k8s

# With version confirmation
./scripts/release/verify-upgrade.sh --expected-version vX.Y.Z

# Single component
./scripts/release/verify-upgrade.sh --component api

# Machine-readable output
./scripts/release/verify-upgrade.sh --json
```

Or verify manually — see the full [Verification Matrix](./verification-matrix.md) for all checks.

### Quick Manual Checks

| # | Component | Command | Pass Criteria |
|---|-----------|---------|---------------|
| 1 | API | `curl -sf ${STOA_API_URL}/v1/health` | HTTP 200 |
| 2 | Gateway | `curl -sf ${STOA_GATEWAY_URL}/health` | HTTP 200 |
| 3 | Auth | `curl -sf ${STOA_AUTH_URL}/realms/stoa/.well-known/openid-configuration` | `"issuer"` present |
| 4 | Console | `curl -sf -o /dev/null -w '%{http_code}' ${STOA_CONSOLE_URL}` | `200` |
| 5 | Portal | `curl -sf -o /dev/null -w '%{http_code}' ${STOA_PORTAL_URL}` | `200` |
| 6 | MCP | `curl -sf ${STOA_GATEWAY_URL}/mcp/capabilities` | Valid JSON |
| 7 | Pods | `kubectl get pods -n stoa-system --no-headers \| grep -v Running` | Empty |

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
