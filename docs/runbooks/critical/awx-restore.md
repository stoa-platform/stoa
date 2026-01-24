# AWX Database Restore Runbook

> **Severity**: Critical
> **Tickets**: CAB-104, CAB-107
> **MTTR Target**: < 1 hour
> **Last Updated**: 2026-01-05

## Overview

This runbook describes the procedure to restore AWX (Ansible Tower) database from S3 backups.

## When to Use

- AWX database corruption
- Accidental data deletion
- Disaster recovery
- Migration to new cluster

---

## Prerequisites

- [ ] AWS CLI configured with appropriate permissions
- [ ] `kubectl` access to the cluster
- [ ] Access to backup S3 bucket (`stoa-backups-{env}-eu-west-3`)
- [ ] AWX namespace access
- [ ] Slack notification sent to `#ops-alerts`

---

## 1. Symptoms

### Indicators
- AWX UI shows database connection errors
- Jobs history missing or corrupted
- Inventory data incorrect
- Authentication failures

### Alerts
- `AWXDatabaseConnectionFailed`
- `AWXPostgresDown`

---

## 2. Quick Diagnosis (< 5 min)

```bash
# Check AWX pod status
kubectl get pods -n awx

# Check PostgreSQL pod
kubectl get pods -n awx -l app.kubernetes.io/component=database

# Check PostgreSQL logs
kubectl logs -n awx deploy/awx-postgres --tail=100

# Verify database connection
kubectl exec -n awx deploy/awx-postgres -- psql -U awx -d awx -c "SELECT 1;"
```

---

## 3. List Available Backups

```bash
# List all available backups
./scripts/backup/backup-awx.sh --list

# Or directly with AWS CLI
aws s3 ls s3://stoa-backups-{env}-eu-west-3/awx/ --recursive | sort -r | head -20
```

---

## 4. Restore Procedure

### 4.1 Notify Team

```bash
# Send Slack notification
curl -X POST -H 'Content-type: application/json' \
  --data '{"channel": "#ops-alerts", "text": ":warning: Starting AWX database restore - ETA 30min"}' \
  "$SLACK_WEBHOOK_URL"
```

### 4.2 Scale Down AWX

```bash
# Scale down AWX to prevent writes during restore
kubectl scale deployment awx -n awx --replicas=0
kubectl scale deployment awx-task -n awx --replicas=0

# Verify pods are terminated
kubectl get pods -n awx -l app.kubernetes.io/name=awx
```

### 4.3 Create Pre-Restore Backup

```bash
# Safety backup before restore
./scripts/backup/backup-awx.sh

# Note the backup path for rollback if needed
```

### 4.4 Perform Restore

```bash
# Using the restore script
export RESTORE_CONFIRM=true
./scripts/backup/backup-awx.sh --restore s3://stoa-backups-{env}-eu-west-3/awx/2024-01-15/awx-backup-20240115_020000.sql.gz

# Or manually:
# 1. Download backup
aws s3 cp s3://stoa-backups-{env}-eu-west-3/awx/2024-01-15/awx-backup.sql.gz /tmp/

# 2. Copy to PostgreSQL pod
POSTGRES_POD=$(kubectl get pods -n awx -l app.kubernetes.io/component=database -o jsonpath='{.items[0].metadata.name}')
gunzip -c /tmp/awx-backup.sql.gz | kubectl exec -i -n awx $POSTGRES_POD -- tee /tmp/restore.dump > /dev/null

# 3. Restore database
kubectl exec -n awx $POSTGRES_POD -- pg_restore -U awx -d awx --clean --if-exists /tmp/restore.dump

# 4. Cleanup
kubectl exec -n awx $POSTGRES_POD -- rm -f /tmp/restore.dump
```

### 4.5 Scale Up AWX

```bash
# Scale AWX back up
kubectl scale deployment awx -n awx --replicas=1
kubectl scale deployment awx-task -n awx --replicas=1

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=awx -n awx --timeout=300s
```

---

## 5. Verification

### 5.1 Check Database Connection

```bash
kubectl exec -n awx deploy/awx-postgres -- psql -U awx -d awx -c "SELECT count(*) FROM main_organization;"
```

### 5.2 Check AWX UI

```bash
# Port-forward to test locally
kubectl port-forward svc/awx-service -n awx 8052:80

# Open browser: http://localhost:8052
```

### 5.3 Verify Data Integrity

- [ ] Organizations visible
- [ ] Projects synced
- [ ] Inventories populated
- [ ] Credentials intact
- [ ] Job templates available
- [ ] Recent job history restored

### 5.4 Run Test Job

```bash
# Via AWX CLI
awx job_templates launch --name "Health Check" --wait
```

---

## 6. Rollback

If restore fails, revert to pre-restore backup:

```bash
# Use the backup created in step 4.3
./scripts/backup/backup-awx.sh --restore s3://stoa-backups-{env}-eu-west-3/awx/{date}/awx-backup-pre-restore.sql.gz
```

---

## 7. Post-Restore Actions

1. **Clear AWX Cache**
   ```bash
   kubectl exec -n awx deploy/awx -- awx-manage clearsessions
   ```

2. **Restart AWX Services**
   ```bash
   kubectl rollout restart deployment awx -n awx
   kubectl rollout restart deployment awx-task -n awx
   ```

3. **Update Documentation**
   - Record restore in incident log
   - Update MTTR metrics

---

## 8. Escalation

| Stage | Contact | Condition |
|-------|---------|-----------|
| L1 | On-call DevOps | Initial response |
| L2 | Platform Team | If restore fails |
| L3 | AWS Support | S3/KMS access issues |

---

## 9. Prevention

### Monitoring
- Database backup CronJob status
- S3 backup object count
- Backup file size anomalies

### Regular Testing
- Monthly restore test in dev environment
- Quarterly DR drill

### Alerts to Configure
```yaml
- alert: AWXBackupFailed
  expr: kube_job_status_failed{job_name=~"backup-awx.*"} > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "AWX backup job failed"
```

---

## Related Runbooks

- [Vault Restore](vault-restore.md)
- [Database Connection Issues](database-connection.md)
- [AWX Unreachable](../medium/awx-unreachable.md)
