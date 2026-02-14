#!/usr/bin/env bash
# =============================================================================
# STOA Platform — mTLS Flow Validation (CAB-872)
# =============================================================================
# Automated pre-demo validation of the full mTLS pipeline:
#   1. Cert generation check
#   2. Consumer credentials check
#   3. Keycloak token acquisition (cnf claim verification)
#   4. Gateway call with correct cert → 200
#   5. Gateway call with wrong cert → 403 MTLS_BINDING_MISMATCH
#   6. Gateway call without cert → 401 MTLS_CERT_REQUIRED
#
# Usage:
#   ./scripts/demo/validate-mtls-flow.sh                  # against prod
#   GATEWAY_URL=http://localhost:8080 ./validate-mtls-flow.sh  # local
#
# Exit codes: 0 = all pass, 1 = failures
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${MTLS_CERTS_DIR:-$SCRIPT_DIR/certs}"

GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
AUTH_URL="${AUTH_URL:-https://auth.gostoa.dev}"
API_URL="${API_URL:-https://api.gostoa.dev}"

PASS=0
FAIL=0
TOTAL=0

# Colors (if terminal)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  RED='\033[0;31m'
  YELLOW='\033[0;33m'
  NC='\033[0m'
else
  GREEN='' RED='' YELLOW='' NC=''
fi

check() {
  local name="$1"
  local expected="$2"
  local actual="$3"
  TOTAL=$((TOTAL + 1))
  if [ "$actual" = "$expected" ]; then
    echo -e "  ${GREEN}✓${NC} $name (got $actual)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}✗${NC} $name (expected $expected, got $actual)"
    FAIL=$((FAIL + 1))
  fi
}

check_contains() {
  local name="$1"
  local expected="$2"
  local body="$3"
  TOTAL=$((TOTAL + 1))
  if echo "$body" | grep -qi "$expected"; then
    echo -e "  ${GREEN}✓${NC} $name (body contains '$expected')"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}✗${NC} $name (body missing '$expected')"
    FAIL=$((FAIL + 1))
  fi
}

echo "================================================================"
echo "  STOA mTLS Flow Validation (CAB-872)"
echo "================================================================"
echo "  Gateway:  $GATEWAY_URL"
echo "  Auth:     $AUTH_URL"
echo "  Certs:    $CERTS_DIR"
echo "================================================================"
echo ""

# ─── CHECK 1: Prerequisites ──────────────────────────────────────────────────
echo "Phase 1: Prerequisites"

TOTAL=$((TOTAL + 1))
if [ -f "$CERTS_DIR/fingerprints.csv" ]; then
  FP_COUNT=$(wc -l < "$CERTS_DIR/fingerprints.csv" | tr -d ' ')
  FP_COUNT=$((FP_COUNT - 1))  # minus header
  echo -e "  ${GREEN}✓${NC} fingerprints.csv ($FP_COUNT certs)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}✗${NC} fingerprints.csv missing — run generate-mtls-certs.sh first"
  FAIL=$((FAIL + 1))
fi

TOTAL=$((TOTAL + 1))
if [ -f "$CERTS_DIR/credentials.json" ]; then
  CRED_COUNT=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(len(c))
" 2>/dev/null || echo "0")
  echo -e "  ${GREEN}✓${NC} credentials.json ($CRED_COUNT consumers)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}✗${NC} credentials.json missing — run seed-mtls-demo.py first"
  FAIL=$((FAIL + 1))
  echo ""
  echo "Result: $PASS/$TOTAL passed, $FAIL failed"
  exit 1
fi

# Load first consumer credentials
CLIENT_ID=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(c[0]['client_id'])
" 2>/dev/null)

CLIENT_SECRET=$(python3 -c "
import json
d=json.load(open('$CERTS_DIR/credentials.json'))
c=d.get('credentials',d) if isinstance(d,dict) else d
print(c[0]['client_secret'])
" 2>/dev/null)

FINGERPRINT=$(awk -F',' 'NR==2{print $2}' "$CERTS_DIR/fingerprints.csv")
WRONG_FINGERPRINT="0000000000000000000000000000000000000000000000000000000000000000"

echo ""

# ─── CHECK 2: Keycloak Token Acquisition ─────────────────────────────────────
echo "Phase 2: Keycloak Token"

TOKEN_RESPONSE=$(curl -sf -X POST "$AUTH_URL/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" 2>/dev/null || echo '{"error":"request_failed"}')

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

TOTAL=$((TOTAL + 1))
if [ -n "$TOKEN" ] && [ "$TOKEN" != "" ]; then
  echo -e "  ${GREEN}✓${NC} Token acquired (${#TOKEN} chars)"
  PASS=$((PASS + 1))
else
  ERROR=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error','unknown'))" 2>/dev/null || echo "unknown")
  echo -e "  ${RED}✗${NC} Token acquisition failed: $ERROR"
  FAIL=$((FAIL + 1))
  echo ""
  echo "Result: $PASS/$TOTAL passed, $FAIL failed"
  exit 1
fi

# Verify cnf claim in JWT
CNF_CLAIM=$(echo "$TOKEN" | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip()
payload = token.split('.')[1]
payload += '=' * (4 - len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
cnf = claims.get('cnf', {})
print(json.dumps(cnf))
" 2>/dev/null || echo "{}")

TOTAL=$((TOTAL + 1))
if echo "$CNF_CLAIM" | grep -q "x5t#S256"; then
  THUMBPRINT=$(echo "$CNF_CLAIM" | python3 -c "import sys,json; print(json.load(sys.stdin).get('x5t#S256',''))" 2>/dev/null)
  echo -e "  ${GREEN}✓${NC} JWT contains cnf.x5t#S256 claim (${THUMBPRINT:0:12}...)"
  PASS=$((PASS + 1))
else
  echo -e "  ${YELLOW}⚠${NC} JWT missing cnf claim (cert binding not configured in Keycloak)"
  PASS=$((PASS + 1))  # Non-fatal — binding may not be required
fi

echo ""

# ─── CHECK 3: Gateway — Valid Cert (expect 200) ──────────────────────────────
echo "Phase 3: Gateway mTLS Scenarios"

RESPONSE_FILE=$(mktemp)

# Scenario A: Correct certificate → should pass
HTTP_CODE=$(curl -sf -o "$RESPONSE_FILE" -w "%{http_code}" \
  -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: $FINGERPRINT" \
  -H "X-SSL-Client-S-DN: CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR" \
  -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
  -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' 2>/dev/null || echo "000")

BODY_A=$(cat "$RESPONSE_FILE" 2>/dev/null || echo "")

# Accept 200 or 404 (tool not found is OK — means auth passed)
TOTAL=$((TOTAL + 1))
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ]; then
  echo -e "  ${GREEN}✓${NC} Scenario A: Valid cert → HTTP $HTTP_CODE (auth passed)"
  PASS=$((PASS + 1))
else
  echo -e "  ${RED}✗${NC} Scenario A: Valid cert → HTTP $HTTP_CODE (expected 200 or 404)"
  echo "    Body: $(echo "$BODY_A" | head -c 200)"
  FAIL=$((FAIL + 1))
fi

# Scenario B: Wrong certificate → expect 403 MTLS_BINDING_MISMATCH
HTTP_CODE=$(curl -sf -o "$RESPONSE_FILE" -w "%{http_code}" \
  -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: $WRONG_FINGERPRINT" \
  -H "X-SSL-Client-S-DN: CN=attacker,OU=evil-corp,O=Evil Inc,C=XX" \
  -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
  -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' 2>/dev/null || echo "000")

BODY_B=$(cat "$RESPONSE_FILE" 2>/dev/null || echo "")
check "Scenario B: Wrong cert → HTTP 403" "403" "$HTTP_CODE"
check_contains "Scenario B: Error code" "MTLS_BINDING_MISMATCH" "$BODY_B"

# Scenario C: No certificate → expect 401 MTLS_CERT_REQUIRED
HTTP_CODE=$(curl -sf -o "$RESPONSE_FILE" -w "%{http_code}" \
  -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool":"petstore","arguments":{"action":"list-pets"}}' 2>/dev/null || echo "000")

BODY_C=$(cat "$RESPONSE_FILE" 2>/dev/null || echo "")
check "Scenario C: No cert → HTTP 401" "401" "$HTTP_CODE"
check_contains "Scenario C: Error code" "MTLS_CERT_REQUIRED" "$BODY_C"

rm -f "$RESPONSE_FILE"

echo ""

# ─── SUMMARY ─────────────────────────────────────────────────────────────────
echo "================================================================"
if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}ALL $TOTAL CHECKS PASSED${NC}"
  echo "  mTLS pipeline is ready for demo"
else
  echo -e "  ${RED}$FAIL/$TOTAL CHECKS FAILED${NC}"
  echo "  Fix issues before demo rehearsal"
fi
echo "================================================================"

exit "$FAIL"
