---
description: Secrets management strategy — Vault, ESO, AWS SM. Consult when adding/modifying credentials or env vars.
globs: "deploy/**,k8s/**,charts/**,.env*,**/secrets*"
---

# Secrets Management

## Architecture

```
HashiCorp Vault (runtime source of truth)
       │
       ▼
External Secrets Operator (ESO) ──sync──▶ K8s Secrets ──mount──▶ Pods
       │
AWS Secrets Manager (bootstrap only — Vault unseal keys, root tokens)
```

- **Vault** = abstraction layer, cloud-agnostic, runtime secret storage
- **AWS SM** = bootstrap only (Vault unseal, terraform state encryption)
- **ESO** = sync mechanism (Vault → K8s Secrets, auto-refresh)

## Vault Paths

| Path | Content |
|------|---------|
| `secret/apim/{env}/database` | PostgreSQL credentials |
| `secret/apim/{env}/minio` | MinIO/S3 credentials |
| `secret/apim/{env}/gateway-admin` | Gateway admin token |
| `secret/apim/{env}/keycloak-admin` | Keycloak admin credentials |
| `secret/stoa/data/gateway` | Gateway runtime secrets (JWT, API keys, client secret) |
| `secret/subscriptions/*` | Tenant-specific subscription secrets |

Where `{env}` = `dev`, `staging`, `prod`.

## ESO Configuration (Helm)

In `charts/stoa-platform/values.yaml`:
```yaml
externalSecret:
  enabled: false          # Toggle per environment
  refreshInterval: 1h     # Vault → K8s sync interval
  secretStoreRef: vault-backend   # ClusterSecretStore name
  vaultPath: stoa/data/gateway    # Vault KV path
```

ESO syncs these keys to K8s Secret `stoa-gateway-secrets`:
- `control_plane_api_key`
- `jwt_secret`
- `keycloak_client_secret`
- `admin_api_token`

## Agent Checklist

When touching secrets, env vars, or credentials:

1. **Never hardcode** — use Vault path + ESO, or K8s Secret reference
2. **New secret?** → Add to Vault path + ESO `ExternalSecret` manifest + Helm values
3. **K8s manifest** → Use `envFrom: secretRef` or `env.valueFrom.secretKeyRef`
4. **Non-critical secret** → Set `optional: true` on the secretRef to avoid pod crash
5. **CI/CD secret** → Add to GitHub repo/org secrets, reference as `${{ secrets.NAME }}`
6. **Local dev** → Use `.env` file (gitignored), never commit

## Anti-Patterns

| Anti-Pattern | Why It's Wrong | Correct Approach |
|-------------|---------------|-----------------|
| Hardcoded password in code | Committed to git, visible in image layers | Vault + ESO → K8s Secret |
| `kubectl create secret` manual | Drift, no audit trail, lost on cluster rebuild | ESO + Vault, or Helm `templates/` |
| Secret in `ConfigMap` | ConfigMaps are not encrypted at rest | Use `Secret` resource (encrypted etcd) |
| Secret in `Dockerfile ENV` | Baked into image layers, visible via `docker inspect` | Runtime env from K8s Secret |
| Secret in GitHub Actions workflow file | Committed to git | Use GitHub Secrets (`${{ secrets.X }}`) |
| `.env` file committed | Plaintext in repo history forever | `.gitignore` + Vault for shared secrets |

## Rotation Procedure

```
1. Update secret value in Vault (UI or CLI)
2. ESO detects change on next refreshInterval (default: 1h)
   — or force: kubectl annotate externalsecret <name> force-sync=$(date +%s)
3. K8s Secret updated automatically
4. Trigger pod restart: kubectl rollout restart deployment/<name> -n stoa-system
5. Verify: kubectl get externalsecret -n stoa-system (status: SecretSynced)
```

## GitHub Actions Secrets (CI/CD)

| Secret | Used By | Purpose |
|--------|---------|---------|
| `AWS_ROLE_ARN` | All deploy jobs | IAM role for ECR + EKS |
| `GATEWAY_API_KEYS` | control-plane-api deploy | Gateway registration auth |
| `STOA_CONTROL_PLANE_API_KEY` | stoa-gateway deploy | Gateway → API auth |
| `SONAR_TOKEN` | Quality gate jobs | SonarCloud analysis |
| `CODECOV_TOKEN` | Coverage upload | Codecov reporting |
