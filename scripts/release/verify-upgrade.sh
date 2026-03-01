#!/usr/bin/env bash
# verify-upgrade.sh — Post-upgrade verification for STOA Platform
# Runs all component health checks and reports pass/fail.
# Exit 0 = all checks pass, Exit 1 = at least one check failed.
#
# Usage:
#   ./scripts/release/verify-upgrade.sh                    # Use env vars
#   ./scripts/release/verify-upgrade.sh --base-domain gostoa.dev  # Override domain
#   ./scripts/release/verify-upgrade.sh --namespace stoa-system    # Override namespace
#   ./scripts/release/verify-upgrade.sh --skip-k8s                 # Skip kubectl checks

set -euo pipefail

# --- Configuration ---
BASE_DOMAIN="${BASE_DOMAIN:-gostoa.dev}"
NAMESPACE="${NAMESPACE:-stoa-system}"
SKIP_K8S="${SKIP_K8S:-false}"
TIMEOUT=10

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --base-domain) BASE_DOMAIN="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --skip-k8s) SKIP_K8S=true; shift ;;
    --help) echo "Usage: $0 [--base-domain DOMAIN] [--namespace NS] [--skip-k8s]"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

STOA_API_URL="${STOA_API_URL:-https://api.${BASE_DOMAIN}}"
STOA_GATEWAY_URL="${STOA_GATEWAY_URL:-https://mcp.${BASE_DOMAIN}}"
STOA_AUTH_URL="${STOA_AUTH_URL:-https://auth.${BASE_DOMAIN}}"
STOA_CONSOLE_URL="${STOA_CONSOLE_URL:-https://console.${BASE_DOMAIN}}"
STOA_PORTAL_URL="${STOA_PORTAL_URL:-https://portal.${BASE_DOMAIN}}"

# --- State ---
PASS=0
FAIL=0
TOTAL=0
RESULTS=()

# --- Helpers ---
check() {
  local name="$1"
  local cmd="$2"
  local expected="$3"
  TOTAL=$((TOTAL + 1))

  local output
  local status=0
  output=$(eval "$cmd" 2>&1) || status=$?

  if [[ $status -eq 0 ]] && echo "$output" | grep -qE "$expected"; then
    PASS=$((PASS + 1))
    RESULTS+=("PASS  $name")
    printf "  \033[32mPASS\033[0m  %s\n" "$name"
  else
    FAIL=$((FAIL + 1))
    RESULTS+=("FAIL  $name — got: ${output:0:120}")
    printf "  \033[31mFAIL\033[0m  %s\n" "$name"
    printf "        %s\n" "${output:0:200}"
  fi
}

# --- Banner ---
echo ""
echo "================================================"
echo "  STOA Platform — Post-Upgrade Verification"
echo "================================================"
echo "  Domain:    ${BASE_DOMAIN}"
echo "  Namespace: ${NAMESPACE}"
echo "  Skip K8s:  ${SKIP_K8S}"
echo "  Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================"
echo ""

# --- HTTP Health Checks ---
echo "HTTP Health Checks"
echo "------------------"

check "API Health" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_API_URL}/v1/health" \
  "healthy\|ok\|200"

check "Gateway Health" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_GATEWAY_URL}/health" \
  "healthy\|ok\|200"

check "Auth (Keycloak) Health" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_AUTH_URL}/realms/stoa/.well-known/openid-configuration" \
  "issuer"

check "MCP Discovery" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_GATEWAY_URL}/mcp/capabilities" \
  "capabilities\|tools\|version"

check "Console UI" \
  "curl -sf --max-time ${TIMEOUT} -o /dev/null -w '%{http_code}' ${STOA_CONSOLE_URL}" \
  "200"

check "Portal" \
  "curl -sf --max-time ${TIMEOUT} -o /dev/null -w '%{http_code}' ${STOA_PORTAL_URL}" \
  "200"

# --- Kubernetes Checks ---
if [[ "$SKIP_K8S" != "true" ]]; then
  echo ""
  echo "Kubernetes Checks"
  echo "-----------------"

  check "Pods Running" \
    "kubectl get pods -n ${NAMESPACE} --no-headers 2>&1 | grep -cv Running || echo 0" \
    "^0$"

  check "No CrashLoopBackOff" \
    "kubectl get pods -n ${NAMESPACE} --no-headers 2>&1 | grep -c CrashLoopBackOff || echo 0" \
    "^0$"

  check "No Recent Restarts (>3)" \
    "kubectl get pods -n ${NAMESPACE} -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount}{\"\\n\"}{end}' 2>&1 | awk '\$2 > 3 {count++} END {print count+0}'" \
    "^0$"

  # ArgoCD check (optional — only if argocd namespace exists)
  if kubectl get namespace argocd &>/dev/null; then
    check "ArgoCD Apps Synced" \
      "kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.status.sync.status}{\"\\n\"}{end}' 2>&1 | grep -cv Synced || echo 0" \
      "^0$"
  fi
fi

# --- Summary ---
echo ""
echo "================================================"
echo "  Results: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "================================================"
echo ""

for r in "${RESULTS[@]}"; do
  echo "  $r"
done

echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "VERIFICATION FAILED — ${FAIL} check(s) need attention."
  echo "See upgrade guide: docs/releases/_template/upgrade-guide.md"
  exit 1
else
  echo "ALL CHECKS PASSED — upgrade verified successfully."
  exit 0
fi
