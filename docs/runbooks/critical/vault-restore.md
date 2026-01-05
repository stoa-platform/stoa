# Vault Snapshot Restore Runbook

> **Severity**: Critical
> **Tickets**: CAB-105, CAB-107
> **MTTR Target**: < 1 hour
> **Last Updated**: 2026-01-05

## Overview

This runbook describes the procedure to restore HashiCorp Vault from Raft snapshots stored in S3.

## When to Use

- Vault data corruption
- Accidental secret deletion
- Disaster recovery
- Migration to new cluster
- Recovery from failed upgrade

---

## Prerequisites

- [ ] AWS CLI configured with appropriate permissions
- [ ] `kubectl` access to the cluster
- [ ] Vault root token or recovery keys
- [ ] Access to backup S3 bucket (`stoa-backups-{env}-eu-west-3`)
- [ ] Vault namespace access
- [ ] Slack notification sent to `#ops-alerts`

---

## 1. Symptoms

### Indicators
- Vault returns 500 errors
- Secrets missing or corrupted
- Authentication policies broken
- Raft consensus issues

### Alerts
- `VaultSealed`
- `VaultDataCorruption`
- `VaultRaftPeersMismatch`

---

## 2. Quick Diagnosis (< 5 min)

```bash
# Check Vault pod status
kubectl get pods -n vault

# Check Vault status
kubectl exec -n vault vault-0 -- vault status

# Check Raft peers
kubectl exec -n vault vault-0 -- vault operator raft list-peers

# Check recent logs
kubectl logs -n vault vault-0 --tail=100
```

---

## 3. List Available Snapshots

```bash
# List all available snapshots
./scripts/backup/backup-vault.sh --list

# Or directly with AWS CLI
aws s3 ls s3://stoa-backups-{env}-eu-west-3/vault/ --recursive | sort -r | head -20
```

---

## 4. Pre-Restore Preparation

### 4.1 Notify Team

```bash
# Send Slack notification
curl -X POST -H 'Content-type: application/json' \
  --data '{"channel": "#ops-alerts", "text": ":rotating_light: Starting Vault restore - ALL VAULT-DEPENDENT SERVICES WILL BE IMPACTED"}' \
  "$SLACK_WEBHOOK_URL"
```

### 4.2 Document Current State

```bash
# Record current Vault state
kubectl exec -n vault vault-0 -- vault status > /tmp/vault-status-before.txt
kubectl exec -n vault vault-0 -- vault operator raft list-peers > /tmp/vault-peers-before.txt
```

### 4.3 Create Pre-Restore Snapshot

```bash
# Safety snapshot before restore
./scripts/backup/backup-vault.sh

# Note the snapshot path for rollback if needed
```

---

## 5. Restore Procedure

### 5.1 Get Vault Token

```bash
# Option 1: From Kubernetes secret
export VAULT_TOKEN=$(kubectl get secret -n vault vault-root-token -o jsonpath='{.data.token}' | base64 -d)

# Option 2: From init secret
export VAULT_TOKEN=$(kubectl get secret -n vault vault-init -o jsonpath='{.data.root_token}' | base64 -d)

# Set Vault address
export VAULT_ADDR="https://vault.stoa.cab-i.com"
```

### 5.2 Perform Restore

```bash
# Using the restore script (recommended)
export VAULT_TOKEN=<token>
export VAULT_ADDR=https://vault.stoa.cab-i.com
./scripts/backup/backup-vault.sh --restore s3://stoa-backups-{env}-eu-west-3/vault/2024-01-15/vault-snapshot-20240115_030000.snap --force

# Or manually:
# 1. Download snapshot
aws s3 cp s3://stoa-backups-{env}-eu-west-3/vault/2024-01-15/vault-snapshot.snap /tmp/

# 2. Restore snapshot (force required for in-place restore)
vault operator raft snapshot restore -force /tmp/vault-snapshot.snap
```

### 5.3 Restart Vault Pods

**Important**: After Raft snapshot restore, all Vault pods must be restarted.

```bash
# Restart all Vault pods
kubectl rollout restart statefulset vault -n vault

# Wait for rollout
kubectl rollout status statefulset vault -n vault --timeout=300s

# Verify all pods are ready
kubectl get pods -n vault -l app.kubernetes.io/name=vault
```

### 5.4 Unseal Vault (if needed)

If using manual unseal:

```bash
# Get unseal keys
UNSEAL_KEY_1=$(kubectl get secret -n vault vault-init -o jsonpath='{.data.unseal_key_1}' | base64 -d)
UNSEAL_KEY_2=$(kubectl get secret -n vault vault-init -o jsonpath='{.data.unseal_key_2}' | base64 -d)
UNSEAL_KEY_3=$(kubectl get secret -n vault vault-init -o jsonpath='{.data.unseal_key_3}' | base64 -d)

# Unseal each pod
for pod in vault-0 vault-1 vault-2; do
  kubectl exec -n vault $pod -- vault operator unseal $UNSEAL_KEY_1
  kubectl exec -n vault $pod -- vault operator unseal $UNSEAL_KEY_2
  kubectl exec -n vault $pod -- vault operator unseal $UNSEAL_KEY_3
done
```

If using auto-unseal (AWS KMS):
- Pods should auto-unseal after restart
- Verify with `vault status`

---

## 6. Verification

### 6.1 Check Vault Status

```bash
# All pods should be unsealed
for pod in vault-0 vault-1 vault-2; do
  echo "=== $pod ==="
  kubectl exec -n vault $pod -- vault status
done
```

### 6.2 Check Raft Cluster

```bash
kubectl exec -n vault vault-0 -- vault operator raft list-peers
```

Expected output:
```
Node       Address                        State       Voter
----       -------                        -----       -----
vault-0    vault-0.vault-internal:8201    leader      true
vault-1    vault-1.vault-internal:8201    follower    true
vault-2    vault-2.vault-internal:8201    follower    true
```

### 6.3 Verify Secrets Access

```bash
# Test secret read
vault kv get secret/stoa/test

# List auth methods
vault auth list

# List policies
vault policy list
```

### 6.4 Test Dependent Services

```bash
# Keycloak (uses Vault for secrets)
kubectl logs -n keycloak deploy/keycloak --tail=20 | grep -i vault

# Control-Plane API
kubectl logs -n stoa-system deploy/control-plane-api --tail=20 | grep -i vault

# AWX credentials
kubectl exec -n awx deploy/awx -- awx-manage check_creds
```

---

## 7. Rollback

If restore fails, revert to pre-restore snapshot:

```bash
./scripts/backup/backup-vault.sh --restore s3://stoa-backups-{env}-eu-west-3/vault/{date}/vault-snapshot-pre-restore.snap --force
```

---

## 8. Post-Restore Actions

1. **Verify All Integrations**
   ```bash
   # Keycloak
   curl -s https://auth.stoa.cab-i.com/health/ready

   # API Gateway
   curl -s https://gateway.stoa.cab-i.com/rest/apigateway/health

   # Control Plane API
   curl -s https://api.stoa.cab-i.com/health
   ```

2. **Rotate Root Token** (recommended after restore)
   ```bash
   vault token revoke -self
   vault operator generate-root -init
   # Follow generate-root procedure
   ```

3. **Update Documentation**
   - Record restore in incident log
   - Update MTTR metrics
   - Document any data loss

---

## 9. Escalation

| Stage | Contact | Condition |
|-------|---------|-----------|
| L1 | On-call DevOps | Initial response |
| L2 | Platform Team | If restore fails |
| L3 | HashiCorp Support | Raft/cluster issues |
| L4 | AWS Support | KMS/S3 access issues |

---

## 10. Prevention

### Monitoring
- Vault backup CronJob status
- Raft peer count
- Seal status

### Regular Testing
- Monthly restore test in dev environment
- Quarterly DR drill

### Alerts to Configure
```yaml
- alert: VaultBackupFailed
  expr: kube_job_status_failed{job_name=~"backup-vault.*"} > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Vault backup job failed"

- alert: VaultRaftPeersLow
  expr: vault_raft_peers < 3
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Vault Raft cluster has less than 3 peers"
```

---

## Important Notes

1. **Data Consistency**: Vault snapshot is point-in-time. Any secrets created after the snapshot will be lost.

2. **Lease Invalidation**: All dynamic secrets and leases will be invalidated after restore.

3. **Token Revocation**: All tokens (except root) become invalid after restore.

4. **PKI Impact**: Any certificates issued by Vault PKI after the snapshot won't be tracked.

---

## Related Runbooks

- [AWX Restore](awx-restore.md)
- [Vault Sealed](vault-sealed.md)
- [Certificate Expiration](../high/certificate-expiration.md)
