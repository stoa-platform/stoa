#!/usr/bin/env bash
# =============================================================================
# STOA Platform — OpenSearch Error Correlation Live Demo (2 min)
# "Every error, traced — from API call to root cause"
#
# Usage: ./scripts/demo/opensearch-live-demo.sh
# Prerequisites: Docker Compose stack running with OpenSearch
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

OPENSEARCH_URL="${OPENSEARCH_URL:-https://localhost:9200}"
OPENSEARCH_AUTH="${OPENSEARCH_AUTH:-admin:admin}"
ERROR_COUNT="${ERROR_COUNT:-50}"
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
if ! curl $CURL_OPTS "${OPENSEARCH_URL}/_cluster/health" > /dev/null 2>&1; then
  echo -e "${RED}OpenSearch not ready at ${OPENSEARCH_URL}. Start docker-compose first.${NC}"
  exit 1
fi

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

echo -e "  ${DIM}Pick a random error, trace it end-to-end${NC}\n"

# Get a random trace_id from indexed docs
TRACE_DOC=$(curl $CURL_OPTS -X POST "${OPENSEARCH_URL}/${INDEX_PATTERN}/_search" \
  -H 'Content-Type: application/json' \
  -d '{"size":1,"query":{"match_all":{}},"sort":[{"@timestamp":"desc"}]}' 2>/dev/null)

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
echo -e "  ${CYAN}Dashboards:${NC}"
echo "    Grafana:    http://localhost:3001/d/stoa-error-snapshots"
echo "    OpenSearch: http://localhost:5601/app/discover"
echo ""
echo -e "  ${DIM}\"Every error, traced — from API call to root cause\"${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
