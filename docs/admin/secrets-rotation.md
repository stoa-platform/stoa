# Secrets Rotation

## Architecture

```
HashiCorp Vault (runtime source of truth)
       │
       ▼
External Secrets Operator (ESO) ──sync──▶ K8s Secrets ──mount──▶ Pods
       │
AWS Secrets Manager (bootstrap only — Vault unseal keys)
```

## Rotation Procedure

### Step 1 — Update the secret in Vault

```bash
# Via Vault CLI
vault kv put secret/apim/prod/database \
  username=stoa_app \
  password=<new-password> \
  host=postgresql.stoa-system.svc \
  port=5432 \
  database=stoa

# Via Vault UI
# Navigate to secret/apim/prod/database > Create new version
```

### Step 2 — Wait for ESO sync (or force it)

ESO checks Vault every `refreshInterval` (default: 1h). To force an immediate sync:

```bash
kubectl annotate externalsecret stoa-gateway-secrets \
  -n stoa-system \
  force-sync="$(date +%s)" \
  --overwrite
```

### Step 3 — Verify sync status

```bash
kubectl get externalsecret -n stoa-system
```

Expected output:

```
NAME                     STORE           REFRESH INTERVAL   STATUS
stoa-gateway-secrets     vault-backend   1h                 SecretSynced
```

If status is `SecretSyncError`, check ESO logs:

```bash
kubectl logs -f deploy/external-secrets -n external-secrets
```

### Step 4 — Restart affected pods

```bash
kubectl rollout restart deployment/control-plane-api -n stoa-system
kubectl rollout restart deployment/mcp-gateway -n stoa-system
```

### Step 5 — Verify pods are healthy

```bash
kubectl get pods -n stoa-system -w
curl -s https://api.<BASE_DOMAIN>/health/ready
```

## Secrets Inventory

### Database Credentials

| Vault Path | K8s Secret | Used By |
|-----------|-----------|---------|
| `secret/apim/{env}/database` | `stoa-db-credentials` | control-plane-api |

Rotation impact: Control Plane API loses DB connectivity until pod restart.

### Keycloak Admin

| Vault Path | K8s Secret | Used By |
|-----------|-----------|---------|
| `secret/apim/{env}/keycloak-admin` | `stoa-keycloak-admin` | control-plane-api (admin operations) |

Rotation impact: Admin API operations fail until pod restart.

### Gateway Secrets

| Vault Path | K8s Secret | Used By |
|-----------|-----------|---------|
| `secret/stoa/data/gateway` | `stoa-gateway-secrets` | mcp-gateway, stoa-gateway |

Keys in this secret:

| Key | Purpose | Rotation Impact |
|-----|---------|----------------|
| `control_plane_api_key` | Gateway → Control Plane auth | Gateway can't fetch config |
| `jwt_secret` | JWT token validation | All tokens invalidated |
| `keycloak_client_secret` | OIDC client auth | Token exchange fails |
| `admin_api_token` | Gateway admin API | Admin operations fail |

> **Warning**: Rotating `jwt_secret` invalidates all existing tokens. Coordinate with users or rotate during maintenance window.

### MinIO / S3 Credentials

| Vault Path | K8s Secret | Used By |
|-----------|-----------|---------|
| `secret/apim/{env}/minio` | `stoa-minio-credentials` | control-plane-api |

Rotation impact: Spec uploads/downloads fail until pod restart.

## Rotation Schedule

| Secret | Frequency | Notes |
|--------|----------|-------|
| Database password | 90 days | Coordinate with DB admin |
| Keycloak client secret | 90 days | Regenerate in Keycloak admin first |
| Gateway API keys | 90 days | Update both API and gateway simultaneously |
| JWT secret | 180 days | Schedule during maintenance window |
| MinIO credentials | 90 days | Update MinIO IAM policy first |

## Emergency Rotation

If a secret is compromised:

1. **Immediately** update the secret in Vault
2. Force ESO sync (see Step 2 above)
3. Restart all affected deployments
4. Check audit logs for unauthorized access:
   ```bash
   kubectl logs deploy/control-plane-api -n stoa-system --since=24h | grep -i "unauthorized\|forbidden\|401\|403"
   ```
5. If JWT secret was compromised, rotate it and notify all API consumers

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `SecretSyncError` in ESO | Vault sealed or path wrong | Check Vault status, verify path |
| Pod `CrashLoopBackOff` after rotation | New secret format wrong | Check env var names match expected keys |
| `401 Unauthorized` after rotation | Old token cached | Restart pods, clear client token caches |
| ESO sync stuck | ClusterSecretStore misconfigured | `kubectl describe clustersecretstore vault-backend` |
