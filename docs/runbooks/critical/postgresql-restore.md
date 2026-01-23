# PostgreSQL Database Restore Runbook

> **Severity**: Critical
> **Tickets**: CAB-853
> **MTTR Target**: < 1 hour
> **Last Updated**: 2026-01-23

## Overview

This runbook describes the procedure to restore the STOA Control-Plane PostgreSQL database from S3 backups.

## When to Use

- Database corruption
- Accidental data deletion
- Disaster recovery
- Migration to new cluster
- Recovery from failed upgrade

---

## Prerequisites

- [ ] AWS CLI configured with appropriate permissions
- [ ] `kubectl` access to the cluster
- [ ] Access to backup S3 bucket (`stoa-backups`)
- [ ] Access to `stoa-system` namespace
- [ ] Slack notification sent to `#ops-alerts`

---

## 1. Symptoms

### Indicators
- Control-Plane API returns 500 errors
- Database connection failures
- Missing tenants, APIs, or users
- Authentication failures

### Alerts
- `PostgresDown`
- `ControlPlaneAPIUnhealthy`
- `DatabaseConnectionFailed`

---

## 2. Quick Diagnosis (< 5 min)

```bash
# Check PostgreSQL pod status
kubectl get pods -n stoa-system -l app=control-plane-db

# Check PostgreSQL logs
kubectl logs -n stoa-system control-plane-db-0 --tail=100

# Test database connection
kubectl exec -n stoa-system control-plane-db-0 -- \
  psql -U stoa -d stoa -c "SELECT 1;"

# Check database size
kubectl exec -n stoa-system control-plane-db-0 -- \
  psql -U stoa -d stoa -c "SELECT pg_size_pretty(pg_database_size('stoa'));"
```

---

## 3. List Available Backups

```bash
# Using the backup script (recommended)
S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 \
  ./scripts/backup/backup-postgres.sh --list

# Or directly with AWS CLI
aws s3 ls s3://stoa-backups/postgres/ --recursive | sort -r | head -10
```

### Backup Information
- **Bucket**: `s3://stoa-backups/postgres/`
- **Format**: `YYYY-MM-DD/stoa_backup_YYYYMMDD_HHMMSS.sql.gz`
- **Schedule**: Daily at 02:00 UTC
- **Retention**: 7 days

---

## 4. Pre-Restore Preparation

### 4.1 Notify Team

```bash
# Send Slack notification
curl -X POST -H 'Content-type: application/json' \
  --data '{"channel": "#ops-alerts", "text": ":rotating_light: Starting PostgreSQL restore - Control-Plane API will be unavailable"}' \
  "$SLACK_WEBHOOK_URL"
```

### 4.2 Create Pre-Restore Backup

```bash
# Safety backup before restore
S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 \
  ./scripts/backup/backup-postgres.sh

# Note the backup path for rollback if needed
```

### 4.3 Scale Down Control-Plane API

```bash
# Stop writes to database during restore
kubectl scale deployment control-plane-api -n stoa-system --replicas=0

# Verify pods are terminated
kubectl get pods -n stoa-system -l app=control-plane-api
```

---

## 5. Restore Procedure

### Option A: Using Restore Script (Recommended)

```bash
# Restore from specific backup
S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 \
  ./scripts/backup/backup-postgres.sh \
  --restore s3://stoa-backups/postgres/2026-01-23/stoa_backup_20260123_020003.sql.gz

# With force flag (no confirmation prompt)
S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 \
  ./scripts/backup/backup-postgres.sh \
  --restore s3://stoa-backups/postgres/2026-01-23/stoa_backup_20260123_020003.sql.gz \
  --force
```

### Option B: Manual Restore

```bash
# 1. Download backup
BACKUP_PATH="postgres/2026-01-23/stoa_backup_20260123_020003.sql.gz"
aws s3 cp "s3://stoa-backups/$BACKUP_PATH" /tmp/backup.sql.gz

# 2. Verify integrity
gunzip -t /tmp/backup.sql.gz

# 3. Copy to PostgreSQL pod
kubectl cp /tmp/backup.sql.gz stoa-system/control-plane-db-0:/tmp/backup.sql.gz

# 4. Restore database
kubectl exec -n stoa-system control-plane-db-0 -- bash -c \
  "gunzip -c /tmp/backup.sql.gz | psql -U stoa -d stoa"

# 5. Cleanup
kubectl exec -n stoa-system control-plane-db-0 -- rm -f /tmp/backup.sql.gz
rm /tmp/backup.sql.gz
```

### 5.1 Scale Up Control-Plane API

```bash
# Restart Control-Plane API
kubectl scale deployment control-plane-api -n stoa-system --replicas=2

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app=control-plane-api -n stoa-system --timeout=300s
```

---

## 6. Verification

### 6.1 Check Database Status

```bash
# Verify tables exist
kubectl exec -n stoa-system control-plane-db-0 -- \
  psql -U stoa -d stoa -c "\dt"

# Expected: 25 tables
```

### 6.2 Verify Record Counts

```bash
kubectl exec -n stoa-system control-plane-db-0 -- \
  psql -U stoa -d stoa -c "
SELECT
  (SELECT COUNT(*) FROM tenants) as tenants,
  (SELECT COUNT(*) FROM apis) as apis,
  (SELECT COUNT(*) FROM subscriptions) as subscriptions,
  (SELECT COUNT(*) FROM users) as users;
"
```

### 6.3 Test API Health

```bash
# Check Control-Plane API health
curl -s https://api.stoa.cab-i.com/health | jq .

# Verify Keycloak integration
curl -s https://api.stoa.cab-i.com/api/v1/tenants -H "Authorization: Bearer $TOKEN"
```

### 6.4 Verification Checklist

- [ ] All 25 tables present
- [ ] Tenant count matches expected
- [ ] Control-Plane API responds to health check
- [ ] Authentication working (Keycloak integration)
- [ ] Console UI can load tenants

---

## 7. Recovery Metrics (Baseline)

> Tested: 2026-01-23 (CAB-853)

| Metric | Value |
|--------|-------|
| Backup size (compressed) | 22 KB |
| Backup size (uncompressed) | 140 KB |
| Restore time | < 2 seconds |
| Tables | 25 |
| Tenants | 4 |
| APIs | 10 |
| Users | 7 |

**Note**: Restore time scales with database size. For larger databases, expect:
- 100 MB backup: ~1-2 minutes
- 1 GB backup: ~10-15 minutes

---

## 8. Rollback

If restore fails or causes issues, revert to pre-restore backup:

```bash
S3_BUCKET=stoa-backups AWS_REGION=eu-west-1 \
  ./scripts/backup/backup-postgres.sh \
  --restore s3://stoa-backups/postgres/{date}/stoa_backup_pre-restore.sql.gz \
  --force
```

---

## 9. Post-Restore Actions

1. **Verify All Integrations**
   ```bash
   # Control-Plane API
   curl -s https://api.stoa.cab-i.com/health

   # Console UI
   curl -s https://console.stoa.cab-i.com

   # Developer Portal
   curl -s https://portal.stoa.cab-i.com
   ```

2. **Clear API Cache** (if applicable)
   ```bash
   kubectl rollout restart deployment control-plane-api -n stoa-system
   ```

3. **Update Documentation**
   - Record restore in incident log
   - Update MTTR metrics
   - Document any data loss

---

## 10. Escalation

| Stage | Contact | Condition |
|-------|---------|-----------|
| L1 | On-call DevOps | Initial response |
| L2 | Platform Team | If restore fails |
| L3 | AWS Support | S3/KMS access issues |

---

## 11. Prevention

### Monitoring
- PostgreSQL backup CronJob status
- S3 backup object count and size
- Database connection pool metrics

### Regular Testing
- Monthly restore test in dev environment
- Quarterly DR drill

### Alerts to Configure
```yaml
- alert: PostgresBackupFailed
  expr: kube_job_status_failed{job_name=~"backup-postgres.*"} > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "PostgreSQL backup job failed"

- alert: PostgresBackupMissing
  expr: time() - s3_object_last_modified{bucket="stoa-backups",prefix="postgres"} > 86400
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "No PostgreSQL backup in last 24 hours"
```

---

## Important Notes

1. **Data Consistency**: Backup is point-in-time. Any data created after the backup will be lost.

2. **Dependent Services**: Control-Plane API depends on this database. Plan for brief downtime during restore.

3. **Keycloak Integration**: User sessions may need to be re-authenticated after restore.

4. **MCP Gateway**: May need restart if tool registrations were affected.

---

## Test History

| Date | Tester | Result | Notes |
|------|--------|--------|-------|
| 2026-01-23 | @claude | Success | Initial test (CAB-853) - 25 tables, < 2s restore |

---

## Related Runbooks

- [Vault Restore](vault-restore.md)
- [AWX Restore](awx-restore.md)
- [Database Connection Issues](database-connection.md)
