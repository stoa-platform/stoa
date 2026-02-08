# Runbook: Vault Emergency Unseal + Credentials Integrity

> **Severity**: Critical
> **Last updated**: 2026-02-08
> **Owner**: Platform Team
> **Linear Issue**: CAB-1042

---

## 1. Overview

This runbook covers two related failure scenarios:
1. **Vault sealed** — auto-unseal has failed, all secret-dependent services are down
2. **DB credentials drift** — PostgreSQL password in Vault doesn't match the actual database

Both were identified during the CAB-1033 audit. Auto-unseal via AWS KMS is the primary prevention mechanism (configured in stoa-infra).

---

## 2. Quick Diagnosis (< 5 min)

```bash
# 1. Vault pod status
kubectl get pods -n vault -l app.kubernetes.io/name=vault

# 2. Vault seal status (200=ok, 503=sealed, 501=not initialized)
kubectl exec -n vault vault-0 -- vault status

# 3. Check auto-unseal logs
kubectl logs -n vault vault-0 --tail=50 | grep -i "seal\|kms\|unseal"

# 4. Check Prometheus alert
kubectl get prometheusrules -n vault vault-alerts -o yaml 2>/dev/null

# 5. Check DB credentials CronJob
kubectl get cronjobs -n stoa-system vault-db-credentials-check
kubectl get jobs -n stoa-system -l app.kubernetes.io/name=vault-db-credentials-check --sort-by=.status.startTime
```

---

## 3. Resolution: Vault Sealed

### Path A: Fix Auto-Unseal (preferred)

Auto-unseal uses AWS KMS. If it's failing, check:

```bash
# 1. Verify IRSA annotation on Vault service account
kubectl get sa -n vault vault -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'

# 2. Verify KMS key is accessible
aws kms describe-key --key-id alias/vault-unseal-key --region eu-west-1

# 3. Check KMS key policy allows the Vault IAM role
aws kms get-key-policy --key-id alias/vault-unseal-key --policy-name default --region eu-west-1

# 4. If IRSA is correct and KMS is accessible, restart the pod
kubectl delete pod -n vault vault-0
# Pod should auto-unseal on startup
kubectl exec -n vault vault-0 -- vault status
```

### Path B: Manual Unseal (if auto-unseal is broken)

> **WARNING**: Requires unseal keys stored in AWS Secrets Manager

```bash
# 1. Retrieve unseal keys
aws secretsmanager get-secret-value --secret-id stoa/vault-init-keys --region eu-west-1 \
  --query 'SecretString' --output text | jq -r '.unseal_keys_b64[]'

# 2. Unseal with threshold keys (3 of 5)
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_1>
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_2>
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_3>

# 3. Verify
kubectl exec -n vault vault-0 -- vault status
```

### Path C: Single-Node Dev Recovery

For dev environments without HA:

```bash
# Force restart and hope auto-unseal works
kubectl delete pod -n vault vault-0
sleep 30
kubectl exec -n vault vault-0 -- vault status

# If still sealed, use manual unseal (Path B)
```

---

## 4. Resolution: DB Credentials Drift

### Diagnosis

```bash
# 1. Run the standalone verification script
./scripts/verify-vault-db-credentials.sh --from-k8s-secret

# 2. Or check manually (never log the password)
kubectl get secret -n stoa-system postgresql-credentials -o jsonpath='{.data.username}' | base64 -d
# Compare with actual DB user
```

### Fix: Update Vault to Match DB

```bash
# 1. Get the actual DB password (from RDS console or parameter store)
# 2. Update Vault
vault kv put secret/apim/dev/database \
  username=<USER> \
  password=<ACTUAL_DB_PASSWORD> \
  host=<HOST> \
  port=5432 \
  database=<DB_NAME>

# 3. Force External Secrets to re-sync
kubectl annotate externalsecret -n stoa-system postgresql-credentials \
  force-sync=$(date +%s) --overwrite

# 4. Wait for sync
kubectl get externalsecret -n stoa-system postgresql-credentials

# 5. Restart services that cache DB connections
kubectl rollout restart deployment -n stoa-system control-plane-api
```

### Fix: Update DB to Match Vault

```bash
# 1. Read password from Vault (don't log it)
VAULT_PASS=$(vault kv get -field=password secret/apim/dev/database)

# 2. Connect to PostgreSQL as superuser and update
psql -h <HOST> -U postgres -c "ALTER USER <USER> PASSWORD '$VAULT_PASS';"

# 3. Verify
./scripts/verify-vault-db-credentials.sh --from-k8s-secret
```

---

## 5. Post-Resolution Verification

- [ ] `vault status` shows `Sealed: false`
- [ ] `./scripts/verify-vault-db-credentials.sh --from-k8s-secret` passes
- [ ] External Secrets are syncing: `kubectl get externalsecrets -n stoa-system`
- [ ] Control Plane API is healthy: `curl -s https://api.gostoa.dev/health`
- [ ] Keycloak is healthy: `curl -s https://auth.gostoa.dev/health/ready`
- [ ] No `VaultSealed` or `VaultDBCredentialsCheckFailing` alerts firing

---

## 6. Escalation

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If auto-unseal fails | Slack `#platform-team` |
| L3 | AWS Support | KMS/IAM issues | Support ticket |
| L4 | HashiCorp Support | Storage corruption | Support ticket |

---

## 7. Prevention: stoa-infra Configuration

The following changes belong in **stoa-infra** (not this repo):

### AWS KMS Auto-Unseal (Vault Helm Values)

```yaml
# stoa-infra/charts/vault/values.yaml
server:
  ha:
    enabled: true
    raft:
      enabled: true
      config: |
        seal "awskms" {
          region     = "eu-west-1"
          kms_key_id = "alias/vault-unseal-key"
        }

        storage "raft" {
          path = "/vault/data"
        }

        listener "tcp" {
          address     = "0.0.0.0:8200"
          tls_disable = true
        }

        telemetry {
          prometheus_retention_time = "24h"
          disable_hostname = true
        }
  serviceAccount:
    annotations:
      eks.amazonaws.com/role-arn: "arn:aws:iam::role/vault-kms-unseal"
```

### Terraform for KMS Key + IAM Role

```hcl
# stoa-infra/terraform/modules/vault-kms/main.tf
resource "aws_kms_key" "vault_unseal" {
  description = "Vault auto-unseal key"
  key_usage   = "ENCRYPT_DECRYPT"
  tags = {
    Service = "vault"
    Purpose = "auto-unseal"
  }
}

resource "aws_kms_alias" "vault_unseal" {
  name          = "alias/vault-unseal-key"
  target_key_id = aws_kms_key.vault_unseal.key_id
}

resource "aws_iam_role" "vault_kms_unseal" {
  name = "vault-kms-unseal"
  assume_role_policy = data.aws_iam_policy_document.vault_assume.json
}

resource "aws_iam_role_policy" "vault_kms" {
  role   = aws_iam_role.vault_kms_unseal.id
  policy = data.aws_iam_policy_document.vault_kms.json
}

data "aws_iam_policy_document" "vault_kms" {
  statement {
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey"]
    resources = [aws_kms_key.vault_unseal.arn]
  }
}
```

### Action Items for stoa-infra

| # | Action | File | Priority |
|---|--------|------|----------|
| 1 | Add `seal "awskms"` to Vault Helm values | `charts/vault/values.yaml` | P0 |
| 2 | Create KMS key + alias via Terraform | `terraform/modules/vault-kms/` | P0 |
| 3 | Create IAM role with IRSA for Vault SA | `terraform/modules/vault-kms/` | P0 |
| 4 | Enable Vault telemetry in Helm values | `charts/vault/values.yaml` | P1 |

---

## 8. Related Runbooks

- [Vault Sealed State](vault-sealed.md)
- [Vault Snapshot Restore](vault-restore.md)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-08 | Platform Team | Initial creation (CAB-1042) |
