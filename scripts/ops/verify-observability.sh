#!/usr/bin/env bash
# verify-observability.sh — CAB-2009 Acceptance Criteria verification
#
# Usage: ./scripts/ops/verify-observability.sh [--kubeconfig PATH]
#
# Verifies all 12 ACs for the observability stack deployment.
# Returns exit 0 only if ALL checks pass.
#
# Prerequisites: kubectl, curl, jq, base64

set -euo pipefail

KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config-stoa-ovh}"
PASS=0
FAIL=0
SKIP=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

while [[ $# -gt 0 ]]; do
  case $1 in
    --kubeconfig) KUBECONFIG_PATH="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--kubeconfig PATH]"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

export KUBECONFIG="$KUBECONFIG_PATH"

check_pass() { PASS=$((PASS + 1)); echo -e "${GREEN}PASS${NC} $1: $2"; }
check_fail() { FAIL=$((FAIL + 1)); echo -e "${RED}FAIL${NC} $1: $2 — $3"; }
check_skip() { SKIP=$((SKIP + 1)); echo -e "${YELLOW}SKIP${NC} $1: $2 — $3"; }

# Port-forward helper: starts port-forward, returns PID
# Usage: pf_start <namespace> <svc> <local_port> <remote_port>
PF_PIDS=()
pf_start() {
  kubectl port-forward -n "$1" "svc/$2" "$3:$4" &>/dev/null &
  PF_PIDS+=($!)
  sleep 2
}

# Cleanup all port-forwards on exit
cleanup() {
  for pid in "${PF_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

# Get OpenSearch admin password
get_os_pass() {
  kubectl get secret opensearch-admin-secret -n opensearch \
    -o jsonpath='{.data.password}' 2>/dev/null | base64 -d
}

# OpenSearch curl helper (with auth + TLS skip)
os_curl() {
  local os_pass
  os_pass=$(get_os_pass)
  curl -sk -u "admin:${os_pass}" "$@" 2>/dev/null
}

# ── Connectivity check ──
if ! kubectl cluster-info &>/dev/null; then
  echo -e "${RED}ERROR${NC}: Cannot reach cluster with KUBECONFIG=$KUBECONFIG_PATH"
  exit 2
fi

echo "=== CAB-2009 Observability Stack Verification ==="
echo "Cluster: $(kubectl config current-context)"
echo "Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# ── AC1: Tempo pods Running ──
echo "--- Phase 1: Tempo ---"
TEMPO_PHASE=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=tempo \
  -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
TEMPO_READY=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=tempo \
  -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")

if [[ "$TEMPO_PHASE" == "Running" && "$TEMPO_READY" == "True" ]]; then
  check_pass "AC1" "Tempo pods Running + Ready in monitoring namespace"
elif [[ -z "$TEMPO_PHASE" ]]; then
  check_fail "AC1" "Tempo pods Running" "No Tempo pods found"
else
  check_fail "AC1" "Tempo pods Running" "Phase=$TEMPO_PHASE Ready=$TEMPO_READY"
fi

# ── AC2: Tempo OTLP gRPC port ──
TEMPO_SVC=$(kubectl get svc -n monitoring -l app.kubernetes.io/name=tempo \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
OTLP_PORT=$(kubectl get svc -n monitoring "$TEMPO_SVC" \
  -o jsonpath='{.spec.ports[?(@.port==4317)].port}' 2>/dev/null || echo "")

if [[ "$OTLP_PORT" == "4317" ]]; then
  check_pass "AC2" "Tempo OTLP gRPC port 4317 on svc/$TEMPO_SVC"
elif [[ -z "$TEMPO_SVC" ]]; then
  check_fail "AC2" "Tempo OTLP endpoint" "No Tempo service found"
else
  check_fail "AC2" "Tempo OTLP endpoint" "Port 4317 not found on svc/$TEMPO_SVC"
fi

echo ""
echo "--- Phase 2: OpenSearch ---"

# ── AC3: OpenSearch cluster health ──
OS_SVC="opensearch-cluster-master"
pf_start opensearch "$OS_SVC" 19200 9200

HEALTH=$(os_curl "https://localhost:19200/_cluster/health" | jq -r '.status' 2>/dev/null || echo "")

if [[ "$HEALTH" == "green" || "$HEALTH" == "yellow" ]]; then
  NODE_COUNT=$(os_curl "https://localhost:19200/_cluster/health" | jq -r '.number_of_nodes' 2>/dev/null || echo "?")
  check_pass "AC3" "OpenSearch cluster health=$HEALTH (${NODE_COUNT} nodes)"
elif [[ -n "$HEALTH" ]]; then
  check_fail "AC3" "OpenSearch cluster health" "Status: $HEALTH"
else
  check_fail "AC3" "OpenSearch cluster health" "Could not query health API (auth or connectivity issue)"
fi

# ─��� AC4: Security init completed ──
# .opendistro_security blocks _count API, check via _cat/indices
SEC_EXISTS=$(os_curl "https://localhost:19200/_cat/indices/.opendistro_security?h=docs.count" 2>/dev/null | tr -d '[:space:]')
INIT_POD=$(kubectl get pods -n opensearch --field-selector=status.phase=Succeeded \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -n "$SEC_EXISTS" && "$SEC_EXISTS" -gt 0 ]] 2>/dev/null; then
  check_pass "AC4" "Security init completed (.opendistro_security has $SEC_EXISTS docs)"
elif [[ -n "$INIT_POD" ]]; then
  check_pass "AC4" "Security init completed (pod $INIT_POD succeeded)"
else
  check_fail "AC4" "Security init" "No .opendistro_security docs and no successful init pod"
fi

# ── AC5: Index templates ──
TEMPLATES=$(os_curl "https://localhost:19200/_index_template" | jq -r '.index_templates[].name' 2>/dev/null || echo "")
LEGACY_TEMPLATES=$(os_curl "https://localhost:19200/_template" | jq -r 'keys[]' 2>/dev/null || echo "")
ALL_TEMPLATES=$(echo -e "${TEMPLATES}\n${LEGACY_TEMPLATES}" | sort -u)

EXPECTED=("stoa-logs" "gateway-logs" "audit")
MISSING=()
for tmpl in "${EXPECTED[@]}"; do
  if ! echo "$ALL_TEMPLATES" | grep -q "$tmpl"; then
    MISSING+=("$tmpl")
  fi
done

if [[ ${#MISSING[@]} -eq 0 ]]; then
  check_pass "AC5" "Index templates exist: ${EXPECTED[*]}"
elif [[ -z "$ALL_TEMPLATES" ]]; then
  check_fail "AC5" "Index templates" "Could not query templates"
else
  FOUND=$(echo "$ALL_TEMPLATES" | grep -E "stoa-logs|gateway-logs|audit" | tr '\n' ', ')
  check_fail "AC5" "Index templates" "Missing: ${MISSING[*]}. Found: ${FOUND:-none}"
fi

# ── AC6: OIDC configuration ──
OIDC_COUNT=$(kubectl get configmap -n opensearch -o yaml 2>/dev/null | grep -c "openid" 2>/dev/null || echo "0")
OIDC_COUNT=$(echo "$OIDC_COUNT" | tr -d '[:space:]')

if [[ "$OIDC_COUNT" -gt 0 ]]; then
  check_pass "AC6" "OpenSearch OIDC configuration present ($OIDC_COUNT references)"
else
  check_fail "AC6" "OpenSearch OIDC" "No OIDC configuration found in configmaps"
fi

echo ""
echo "--- Phase 3: Data Prepper ---"

# ── AC7: Data Prepper pods ──
DP_PHASE=$(kubectl get pods -n opensearch -l app.kubernetes.io/name=data-prepper \
  -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
if [[ -z "$DP_PHASE" ]]; then
  DP_PHASE=$(kubectl get pods -n opensearch -l app=data-prepper \
    -o jsonpath='{.items[0].status.phase}' 2>/dev/null || echo "")
fi

if [[ "$DP_PHASE" == "Running" ]]; then
  check_pass "AC7" "Data Prepper pods Running in opensearch namespace"
elif [[ -z "$DP_PHASE" ]]; then
  check_fail "AC7" "Data Prepper pods" "No Data Prepper pods found in opensearch namespace"
else
  check_fail "AC7" "Data Prepper pods" "Phase=$DP_PHASE"
fi

# ── AC8: Data Prepper health ──
DP_SVC=$(kubectl get svc -n opensearch -l app.kubernetes.io/name=data-prepper \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [[ -z "$DP_SVC" ]]; then
  DP_SVC=$(kubectl get svc -n opensearch -l app=data-prepper \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

if [[ -n "$DP_SVC" ]]; then
  pf_start opensearch "$DP_SVC" 21890 21890
  DP_HEALTH=$(curl -s http://localhost:21890 2>/dev/null || echo "")
  if [[ -n "$DP_HEALTH" ]]; then
    check_pass "AC8" "Data Prepper health endpoint responds on :21890"
  else
    check_fail "AC8" "Data Prepper health" "Health check on :21890 returned empty"
  fi
else
  check_fail "AC8" "Data Prepper health" "No Data Prepper service found"
fi

echo ""
echo "--- Phase 4: End-to-End ---"

# ── AC9: E2E trace flow ──
# Data Prepper creates otel-v1-apm-span-* indices (default trace analytics template)
TRACE_COUNT=$(os_curl "https://localhost:19200/otel-v1-apm-span*/_count" | jq -r '.count' 2>/dev/null || echo "")

if [[ -z "$TRACE_COUNT" || "$TRACE_COUNT" == "null" ]]; then
  check_fail "AC9" "E2E trace flow" "No trace index found (otel-v1-apm-span*)"
elif [[ "$TRACE_COUNT" -gt 0 ]] 2>/dev/null; then
  check_pass "AC9" "E2E trace flow ($TRACE_COUNT spans in otel-v1-apm-span)"
else
  check_fail "AC9" "E2E trace flow" "Trace index exists but has 0 documents"
fi

# ─��� AC10: ArgoCD Applications ──
AC10_PASS=true
AC10_DETAILS=""
for entry in "stoa-tempo:tempo" "stoa-opensearch:opensearch" "stoa-data-prepper:data-prepper"; do
  app_prefixed="${entry%%:*}"
  app_short="${entry##*:}"
  SYNC=$(kubectl get application "$app_prefixed" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || \
         kubectl get application "$app_short" -n argocd -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "NOT_FOUND")
  HEALTH_STATUS=$(kubectl get application "$app_prefixed" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || \
           kubectl get application "$app_short" -n argocd -o jsonpath='{.status.health.status}' 2>/dev/null || echo "NOT_FOUND")
  if [[ "$SYNC" == "Synced" && "$HEALTH_STATUS" == "Healthy" ]]; then
    AC10_DETAILS="$AC10_DETAILS $app_short=OK"
  else
    AC10_PASS=false
    AC10_DETAILS="$AC10_DETAILS $app_short=$SYNC/$HEALTH_STATUS"
  fi
done

if $AC10_PASS; then
  check_pass "AC10" "All ArgoCD apps Synced+Healthy:$AC10_DETAILS"
else
  check_fail "AC10" "ArgoCD Applications" "Status:$AC10_DETAILS"
fi

# ── AC11: Resources managed by ArgoCD ──
UNMANAGED_OS=$(kubectl get all -n opensearch -o json 2>/dev/null | \
  jq '[.items[] | select(.metadata.labels["argocd.argoproj.io/instance"] == null)] | length' 2>/dev/null || echo "-1")
UNMANAGED_MON=$(kubectl get pods -n opensearch -l app.kubernetes.io/name=data-prepper -o json 2>/dev/null | \
  jq '[.items[] | select(.metadata.labels["argocd.argoproj.io/instance"] == null)] | length' 2>/dev/null || echo "0")

if [[ "$UNMANAGED_OS" == "0" ]]; then
  check_pass "AC11" "All opensearch resources managed by ArgoCD"
elif [[ "$UNMANAGED_OS" == "-1" ]]; then
  check_skip "AC11" "ArgoCD management" "Could not query opensearch namespace"
else
  check_fail "AC11" "ArgoCD management" "$UNMANAGED_OS unmanaged resources in opensearch namespace"
fi

# ── AC12: ISM policies ──
ISM_POLICIES=$(os_curl "https://localhost:19200/_plugins/_ism/policies" | \
  jq -r '.policies[].policy.policy_id' 2>/dev/null || echo "")

if [[ -n "$ISM_POLICIES" ]]; then
  POLICY_COUNT=$(echo "$ISM_POLICIES" | wc -l | tr -d ' ')
  check_pass "AC12" "ISM policies active ($POLICY_COUNT: $(echo "$ISM_POLICIES" | tr '\n' ', '))"
else
  check_fail "AC12" "ISM policies" "No ISM policies found"
fi

# ── Summary ──
echo ""
echo "=== Summary ==="
TOTAL=$((PASS + FAIL + SKIP))
echo -e "Total: $TOTAL | ${GREEN}Pass: $PASS${NC} | ${RED}Fail: $FAIL${NC} | ${YELLOW}Skip: $SKIP${NC}"
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo -e "${RED}VERIFICATION FAILED${NC} — $FAIL acceptance criteria not met"
  exit 1
elif [[ $SKIP -gt 0 ]]; then
  echo -e "${YELLOW}VERIFICATION INCOMPLETE${NC} — $SKIP criteria skipped"
  exit 1
else
  echo -e "${GREEN}ALL ACCEPTANCE CRITERIA PASSED${NC}"
  exit 0
fi
