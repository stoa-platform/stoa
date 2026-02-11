#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Production Smoke Test (OVH)
# =============================================================================
# Validates all 8 demo acts work against production URLs (*.gostoa.dev).
# Run this before Demo Day to ensure everything is operational.
#
# Usage:
#   ./scripts/demo/smoke-test-production.sh              # Run all checks
#   ./scripts/demo/smoke-test-production.sh --verbose     # Show response bodies
#   KUBECONFIG=~/.kube/config-stoa-ovh ./scripts/demo/smoke-test-production.sh
# =============================================================================

set -euo pipefail

VERBOSE="${VERBOSE:-false}"
for arg in "$@"; do
  case $arg in
    --verbose|-v) VERBOSE=true ;;
    --help|-h)
      echo "Usage: $0 [--verbose]"
      echo "  --verbose  Show response bodies for debugging"
      exit 0
      ;;
  esac
done

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1"
  local result="$2"
  local expected="$3"

  if echo "$result" | grep -q "$expected"; then
    echo -e "  ${GREEN}PASS${NC}  $label"
    PASS=$((PASS + 1))
    return 0
  else
    echo -e "  ${RED}FAIL${NC}  $label (expected: $expected)"
    if [ "$VERBOSE" = true ]; then
      echo "        Response: $result"
    fi
    FAIL=$((FAIL + 1))
    return 1
  fi
}

warn_check() {
  local label="$1"
  local result="$2"
  local expected="$3"

  if echo "$result" | grep -q "$expected"; then
    echo -e "  ${GREEN}PASS${NC}  $label"
    PASS=$((PASS + 1))
    return 0
  else
    echo -e "  ${YELLOW}WARN${NC}  $label (fallback expected — $expected)"
    WARN=$((WARN + 1))
    return 0
  fi
}

echo ""
echo "================================================================"
echo -e "  ${BOLD}STOA Platform — Production Smoke Test${NC}"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  Target: *.gostoa.dev (OVH MKS)"
echo "================================================================"

# ─────────────────────────────────────────────────────────────────────
# Act 1: Console (Control Plane UI)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 1: Console${NC}"
R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://console.gostoa.dev/ 2>/dev/null || echo "000")
check "Console HTTPS reachable" "$R" "200\|302"

R=$(curl -s --max-time 10 https://api.gostoa.dev/health 2>/dev/null || echo "error")
check "CP API health" "$R" "healthy"

# ─────────────────────────────────────────────────────────────────────
# Act 2: Portal (Developer Portal)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 2: Portal${NC}"
R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://portal.gostoa.dev/ 2>/dev/null || echo "000")
check "Portal HTTPS reachable" "$R" "200\|302"

# ─────────────────────────────────────────────────────────────────────
# Act 3: Gateway (Rust)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 3: Gateway${NC}"
R=$(curl -s --max-time 10 https://gateway.gostoa.dev/health 2>/dev/null || echo "error")
check "Gateway /health" "$R" "healthy\|OK\|ok\|UP"

R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://gateway.gostoa.dev/.well-known/openid-configuration 2>/dev/null || echo "000")
check "Gateway OIDC discovery" "$R" "200"

# ─────────────────────────────────────────────────────────────────────
# Act 4: Observability (Grafana + Prometheus)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 4: Observability${NC}"
R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://console.gostoa.dev/grafana/ 2>/dev/null || echo "000")
check "Grafana reachable" "$R" "200\|302"

R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 https://console.gostoa.dev/grafana/login 2>/dev/null || echo "000")
check "Grafana login (OIDC redirect)" "$R" "200\|302\|307"

# ─────────────────────────────────────────────────────────────────────
# Act 5: OpenSearch (Logs)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 5: OpenSearch${NC}"
R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://opensearch.gostoa.dev/ 2>/dev/null || echo "000")
check "OpenSearch Dashboards HTTPS" "$R" "200\|302"

# ─────────────────────────────────────────────────────────────────────
# Act 6: Federation (Keycloak + LDAP)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 6: Federation${NC}"
R=$(curl -s --max-time 10 https://auth.gostoa.dev/realms/stoa/.well-known/openid-configuration 2>/dev/null || echo "error")
check "Keycloak stoa realm OIDC" "$R" "issuer"

# Check federation realms exist
for realm in idp-source-alpha idp-source-beta demo-org-alpha demo-org-beta demo-org-gamma; do
  R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 "https://auth.gostoa.dev/realms/$realm/.well-known/openid-configuration" 2>/dev/null || echo "000")
  check "Realm $realm exists" "$R" "200"
done

# Test LDAP federation: eve-gamma token via ROPC
R=$(curl -s --max-time 15 -X POST "https://auth.gostoa.dev/realms/demo-org-gamma/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=federation-demo&client_secret=gamma-demo-secret&username=eve-gamma&password=demo" 2>/dev/null || echo "error")
check "LDAP federation (eve-gamma token)" "$R" "access_token"

# ─────────────────────────────────────────────────────────────────────
# Act 7: MCP (Tool Invocation)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 7: MCP${NC}"
R=$(curl -sI -o /dev/null -w "%{http_code}" --max-time 10 https://mcp.gostoa.dev/health 2>/dev/null || echo "000")
check "MCP endpoint health" "$R" "200"

R=$(curl -s --max-time 10 https://mcp.gostoa.dev/mcp/v1/tools 2>/dev/null || echo "error")
check "MCP tools list" "$R" "tools\|name"

# ─────────────────────────────────────────────────────────────────────
# Act 8: Born GitOps (informational — local git stats)
# ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}Act 8: Born GitOps${NC}"
echo -e "  ${GREEN}PASS${NC}  N/A (local presentation, no remote check needed)"
PASS=$((PASS + 1))

# ─────────────────────────────────────────────────────────────────────
# K8s Cluster Health (if KUBECONFIG available)
# ─────────────────────────────────────────────────────────────────────
KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-stoa-ovh}"
if [ -f "$KUBECONFIG" ]; then
  echo ""
  echo -e "${BLUE}K8s Cluster Health:${NC}"

  # Pods in stoa-system
  NOT_RUNNING=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n stoa-system --no-headers 2>/dev/null | grep -v Running | grep -v Completed || true)
  if [ -z "$NOT_RUNNING" ]; then
    echo -e "  ${GREEN}PASS${NC}  All stoa-system pods Running"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}FAIL${NC}  Some pods not Running:"
    echo "$NOT_RUNNING" | while read -r line; do echo "        $line"; done
    FAIL=$((FAIL + 1))
  fi

  # TLS certificates
  NOT_READY=$(KUBECONFIG="$KUBECONFIG" kubectl get certificates -A --no-headers 2>/dev/null | grep -v True || true)
  if [ -z "$NOT_READY" ]; then
    echo -e "  ${GREEN}PASS${NC}  All TLS certificates Ready"
    PASS=$((PASS + 1))
  else
    echo -e "  ${YELLOW}WARN${NC}  Some certificates not Ready:"
    echo "$NOT_READY" | while read -r line; do echo "        $line"; done
    WARN=$((WARN + 1))
  fi

  # Monitoring namespace
  MON_RUNNING=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n monitoring --no-headers 2>/dev/null | grep -c Running || echo "0")
  check "Monitoring pods ($MON_RUNNING Running)" "$MON_RUNNING" "[1-9]"

  # OpenSearch namespace
  OS_RUNNING=$(KUBECONFIG="$KUBECONFIG" kubectl get pods -n opensearch --no-headers 2>/dev/null | grep -c Running || echo "0")
  check "OpenSearch pods ($OS_RUNNING Running)" "$OS_RUNNING" "[1-9]"
else
  echo ""
  echo -e "  ${YELLOW}SKIP${NC}  K8s checks (KUBECONFIG not found at $KUBECONFIG)"
fi

# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL + WARN))
echo ""
echo "================================================================"
echo -e "  ${BOLD}Results: ${PASS}/${TOTAL} passed, ${FAIL} failed, ${WARN} warnings${NC}"
if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}${BOLD}ALL CHECKS PASSED — Ready for Demo Day!${NC}"
else
  echo -e "  ${RED}${BOLD}${FAIL} FAILURE(S) — Fix before Demo Day${NC}"
fi
echo "================================================================"
echo ""

exit "$FAIL"
