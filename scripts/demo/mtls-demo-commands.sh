#!/usr/bin/env bash
# =============================================================================
# STOA Platform — mTLS Demo Commands (CAB-864 / CAB-872)
# =============================================================================
# !! DEMO ONLY — NOT FOR PRODUCTION USE !!
# These commands use demo credentials and test certificates.
# =============================================================================
# Live demo script for mTLS + OAuth2 Certificate Binding (RFC 8705).
# Run each section manually during the demo for maximum impact.
#
# Prerequisites:
#   1. ./scripts/demo/generate-mtls-certs.sh       (generate test certs)
#   2. python3 scripts/demo/seed-mtls-demo.py       (seed consumers)
#   3. Gateway running with STOA_MTLS_ENABLED=true
#
# Usage:
#   source scripts/demo/mtls-demo-commands.sh       (load variables)
#   Then copy-paste each section into the terminal
#
#   ./scripts/demo/mtls-demo-commands.sh --validate  (automated pre-flight check)
# =============================================================================

# === Token Lifetime ===
# Keycloak realm "stoa" has accessTokenLifespan=3600s (60 min).
# Act 3b needs ~3 min — verified OK (20x safety margin).
# If token expires mid-demo: re-run STEP 2 to get a fresh one.

# === Configuration (adjust for your environment) ===
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
AUTH_URL="${AUTH_URL:-https://auth.gostoa.dev}"
API_URL="${API_URL:-https://api.gostoa.dev}"
# When sourced, BASH_SOURCE[0] is this file; when executed, $0 works too
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CERTS_DIR="${MTLS_CERTS_DIR:-$SCRIPT_DIR/certs}"

# Load first consumer credentials from seed output
if [ -f "$CERTS_DIR/credentials.json" ]; then
  CONSUMER_CLIENT_ID=$(python3 -c "import json; d=json.load(open('$CERTS_DIR/credentials.json')); c=d.get('credentials',d) if isinstance(d,dict) else d; print(c[0]['client_id'])" 2>/dev/null || echo "")
  CONSUMER_CLIENT_SECRET=$(python3 -c "import json; d=json.load(open('$CERTS_DIR/credentials.json')); c=d.get('credentials',d) if isinstance(d,dict) else d; print(c[0]['client_secret'])" 2>/dev/null || echo "")
fi

# Load fingerprints for demo
if [ -f "$CERTS_DIR/fingerprints.csv" ]; then
  CORRECT_FINGERPRINT=$(awk -F',' 'NR==2{print $2}' "$CERTS_DIR/fingerprints.csv")
  WRONG_FINGERPRINT="0000000000000000000000000000000000000000000000000000000000000000"
fi

# =============================================================================
# --validate: Automated pre-flight check (CAB-872)
# =============================================================================
if [ "${1:-}" = "--validate" ]; then
  set -euo pipefail
  FAILURES=0
  PASS='\033[0;32mPASS\033[0m'
  FAIL='\033[0;31mFAIL\033[0m'

  echo "================================================================"
  echo "  STOA mTLS Validate — RFC 8705 Pre-Flight Check"
  echo "================================================================"
  echo "  Gateway:  $GATEWAY_URL"
  echo "  Auth:     $AUTH_URL"
  echo "  Certs:    $CERTS_DIR"
  echo ""

  # CHECK 1: Prerequisites
  echo -n "  [1/6] Prerequisites (credentials.json + fingerprints.csv)... "
  if [ -z "${CONSUMER_CLIENT_ID:-}" ] || [ -z "${CORRECT_FINGERPRINT:-}" ]; then
    echo -e "$FAIL"
    echo "        credentials.json or fingerprints.csv missing in $CERTS_DIR"
    echo "        Run: ./scripts/demo/generate-mtls-certs.sh && python3 scripts/demo/seed-mtls-demo.py"
    FAILURES=$((FAILURES + 1))
    echo ""
    echo "Cannot continue without prerequisites. $FAILURES check(s) failed."
    exit $FAILURES
  fi
  echo -e "$PASS (client_id=${CONSUMER_CLIENT_ID:0:8}..., fingerprint=${CORRECT_FINGERPRINT:0:16}...)"

  # CHECK 2: Get token
  echo -n "  [2/6] Token acquisition (client_credentials grant)... "
  TOKEN_RESPONSE=$(curl -sf -X POST "$AUTH_URL/realms/stoa/protocol/openid-connect/token" \
    -d "grant_type=client_credentials" \
    -d "client_id=$CONSUMER_CLIENT_ID" \
    -d "client_secret=$CONSUMER_CLIENT_SECRET" 2>/dev/null || echo "")
  TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
  if [ -z "$TOKEN" ]; then
    echo -e "$FAIL"
    echo "        Could not get token from $AUTH_URL"
    echo "        Response: ${TOKEN_RESPONSE:0:200}"
    FAILURES=$((FAILURES + 1))
  else
    echo -e "$PASS (${#TOKEN} chars)"
  fi

  # CHECK 3: cnf.x5t#S256 in JWT
  echo -n "  [3/6] JWT cnf.x5t#S256 claim present... "
  if [ -n "$TOKEN" ]; then
    CNF_CLAIM=$(echo "$TOKEN" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
cnf = claims.get('cnf', {})
print(cnf.get('x5t#S256', ''))
" 2>/dev/null || echo "")
    if [ -n "$CNF_CLAIM" ]; then
      echo -e "$PASS (x5t#S256=${CNF_CLAIM:0:16}...)"
    else
      echo -e "$FAIL"
      echo "        Token missing cnf.x5t#S256 claim (Keycloak mapper not configured?)"
      FAILURES=$((FAILURES + 1))
    fi
  else
    echo -e "$FAIL (skipped — no token)"
    FAILURES=$((FAILURES + 1))
  fi

  # CHECK 4: Correct cert → expect 200
  echo -n "  [4/6] Correct certificate → HTTP 200... "
  if [ -n "$TOKEN" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-SSL-Client-Verify: SUCCESS" \
      -H "X-SSL-Client-Fingerprint: $CORRECT_FINGERPRINT" \
      -H "X-SSL-Client-S-DN: CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR" \
      -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
      -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}' 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
      echo -e "$PASS (HTTP $HTTP_CODE)"
    else
      echo -e "$FAIL (HTTP $HTTP_CODE, expected 200)"
      FAILURES=$((FAILURES + 1))
    fi
  else
    echo -e "$FAIL (skipped — no token)"
    FAILURES=$((FAILURES + 1))
  fi

  # CHECK 5: Wrong cert → expect 403
  echo -n "  [5/6] Wrong certificate → HTTP 403... "
  if [ -n "$TOKEN" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-SSL-Client-Verify: SUCCESS" \
      -H "X-SSL-Client-Fingerprint: $WRONG_FINGERPRINT" \
      -H "X-SSL-Client-S-DN: CN=attacker,OU=evil-corp,O=Evil Inc,C=XX" \
      -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
      -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}' 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "403" ]; then
      echo -e "$PASS (HTTP $HTTP_CODE)"
    else
      echo -e "$FAIL (HTTP $HTTP_CODE, expected 403)"
      FAILURES=$((FAILURES + 1))
    fi
  else
    echo -e "$FAIL (skipped — no token)"
    FAILURES=$((FAILURES + 1))
  fi

  # CHECK 6: No cert → expect 401
  echo -n "  [6/6] No certificate → HTTP 401... "
  if [ -n "$TOKEN" ]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}' 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "401" ]; then
      echo -e "$PASS (HTTP $HTTP_CODE)"
    else
      echo -e "$FAIL (HTTP $HTTP_CODE, expected 401)"
      FAILURES=$((FAILURES + 1))
    fi
  else
    echo -e "$FAIL (skipped — no token)"
    FAILURES=$((FAILURES + 1))
  fi

  # Summary
  echo ""
  echo "================================================================"
  if [ "$FAILURES" -eq 0 ]; then
    echo -e "  \033[0;32mALL 6 CHECKS PASSED\033[0m — mTLS demo ready"
  else
    echo -e "  \033[0;31m$FAILURES CHECK(S) FAILED\033[0m — fix issues above"
  fi
  echo "================================================================"
  exit "$FAILURES"
fi

# =============================================================================
# Source mode: print demo commands for copy-paste
# =============================================================================

echo "================================================================"
echo "  STOA mTLS Demo — RFC 8705 Certificate Binding"
echo "================================================================"
echo ""
echo "  Gateway:     $GATEWAY_URL"
echo "  Auth:        $AUTH_URL"
echo "  Client ID:   ${CONSUMER_CLIENT_ID:-NOT SET}"
echo "  Fingerprint: ${CORRECT_FINGERPRINT:0:16}..."
echo ""
echo "  Copy-paste each section below during the demo."
echo "================================================================"

# =============================================================================
# DEMO STEP 1: Show bulk onboarding result
# =============================================================================
cat << 'STEP1'

# ─── STEP 1: "We just onboarded 100 enterprise clients with certificates" ───
# (Already done by seed-mtls-demo.py — show the result)

STEP1
echo "
curl -s $API_URL/v1/consumers/acme-corp?page_size=5 \\
  -H \"Authorization: Bearer \$ADMIN_TOKEN\" | python3 -m json.tool
"

# =============================================================================
# DEMO STEP 2: Get a cert-bound token from Keycloak
# =============================================================================
cat << 'STEP2'

# ─── STEP 2: "The consumer gets a token — with certificate binding built in" ───
# The Keycloak client has a cnf.x5t#S256 protocol mapper configured automatically.
# The token will contain the certificate fingerprint in the 'cnf' claim (RFC 8705).

STEP2
echo "
# Get cert-bound token
TOKEN=\$(curl -s -X POST \"$AUTH_URL/realms/stoa/protocol/openid-connect/token\" \\
  -d \"grant_type=client_credentials\" \\
  -d \"client_id=$CONSUMER_CLIENT_ID\" \\
  -d \"client_secret=$CONSUMER_CLIENT_SECRET\" \\
  | python3 -c \"import sys,json; print(json.load(sys.stdin)['access_token'])\")
echo \"Token acquired (first 50 chars): \${TOKEN:0:50}...\"
"

# =============================================================================
# DEMO STEP 3: Decode the JWT to show the cnf claim
# =============================================================================
cat << 'STEP3'

# ─── STEP 3: "Look inside the token — the certificate fingerprint is embedded" ───
# The 'cnf' claim binds this token to a specific X.509 certificate.
# No one can use this token without presenting the matching certificate.

STEP3
echo "
echo \$TOKEN | python3 -c \"
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print(json.dumps({
    'sub': claims.get('sub', ''),
    'cnf': claims.get('cnf', {}),
    'tenant_id': claims.get('tenant_id', ''),
    'consumer_id': claims.get('consumer_id', ''),
}, indent=2))
\"
# Expected: { \"cnf\": { \"x5t#S256\": \"<base64url fingerprint>\" } }
"

# =============================================================================
# DEMO STEP 4: Call gateway WITH correct certificate (simulating F5)
# =============================================================================
cat << 'STEP4'

# ─── STEP 4: "The client calls the API through F5 — certificate matches token" ───
# F5 terminates mTLS and injects X-SSL-* headers.
# We simulate F5 by injecting the headers directly.
# The gateway verifies: cert fingerprint == JWT cnf.x5t#S256 → ACCESS GRANTED

STEP4
echo "
curl -s -w \"\\nHTTP %{http_code}\\n\" \\
  -X POST \"$GATEWAY_URL/mcp/v1/tools/invoke\" \\
  -H \"Content-Type: application/json\" \\
  -H \"Authorization: Bearer \$TOKEN\" \\
  -H \"X-SSL-Client-Verify: SUCCESS\" \\
  -H \"X-SSL-Client-Fingerprint: $CORRECT_FINGERPRINT\" \\
  -H \"X-SSL-Client-S-DN: CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR\" \\
  -H \"X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR\" \\
  -d '{\"tool\": \"petstore\", \"arguments\": {\"action\": \"list-pets\"}}'
# Expected: HTTP 200 — Certificate matches token binding ✅
"

# =============================================================================
# DEMO STEP 5: Call gateway WITH WRONG certificate → BINDING MISMATCH
# =============================================================================
cat << 'STEP5'

# ─── STEP 5: "What if someone steals the token and uses a different certificate?" ───
# The fingerprint doesn't match the cnf claim in the JWT.
# This detects stolen tokens — even with a valid JWT, wrong cert = REJECTED.

STEP5
echo "
curl -s -w \"\\nHTTP %{http_code}\\n\" \\
  -X POST \"$GATEWAY_URL/mcp/v1/tools/invoke\" \\
  -H \"Content-Type: application/json\" \\
  -H \"Authorization: Bearer \$TOKEN\" \\
  -H \"X-SSL-Client-Verify: SUCCESS\" \\
  -H \"X-SSL-Client-Fingerprint: $WRONG_FINGERPRINT\" \\
  -H \"X-SSL-Client-S-DN: CN=attacker,OU=evil-corp,O=Evil Inc,C=XX\" \\
  -H \"X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR\" \\
  -d '{\"tool\": \"petstore\", \"arguments\": {\"action\": \"list-pets\"}}'
# Expected: HTTP 403 — MTLS_BINDING_MISMATCH 🚫 (stolen token detected!)
"

# =============================================================================
# DEMO STEP 6: Call gateway WITHOUT certificate → CERT REQUIRED
# =============================================================================
cat << 'STEP6'

# ─── STEP 6: "Without a certificate? No access to sensitive APIs." ───
# On routes configured with STOA_MTLS_REQUIRED_ROUTES, no cert = no access.

STEP6
echo "
curl -s -w \"\\nHTTP %{http_code}\\n\" \\
  -X POST \"$GATEWAY_URL/mcp/v1/tools/invoke\" \\
  -H \"Content-Type: application/json\" \\
  -H \"Authorization: Bearer \$TOKEN\" \\
  -d '{\"tool\": \"petstore\", \"arguments\": {\"action\": \"list-pets\"}}'
# Expected: HTTP 401 — MTLS_CERT_REQUIRED 🔒 (certificate required on this route)
"

# =============================================================================
# TALKING POINTS (for presenter reference)
# =============================================================================
cat << 'TALKING'

# ─── TALKING POINTS ───
#
# "This is RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication.
#  The standard used by banks, payment processors, and regulated industries."
#
# "The certificate fingerprint is embedded in every JWT token.
#  Even if a token is stolen, it's useless without the matching certificate."
#
# "We just onboarded 100 enterprise clients with certificates in under 5 seconds.
#  Each one got an OAuth2 client with automatic certificate binding.
#  No manual configuration. No ServiceNow ticket. No 3-week onboarding process."
#
# "The F5 handles TLS termination. The STOA Gateway validates the binding.
#  Zero trust, end to end."
#
# "And it's all automatic: rotate a certificate, the binding updates.
#  Revoke a certificate, the client is instantly blocked."

TALKING
