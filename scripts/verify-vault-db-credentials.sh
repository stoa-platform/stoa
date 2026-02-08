#!/usr/bin/env bash
# verify-vault-db-credentials.sh — Verify PostgreSQL credentials match between Vault and actual DB
#
# Usage:
#   ./scripts/verify-vault-db-credentials.sh --from-k8s-secret
#   ./scripts/verify-vault-db-credentials.sh --vault-path apim/dev/database
#
# Requirements:
#   --from-k8s-secret: kubectl with access to stoa-system namespace
#   --vault-path:      vault CLI authenticated + psql
#
# SECURITY: This script NEVER logs passwords

set -euo pipefail

NAMESPACE="${NAMESPACE:-stoa-system}"
SECRET_NAME="${SECRET_NAME:-postgresql-credentials}"
VAULT_PATH=""
FROM_K8S_SECRET=false

usage() {
  echo "Usage: $0 [--from-k8s-secret] [--vault-path PATH] [--namespace NS] [--secret-name NAME]"
  echo ""
  echo "Options:"
  echo "  --from-k8s-secret    Read credentials from K8s secret (synced by External Secrets)"
  echo "  --vault-path PATH    Read credentials directly from Vault (e.g., apim/dev/database)"
  echo "  --namespace NS       K8s namespace (default: stoa-system)"
  echo "  --secret-name NAME   K8s secret name (default: postgresql-credentials)"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --from-k8s-secret) FROM_K8S_SECRET=true; shift ;;
    --vault-path) VAULT_PATH="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "[ERROR] Unknown option: $1"; usage ;;
  esac
done

if [[ "$FROM_K8S_SECRET" == "false" ]] && [[ -z "$VAULT_PATH" ]]; then
  echo "[ERROR] Specify --from-k8s-secret or --vault-path"
  usage
fi

echo "==> Vault DB Credentials Verification ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
echo ""

# ---- Step 1: Check Vault health ----
echo "--- Step 1: Vault Health Check ---"

VAULT_ADDR="${VAULT_ADDR:-https://vault.gostoa.dev}"
echo "[INFO] Vault address: $VAULT_ADDR"

VAULT_HEALTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$VAULT_ADDR/v1/sys/health" 2>/dev/null || echo "000")

case $VAULT_HEALTH_CODE in
  200|429|472|473)
    echo "[OK] Vault is healthy (HTTP $VAULT_HEALTH_CODE - unsealed)"
    ;;
  501)
    echo "[ERROR] Vault is NOT INITIALIZED (HTTP 501)"
    echo "[INFO] Run: vault operator init"
    exit 1
    ;;
  503)
    echo "[ERROR] Vault is SEALED (HTTP 503)"
    echo "[INFO] See runbook: docs/runbooks/critical/vault-sealed.md"
    exit 1
    ;;
  000)
    echo "[WARN] Cannot reach Vault at $VAULT_ADDR (may be expected if running outside cluster)"
    ;;
  *)
    echo "[WARN] Unexpected Vault health status: HTTP $VAULT_HEALTH_CODE"
    ;;
esac
echo ""

# ---- Step 2: Read credentials ----
echo "--- Step 2: Read Credentials ---"

if [[ "$FROM_K8S_SECRET" == "true" ]]; then
  echo "[INFO] Reading from K8s secret: $NAMESPACE/$SECRET_NAME"

  if ! kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" &>/dev/null; then
    echo "[ERROR] Secret $SECRET_NAME not found in namespace $NAMESPACE"
    echo "[INFO] Check ExternalSecret sync: kubectl get externalsecrets -n $NAMESPACE"
    exit 1
  fi

  DB_HOST=$(kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o jsonpath='{.data.host}' | base64 -d)
  DB_PORT=$(kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o jsonpath='{.data.port}' | base64 -d)
  DB_USER=$(kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o jsonpath='{.data.username}' | base64 -d)
  DB_PASS=$(kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o jsonpath='{.data.password}' | base64 -d)
  DB_NAME=$(kubectl get secret -n "$NAMESPACE" "$SECRET_NAME" -o jsonpath='{.data.database}' | base64 -d)

  echo "[OK] Credentials read from K8s secret"
else
  echo "[INFO] Reading from Vault path: secret/data/$VAULT_PATH"

  if ! command -v vault &>/dev/null; then
    echo "[ERROR] vault CLI not found"
    exit 1
  fi

  DB_HOST=$(vault kv get -field=host "secret/$VAULT_PATH")
  DB_PORT=$(vault kv get -field=port "secret/$VAULT_PATH")
  DB_USER=$(vault kv get -field=username "secret/$VAULT_PATH")
  DB_PASS=$(vault kv get -field=password "secret/$VAULT_PATH")
  DB_NAME=$(vault kv get -field=database "secret/$VAULT_PATH")

  echo "[OK] Credentials read from Vault"
fi

echo "[INFO] Host: $DB_HOST:${DB_PORT:-5432}"
echo "[INFO] Database: $DB_NAME"
echo "[INFO] User: $DB_USER"
echo "[INFO] Password: ********"
echo ""

# ---- Step 3: Test PostgreSQL connection ----
echo "--- Step 3: PostgreSQL Connection Test ---"

if ! command -v psql &>/dev/null; then
  echo "[ERROR] psql not found. Install postgresql-client."
  exit 1
fi

if PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1 AS connection_ok;" -q --no-password 2>&1; then
  echo ""
  echo "[OK] PostgreSQL connection SUCCESSFUL"
  echo "[OK] Credentials are valid and in sync"
  exit 0
else
  echo ""
  echo "[ERROR] PostgreSQL connection FAILED"
  echo ""
  echo "Possible causes:"
  echo "  1. Password in Vault doesn't match actual DB password"
  echo "  2. Database host is unreachable from this network"
  echo "  3. User doesn't exist or has been dropped"
  echo "  4. Database doesn't exist"
  echo ""
  echo "Remediation:"
  echo "  1. Compare Vault password with actual DB: vault kv get secret/$VAULT_PATH"
  echo "  2. Reset DB password to match Vault, or update Vault to match DB"
  echo "  3. After fixing, restart pods that cache DB connections"
  echo "  4. See runbook: docs/runbooks/critical/vault-emergency-unseal.md"
  exit 1
fi
