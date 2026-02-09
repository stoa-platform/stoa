# Backup & Restore

## Backup Targets

| Component | Data | Method | Frequency |
|-----------|------|--------|-----------|
| PostgreSQL | Platform state (tenants, APIs, subscriptions) | `pg_dump` | Daily |
| Keycloak | Realm config, users, roles | Realm export | Daily |
| MinIO / S3 | API specs, artifacts | Bucket sync / `mc mirror` | Daily |
| Vault | Secrets (auto-snapshotted) | Raft snapshots | Hourly |

## PostgreSQL Backup

### Create Backup

```bash
# From a pod with psql access
kubectl exec -it deploy/control-plane-api -n stoa-system -- \
  pg_dump -h postgresql.stoa-system.svc -U stoa_app -d stoa \
  --format=custom --compress=9 \
  -f /tmp/stoa-backup-$(date +%Y%m%d).dump

# Copy to local
kubectl cp stoa-system/control-plane-api-<pod>:/tmp/stoa-backup-$(date +%Y%m%d).dump \
  ./backups/stoa-backup-$(date +%Y%m%d).dump
```

Or from a machine with direct DB access:

```bash
pg_dump -h <db-host> -U stoa_app -d stoa \
  --format=custom --compress=9 \
  -f stoa-backup-$(date +%Y%m%d).dump
```

### Restore Backup

```bash
# Drop and recreate (use with caution)
pg_restore -h <db-host> -U stoa_app -d stoa \
  --clean --if-exists \
  stoa-backup-20260209.dump

# Or restore to a different database first (safer)
createdb -h <db-host> -U stoa_app stoa_restore
pg_restore -h <db-host> -U stoa_app -d stoa_restore \
  stoa-backup-20260209.dump

# Then swap databases (requires superuser)
psql -h <db-host> -U postgres -c "
  SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='stoa';
  ALTER DATABASE stoa RENAME TO stoa_old;
  ALTER DATABASE stoa_restore RENAME TO stoa;"
```

### Post-Restore

After restoring the database, run Alembic to ensure schema is up to date:

```bash
kubectl exec -it deploy/control-plane-api -n stoa-system -- \
  alembic upgrade head
```

Then restart the API:

```bash
kubectl rollout restart deployment/control-plane-api -n stoa-system
```

## Keycloak Backup

### Export Realm

```bash
# Via Keycloak Admin API
curl -s -X POST "https://auth.<BASE_DOMAIN>/admin/realms/stoa/partial-export?exportClients=true&exportGroupsAndRoles=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -o keycloak-stoa-realm-$(date +%Y%m%d).json
```

Or via `kc.sh` in the Keycloak pod:

```bash
kubectl exec -it deploy/keycloak -n stoa-system -- \
  /opt/keycloak/bin/kc.sh export \
  --realm stoa \
  --dir /tmp/export

kubectl cp stoa-system/keycloak-<pod>:/tmp/export ./backups/keycloak/
```

### Import Realm

```bash
# Copy realm file to pod
kubectl cp keycloak-stoa-realm-20260209.json \
  stoa-system/keycloak-<pod>:/tmp/realm-import.json

# Import (creates or updates)
kubectl exec -it deploy/keycloak -n stoa-system -- \
  /opt/keycloak/bin/kc.sh import \
  --file /tmp/realm-import.json \
  --override true
```

> **Note**: Importing with `--override true` replaces existing realm configuration. Back up before importing.

## MinIO / S3 Backup

### Using MinIO Client (`mc`)

```bash
# Configure alias
mc alias set stoa-minio https://minio.<BASE_DOMAIN> <access-key> <secret-key>

# Mirror bucket to local
mc mirror stoa-minio/stoa-specs ./backups/minio/stoa-specs/
mc mirror stoa-minio/stoa-artifacts ./backups/minio/stoa-artifacts/
```

### Restore

```bash
mc mirror ./backups/minio/stoa-specs/ stoa-minio/stoa-specs/
mc mirror ./backups/minio/stoa-artifacts/ stoa-minio/stoa-artifacts/
```

## Disaster Recovery Procedure

### Full Platform Recovery

1. **Provision infrastructure** (EKS, RDS, S3 — via Terraform)
   ```bash
   cd stoa-infra/terraform/environments/prod
   terraform init && terraform apply
   ```

2. **Restore Vault** (from Raft snapshot)
   ```bash
   vault operator raft snapshot restore vault-snapshot-latest.snap
   ```

3. **Restore PostgreSQL** (from latest pg_dump)
   ```bash
   pg_restore -h <new-db-host> -U stoa_app -d stoa stoa-backup-latest.dump
   ```

4. **Restore Keycloak realm**
   ```bash
   # Import realm JSON via admin API or kc.sh
   ```

5. **Install STOA via Helm**
   ```bash
   helm upgrade --install stoa-platform ./charts/stoa-platform \
     -n stoa-system --create-namespace -f prod-values.yaml
   ```

6. **Restore MinIO data**
   ```bash
   mc mirror ./backups/minio/ stoa-minio/
   ```

7. **Run Alembic migrations**
   ```bash
   kubectl exec deploy/control-plane-api -n stoa-system -- alembic upgrade head
   ```

8. **Verify health**
   ```bash
   curl -s https://api.<BASE_DOMAIN>/health/ready
   curl -s https://mcp.<BASE_DOMAIN>/health
   ```

## Automated Backup Script

See `scripts/backup/` for automated backup scripts that can be run as CronJobs.

## Retention Policy

| Data | Retention | Storage |
|------|----------|---------|
| Database backups | 30 days | S3 (Glacier after 7 days) |
| Keycloak exports | 30 days | S3 |
| MinIO mirrors | 14 days | S3 |
| Vault snapshots | 90 days | S3 (encrypted) |
