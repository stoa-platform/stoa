#!/usr/bin/env bash
# Auto-unseal Vault after container restart
# Reads unseal keys from init-keys.json (protected file, 600)
#
# This script is called by vault-unseal.service (systemd)
# Council adjustment #1: Vault must survive restarts without manual unseal
set -euo pipefail

VAULT_ADDR="http://127.0.0.1:8200"
KEYS_FILE="/opt/vault/init-keys.json"
MAX_WAIT=60
WAIT_INTERVAL=2

# Wait for Vault to be responsive
echo "Waiting for Vault to respond..."
elapsed=0
while [ $elapsed -lt $MAX_WAIT ]; do
  HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' \
    "${VAULT_ADDR}/v1/sys/health?standbyok=true&uninitcode=501&sealedcode=503" 2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "200" ]; then
    echo "Vault already unsealed."
    exit 0
  elif [ "$HTTP_CODE" = "503" ]; then
    echo "Vault is sealed. Proceeding with unseal..."
    break
  elif [ "$HTTP_CODE" = "501" ]; then
    echo "ERROR: Vault not initialized. Run init-vault.sh first."
    exit 1
  fi

  sleep $WAIT_INTERVAL
  elapsed=$((elapsed + WAIT_INTERVAL))
done

if [ $elapsed -ge $MAX_WAIT ]; then
  echo "ERROR: Vault not responsive after ${MAX_WAIT}s"
  exit 1
fi

# Check keys file exists
if [ ! -f "$KEYS_FILE" ]; then
  echo "ERROR: ${KEYS_FILE} not found. Cannot auto-unseal."
  exit 1
fi

# Unseal with 3 keys (threshold)
echo "Unsealing with 3/5 keys..."
for i in 0 1 2; do
  KEY=$(python3 -c "import json; print(json.load(open('${KEYS_FILE}'))['keys'][${i}])")
  RESULT=$(curl -sf -X PUT "${VAULT_ADDR}/v1/sys/unseal" \
    -H "Content-Type: application/json" \
    -d "{\"key\": \"${KEY}\"}")
  STILL_SEALED=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['sealed'])")
  echo "  Key $((i+1))/3 applied. Sealed: ${STILL_SEALED}"
  if [ "$STILL_SEALED" = "False" ]; then
    break
  fi
done

# Final check
HTTP_CODE=$(curl -sf -o /dev/null -w '%{http_code}' "${VAULT_ADDR}/v1/sys/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  echo "Vault unsealed successfully."
else
  echo "ERROR: Vault still not healthy (HTTP $HTTP_CODE)"
  exit 1
fi
