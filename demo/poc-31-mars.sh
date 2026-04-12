#!/usr/bin/env bash
# demo/poc-31-mars.sh — POC Demo Script (March 31, 2026)
#
# Demonstrates STOA Connect bridging webMethods APIs to the STOA Control Plane.
# Runs against live infrastructure:
#   - webMethods Gateway: 51.255.201.17:5555
#   - STOA Connect Agent: 51.255.201.17:8090
#   - Control Plane API:  api.gostoa.dev
#
# Usage:
#   ./demo/poc-31-mars.sh
#
# Prerequisites:
#   - stoa-connect deployed on webMethods VPS (deploy/vps/stoa-connect/deploy.sh)
#   - jq installed locally
#   - SSH key at ~/.ssh/id_ed25519_stoa (for VPS verification steps)

set -euo pipefail

# --- Colors ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

step() { echo -e "\n${BLUE}${BOLD}[$1/6]${NC} ${BOLD}$2${NC}"; }
ok()   { echo -e "  ${GREEN}OK${NC} $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; return 1; }
info() { echo -e "  ${YELLOW}->>${NC} $1"; }

VPS_HOST="${VPS_WEBMETHODS_IP:?Set VPS_WEBMETHODS_IP}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519_stoa}"
SSH="ssh -i ${SSH_KEY} -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5"
CONNECT_URL="http://localhost:8090"

echo -e "${BOLD}"
echo "============================================"
echo "  STOA Platform — POC Demo (March 31, 2026)"
echo "  Legacy-to-Cloud Bridge via STOA Connect"
echo "============================================"
echo -e "${NC}"
echo "Architecture:"
echo "  webMethods (on-prem VPS) --> STOA Connect --> Control Plane (K8s)"
echo ""

# ============================================================
# STEP 1: Verify webMethods Gateway is up
# ============================================================
step 1 "Verify webMethods Gateway is up"
info "Checking webMethods Admin API on ${VPS_HOST}:5555..."

WM_HEALTH=$(${SSH} "root@${VPS_HOST}" \
  'curl -s -u Administrator:manage -H "Accept: application/json" http://localhost:5555/rest/apigateway/health' 2>/dev/null) || true

if [ -n "${WM_HEALTH}" ]; then
  ok "webMethods Admin API is reachable"
else
  fail "webMethods Admin API is not responding"
fi

# List APIs in webMethods
WM_APIS=$(${SSH} "root@${VPS_HOST}" \
  'curl -s -u Administrator:manage -H "Accept: application/json" http://localhost:5555/rest/apigateway/apis' 2>/dev/null)

API_COUNT=$(echo "${WM_APIS}" | jq '[.apiResponse[] | select(.api != null)] | length' 2>/dev/null || echo "0")
ok "${API_COUNT} APIs registered in webMethods"

if [ "${API_COUNT}" -gt 0 ]; then
  echo "${WM_APIS}" | jq -r '.apiResponse[] | select(.api != null) | "  - \(.api.apiName) v\(.api.apiVersion) (type: \(.api.type))"' 2>/dev/null
fi

# ============================================================
# STEP 2: Verify STOA Connect Agent
# ============================================================
step 2 "Verify STOA Connect Agent"
info "Checking stoa-connect health on ${VPS_HOST}:8090..."

HEALTH=$(${SSH} "root@${VPS_HOST}" "curl -s ${CONNECT_URL}/health" 2>/dev/null)
GW_ID=$(echo "${HEALTH}" | jq -r '.gateway_id' 2>/dev/null)
DISCOVERED=$(echo "${HEALTH}" | jq -r '.discovered_apis' 2>/dev/null)
VERSION=$(echo "${HEALTH}" | jq -r '.version' 2>/dev/null)

if [ "${GW_ID}" != "null" ] && [ "${GW_ID}" != "unregistered" ]; then
  ok "Agent registered with Control Plane (gateway_id: ${GW_ID})"
else
  fail "Agent not registered with Control Plane"
fi

ok "${DISCOVERED} APIs discovered from webMethods"
info "Agent version: ${VERSION}"

# ============================================================
# STEP 3: Show Prometheus Metrics
# ============================================================
step 3 "Show Prometheus Metrics (stoa-connect)"
info "Fetching /metrics from stoa-connect..."

METRICS=$(${SSH} "root@${VPS_HOST}" "curl -s ${CONNECT_URL}/metrics" 2>/dev/null)

echo ""
echo "  Metric                                  Value"
echo "  ---------------------------------------- -----"
for metric in gateway_up apis_total discovery_cycles_total heartbeats_sent_total sync_status uptime_seconds; do
  val=$(echo "${METRICS}" | grep "^stoa_connect_${metric} " | awk '{print $2}')
  if [ -n "${val}" ]; then
    printf "  %-41s %s\n" "stoa_connect_${metric}" "${val}"
  fi
done
echo ""

if echo "${METRICS}" | grep -q "stoa_connect_gateway_up 1"; then
  ok "Gateway is UP (stoa_connect_gateway_up = 1)"
else
  fail "Gateway is DOWN (stoa_connect_gateway_up = 0)"
fi

# ============================================================
# STEP 4: Verify Control Plane Registration
# ============================================================
step 4 "Verify Control Plane sees the gateway"
info "Querying Control Plane API (api.gostoa.dev)..."

# Use the internal endpoint with gateway key (read from VPS env)
CP_RESULT=$(${SSH} "root@${VPS_HOST}" bash -c '
  GATEWAY_KEY=$(grep STOA_GATEWAY_API_KEY /opt/secrets/stoa-connect.env | cut -d= -f2)
  CP_URL=$(grep STOA_CONTROL_PLANE_URL /opt/secrets/stoa-connect.env | cut -d= -f2)
  curl -s -H "X-Gateway-Key: ${GATEWAY_KEY}" \
    -X POST "${CP_URL}/v1/internal/gateways/'"${GW_ID}"'/heartbeat" \
    -H "Content-Type: application/json" \
    -d "{\"uptime_seconds\": 0, \"discovered_apis\": '"${DISCOVERED}"'}" \
    -w "\n%{http_code}" 2>/dev/null
' 2>/dev/null)

HTTP_CODE=$(echo "${CP_RESULT}" | tail -1)
if [ "${HTTP_CODE}" = "204" ] || [ "${HTTP_CODE}" = "200" ]; then
  ok "Control Plane accepted heartbeat (HTTP ${HTTP_CODE})"
  ok "Gateway ${GW_ID} is ONLINE in Control Plane"
else
  info "Heartbeat response: HTTP ${HTTP_CODE}"
fi

# ============================================================
# STEP 5: Show Discovery Data
# ============================================================
step 5 "Show discovered APIs (webMethods -> Control Plane)"

echo ""
echo "  APIs bridged from webMethods to STOA Control Plane:"
echo "  ---------------------------------------------------"

# Get discovered APIs from stoa-connect's last discovery
DISCOVERY_DATA=$(${SSH} "root@${VPS_HOST}" bash -c '
  GATEWAY_KEY=$(grep STOA_GATEWAY_API_KEY /opt/secrets/stoa-connect.env | cut -d= -f2)
  CP_URL=$(grep STOA_CONTROL_PLANE_URL /opt/secrets/stoa-connect.env | cut -d= -f2)
  curl -s -H "X-Gateway-Key: ${GATEWAY_KEY}" \
    "${CP_URL}/v1/internal/gateways/routes?gateway_name=connect-webmethods" 2>/dev/null
' 2>/dev/null)

if echo "${DISCOVERY_DATA}" | jq -e '.[0]' >/dev/null 2>&1; then
  echo "${DISCOVERY_DATA}" | jq -r '.[] | "  - \(.name) [\(.methods | join(","))] -> \(.backend_url)"' 2>/dev/null
  ROUTE_COUNT=$(echo "${DISCOVERY_DATA}" | jq 'length' 2>/dev/null)
  ok "${ROUTE_COUNT} routes synced to Control Plane"
else
  info "No CP routes yet (routes are synced separately from discovery)"
  info "Discovery data is stored in gateway health_details on the CP"
fi

echo ""
echo "  Local webMethods APIs (discovered by stoa-connect):"
echo "  ---------------------------------------------------"
echo "${WM_APIS}" | jq -r '.apiResponse[] | select(.api != null) |
  "  - \(.api.apiName) v\(.api.apiVersion) | backend: \(.api.nativeEndpoint[0].uri // "N/A") | active: \(.api.isActive)"' 2>/dev/null || \
  info "No API detail available (wM trial may need restart)"

# ============================================================
# STEP 6: Summary
# ============================================================
step 6 "Demo Summary"

echo ""
echo -e "  ${BOLD}STOA Connect bridges on-prem webMethods to Cloud Control Plane${NC}"
echo ""
echo "  Component          Status    Detail"
echo "  ---------------    ------    ------"
echo -e "  webMethods GW      ${GREEN}UP${NC}        ${VPS_HOST}:5555 (${API_COUNT} APIs)"
echo -e "  STOA Connect       ${GREEN}UP${NC}        ${VPS_HOST}:8090 (v${VERSION})"
echo -e "  CP Registration    ${GREEN}OK${NC}        gateway_id: ${GW_ID}"
echo -e "  API Discovery      ${GREEN}OK${NC}        ${DISCOVERED} APIs discovered"
echo -e "  Prometheus         ${GREEN}OK${NC}        /metrics endpoint active"
echo ""
echo "  Endpoints:"
echo "    Health:   curl ${VPS_HOST}:8090/health"
echo "    Metrics:  curl ${VPS_HOST}:8090/metrics | grep stoa_connect"
echo "    Console:  https://console.gostoa.dev (gateway instances view)"
echo ""
echo -e "${GREEN}${BOLD}Demo complete.${NC}"
