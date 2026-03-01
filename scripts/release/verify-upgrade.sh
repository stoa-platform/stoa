#!/usr/bin/env bash
# verify-upgrade.sh — Post-upgrade verification for STOA Platform
# Runs all component health checks and reports pass/fail.
# Exit 0 = all checks pass, Exit 1 = at least one check failed.
#
# Usage:
#   ./scripts/release/verify-upgrade.sh                              # Use env vars
#   ./scripts/release/verify-upgrade.sh --base-domain gostoa.dev     # Override domain
#   ./scripts/release/verify-upgrade.sh --namespace stoa-system       # Override namespace
#   ./scripts/release/verify-upgrade.sh --skip-k8s                    # Skip kubectl checks
#   ./scripts/release/verify-upgrade.sh --expected-version v2.1.0     # Check image versions
#   ./scripts/release/verify-upgrade.sh --component api               # Test single component
#   ./scripts/release/verify-upgrade.sh --json                        # Machine-readable output

set -euo pipefail

# --- Configuration ---
BASE_DOMAIN="${BASE_DOMAIN:-gostoa.dev}"
NAMESPACE="${NAMESPACE:-stoa-system}"
SKIP_K8S="${SKIP_K8S:-false}"
EXPECTED_VERSION=""
COMPONENT_FILTER=""
JSON_OUTPUT=false
TIMEOUT=10

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --base-domain) BASE_DOMAIN="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --skip-k8s) SKIP_K8S=true; shift ;;
    --expected-version) EXPECTED_VERSION="$2"; shift 2 ;;
    --component) COMPONENT_FILTER="$2"; shift 2 ;;
    --json) JSON_OUTPUT=true; shift ;;
    --help)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --base-domain DOMAIN     Base domain (default: gostoa.dev)"
      echo "  --namespace NS           K8s namespace (default: stoa-system)"
      echo "  --skip-k8s               Skip kubectl checks"
      echo "  --expected-version VER   Check deployed image versions match VER"
      echo "  --component NAME         Test single component (api|gateway|auth|console|portal|mcp)"
      echo "  --json                   Machine-readable JSON output"
      echo "  --help                   Show this help"
      exit 0
      ;;
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
SKIP=0
TOTAL=0
RESULTS=()
JSON_RESULTS=()
START_TIME=$(date +%s)

# --- Helpers ---
check() {
  local component="$1"
  local name="$2"
  local cmd="$3"
  local expected="$4"

  # Apply component filter
  if [[ -n "$COMPONENT_FILTER" ]] && [[ "$component" != "$COMPONENT_FILTER" ]]; then
    SKIP=$((SKIP + 1))
    return
  fi

  TOTAL=$((TOTAL + 1))

  local output
  local status=0
  local start
  start=$(date +%s%N 2>/dev/null || date +%s)
  output=$(eval "$cmd" 2>&1) || status=$?
  local end
  end=$(date +%s%N 2>/dev/null || date +%s)
  local duration_ms=$(( (end - start) / 1000000 ))

  if [[ $status -eq 0 ]] && echo "$output" | grep -qE "$expected"; then
    PASS=$((PASS + 1))
    RESULTS+=("PASS  [$component] $name (${duration_ms}ms)")
    JSON_RESULTS+=("{\"component\":\"$component\",\"check\":\"$name\",\"status\":\"pass\",\"duration_ms\":$duration_ms}")
    if [[ "$JSON_OUTPUT" != "true" ]]; then
      printf "  \033[32mPASS\033[0m  [%-8s] %s (%dms)\n" "$component" "$name" "$duration_ms"
    fi
  else
    FAIL=$((FAIL + 1))
    local snippet="${output:0:120}"
    snippet="${snippet//$'\n'/ }"
    RESULTS+=("FAIL  [$component] $name — got: $snippet")
    JSON_RESULTS+=("{\"component\":\"$component\",\"check\":\"$name\",\"status\":\"fail\",\"duration_ms\":$duration_ms,\"output\":\"$snippet\"}")
    if [[ "$JSON_OUTPUT" != "true" ]]; then
      printf "  \033[31mFAIL\033[0m  [%-8s] %s\n" "$component" "$name"
      printf "        %s\n" "${output:0:200}"
    fi
  fi
}

# --- Banner ---
if [[ "$JSON_OUTPUT" != "true" ]]; then
  echo ""
  echo "================================================"
  echo "  STOA Platform — Post-Upgrade Verification"
  echo "================================================"
  echo "  Domain:    ${BASE_DOMAIN}"
  echo "  Namespace: ${NAMESPACE}"
  echo "  Skip K8s:  ${SKIP_K8S}"
  if [[ -n "$EXPECTED_VERSION" ]]; then
    echo "  Expected:  ${EXPECTED_VERSION}"
  fi
  if [[ -n "$COMPONENT_FILTER" ]]; then
    echo "  Component: ${COMPONENT_FILTER}"
  fi
  echo "  Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "================================================"
  echo ""
fi

# --- Section: Core Health ---
if [[ "$JSON_OUTPUT" != "true" ]]; then
  echo "Core Health"
  echo "-----------"
fi

check "api" "API Health" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_API_URL}/v1/health" \
  "healthy\|ok\|200"

check "gateway" "Gateway Health" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_GATEWAY_URL}/health" \
  "healthy\|ok\|200"

check "auth" "Keycloak OIDC Discovery" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_AUTH_URL}/realms/stoa/.well-known/openid-configuration" \
  "issuer"

check "console" "Console UI" \
  "curl -sf --max-time ${TIMEOUT} -o /dev/null -w '%{http_code}' ${STOA_CONSOLE_URL}" \
  "200"

check "portal" "Portal" \
  "curl -sf --max-time ${TIMEOUT} -o /dev/null -w '%{http_code}' ${STOA_PORTAL_URL}" \
  "200"

# --- Section: MCP Protocol ---
if [[ "$JSON_OUTPUT" != "true" ]]; then
  echo ""
  echo "MCP Protocol"
  echo "------------"
fi

check "mcp" "MCP Discovery" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_GATEWAY_URL}/mcp/capabilities" \
  "capabilities\|tools\|version"

check "mcp" "MCP Tools List" \
  "curl -sf --max-time ${TIMEOUT} -X POST ${STOA_GATEWAY_URL}/mcp/tools/list -H 'Content-Type: application/json' -d '{}'" \
  "tools"

check "mcp" "OAuth Protected Resource" \
  "curl -sf --max-time ${TIMEOUT} ${STOA_GATEWAY_URL}/.well-known/oauth-protected-resource" \
  "authorization_servers\|resource"

# --- Section: Kubernetes ---
if [[ "$SKIP_K8S" != "true" ]]; then
  if [[ "$JSON_OUTPUT" != "true" ]]; then
    echo ""
    echo "Kubernetes"
    echo "----------"
  fi

  check "k8s" "Pods Running" \
    "kubectl get pods -n ${NAMESPACE} --no-headers 2>&1 | grep -cv Running || echo 0" \
    "^0$"

  check "k8s" "No CrashLoopBackOff" \
    "kubectl get pods -n ${NAMESPACE} --no-headers 2>&1 | grep -c CrashLoopBackOff || echo 0" \
    "^0$"

  check "k8s" "No Excessive Restarts (>3)" \
    "kubectl get pods -n ${NAMESPACE} -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount}{\"\\n\"}{end}' 2>&1 | awk '\$2 > 3 {count++} END {print count+0}'" \
    "^0$"

  # ArgoCD check (optional)
  if kubectl get namespace argocd &>/dev/null; then
    check "k8s" "ArgoCD Apps Synced" \
      "kubectl get applications -n argocd -o jsonpath='{range .items[*]}{.status.sync.status}{\"\\n\"}{end}' 2>&1 | grep -cv Synced || echo 0" \
      "^0$"
  fi

  # --- Section: Version Confirmation ---
  if [[ -n "$EXPECTED_VERSION" ]]; then
    if [[ "$JSON_OUTPUT" != "true" ]]; then
      echo ""
      echo "Version Confirmation"
      echo "--------------------"
    fi

    check "api" "API Image Version" \
      "kubectl get deploy/control-plane-api -n ${NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>&1" \
      "${EXPECTED_VERSION}"

    check "gateway" "Gateway Image Version" \
      "kubectl get deploy/stoa-gateway -n ${NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>&1" \
      "${EXPECTED_VERSION}"

    check "console" "Console Image Version" \
      "kubectl get deploy/control-plane-ui -n ${NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>&1" \
      "${EXPECTED_VERSION}"

    check "portal" "Portal Image Version" \
      "kubectl get deploy/stoa-portal -n ${NAMESPACE} -o jsonpath='{.spec.template.spec.containers[0].image}' 2>&1" \
      "${EXPECTED_VERSION}"
  fi

  # --- Section: Error Rate ---
  if [[ "$JSON_OUTPUT" != "true" ]]; then
    echo ""
    echo "Error Rate (last 5 min)"
    echo "-----------------------"
  fi

  check "api" "API Error Rate" \
    "kubectl logs -n ${NAMESPACE} deploy/control-plane-api --since=5m 2>&1 | grep -c ERROR || echo 0" \
    "^[0-4]$"

  check "gateway" "Gateway Error Rate" \
    "kubectl logs -n ${NAMESPACE} deploy/stoa-gateway --since=5m 2>&1 | grep -c ERROR || echo 0" \
    "^[0-4]$"
fi

# --- Summary ---
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

if [[ "$JSON_OUTPUT" == "true" ]]; then
  # JSON output
  echo "{"
  echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"domain\": \"${BASE_DOMAIN}\","
  echo "  \"namespace\": \"${NAMESPACE}\","
  if [[ -n "$EXPECTED_VERSION" ]]; then
    echo "  \"expected_version\": \"${EXPECTED_VERSION}\","
  fi
  echo "  \"duration_seconds\": ${DURATION},"
  echo "  \"summary\": {\"total\": ${TOTAL}, \"pass\": ${PASS}, \"fail\": ${FAIL}, \"skip\": ${SKIP}},"
  echo "  \"verdict\": \"$([ $FAIL -eq 0 ] && echo 'PASS' || echo 'FAIL')\","
  echo "  \"checks\": ["
  local first=true
  for jr in "${JSON_RESULTS[@]}"; do
    if [[ "$first" == "true" ]]; then
      echo "    $jr"
      first=false
    else
      echo "    ,$jr"
    fi
  done
  echo "  ]"
  echo "}"
else
  echo ""
  echo "================================================"
  printf "  Results: %d/%d passed, %d failed" "$PASS" "$TOTAL" "$FAIL"
  if [[ $SKIP -gt 0 ]]; then
    printf ", %d skipped" "$SKIP"
  fi
  echo ""
  echo "  Duration: ${DURATION}s"
  echo "================================================"
  echo ""

  for r in "${RESULTS[@]}"; do
    echo "  $r"
  done

  echo ""

  if [[ $FAIL -gt 0 ]]; then
    echo "VERIFICATION FAILED — ${FAIL} check(s) need attention."
    echo ""
    echo "Troubleshooting:"
    echo "  - Check pod logs:    kubectl logs -n ${NAMESPACE} deploy/<component> --tail=50"
    echo "  - Check pod events:  kubectl describe pod -n ${NAMESPACE} -l app=<component>"
    echo "  - Check ArgoCD:      kubectl get applications -n argocd"
    echo "  - Rollback:          helm rollback stoa-platform -n ${NAMESPACE}"
    echo ""
    echo "See upgrade guide: docs/releases/_template/upgrade-guide.md"
    exit 1
  else
    echo "ALL CHECKS PASSED — upgrade verified successfully."
    exit 0
  fi
fi
