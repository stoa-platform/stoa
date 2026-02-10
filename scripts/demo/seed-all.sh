#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Master Demo Seed Script
# =============================================================================
# Orchestrates all demo data seeding for the "ESB is Dead" demo (24 fev 2026).
#
# Steps:
#   1. Seed demo data (APIs, plans, consumers, subscriptions)
#   2. Seed error snapshots into OpenSearch
#   3. Optionally run traffic generator
#   4. Run federation isolation tests (if --federation flag)
#
# Prerequisites:
#   - Docker Compose stack running: docker compose up -d
#   - pip install httpx (for seed-demo-data.py)
#   - ANORAK_PASSWORD env var set
#
# Usage:
#   ./scripts/demo/seed-all.sh                    # Seed everything
#   ./scripts/demo/seed-all.sh --skip-traffic     # Skip traffic gen
#   ./scripts/demo/seed-all.sh --federation       # Include federation tests
#   ./scripts/demo/seed-all.sh --opensearch-only  # Only seed OpenSearch
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Defaults
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://localhost:8000}"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8080}"
OPENSEARCH_URL="${OPENSEARCH_URL:-https://localhost:9200}"
OPENSEARCH_AUTH="${OPENSEARCH_AUTH:-admin:StOa_Admin_2026!}"
SKIP_TRAFFIC="${SKIP_TRAFFIC:-false}"
FEDERATION="${FEDERATION:-false}"
OPENSEARCH_ONLY="${OPENSEARCH_ONLY:-false}"
TRAFFIC_DURATION="${TRAFFIC_DURATION:-60}"
ERROR_COUNT="${ERROR_COUNT:-50}"

# Parse args
for arg in "$@"; do
  case $arg in
    --skip-traffic)    SKIP_TRAFFIC=true ;;
    --federation)      FEDERATION=true ;;
    --opensearch-only) OPENSEARCH_ONLY=true ;;
    --help|-h)
      echo "Usage: $0 [--skip-traffic] [--federation] [--opensearch-only]"
      echo ""
      echo "Environment:"
      echo "  CONTROL_PLANE_URL   API URL (default: http://localhost:8000)"
      echo "  KEYCLOAK_URL        Keycloak URL (default: http://localhost:8080)"
      echo "  ANORAK_PASSWORD     Admin password (required for seed-demo-data)"
      echo "  OPENSEARCH_URL      OpenSearch URL (default: https://localhost:9200)"
      echo "  TRAFFIC_DURATION    Traffic gen duration in seconds (default: 60)"
      echo "  ERROR_COUNT         Number of error snapshots to seed (default: 50)"
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

log()  { echo -e "${GREEN}[SEED]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
info() { echo -e "${BLUE}[INFO]${NC} $*"; }

PASS=0
FAIL=0

run_step() {
  local step_name="$1"
  shift
  echo ""
  echo "================================================================"
  log "Step: $step_name"
  echo "================================================================"
  if "$@"; then
    log "$step_name — PASSED"
    PASS=$((PASS + 1))
  else
    fail "$step_name — FAILED (continuing)"
    FAIL=$((FAIL + 1))
  fi
}

# ============================================================================
# Health checks
# ============================================================================

check_api() {
  info "Checking Control Plane API at $CONTROL_PLANE_URL..."
  if curl -sf "$CONTROL_PLANE_URL/health" > /dev/null 2>&1; then
    log "API is healthy"
    return 0
  else
    warn "API not reachable at $CONTROL_PLANE_URL"
    return 1
  fi
}

check_opensearch() {
  info "Checking OpenSearch at $OPENSEARCH_URL..."
  if curl -sf -k -u "${OPENSEARCH_AUTH}" "$OPENSEARCH_URL/_cluster/health" > /dev/null 2>&1; then
    log "OpenSearch is healthy"
    return 0
  else
    warn "OpenSearch not reachable at $OPENSEARCH_URL"
    return 1
  fi
}

# ============================================================================
# Seed steps
# ============================================================================

seed_demo_data() {
  if [ -z "${ANORAK_PASSWORD:-}" ]; then
    warn "ANORAK_PASSWORD not set — skipping demo data seed"
    return 1
  fi
  CONTROL_PLANE_URL="$CONTROL_PLANE_URL" \
  KEYCLOAK_URL="$KEYCLOAK_URL" \
  ANORAK_PASSWORD="$ANORAK_PASSWORD" \
    python3 "$REPO_ROOT/scripts/seed-demo-data.py"
}

seed_opensearch() {
  python3 "$REPO_ROOT/scripts/demo/seed-error-snapshot.py" \
    --seed-opensearch \
    --opensearch-url "$OPENSEARCH_URL" \
    --opensearch-auth "$OPENSEARCH_AUTH" \
    --count "$ERROR_COUNT"
}

run_traffic() {
  python3 "$REPO_ROOT/scripts/demo/traffic-generator.py" \
    --duration "$TRAFFIC_DURATION" \
    --no-warmup
}

seed_ldap() {
  # OpenLDAP auto-import doesn't load /ldif-seed — must seed manually
  if docker exec stoa-federation-ldap ldapsearch -x -H ldap://localhost:389 \
    -b "ou=users,dc=demo,dc=stoa" -D "cn=admin,dc=demo,dc=stoa" \
    -w "admin-password" "(uid=eve-gamma)" uid 2>/dev/null | grep -q "uid: eve-gamma"; then
    log "LDAP users already seeded"
  else
    docker exec stoa-federation-ldap ldapadd -x -H ldap://localhost:389 \
      -D "cn=admin,dc=demo,dc=stoa" -w "admin-password" \
      -f /ldif-seed/seed.ldif 2>&1
    log "LDAP users seeded (eve-gamma, frank-gamma)"
  fi
}

disable_keycloak_ssl() {
  # Keycloak master realm defaults to sslRequired=external, blocking HTTP token requests.
  # All tenant/federation realms already have sslRequired=none in their JSON,
  # but master is not imported from JSON so must be patched at runtime.
  local ADMIN_TOKEN
  ADMIN_TOKEN=$(curl -sf -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
    -d "grant_type=password&client_id=admin-cli&username=admin&password=admin" \
    -H "Content-Type: application/x-www-form-urlencoded" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

  if [ -z "$ADMIN_TOKEN" ]; then
    # Try via nginx (master might already block direct HTTP)
    ADMIN_TOKEN=$(curl -sf -X POST "http://localhost/auth/realms/master/protocol/openid-connect/token" \
      -d "grant_type=password&client_id=admin-cli&username=admin&password=admin" \
      -H "Content-Type: application/x-www-form-urlencoded" 2>/dev/null \
      | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
    local KC_ADMIN_URL="http://localhost/auth"
  else
    local KC_ADMIN_URL="$KEYCLOAK_URL"
  fi

  if [ -z "$ADMIN_TOKEN" ]; then
    warn "Could not get Keycloak admin token — SSL disable skipped"
    return 1
  fi

  # Get all realms and disable SSL where needed
  local REALMS
  REALMS=$(curl -sf "${KC_ADMIN_URL}/admin/realms" \
    -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null)

  echo "$REALMS" | python3 -c "
import sys, json, urllib.request
realms = json.load(sys.stdin)
token = '$ADMIN_TOKEN'
url = '${KC_ADMIN_URL}'
fixed = 0
for r in realms:
    if r.get('sslRequired', 'external') != 'none':
        body = json.dumps({'sslRequired': 'none'}).encode()
        req = urllib.request.Request(f'{url}/admin/realms/{r[\"realm\"]}', data=body, method='PUT',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
        fixed += 1
print(f'{fixed} realm(s) fixed' if fixed else 'all realms OK')
"
}

run_federation_tests() {
  if [ -x "$REPO_ROOT/scripts/demo-federation/04-test-isolation.sh" ]; then
    "$REPO_ROOT/scripts/demo-federation/04-test-isolation.sh"
  else
    warn "Federation test script not found or not executable"
    return 1
  fi
}

# ============================================================================
# Main
# ============================================================================

echo "================================================================"
echo "  STOA Platform — Demo Seed Orchestrator"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================"
info "API:         $CONTROL_PLANE_URL"
info "Keycloak:    $KEYCLOAK_URL"
info "OpenSearch:  $OPENSEARCH_URL"
info "Flags:       skip-traffic=$SKIP_TRAFFIC federation=$FEDERATION opensearch-only=$OPENSEARCH_ONLY"

if [ "$OPENSEARCH_ONLY" = true ]; then
  run_step "OpenSearch Health" check_opensearch
  run_step "Seed Error Snapshots (OpenSearch)" seed_opensearch
else
  # Full seed
  run_step "Disable Keycloak SSL (HTTP dev mode)" disable_keycloak_ssl
  run_step "API Health Check" check_api
  run_step "OpenSearch Health Check" check_opensearch
  run_step "Seed Demo Data (APIs, Plans, Consumers)" seed_demo_data
  run_step "Seed Error Snapshots (OpenSearch)" seed_opensearch

  if [ "$SKIP_TRAFFIC" != true ]; then
    run_step "Traffic Generator (${TRAFFIC_DURATION}s)" run_traffic
  else
    info "Skipping traffic generator (--skip-traffic)"
  fi

  if [ "$FEDERATION" = true ]; then
    run_step "Seed LDAP Users (OpenLDAP)" seed_ldap
    run_step "Federation Isolation Tests" run_federation_tests
  fi
fi

# Summary
echo ""
echo "================================================================"
echo "  SEED SUMMARY"
echo "================================================================"
log "Passed: $PASS"
if [ "$FAIL" -gt 0 ]; then
  fail "Failed: $FAIL"
else
  log "Failed: 0"
fi
echo ""
info "Grafana:    http://localhost:3001"
info "Dashboard:  http://localhost:3001/d/stoa-error-snapshots"
info "Gateway:    http://localhost:3001/d/stoa-gateway-metrics"
info "OpenSearch: http://localhost:5601"
echo "================================================================"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
