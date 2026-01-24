# Runbook: Vault - Sealed State

> **Severity**: Critical
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `VaultSealed` | `vault_core_unsealed == 0` | [Vault Dashboard](https://grafana.gostoa.dev/d/vault) |
| `VaultDown` | `up{job="vault"} == 0` | [Vault Dashboard](https://grafana.gostoa.dev/d/vault) |

### Observed Behavior

- Applications cannot read secrets
- `permission denied` or `connection refused` errors to Vault
- Pods in `CrashLoopBackOff` with Vault error
- Control-Plane API returns 500 on endpoints requiring secrets

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Cannot log in (Keycloak secrets inaccessible) |
| **APIs** | Deployments blocked, no access to backend credentials |
| **SLA** | Major degradation - Platform non-functional |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check Vault pod status
kubectl get pods -n vault -l app.kubernetes.io/name=vault

# 2. Check Vault status (sealed/unsealed)
kubectl exec -n vault vault-0 -- vault status

# 3. Check logs
kubectl logs -n vault vault-0 --tail=50

# 4. Check events
kubectl get events -n vault --sort-by='.lastTimestamp' | tail -20

# 5. Check service status
kubectl get svc -n vault
```

### Verification Points

- [ ] Vault pod running?
- [ ] Vault initialized?
- [ ] Vault unsealed?
- [ ] AWS KMS accessible (auto-unseal)?
- [ ] Storage backend (S3/Raft) accessible?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Pod restart (lost unseal state) | High | `kubectl describe pod -n vault vault-0` |
| AWS KMS inaccessible | Medium | `aws kms describe-key --key-id <key-id>` |
| Storage backend corrupted | Low | Vault logs |
| Blocking network policy | Low | `kubectl get networkpolicy -n vault` |

---

## 3. Resolution

### Case 1: AWS KMS Auto-unseal (normal configuration)

> Vault should auto-unseal via AWS KMS. If it doesn't:

```bash
# 1. Check that the pod can reach AWS KMS
kubectl exec -n vault vault-0 -- \
  wget -q -O- https://kms.eu-west-1.amazonaws.com --timeout=5 || echo "KMS unreachable"

# 2. Check AWS credentials (IRSA)
kubectl describe serviceaccount -n vault vault
kubectl get pods -n vault vault-0 -o jsonpath='{.spec.serviceAccountName}'

# 3. Check auto-unseal logs
kubectl logs -n vault vault-0 | grep -i "unseal\|kms\|seal"

# 4. If IRSA misconfigured, check the annotation
kubectl get sa -n vault vault -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'

# 5. Restart the pod to retry auto-unseal
kubectl delete pod -n vault vault-0
```

### Case 2: Manual unseal (if auto-unseal fails)

> **WARNING**: Requires unseal keys (stored securely outside cluster)

```bash
# 1. Retrieve unseal keys from secure storage
# (AWS Secrets Manager, physical vault, etc.)

# 2. Unseal with threshold of keys (usually 3 of 5)
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_1>
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_2>
kubectl exec -n vault vault-0 -- vault operator unseal <UNSEAL_KEY_3>

# 3. Check status
kubectl exec -n vault vault-0 -- vault status
```

### Case 3: Vault not initialized (new cluster)

```bash
# 1. Check if Vault is initialized
kubectl exec -n vault vault-0 -- vault status | grep Initialized

# 2. If not initialized, initialize
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=5 \
  -key-threshold=3 \
  -format=json > vault-init.json

# IMPORTANT: Save vault-init.json to AWS Secrets Manager immediately!
aws secretsmanager create-secret \
  --name stoa/vault-init-keys \
  --secret-string file://vault-init.json

# 3. Delete the local file
rm -f vault-init.json
```

### Corrective Action (fix root cause)

```bash
# Check auto-unseal configuration in ConfigMap
kubectl get configmap -n vault vault-config -o yaml | grep -A10 seal

# Expected configuration for AWS KMS auto-unseal:
# seal "awskms" {
#   region     = "eu-west-1"
#   kms_key_id = "alias/vault-unseal-key"
# }

# If configuration is incorrect, update Helm values
helm upgrade vault hashicorp/vault -n vault \
  --set server.ha.enabled=true \
  --set server.ha.raft.enabled=true \
  -f vault-values.yaml
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] `vault status` shows `Sealed: false`
- [ ] Applications can read secrets
- [ ] No errors in Vault logs
- [ ] External Secrets Operator syncing
- [ ] Control-Plane API responds normally

### Verification Commands

```bash
# Check Vault status
kubectl exec -n vault vault-0 -- vault status

# Test reading a secret
kubectl exec -n vault vault-0 -- vault kv get secret/dev/gateway-admin

# Check External Secrets
kubectl get externalsecrets -A

# Check that K8s secrets are synchronized
kubectl get secrets -n stoa-system gateway-admin-secret -o yaml

# Test Control-Plane API endpoint
curl -s https://api.gostoa.dev/health | jq .
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If auto-unseal fails | Slack `#platform-team` |
| L3 | HashiCorp Support | If storage corruption | Support ticket |

### Emergency Contacts

| Role | Contact |
|------|---------|
| Unseal Keys Holder | @security-team (emergency access procedure) |
| AWS Account Admin | @cloud-team |

---

## 6. Prevention

### Recommended Monitoring

```yaml
# Recommended Prometheus alerts
groups:
  - name: vault
    rules:
      - alert: VaultSealed
        expr: vault_core_unsealed == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Vault is sealed"

      - alert: VaultAutoUnsealFailing
        expr: increase(vault_core_unseal_ops{type="recovery"}[5m]) > 0
        for: 5m
        labels:
          severity: warning
```

### Best Practices

1. **Always use auto-unseal** with AWS KMS in production
2. **Test failover** regularly (delete pod, verify auto-unseal)
3. **Backup unseal keys** in multiple secure locations
4. **Configure HA** with Raft to avoid single point of failure

---

## 7. References

### Documentation

- [HashiCorp Vault Auto-unseal AWS KMS](https://developer.hashicorp.com/vault/docs/configuration/seal/awskms)
- [Vault Troubleshooting](https://developer.hashicorp.com/vault/tutorials/operations/troubleshooting)

### Grafana Dashboards

- [Vault Overview](https://grafana.gostoa.dev/d/vault)
- [Vault Audit Logs](https://grafana.gostoa.dev/d/vault-audit)

### Previous Incidents

| Date | Issue | Resolution |
|------|-------|------------|
| - | - | - |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
