#!/usr/bin/env bash
# Orchestrator — runs all 3 traffic seeds.
# Usage:
#   ./scripts/traffic/seed-all.sh
#   ./scripts/traffic/seed-all.sh --only link
#   ./scripts/traffic/seed-all.sh --verify

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RUN_EDGE_MCP=true; RUN_LINK=true; RUN_CONNECT=true; RUN_VERIFY=false
while [ $# -gt 0 ]; do
  case "$1" in
    --skip-edge-mcp) RUN_EDGE_MCP=false ;;
    --skip-link)     RUN_LINK=false ;;
    --skip-connect)  RUN_CONNECT=false ;;
    --verify)        RUN_VERIFY=true ;;
    --only)
      RUN_EDGE_MCP=false; RUN_LINK=false; RUN_CONNECT=false; shift
      case "${1:-}" in
        edge-mcp) RUN_EDGE_MCP=true ;; link) RUN_LINK=true ;; connect) RUN_CONNECT=true ;;
        *) echo "Unknown: $1"; exit 1 ;;
      esac ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
  shift
done

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
TOTAL_OK=0; TOTAL_FAIL=0

run_seed() {
  local label="$1" script="$2"
  echo ""
  echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
  echo -e "${CYAN}  [$label] Seed${NC}"
  echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
  echo ""
  [ ! -x "$script" ] && { echo -e "  ${RED}SKIP${NC} — $script not executable"; return; }
  local output
  output=$("$script" 2>&1) || true
  echo "$output"
  local ok fail
  ok=$(echo "$output" | grep -oE '[0-9]+ ok' | tail -1 | grep -oE '[0-9]+' || echo "0")
  fail=$(echo "$output" | grep -oE '[0-9]+ fail' | tail -1 | grep -oE '[0-9]+' || echo "0")
  TOTAL_OK=$((TOTAL_OK + ok)); TOTAL_FAIL=$((TOTAL_FAIL + fail))
}

echo -e "${CYAN}STOA Traffic Seed — All Modes${NC}"
echo "$(date '+%Y-%m-%d %H:%M:%S')"

[ "$RUN_EDGE_MCP" = true ] && run_seed "edge-mcp" "$SCRIPT_DIR/local-traffic-seed.sh"
[ "$RUN_LINK" = true ]     && run_seed "link"      "$SCRIPT_DIR/link-traffic-seed.sh"
[ "$RUN_CONNECT" = true ]  && run_seed "connect"   "$SCRIPT_DIR/connect-traffic-seed.sh"

echo ""
echo -e "${CYAN}═══ TOTAL ════════════════════════════════════════════════${NC}"
if [ "$TOTAL_FAIL" -gt 0 ]; then
  echo -e "  ${GREEN}${TOTAL_OK} ok${NC}, ${RED}${TOTAL_FAIL} fail${NC}"
else
  echo -e "  ${GREEN}${TOTAL_OK} ok${NC}, 0 fail"
fi

[ "$RUN_VERIFY" = true ] && { echo ""; "$SCRIPT_DIR/verify-isolation.sh"; }
[ "$TOTAL_FAIL" -gt 0 ] && exit 1
exit 0
