#!/usr/bin/env bash
# =============================================================================
# STOA Platform — OpenSearch Error Snapshots Verification
# =============================================================================
# Verifies the full error snapshot pipeline: seed → index → query.
#
# Usage:
#   ./scripts/demo/test-opensearch.sh                       # Default (50 docs)
#   ./scripts/demo/test-opensearch.sh --count 100           # Custom count
#   OPENSEARCH_URL=https://os:9200 ./scripts/demo/test-opensearch.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

OPENSEARCH_URL="${OPENSEARCH_URL:-https://localhost:9200}"
OPENSEARCH_AUTH="${OPENSEARCH_AUTH:-admin:admin}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
ERROR_COUNT="${ERROR_COUNT:-50}"
CURL_OPTS="-sfk -u ${OPENSEARCH_AUTH}"

for arg in "$@"; do
  case $arg in
    --count)  shift; ERROR_COUNT="$1"; shift ;;
    --count=*) ERROR_COUNT="${arg#*=}" ;;
    --help|-h)
      echo "Usage: $0 [--count N]"
      echo "  --count N   Number of error docs to seed (default: 50)"
      exit 0
      ;;
  esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[PASS]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }

PASS=0
FAIL=0

run_check() {
  local name="$1"
  shift
  echo -n "  $name... "
  if "$@"; then
    echo -e "${GREEN}OK${NC}"
    PASS=$((PASS + 1))
  else
    echo -e "${RED}FAIL${NC}"
    FAIL=$((FAIL + 1))
  fi
}

echo ""
echo "================================================================"
echo "  STOA Platform — OpenSearch Verification"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================"
info "OpenSearch: $OPENSEARCH_URL"
info "Grafana:    $GRAFANA_URL"
info "Count:      $ERROR_COUNT"
echo ""

# ── Step 1: Health check ──────────────────────────────────────────────────
echo -e "${BLUE}Step 1: OpenSearch Health${NC}"

run_check "Cluster health" bash -c "
  STATUS=\$(curl $CURL_OPTS '$OPENSEARCH_URL/_cluster/health' 2>/dev/null | python3 -c \"import sys,json; print(json.load(sys.stdin)['status'])\" 2>/dev/null)
  [ \"\$STATUS\" = 'green' ] || [ \"\$STATUS\" = 'yellow' ]
"

# ── Step 2: Seed error snapshots ──────────────────────────────────────────
echo ""
echo -e "${BLUE}Step 2: Seed ${ERROR_COUNT} Error Snapshots${NC}"

run_check "Seed via seed-error-snapshot.py" python3 \
  "$REPO_ROOT/scripts/demo/seed-error-snapshot.py" \
  --seed-opensearch \
  --opensearch-url "$OPENSEARCH_URL" \
  --opensearch-auth "$OPENSEARCH_AUTH" \
  --count "$ERROR_COUNT"

# ── Step 3: Verify indexed documents ─────────────────────────────────────
echo ""
echo -e "${BLUE}Step 3: Verify Indexed Documents${NC}"

INDEX_PATTERN="stoa-errors-*"

run_check "Document count >= $ERROR_COUNT" bash -c "
  COUNT=\$(curl $CURL_OPTS '$OPENSEARCH_URL/$INDEX_PATTERN/_count' 2>/dev/null | python3 -c \"import sys,json; print(json.load(sys.stdin)['count'])\" 2>/dev/null)
  [ \"\$COUNT\" -ge $ERROR_COUNT ] 2>/dev/null
"

# ── Step 4: Verify tenant distribution ───────────────────────────────────
echo ""
echo -e "${BLUE}Step 4: Verify Data Distribution${NC}"

run_check "Tenant distribution (4 tenants)" bash -c "
  RESULT=\$(curl $CURL_OPTS -X POST '$OPENSEARCH_URL/$INDEX_PATTERN/_search?size=0' \
    -H 'Content-Type: application/json' \
    -d '{\"aggs\":{\"tenants\":{\"terms\":{\"field\":\"tenant_id.keyword\"}}}}' 2>/dev/null)
  BUCKET_COUNT=\$(echo \"\$RESULT\" | python3 -c \"import sys,json; print(len(json.load(sys.stdin)['aggregations']['tenants']['buckets']))\" 2>/dev/null)
  [ \"\$BUCKET_COUNT\" -ge 2 ] 2>/dev/null
"

run_check "Error type distribution (7 types)" bash -c "
  RESULT=\$(curl $CURL_OPTS -X POST '$OPENSEARCH_URL/$INDEX_PATTERN/_search?size=0' \
    -H 'Content-Type: application/json' \
    -d '{\"aggs\":{\"types\":{\"terms\":{\"field\":\"error_type.keyword\"}}}}' 2>/dev/null)
  BUCKET_COUNT=\$(echo \"\$RESULT\" | python3 -c \"import sys,json; print(len(json.load(sys.stdin)['aggregations']['types']['buckets']))\" 2>/dev/null)
  [ \"\$BUCKET_COUNT\" -ge 3 ] 2>/dev/null
"

run_check "Severity distribution (3 levels)" bash -c "
  RESULT=\$(curl $CURL_OPTS -X POST '$OPENSEARCH_URL/$INDEX_PATTERN/_search?size=0' \
    -H 'Content-Type: application/json' \
    -d '{\"aggs\":{\"severities\":{\"terms\":{\"field\":\"severity.keyword\"}}}}' 2>/dev/null)
  BUCKET_COUNT=\$(echo \"\$RESULT\" | python3 -c \"import sys,json; print(len(json.load(sys.stdin)['aggregations']['severities']['buckets']))\" 2>/dev/null)
  [ \"\$BUCKET_COUNT\" -ge 2 ] 2>/dev/null
"

# ── Step 5: Grafana datasource ───────────────────────────────────────────
echo ""
echo -e "${BLUE}Step 5: Grafana Datasource${NC}"

run_check "Grafana API responds" bash -c "
  curl -sf '$GRAFANA_URL/api/health' > /dev/null 2>&1
"

# ── Summary ──────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo ""
echo "================================================================"
echo -e "  Result: ${PASS}/${TOTAL} checks passed"
if [ "$FAIL" -gt 0 ]; then
  fail "${FAIL} check(s) failed"
  echo "================================================================"
  exit 1
else
  log "All checks passed — OpenSearch pipeline verified"
  echo "================================================================"
  exit 0
fi
