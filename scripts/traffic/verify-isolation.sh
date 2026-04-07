#!/usr/bin/env bash
# Verify tenant isolation in link seed output.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0; SKIP=0

check() {
  local label="$1" condition="$2"
  if eval "$condition"; then
    echo -e "  ${GREEN}PASS${NC}  $label"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}FAIL${NC}  $label"; FAIL=$((FAIL+1))
  fi
}
check_skip() { echo -e "  ${YELLOW}SKIP${NC}  $1 — $2"; SKIP=$((SKIP+1)); }

LOGFILE=""
if [ "${1:-}" = "--from-file" ] && [ -n "${2:-}" ]; then
  LOGFILE="$2"
else
  LOGFILE=$(mktemp); trap 'rm -f "$LOGFILE"' EXIT
  echo "Running link seed to capture output..."
  "$SCRIPT_DIR/link-traffic-seed.sh" > "$LOGFILE" 2>&1 || true
  echo ""
fi

echo "═══════════════════════════════════════════════════════════"
echo "  Tenant Isolation Verification"
echo "═══════════════════════════════════════════════════════════"
echo ""

echo "1. Tenant presence:"
ACME=$(grep -c "acme-corp" "$LOGFILE" || true)
GLOBEX=$(grep -c "globex-inc" "$LOGFILE" || true)
INITECH=$(grep -c "initech" "$LOGFILE" || true)
check "acme-corp has traces ($ACME lines)" "[ $ACME -gt 0 ]"
check "globex-inc has traces ($GLOBEX lines)" "[ $GLOBEX -gt 0 ]"
check "initech has traces ($INITECH lines)" "[ $INITECH -gt 0 ]"
echo ""

echo "2. Gateway presence:"
KONG=$(grep -c "kong-k3d" "$LOGFILE" || true)
WM=$(grep -c "wm-docker" "$LOGFILE" || true)
[ "$KONG" -gt 0 ] && check "Kong k3d ($KONG lines)" "true" || check_skip "Kong k3d" "unreachable"
[ "$WM" -gt 0 ] && check "wM Docker ($WM lines)" "true" || check_skip "wM Docker" "unreachable"
echo ""

echo "3. Assertion errors:"
ERRORS=$(grep -c '^  FAIL' "$LOGFILE" || true)
check "Zero unexpected failures ($ERRORS found)" "[ $ERRORS -eq 0 ]"
echo ""

echo "4. Cross-tenant isolation:"
CROSS=$(grep -v "Tenants:\|Config:\|TOTAL\|═" "$LOGFILE" | grep -c "acme-corp.*globex-inc\|globex-inc.*acme-corp\|acme-corp.*initech\|initech.*acme-corp\|globex-inc.*initech\|initech.*globex-inc" || true)
check "No cross-tenant contamination ($CROSS)" "[ $CROSS -eq 0 ]"
echo ""

echo "═══════════════════════════════════════════════════════════"
TOTAL=$((PASS + FAIL + SKIP))
if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}PASS${NC} — $PASS/$TOTAL checks ($SKIP skipped)"
else
  echo -e "  ${RED}FAIL${NC} — $PASS passed, $FAIL failed, $SKIP skipped"
fi
echo "═══════════════════════════════════════════════════════════"
[ "$FAIL" -gt 0 ] && exit 1
exit 0
