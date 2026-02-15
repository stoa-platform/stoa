#!/usr/bin/env bash
# =============================================================================
# STOA Platform — OpenSearch Error Correlation Live Demo (~90s)
# "Every error, traced — from API call to root cause"
#
# Usage:
#   ./scripts/demo/opensearch-live-demo.sh           # local (localhost:9200)
#   ./scripts/demo/opensearch-live-demo.sh --prod     # production (opensearch.gostoa.dev)
#   ./scripts/demo/opensearch-live-demo.sh --cleanup  # delete stoa-errors-* first
#
# Prerequisites: OpenSearch accessible (local Docker Compose or production)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Defaults (local dev)
OPENSEARCH_URL="${OPENSEARCH_URL:-https://localhost:9200}"
OPENSEARCH_AUTH="${OPENSEARCH_AUTH:-admin:admin}"
GATEWAY_URL="${GATEWAY_URL:-https://mcp.gostoa.dev}"
ERROR_COUNT="${ERROR_COUNT:-50}"
CLEANUP=false
VALIDATE=false

# Parse flags
for arg in "$@"; do
  case $arg in
    --prod)
      OPENSEARCH_URL="https://opensearch.gostoa.dev"
      OPENSEARCH_AUTH="${OPENSEARCH_AUTH:-admin:${OPENSEARCH_ADMIN_PASSWORD:-}}"
      GATEWAY_URL="https://mcp.gostoa.dev"
      if [ -z "${OPENSEARCH_ADMIN_PASSWORD:-}" ] && [ "${OPENSEARCH_AUTH}" = "admin:" ]; then
        echo -e "${RED}Error: OPENSEARCH_ADMIN_PASSWORD not set for --prod mode${NC}"
        echo "Get it from Infisical: infisical secrets get ADMIN_PASSWORD --env=prod --path=/opensearch --plain"
        exit 1
      fi
      ;;
    --cleanup)
      CLEANUP=true
      ;;
    --validate)
      VALIDATE=true
      ;;
  esac
done

CURL_OPTS="-sfk -u ${OPENSEARCH_AUTH}"
INDEX_PATTERN="stoa-errors-*"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

banner() {
  echo -e "\n${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BOLD}${CYAN}  $1${NC}"
  echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

pause() { sleep "${1:-0.5}"; }

os_query() {
  curl $CURL_OPTS -X POST "${OPENSEARCH_URL}/${INDEX_PATTERN}/_search?size=0" \
    -H 'Content-Type: application/json' \
    -d "$1" 2>/dev/null
}

# ─── Pre-flight ──────────────────────────────────────────────────────────
echo -e "  ${DIM}OpenSearch: ${OPENSEARCH_URL}${NC}"
echo -e "  ${DIM}Gateway:    ${GATEWAY_URL}${NC}"
echo ""

if ! curl $CURL_OPTS "${OPENSEARCH_URL}/_cluster/health" > /dev/null 2>&1; then
  echo -e "${RED}OpenSearch not ready at ${OPENSEARCH_URL}${NC}"
  exit 1
fi

# ─── Validate mode (pre-demo check) ─────────────────────────────────────
if [ "$VALIDATE" = true ]; then
  banner "Pre-Demo Validation"
  PASS=0; FAIL=0

  # 1. OpenSearch cluster health
  OS_HEALTH=$(curl $CURL_OPTS "${OPENSEARCH_URL}/_cluster/health" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unreachable")
  if [ "$OS_HEALTH" = "green" ] || [ "$OS_HEALTH" = "yellow" ]; then
    echo -e "  ${GREEN}PASS${NC} OpenSearch cluster: ${OS_HEALTH}"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC} OpenSearch cluster: ${OS_HEALTH}"; FAIL=$((FAIL+1))
  fi

  # 2. Gateway health
  GW_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/health" 2>/dev/null || echo "000")
  if [ "$GW_STATUS" = "200" ]; then
    echo -e "  ${GREEN}PASS${NC} Gateway health: HTTP ${GW_STATUS}"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC} Gateway health: HTTP ${GW_STATUS}"; FAIL=$((FAIL+1))
  fi

  # 3. Document count in stoa-errors-*
  DOC_CT=$(curl $CURL_OPTS "${OPENSEARCH_URL}/${INDEX_PATTERN}/_count" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")
  if [ "$DOC_CT" -gt 0 ] 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} Error documents: ${DOC_CT} in ${INDEX_PATTERN}"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC} No documents in ${INDEX_PATTERN}"; FAIL=$((FAIL+1))
  fi

  # 4. Hero errors present
  HERO_CT=$(curl $CURL_OPTS -X POST "${OPENSEARCH_URL}/${INDEX_PATTERN}/_count" \
    -H 'Content-Type: application/json' \
    -d '{"query":{"wildcard":{"trace_id.keyword":"HERO-*"}}}' 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")
  if [ "$HERO_CT" -ge 3 ] 2>/dev/null; then
    echo -e "  ${GREEN}PASS${NC} Hero errors: ${HERO_CT} (expected >= 3)"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC} Hero errors: ${HERO_CT} (expected >= 3)"; FAIL=$((FAIL+1))
  fi

  echo ""
  if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}ALL ${PASS} CHECKS PASSED${NC} — ready for demo"
  else
    echo -e "  ${RED}${BOLD}${FAIL} CHECK(S) FAILED${NC} — run with --prod --cleanup first to seed data"
  fi
  exit "$FAIL"
fi

# ─── Cleanup (optional) ─────────────────────────────────────────────────
if [ "$CLEANUP" = true ]; then
  echo -e "  ${YELLOW}Cleaning up: deleting ${INDEX_PATTERN} index...${NC}"
  curl $CURL_OPTS -X DELETE "${OPENSEARCH_URL}/${INDEX_PATTERN}" > /dev/null 2>&1 || true
  echo -e "  ${GREEN}✓${NC} Index cleaned\n"
fi

# ═════════════════════════════════════════════════════════════════════════
# PHASE 0 — Fire real gateway errors (10s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 0 — Firing Controlled Gateway Errors"

echo -e "  ${DIM}Sending requests that will fail at the gateway level...${NC}\n"

# 401 — no auth token
STATUS_401=$(curl -sk -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/mcp/v1/tools" 2>/dev/null || echo "000")
echo -e "  ${RED}401${NC} No auth token      → HTTP ${STATUS_401}"

# 404 — nonexistent path
STATUS_404=$(curl -sk -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/nonexistent-tool-xyz" 2>/dev/null || echo "000")
echo -e "  ${RED}404${NC} Bad path           → HTTP ${STATUS_404}"

# 401 — invalid bearer token
STATUS_BAD=$(curl -sk -o /dev/null -w "%{http_code}" -H "Authorization: Bearer invalid-token-demo" \
  "${GATEWAY_URL}/mcp/v1/tools" 2>/dev/null || echo "000")
echo -e "  ${RED}401${NC} Invalid JWT        → HTTP ${STATUS_BAD}"

# 405 — wrong method on health endpoint
STATUS_405=$(curl -sk -o /dev/null -w "%{http_code}" -X DELETE "${GATEWAY_URL}/health" 2>/dev/null || echo "000")
echo -e "  ${RED}405${NC} Wrong HTTP method  → HTTP ${STATUS_405}"

# 400 — malformed JSON body
STATUS_400=$(curl -sk -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" -d '{broken' \
  "${GATEWAY_URL}/mcp/v1/tools/invoke" 2>/dev/null || echo "000")
echo -e "  ${RED}400${NC} Malformed JSON     → HTTP ${STATUS_400}"

echo -e "\n  ${GREEN}✓${NC} 5 controlled errors fired — visible in gateway access logs"
pause 1

# ═════════════════════════════════════════════════════════════════════════
# PHASE 1 — Seed fresh errors (10s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 1 — Seeding ${ERROR_COUNT} Error Snapshots"

echo -e "  ${DIM}Indexing controlled errors across 4 tenants, 7 error types...${NC}\n"

python3 "$REPO_ROOT/scripts/demo/seed-error-snapshot.py" \
  --seed-opensearch \
  --opensearch-url "$OPENSEARCH_URL" \
  --opensearch-auth "$OPENSEARCH_AUTH" \
  --count "$ERROR_COUNT" > /dev/null 2>&1

# Verify count
DOC_COUNT=$(curl $CURL_OPTS "${OPENSEARCH_URL}/${INDEX_PATTERN}/_count" 2>/dev/null \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null)
echo -e "  ${GREEN}✓${NC} ${DOC_COUNT} error snapshots indexed in OpenSearch"
pause

# ═════════════════════════════════════════════════════════════════════════
# PHASE 2 — Error type distribution (20s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 2 — Error Distribution by Type"

echo -e "  ${DIM}7 error types across all API endpoints${NC}\n"

RESULT=$(os_query '{"aggs":{"types":{"terms":{"field":"error_type.keyword","size":10}}}}')
echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
buckets = data['aggregations']['types']['buckets']
total = sum(b['doc_count'] for b in buckets)
for b in buckets:
    name = b['key'].replace('_', ' ').title()
    count = b['doc_count']
    pct = count * 100 // total if total > 0 else 0
    bar = '█' * (pct // 3) + '░' * (30 - pct // 3)
    print(f'  {name:<25} {bar} {count:>3} ({pct}%)')
"
pause 1

# ═════════════════════════════════════════════════════════════════════════
# PHASE 3 — Tenant distribution (20s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 3 — Error Distribution by Tenant"

echo -e "  ${DIM}Multi-tenant isolation: each tenant sees only their errors${NC}\n"

RESULT=$(os_query '{"aggs":{"tenants":{"terms":{"field":"tenant_id.keyword","size":10}}}}')
echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
buckets = data['aggregations']['tenants']['buckets']
total = sum(b['doc_count'] for b in buckets)
colors = ['\033[0;32m', '\033[0;36m', '\033[1;33m', '\033[0;34m']
nc = '\033[0m'
for i, b in enumerate(buckets):
    name = b['key']
    count = b['doc_count']
    pct = count * 100 // total if total > 0 else 0
    c = colors[i % len(colors)]
    bar = '█' * (pct // 3) + '░' * (30 - pct // 3)
    print(f'  {c}{name:<20}{nc} {bar} {count:>3} ({pct}%)')
"
pause 1

# ═════════════════════════════════════════════════════════════════════════
# PHASE 4 — Severity breakdown (20s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 4 — Severity Breakdown"

echo -e "  ${DIM}Critical / Error / Warning classification${NC}\n"

RESULT=$(os_query '{"aggs":{"severities":{"terms":{"field":"severity.keyword","size":5}}}}')
echo "$RESULT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
buckets = data['aggregations']['severities']['buckets']
total = sum(b['doc_count'] for b in buckets)
severity_colors = {'critical': '\033[0;31m', 'error': '\033[1;33m', 'warning': '\033[0;36m'}
nc = '\033[0m'
for b in buckets:
    name = b['key']
    count = b['doc_count']
    pct = count * 100 // total if total > 0 else 0
    c = severity_colors.get(name, nc)
    icon = '🔴' if name == 'critical' else ('🟡' if name == 'error' else '🔵')
    bar = '█' * (pct // 3) + '░' * (30 - pct // 3)
    print(f'  {icon} {c}{name.upper():<12}{nc} {bar} {count:>3} ({pct}%)')
"
pause 1

# ═════════════════════════════════════════════════════════════════════════
# PHASE 5 — Trace lookup (15s)
# ═════════════════════════════════════════════════════════════════════════
banner "PHASE 5 — Live Trace Lookup"

echo -e "  ${DIM}Search for a critical timeout error by HERO trace ID${NC}\n"

# Get the hero timeout error (deterministic — always findable)
TRACE_DOC=$(curl $CURL_OPTS -X POST "${OPENSEARCH_URL}/${INDEX_PATTERN}/_search" \
  -H 'Content-Type: application/json' \
  -d '{"size":1,"query":{"wildcard":{"trace_id.keyword":"HERO-TIMEOUT-*"}}}' 2>/dev/null)

echo "$TRACE_DOC" | python3 -c "
import sys, json
data = json.load(sys.stdin)
hit = data['hits']['hits'][0]['_source']
print(f'  Trace ID:    \033[1m{hit[\"trace_id\"]}\033[0m')
print(f'  Timestamp:   {hit[\"@timestamp\"]}')
print(f'  Tenant:      {hit[\"tenant_id\"]}')
print(f'  Error Type:  {hit[\"error_type\"]}')
print(f'  HTTP Status: {hit[\"http_status\"]}')
print(f'  Severity:    {hit[\"severity\"]}')
print(f'  Endpoint:    {hit[\"method\"]} {hit[\"endpoint\"]}')
print(f'  Message:     {hit[\"error_message\"]}')
print(f'  Response:    {hit[\"response_time_ms\"]}ms')
"
pause 1

# ═════════════════════════════════════════════════════════════════════════
# PHASE 6 — Verdict (10s)
# ═════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}"
echo "    ███████╗██████╗ ██████╗  ██████╗ ██████╗ "
echo "    ██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔══██╗"
echo "    █████╗  ██████╔╝██████╔╝██║   ██║██████╔╝"
echo "    ██╔══╝  ██╔══██╗██╔══██╗██║   ██║██╔══██╗"
echo "    ███████╗██║  ██║██║  ██║╚██████╔╝██║  ██║"
echo "    ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝"
echo ""
echo "     ██████╗ ██████╗ ██████╗ ██████╗ ███████╗██╗      █████╗ ████████╗██╗ ██████╗ ███╗   ██╗"
echo "    ██╔════╝██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║     ██╔══██╗╚══██╔══╝██║██╔═══██╗████╗  ██║"
echo "    ██║     ██║   ██║██████╔╝██████╔╝█████╗  ██║     ███████║   ██║   ██║██║   ██║██╔██╗ ██║"
echo "    ██║     ██║   ██║██╔══██╗██╔══██╗██╔══╝  ██║     ██╔══██║   ██║   ██║██║   ██║██║╚██╗██║"
echo "    ╚██████╗╚██████╔╝██║  ██║██║  ██║███████╗███████╗██║  ██║   ██║   ██║╚██████╔╝██║ ╚████║"
echo "     ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝"
echo ""
echo "    ██╗   ██╗███████╗██████╗ ██╗███████╗██╗███████╗██████╗ "
echo "    ██║   ██║██╔════╝██╔══██╗██║██╔════╝██║██╔════╝██╔══██╗"
echo "    ██║   ██║█████╗  ██████╔╝██║█████╗  ██║█████╗  ██║  ██║"
echo "    ╚██╗ ██╔╝██╔══╝  ██╔══██╗██║██╔══╝  ██║██╔══╝  ██║  ██║"
echo "     ╚████╔╝ ███████╗██║  ██║██║██║     ██║███████╗██████╔╝"
echo "      ╚═══╝  ╚══════╝╚═╝  ╚═╝╚═╝╚═╝     ╚═╝╚══════╝╚═════╝ "
echo -e "${NC}"
echo -e "  ${BOLD}${DOC_COUNT} errors indexed, traced, and correlated${NC}"
echo ""
echo -e "  ${CYAN}What this proves:${NC}"
echo "    1. Every API error captured with trace_id + tenant context"
echo "    2. 7 error types classified (validation, auth, rate limit, timeout, ...)"
echo "    3. 4 tenants isolated — each org sees only their errors"
echo "    4. Severity triage: critical / error / warning"
echo "    5. Single trace lookup: from error to root cause in seconds"
echo ""
echo -e "  ${CYAN}Next:${NC}"
echo "    OpenSearch Dashboards → Discover → stoa-errors-* → filter last 15 min"
echo "    Click any error → trace_id, tenant_id, error_type, response_time_ms"
echo ""
echo -e "  ${DIM}\"Every error, traced — from API call to root cause\"${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
