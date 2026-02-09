# Upgrade

## Pre-Upgrade Checklist

- [ ] Back up PostgreSQL database (see [backup-restore.md](backup-restore.md))
- [ ] Back up Keycloak realm export
- [ ] Note current Helm revision: `helm history stoa-platform -n stoa-system`
- [ ] Check Kyverno policies are compatible: `kubectl get cpol -A`
- [ ] Review release notes for breaking changes
- [ ] Verify CRD changes (if any): `diff charts/stoa-platform/crds/ <previous-version>`
- [ ] Notify users of maintenance window (if JWT secret rotation needed)

## Upgrade Procedure

### Step 1 — Update CRDs (if changed)

CRDs are not managed by Helm upgrades. Apply them manually before upgrading:

```bash
kubectl apply -f charts/stoa-platform/crds/
```

### Step 2 — Helm Upgrade

```bash
# Dry-run first
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f my-values.yaml \
  --dry-run

# Apply
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f my-values.yaml
```

### Step 3 — Run Database Migrations

```bash
kubectl exec -it deploy/control-plane-api -n stoa-system -- \
  alembic upgrade head
```

Verify migration state:

```bash
kubectl exec deploy/control-plane-api -n stoa-system -- \
  alembic current
```

### Step 4 — Verify Pods

```bash
# Watch rollout
kubectl rollout status deployment/control-plane-api -n stoa-system
kubectl rollout status deployment/mcp-gateway -n stoa-system
kubectl rollout status deployment/control-plane-ui -n stoa-system
kubectl rollout status deployment/portal -n stoa-system

# All pods running
kubectl get pods -n stoa-system
```

### Step 5 — Post-Upgrade Verification

```bash
# Health checks
curl -s https://api.<BASE_DOMAIN>/health/ready
curl -s https://mcp.<BASE_DOMAIN>/health

# Verify image versions
kubectl get deploy -n stoa-system -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'

# Run smoke tests (if E2E available)
cd e2e && npx playwright test --grep @smoke
```

## Rollback

If the upgrade fails:

```bash
# Check Helm history
helm history stoa-platform -n stoa-system

# Rollback to previous revision
helm rollback stoa-platform <revision> -n stoa-system

# Verify rollback
kubectl get pods -n stoa-system
curl -s https://api.<BASE_DOMAIN>/health/ready
```

> **Warning**: If Alembic migrations were applied, database rollback requires running `alembic downgrade -1` before Helm rollback. Check if the previous code version is compatible with the new schema.

### Database Migration Rollback

```bash
# Downgrade one migration
kubectl exec deploy/control-plane-api -n stoa-system -- \
  alembic downgrade -1

# Verify current state
kubectl exec deploy/control-plane-api -n stoa-system -- \
  alembic current
```

## Version Compatibility

| Component | Upgrade Path | Notes |
|-----------|-------------|-------|
| Control Plane API | Any → latest | Always run Alembic after upgrade |
| MCP Gateway | Any → latest | OPA policies may need updating |
| Console UI | Any → latest | Static assets, no state |
| Portal | Any → latest | Static assets, no state |
| STOA Gateway | Any → latest | Zero-downtime with rolling update |
| Keycloak | Minor versions only | Major upgrades require migration guide |

## Upgrading Keycloak

Keycloak upgrades require special care:

1. Export the `stoa` realm before upgrading
2. Follow the [Keycloak upgrade guide](https://www.keycloak.org/docs/latest/upgrading/) for your version
3. Test the upgrade in a staging environment first
4. Import the realm if needed after upgrade

## Upgrading PostgreSQL

Major PostgreSQL upgrades (e.g., 15 → 16):

1. Back up with `pg_dump` (logical backup — portable across versions)
2. Provision new PostgreSQL instance
3. Restore from dump: `pg_restore`
4. Update `DATABASE_URL` in Vault
5. Force ESO sync and restart pods
6. Verify connectivity
