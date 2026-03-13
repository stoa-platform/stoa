#!/usr/bin/env bash
# =============================================================================
# Setup Vault PKI Secrets Engine (mTLS Certificate Authority)
# =============================================================================
# Configures Vault as an intermediate CA for issuing mTLS certificates.
# Used by: stoa-gateway mTLS, service-to-service auth, client certificates.
#
# Usage:
#   ./setup-pki-engine.sh                   # Full setup (root CA + intermediate + roles)
#   ./setup-pki-engine.sh --issue <cn>      # Issue a test certificate
#
# Prerequisites:
#   - VAULT_ADDR set (default: https://hcvault.gostoa.dev)
#   - VAULT_TOKEN set (admin token)
#
# Architecture:
#   pki/         → Root CA (10y TTL, offline, signs intermediate only)
#   pki_int/     → Intermediate CA (1y TTL, issues leaf certs)
#   Roles:       gateway-mtls (30d), service-mesh (7d)
#
# Phase 5 — CAB-1802
# =============================================================================
set -euo pipefail

VAULT_ADDR="${VAULT_ADDR:-https://hcvault.gostoa.dev}"
VAULT_TOKEN="${VAULT_TOKEN:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOMAIN="gostoa.dev"
ISSUE_CN=""

for arg in "$@"; do
  case $arg in
    --issue) shift; ISSUE_CN="${2:-}"; shift ;;
  esac
done

if [ -z "$VAULT_TOKEN" ]; then
  echo "ERROR: VAULT_TOKEN not set."
  exit 1
fi

vault_api() {
  local method="$1" path="$2"
  shift 2
  curl -sf -X "$method" "${VAULT_ADDR}/v1${path}" \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    -H "Content-Type: application/json" \
    "$@"
}

# --- Issue a test certificate ---
if [ -n "$ISSUE_CN" ]; then
  echo "Issuing certificate for: ${ISSUE_CN}"
  RESULT=$(vault_api POST "/pki_int/issue/gateway-mtls" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'common_name': '${ISSUE_CN}',
    'ttl': '720h'
}))
")")
  echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)['data']
print('Certificate:')
print(data['certificate'][:80] + '...')
print()
print('Issuing CA:')
print(data['issuing_ca'][:80] + '...')
print()
print(f'Serial: {data[\"serial_number\"]}')
print(f'Expiration: {data[\"expiration\"]}')
"
  exit 0
fi

# =============================================================================
# Full Setup
# =============================================================================
echo "=== Vault PKI Engine Setup ==="
echo "Vault:  ${VAULT_ADDR}"
echo "Domain: ${DOMAIN}"
echo ""

# Step 1: Enable Root CA PKI engine
echo "[1/7] Enabling Root CA PKI engine at pki/..."
vault_api POST "/sys/mounts/pki" \
  -d '{"type": "pki", "config": {"max_lease_ttl": "87600h"}}' 2>/dev/null \
  && echo "  Enabled (max TTL: 10y)" || echo "  Already enabled"

# Step 2: Generate Root CA
echo "[2/7] Generating Root CA..."
ROOT_RESULT=$(vault_api POST "/pki/root/generate/internal" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'common_name': 'STOA Platform Root CA',
    'organization': 'STOA Platform',
    'ou': 'Infrastructure',
    'country': 'FR',
    'ttl': '87600h',
    'issuer_name': 'stoa-root-ca',
    'key_type': 'ec',
    'key_bits': 256
}))
")" 2>/dev/null)

if echo "$ROOT_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('certificate','')[:40])" 2>/dev/null | grep -q "BEGIN"; then
  echo "  Root CA generated (EC P-256, 10y)"
else
  echo "  Root CA already exists (skipping)"
fi

# Step 3: Configure Root CA URLs
echo "[3/7] Configuring Root CA URLs..."
vault_api POST "/pki/config/urls" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'issuing_certificates': '${VAULT_ADDR}/v1/pki/ca',
    'crl_distribution_points': '${VAULT_ADDR}/v1/pki/crl'
}))
")" > /dev/null
echo "  URLs configured"

# Step 4: Enable Intermediate CA PKI engine
echo "[4/7] Enabling Intermediate CA PKI engine at pki_int/..."
vault_api POST "/sys/mounts/pki_int" \
  -d '{"type": "pki", "config": {"max_lease_ttl": "43800h"}}' 2>/dev/null \
  && echo "  Enabled (max TTL: 5y)" || echo "  Already enabled"

# Step 5: Generate Intermediate CSR + sign with Root
echo "[5/7] Generating Intermediate CA..."

# Generate CSR
CSR_RESULT=$(vault_api POST "/pki_int/intermediate/generate/internal" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'common_name': 'STOA Platform Intermediate CA',
    'organization': 'STOA Platform',
    'ou': 'Infrastructure',
    'country': 'FR',
    'issuer_name': 'stoa-intermediate-ca',
    'key_type': 'ec',
    'key_bits': 256
}))
")" 2>/dev/null)

CSR=$(echo "$CSR_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('csr',''))" 2>/dev/null || echo "")

if [ -n "$CSR" ] && [ "$CSR" != "" ]; then
  # Sign with Root CA
  SIGN_RESULT=$(vault_api POST "/pki/root/sign-intermediate" \
    -d "$(python3 -c "
import json
print(json.dumps({
    'csr': '''${CSR}''',
    'format': 'pem_bundle',
    'ttl': '43800h'
}))
")")

  SIGNED_CERT=$(echo "$SIGN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['certificate'])")

  # Set signed certificate on intermediate
  vault_api POST "/pki_int/intermediate/set-signed" \
    -d "$(python3 -c "import json; print(json.dumps({'certificate': '''${SIGNED_CERT}'''}))")" > /dev/null

  echo "  Intermediate CA signed by Root (EC P-256, 5y)"
else
  echo "  Intermediate CA already exists (skipping)"
fi

# Step 6: Configure Intermediate CA URLs
vault_api POST "/pki_int/config/urls" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'issuing_certificates': '${VAULT_ADDR}/v1/pki_int/ca',
    'crl_distribution_points': '${VAULT_ADDR}/v1/pki_int/crl'
}))
")" > /dev/null

# Step 7: Create issuing roles
echo "[6/7] Creating issuing roles..."

# Gateway mTLS role — for stoa-gateway client/server certificates
vault_api POST "/pki_int/roles/gateway-mtls" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'allowed_domains': ['${DOMAIN}', 'svc.cluster.local'],
    'allow_subdomains': True,
    'allow_bare_domains': False,
    'max_ttl': '720h',
    'ttl': '720h',
    'key_type': 'ec',
    'key_bits': 256,
    'require_cn': True,
    'server_flag': True,
    'client_flag': True,
    'key_usage': ['DigitalSignature', 'KeyEncipherment'],
    'ext_key_usage': ['ServerAuth', 'ClientAuth'],
    'organization': ['STOA Platform']
}))
")" && echo "  Role 'gateway-mtls' created (30d TTL, *.gostoa.dev)"

# Service mesh role — shorter TTL for internal service-to-service
vault_api POST "/pki_int/roles/service-mesh" \
  -d "$(python3 -c "
import json
print(json.dumps({
    'allowed_domains': ['svc.cluster.local', 'stoa-system.svc.cluster.local'],
    'allow_subdomains': True,
    'allow_bare_domains': True,
    'max_ttl': '168h',
    'ttl': '168h',
    'key_type': 'ec',
    'key_bits': 256,
    'require_cn': True,
    'server_flag': True,
    'client_flag': True,
    'organization': ['STOA Platform']
}))
")" && echo "  Role 'service-mesh' created (7d TTL, *.svc.cluster.local)"

# Step 7: Write PKI policy
echo "[7/7] Writing pki-issuer policy..."
POLICY_FILE="${SCRIPT_DIR}/policies/pki-issuer.hcl"
cat > "$POLICY_FILE" << 'POLICY'
# PKI issuer policy — issue mTLS certificates via Vault CA
# Used by: stoa-gateway (gateway-mtls role), K8s cert-manager (service-mesh role)

# Issue certificates (gateway mTLS — 30d TTL)
path "pki_int/issue/gateway-mtls" {
  capabilities = ["create", "update"]
}

# Issue certificates (service mesh — 7d TTL)
path "pki_int/issue/service-mesh" {
  capabilities = ["create", "update"]
}

# Read CA chain (needed for trust bundle distribution)
path "pki_int/ca/pem" {
  capabilities = ["read"]
}
path "pki_int/ca_chain" {
  capabilities = ["read"]
}
path "pki/ca/pem" {
  capabilities = ["read"]
}

# List certificates (informational)
path "pki_int/certs" {
  capabilities = ["list"]
}

# Revoke certificates
path "pki_int/revoke" {
  capabilities = ["create", "update"]
}
POLICY
echo "  Policy written to: ${POLICY_FILE}"

vault_api PUT "/sys/policies/acl/pki-issuer" \
  -d "$(python3 -c "import json; print(json.dumps({'policy': open('${POLICY_FILE}').read()}))")"
echo "  Policy 'pki-issuer' applied"

echo ""
echo "=== PKI Engine Setup Complete ==="
echo ""
echo "Engines:"
echo "  pki/       Root CA (STOA Platform Root CA, EC P-256, 10y)"
echo "  pki_int/   Intermediate CA (signed by Root, EC P-256, 5y)"
echo ""
echo "Roles:"
echo "  gateway-mtls   *.gostoa.dev              TTL 30d  (stoa-gateway mTLS)"
echo "  service-mesh   *.svc.cluster.local        TTL 7d   (K8s internal)"
echo ""
echo "Policy: pki-issuer"
echo ""
echo "Test: $0 --issue mcp.gostoa.dev"
echo ""
echo "Future integration:"
echo "  - cert-manager + Vault issuer for K8s automatic cert rotation"
echo "  - stoa-gateway mTLS with Vault-issued client certs"
