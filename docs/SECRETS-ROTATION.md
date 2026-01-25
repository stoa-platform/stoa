# STOA Platform - Secrets Rotation Procedure

## Overview

This document describes the procedure for rotating secrets in the STOA platform.
All secrets are stored in HashiCorp Vault and synchronized to Kubernetes via External Secrets Operator.

## Vault Paths

| Path | Description | Rotation Frequency |
|------|-------------|-------------------|
| `secret/apim/{env}/database` | PostgreSQL credentials | 90 days |
| `secret/apim/{env}/minio` | MinIO credentials | 90 days |
| `secret/apim/{env}/gateway-admin` | Gateway admin | 90 days |
| `secret/apim/{env}/keycloak-admin` | Keycloak admin | 90 days |

## Quick Rotation (Manual)

### Prerequisites

```bash
# Port-forward to Vault
kubectl port-forward svc/vault -n vault 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200

# Authenticate (from vault pod)
kubectl exec -it vault-0 -n vault -- vault token create -policy=admin -ttl=1h
export VAULT_TOKEN=<token>
```

### 1. Rotate PostgreSQL Password

```bash
# Generate new password
NEW_DB_PASS=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)

# Update Vault
vault kv put secret/apim/dev/database \
  username="stoa" \
  password="$NEW_DB_PASS" \
  host="control-plane-db.stoa-system.svc.cluster.local" \
  port="5432" \
  database="stoa"

# Update PostgreSQL directly
kubectl exec control-plane-db-0 -n stoa-system -- \
  psql -U stoa -d stoa -c "ALTER USER stoa WITH PASSWORD '$NEW_DB_PASS';"

# Trigger secret sync (if using ESO)
kubectl annotate externalsecret postgresql-credentials -n stoa-system \
  force-sync=$(date +%s) --overwrite

# Or manually update K8s secrets
kubectl patch secret postgresql-credentials -n stoa-system \
  -p="{\"stringData\":{\"password\":\"$NEW_DB_PASS\"}}"
kubectl patch secret control-plane-db-secret -n stoa-system \
  -p="{\"stringData\":{\"POSTGRES_PASSWORD\":\"$NEW_DB_PASS\"}}"

# Update DATABASE_URL in api secrets
NEW_DB_URL="postgresql+asyncpg://stoa:${NEW_DB_PASS}@control-plane-db.stoa-system.svc.cluster.local:5432/stoa"
kubectl patch secret control-plane-api-secrets -n stoa-system \
  -p="{\"stringData\":{\"DATABASE_URL\":\"$NEW_DB_URL\"}}"

# Restart affected pods
kubectl rollout restart deployment/control-plane-api -n stoa-system
kubectl rollout restart deployment/mcp-gateway -n stoa-system
kubectl rollout restart statefulset/control-plane-db -n stoa-system
```

### 2. Rotate MinIO Password

```bash
# Generate new passwords
NEW_MINIO_ROOT=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)
NEW_MINIO_SECRET=$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-40)

# Update Vault
vault kv put secret/apim/dev/minio \
  root_user="minioadmin" \
  root_password="$NEW_MINIO_ROOT" \
  access_key="error-snapshots-user" \
  secret_key="$NEW_MINIO_SECRET"

# Update K8s secrets
kubectl patch secret minio-credentials -n stoa-system \
  -p="{\"stringData\":{\"rootPassword\":\"$NEW_MINIO_ROOT\"}}"
kubectl patch secret error-snapshots-minio -n stoa-system \
  -p="{\"stringData\":{\"root-password\":\"$NEW_MINIO_ROOT\",\"secret-key\":\"$NEW_MINIO_SECRET\"}}"

# Restart MinIO
kubectl rollout restart deployment/minio -n stoa-system
```

## Automated Rotation (AWX)

Use the AWX playbook for automated rotation:

```bash
# Via AWX API
curl -X POST https://awx.gostoa.dev/api/v2/job_templates/rotate-credentials/launch/ \
  -H "Authorization: Bearer $AWX_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "extra_vars": {
      "secret_path": "apim/dev/database",
      "rotation_type": "password"
    }
  }'
```

See: `ansible/playbooks/rotate-credentials.yaml`

## Verification

```bash
# Check API health
curl -s https://api.gostoa.dev/health

# Check DB connection
kubectl exec -n stoa-system deploy/control-plane-api -- python -c "
import asyncio, asyncpg, os
async def test():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'])
    print(await conn.fetchval('SELECT 1'))
    await conn.close()
asyncio.run(test())
"

# Check MinIO connection
kubectl exec -n stoa-system deploy/minio -- \
  mc alias set local http://localhost:9000 minioadmin "$NEW_MINIO_ROOT"
```

## Rollback

If rotation fails, restore from Vault history:

```bash
# List versions
vault kv metadata get secret/apim/dev/database

# Restore specific version
vault kv rollback -version=1 secret/apim/dev/database
```

## Emergency Contacts

- Platform Team: platform@cab-i.com
- Security Team: security@cab-i.com

## Audit

All secret rotations are logged in:
- Vault audit log: `vault audit list`
- K8s events: `kubectl get events -n stoa-system`
