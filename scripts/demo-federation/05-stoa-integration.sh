#!/usr/bin/env bash
# =============================================================================
# STOA Federation Demo — STOA Integration
# Shows STOA value-add beyond raw Keycloak federation:
#   - OPA policy evaluation
#   - Realm-aware gateway routing
#   - Federation metadata for observability
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_DIR="${SCRIPT_DIR}/.tokens"

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

OPA_URL="${OPA_URL:-http://localhost:8181}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"

echo -e "${CYAN}=== STOA Integration — Beyond Raw Federation ===${NC}"
echo ""

# 1. OPA Policy Evaluation
echo -e "${YELLOW}1. OPA Policy Engine — Federation Isolation${NC}"
echo "   STOA uses OPA to enforce realm-to-API mapping."
echo "   This is the formal policy, not just gateway code."
echo ""

# Test: Alpha token claims against alpha tenant (should allow)
echo -e "   ${CYAN}Test: Alpha claims → Alpha tenant${NC}"
RESULT=$(curl -s -X POST "${OPA_URL}/v1/data/stoa/federation/allow" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "tenant": "alpha",
      "token": {
        "iss": "http://keycloak:8080/realms/demo-org-alpha",
        "aud": ["stoa-federation-api"],
        "stoa_realm": "demo-org-alpha",
        "exp": 9999999999
      },
      "current_time": 1706400000
    }
  }')
ALLOWED=$(echo "${RESULT}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result', False))" 2>/dev/null || echo "error")
if [ "${ALLOWED}" = "True" ]; then
  echo -e "   ${GREEN}ALLOW${NC} — OPA approved alpha→alpha"
else
  echo -e "   ${RED}DENY${NC} — OPA result: ${RESULT}"
fi

# Test: Alpha token claims against beta tenant (should deny)
echo -e "   ${CYAN}Test: Alpha claims → Beta tenant${NC}"
RESULT=$(curl -s -X POST "${OPA_URL}/v1/data/stoa/federation/allow" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "tenant": "beta",
      "token": {
        "iss": "http://keycloak:8080/realms/demo-org-alpha",
        "aud": ["stoa-federation-api"],
        "stoa_realm": "demo-org-alpha",
        "exp": 9999999999
      },
      "current_time": 1706400000
    }
  }')
ALLOWED=$(echo "${RESULT}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result', False))" 2>/dev/null || echo "error")
if [ "${ALLOWED}" = "False" ]; then
  echo -e "   ${GREEN}DENY${NC} — OPA blocked alpha→beta (correct)"
else
  echo -e "   ${RED}ALLOW${NC} — OPA should have denied! Result: ${RESULT}"
fi

# Get deny reason
REASON=$(curl -s -X POST "${OPA_URL}/v1/data/stoa/federation/deny_reason" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "tenant": "beta",
      "token": {
        "iss": "http://keycloak:8080/realms/demo-org-alpha",
        "stoa_realm": "demo-org-alpha"
      }
    }
  }')
echo -e "   Reason: $(echo "${REASON}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null)"
echo ""

# 2. Realm Inventory
echo -e "${YELLOW}2. Multi-Realm Inventory — Platform Awareness${NC}"
echo "   STOA knows all federated organizations and their protocols."
echo ""

ADMIN_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli&username=admin&password=admin&grant_type=password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)

if [ -n "${ADMIN_TOKEN}" ]; then
  echo "   Federated realms:"
  curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" "${KEYCLOAK_URL}/admin/realms" \
    | python3 -c "
import sys, json
realms = json.load(sys.stdin)
for r in realms:
    name = r['realm']
    if name.startswith('demo-org-'):
        display = r.get('displayName', name)
        enabled = '  enabled' if r.get('enabled') else 'disabled'
        print(f'     - {name}: {display} ({enabled})')
" 2>/dev/null
  echo ""

  # Show IdP configs per realm
  echo "   Identity Provider configurations:"
  for REALM in demo-org-alpha demo-org-beta demo-org-gamma; do
    IDPS=$(curl -s -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      "${KEYCLOAK_URL}/admin/realms/${REALM}/identity-provider/instances" 2>/dev/null)
    IDP_INFO=$(echo "${IDPS}" | python3 -c "
import sys, json
idps = json.load(sys.stdin)
if idps:
    for idp in idps:
        print(f'     - {idp[\"alias\"]} ({idp[\"providerId\"]})')
else:
    print('     - LDAP User Federation (no IdP broker)')
" 2>/dev/null || echo "     - (error reading)")
    echo "   ${REALM}:"
    echo "${IDP_INFO}"
  done
fi

echo ""
echo -e "${CYAN}=== STOA Value Summary ===${NC}"
echo ""
echo "  What STOA adds beyond raw Keycloak federation:"
echo ""
echo "  1. OPA Policy Engine   — Formal, auditable isolation rules"
echo "  2. Realm Awareness     — Platform knows all orgs, protocols, IdPs"
echo "  3. API Subscriptions   — Token scoping tied to API contracts"
echo "  4. Metering per Realm  — Usage tracking per organization"
echo "  5. MCP-Native          — AI agents inherit federation model"
echo "  6. GitOps Realms       — Realm configs as code, not console clicks"
echo ""
echo "  This is not 'Keycloak consulting' — it's API-lifecycle-aware federation."
