#!/usr/bin/env bash
# =============================================================================
# STOA Platform — Cross-Environment Drift Detection
# =============================================================================
# Compares staging vs production environments for image tags, replica counts,
# pod health, endpoint availability, and TLS certificate expiry.
#
# Usage:
#   ./scripts/ops/env-drift-check.sh              # Colored CLI table (default)
#   ./scripts/ops/env-drift-check.sh --json        # Machine-readable JSON
#   ./scripts/ops/env-drift-check.sh --push-metrics # Push results to Pushgateway
#
# Prerequisites:
#   - KUBECONFIG_STAGING: path to staging kubeconfig (or inline base64 via CI)
#   - KUBECONFIG_PROD: path to prod kubeconfig (or inline base64 via CI)
#   - curl, jq, kubectl, openssl installed
#
# Notifications (optional):
#   Source ai-factory-notify.sh and call notify_scheduled with results.
# =============================================================================
set -euo pipefail

# --- Configuration ---
COMPONENTS=(control-plane-api stoa-gateway control-plane-ui stoa-portal)
NAMESPACE="${NAMESPACE:-stoa-system}"
OUTPUT_MODE="table"
PUSH_METRICS=false

# Staging/prod endpoint prefixes
STAGING_ENDPOINTS=(
  "staging-api.gostoa.dev"
  "staging-mcp.gostoa.dev"
  "staging-console.gostoa.dev"
  "staging-portal.gostoa.dev"
  "staging-auth.gostoa.dev"
)
PROD_ENDPOINTS=(
  "api.gostoa.dev"
  "mcp.gostoa.dev"
  "console.gostoa.dev"
  "portal.gostoa.dev"
  "auth.gostoa.dev"
)

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Parse arguments ---
for arg in "$@"; do
  case "$arg" in
    --json) OUTPUT_MODE="json" ;;
    --push-metrics) PUSH_METRICS=true ;;
    --help|-h)
      echo "Usage: $0 [--json] [--push-metrics]"
      echo "  --json          Output machine-readable JSON"
      echo "  --push-metrics  Push results to Prometheus Pushgateway"
      exit 0
      ;;
  esac
done

# --- Helpers ---
kube_staging() {
  kubectl --kubeconfig "${KUBECONFIG_STAGING}" "$@" 2>/dev/null
}

kube_prod() {
  kubectl --kubeconfig "${KUBECONFIG_PROD}" "$@" 2>/dev/null
}

check_prerequisites() {
  local missing=()
  for cmd in kubectl curl jq openssl; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
  done
  if [ -z "${KUBECONFIG_STAGING:-}" ]; then missing+=("KUBECONFIG_STAGING env var"); fi
  if [ -z "${KUBECONFIG_PROD:-}" ]; then missing+=("KUBECONFIG_PROD env var"); fi

  if [ ${#missing[@]} -gt 0 ]; then
    echo -e "${RED}Missing prerequisites: ${missing[*]}${NC}" >&2
    exit 1
  fi
}

# --- Check 1: Image Tag Drift ---
declare -A IMAGE_DRIFT
check_image_drift() {
  local drifts=0
  for comp in "${COMPONENTS[@]}"; do
    local stag_img prod_img
    stag_img=$(kube_staging get deployment/"$comp" -n "$NAMESPACE" \
      -o jsonpath='{.spec.template.spec.containers[0].image}' || echo "N/A")
    prod_img=$(kube_prod get deployment/"$comp" -n "$NAMESPACE" \
      -o jsonpath='{.spec.template.spec.containers[0].image}' || echo "N/A")

    # Extract tag portion after the last colon
    local stag_tag="${stag_img##*:}"
    local prod_tag="${prod_img##*:}"

    if [ "$stag_tag" != "$prod_tag" ]; then
      IMAGE_DRIFT[$comp]="DRIFT: staging=$stag_tag prod=$prod_tag"
      drifts=$((drifts + 1))
    else
      IMAGE_DRIFT[$comp]="OK: $stag_tag"
    fi
  done
  echo "$drifts"
}

# --- Check 2: Replica Count ---
declare -A REPLICA_DRIFT
check_replica_count() {
  local drifts=0
  for comp in "${COMPONENTS[@]}"; do
    local stag_rep prod_rep
    stag_rep=$(kube_staging get deployment/"$comp" -n "$NAMESPACE" \
      -o jsonpath='{.status.readyReplicas}' || echo "0")
    prod_rep=$(kube_prod get deployment/"$comp" -n "$NAMESPACE" \
      -o jsonpath='{.status.readyReplicas}' || echo "0")
    stag_rep="${stag_rep:-0}"
    prod_rep="${prod_rep:-0}"

    if [ "$stag_rep" != "$prod_rep" ]; then
      REPLICA_DRIFT[$comp]="DIFF: staging=$stag_rep prod=$prod_rep"
      drifts=$((drifts + 1))
    else
      REPLICA_DRIFT[$comp]="OK: $stag_rep"
    fi
  done
  echo "$drifts"
}

# --- Check 3: Pod Health ---
declare -A POD_HEALTH_STAGING POD_HEALTH_PROD
check_pod_health() {
  local issues=0
  for comp in "${COMPONENTS[@]}"; do
    local stag_status prod_status
    stag_status=$(kube_staging get pods -n "$NAMESPACE" -l "app=$comp" \
      -o jsonpath='{.items[0].status.phase}' || echo "Unknown")
    prod_status=$(kube_prod get pods -n "$NAMESPACE" -l "app=$comp" \
      -o jsonpath='{.items[0].status.phase}' || echo "Unknown")

    POD_HEALTH_STAGING[$comp]="$stag_status"
    POD_HEALTH_PROD[$comp]="$prod_status"

    if [ "$stag_status" != "Running" ] || [ "$prod_status" != "Running" ]; then
      issues=$((issues + 1))
    fi
  done
  echo "$issues"
}

# --- Check 4: Endpoint Health ---
declare -A ENDPOINT_STAGING ENDPOINT_PROD
check_endpoints() {
  local failures=0
  for i in "${!STAGING_ENDPOINTS[@]}"; do
    local stag_ep="${STAGING_ENDPOINTS[$i]}"
    local prod_ep="${PROD_ENDPOINTS[$i]}"

    local stag_code prod_code
    stag_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$stag_ep" || echo "000")
    prod_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$prod_ep" || echo "000")

    ENDPOINT_STAGING[$stag_ep]="$stag_code"
    ENDPOINT_PROD[$prod_ep]="$prod_code"

    if [ "$stag_code" = "000" ] || [ "$prod_code" = "000" ]; then
      failures=$((failures + 1))
    fi
  done
  echo "$failures"
}

# --- Check 5: TLS Certificate Expiry ---
declare -A TLS_STAGING TLS_PROD
check_tls_expiry() {
  local warnings=0
  local warning_days=14

  for i in "${!STAGING_ENDPOINTS[@]}"; do
    local stag_ep="${STAGING_ENDPOINTS[$i]}"
    local prod_ep="${PROD_ENDPOINTS[$i]}"

    for ep_var in stag_ep prod_ep; do
      local ep="${!ep_var}"
      local expiry days_left
      expiry=$(echo | openssl s_client -servername "$ep" -connect "$ep:443" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")

      if [ -n "$expiry" ]; then
        local expiry_epoch now_epoch
        expiry_epoch=$(date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null || \
                       date -d "$expiry" +%s 2>/dev/null || echo "0")
        now_epoch=$(date +%s)
        days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

        if [ "$ep_var" = "stag_ep" ]; then
          TLS_STAGING[$ep]="${days_left}d"
        else
          TLS_PROD[$ep]="${days_left}d"
        fi

        if [ "$days_left" -lt "$warning_days" ]; then
          warnings=$((warnings + 1))
        fi
      else
        if [ "$ep_var" = "stag_ep" ]; then
          TLS_STAGING[$ep]="ERR"
        else
          TLS_PROD[$ep]="ERR"
        fi
        warnings=$((warnings + 1))
      fi
    done
  done
  echo "$warnings"
}

# --- Output: Table ---
print_table() {
  local img_drifts="$1" rep_drifts="$2" pod_issues="$3" ep_fails="$4" tls_warns="$5"
  local total=$((img_drifts + rep_drifts + pod_issues + ep_fails + tls_warns))

  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║        STOA Cross-Environment Drift Report                  ║${NC}"
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
  echo ""

  # Image tags
  echo -e "${CYAN}── Image Tags ──────────────────────────────────────────────${NC}"
  printf "  %-25s %s\n" "Component" "Status"
  printf "  %-25s %s\n" "─────────" "──────"
  for comp in "${COMPONENTS[@]}"; do
    local status="${IMAGE_DRIFT[$comp]}"
    if [[ "$status" == OK* ]]; then
      printf "  %-25s ${GREEN}%s${NC}\n" "$comp" "$status"
    else
      printf "  %-25s ${RED}%s${NC}\n" "$comp" "$status"
    fi
  done
  echo ""

  # Replicas
  echo -e "${CYAN}── Replica Counts ──────────────────────────────────────────${NC}"
  printf "  %-25s %s\n" "Component" "Status"
  printf "  %-25s %s\n" "─────────" "──────"
  for comp in "${COMPONENTS[@]}"; do
    local status="${REPLICA_DRIFT[$comp]}"
    if [[ "$status" == OK* ]]; then
      printf "  %-25s ${GREEN}%s${NC}\n" "$comp" "$status"
    else
      printf "  %-25s ${YELLOW}%s${NC}\n" "$comp" "$status"
    fi
  done
  echo ""

  # Pod health
  echo -e "${CYAN}── Pod Health ──────────────────────────────────────────────${NC}"
  printf "  %-25s %-12s %s\n" "Component" "Staging" "Prod"
  printf "  %-25s %-12s %s\n" "─────────" "───────" "────"
  for comp in "${COMPONENTS[@]}"; do
    local s="${POD_HEALTH_STAGING[$comp]}" p="${POD_HEALTH_PROD[$comp]}"
    local sc="${GREEN}" pc="${GREEN}"
    [ "$s" != "Running" ] && sc="${RED}"
    [ "$p" != "Running" ] && pc="${RED}"
    printf "  %-25s ${sc}%-12s${NC} ${pc}%s${NC}\n" "$comp" "$s" "$p"
  done
  echo ""

  # Endpoints
  echo -e "${CYAN}── Endpoint Health ─────────────────────────────────────────${NC}"
  printf "  %-35s %-8s %s\n" "Endpoint" "Staging" "Prod"
  printf "  %-35s %-8s %s\n" "────────" "───────" "────"
  for i in "${!STAGING_ENDPOINTS[@]}"; do
    local se="${STAGING_ENDPOINTS[$i]}" pe="${PROD_ENDPOINTS[$i]}"
    local sc="${ENDPOINT_STAGING[$se]}" pc="${ENDPOINT_PROD[$pe]}"
    local scolor="${GREEN}" pcolor="${GREEN}"
    [ "$sc" = "000" ] && scolor="${RED}"
    [ "$pc" = "000" ] && pcolor="${RED}"
    printf "  %-35s ${scolor}%-8s${NC} ${pcolor}%s${NC}\n" "$pe" "$sc" "$pc"
  done
  echo ""

  # TLS
  echo -e "${CYAN}── TLS Certificate Expiry ──────────────────────────────────${NC}"
  printf "  %-35s %-12s %s\n" "Endpoint" "Staging" "Prod"
  printf "  %-35s %-12s %s\n" "────────" "───────" "────"
  for i in "${!STAGING_ENDPOINTS[@]}"; do
    local se="${STAGING_ENDPOINTS[$i]}" pe="${PROD_ENDPOINTS[$i]}"
    local sd="${TLS_STAGING[$se]:-N/A}" pd="${TLS_PROD[$pe]:-N/A}"
    local scolor="${GREEN}" pcolor="${GREEN}"
    [[ "$sd" == "ERR" || "${sd%d}" -lt 14 ]] 2>/dev/null && scolor="${RED}"
    [[ "$pd" == "ERR" || "${pd%d}" -lt 14 ]] 2>/dev/null && pcolor="${RED}"
    printf "  %-35s ${scolor}%-12s${NC} ${pcolor}%s${NC}\n" "$pe" "$sd" "$pd"
  done
  echo ""

  # Summary
  if [ "$total" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}Result: ALL CLEAR — no drift detected${NC}"
  else
    echo -e "${RED}${BOLD}Result: $total issue(s) found${NC}"
    [ "$img_drifts" -gt 0 ] && echo -e "  ${RED}Image drift: $img_drifts component(s)${NC}"
    [ "$rep_drifts" -gt 0 ] && echo -e "  ${YELLOW}Replica diff: $rep_drifts component(s)${NC}"
    [ "$pod_issues" -gt 0 ] && echo -e "  ${RED}Pod issues: $pod_issues component(s)${NC}"
    [ "$ep_fails" -gt 0 ] && echo -e "  ${RED}Endpoint failures: $ep_fails${NC}"
    [ "$tls_warns" -gt 0 ] && echo -e "  ${YELLOW}TLS warnings: $tls_warns${NC}"
  fi
  echo ""
}

# --- Output: JSON ---
print_json() {
  local img_drifts="$1" rep_drifts="$2" pod_issues="$3" ep_fails="$4" tls_warns="$5"
  local total=$((img_drifts + rep_drifts + pod_issues + ep_fails + tls_warns))

  local components_json="["
  local first=true
  for comp in "${COMPONENTS[@]}"; do
    $first || components_json+=","
    first=false
    components_json+=$(jq -n \
      --arg name "$comp" \
      --arg image "${IMAGE_DRIFT[$comp]}" \
      --arg replicas "${REPLICA_DRIFT[$comp]}" \
      --arg pod_staging "${POD_HEALTH_STAGING[$comp]}" \
      --arg pod_prod "${POD_HEALTH_PROD[$comp]}" \
      '{name: $name, image: $image, replicas: $replicas, pod_staging: $pod_staging, pod_prod: $pod_prod}')
  done
  components_json+="]"

  local endpoints_json="["
  first=true
  for i in "${!STAGING_ENDPOINTS[@]}"; do
    $first || endpoints_json+=","
    first=false
    local se="${STAGING_ENDPOINTS[$i]}" pe="${PROD_ENDPOINTS[$i]}"
    endpoints_json+=$(jq -n \
      --arg endpoint "$pe" \
      --arg staging_code "${ENDPOINT_STAGING[$se]}" \
      --arg prod_code "${ENDPOINT_PROD[$pe]}" \
      --arg tls_staging "${TLS_STAGING[$se]:-N/A}" \
      --arg tls_prod "${TLS_PROD[$pe]:-N/A}" \
      '{endpoint: $endpoint, staging_code: $staging_code, prod_code: $prod_code, tls_staging: $tls_staging, tls_prod: $tls_prod}')
  done
  endpoints_json+="]"

  jq -n \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson total "$total" \
    --argjson image_drifts "$img_drifts" \
    --argjson replica_drifts "$rep_drifts" \
    --argjson pod_issues "$pod_issues" \
    --argjson endpoint_failures "$ep_fails" \
    --argjson tls_warnings "$tls_warns" \
    --argjson components "$components_json" \
    --argjson endpoints "$endpoints_json" \
    '{
      timestamp: $timestamp,
      status: (if $total == 0 then "ok" else "drift" end),
      total_issues: $total,
      checks: {
        image_drifts: $image_drifts,
        replica_drifts: $replica_drifts,
        pod_issues: $pod_issues,
        endpoint_failures: $endpoint_failures,
        tls_warnings: $tls_warnings
      },
      components: $components,
      endpoints: $endpoints
    }'
}

# --- Push Metrics to Pushgateway ---
push_metrics() {
  local img_drifts="$1" rep_drifts="$2" pod_issues="$3" ep_fails="$4" tls_warns="$5"
  local total=$((img_drifts + rep_drifts + pod_issues + ep_fails + tls_warns))

  local url="${PUSHGATEWAY_URL:-https://pushgateway.gostoa.dev}"
  local auth_flag=()
  if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
    auth_flag=(-u "$PUSHGATEWAY_AUTH")
  fi

  local metrics
  metrics=$(cat <<PROM
# HELP stoa_env_drift_total Total number of drift issues detected
# TYPE stoa_env_drift_total gauge
stoa_env_drift_total $total
# HELP stoa_env_drift_image Image tag drift count
# TYPE stoa_env_drift_image gauge
stoa_env_drift_image $img_drifts
# HELP stoa_env_drift_replicas Replica count drift
# TYPE stoa_env_drift_replicas gauge
stoa_env_drift_replicas $rep_drifts
# HELP stoa_env_drift_pods Pod health issues
# TYPE stoa_env_drift_pods gauge
stoa_env_drift_pods $pod_issues
# HELP stoa_env_drift_endpoints Endpoint failures
# TYPE stoa_env_drift_endpoints gauge
stoa_env_drift_endpoints $ep_fails
# HELP stoa_env_drift_tls TLS certificate warnings
# TYPE stoa_env_drift_tls gauge
stoa_env_drift_tls $tls_warns
PROM
)

  if curl -s "${auth_flag[@]}" --data-binary "$metrics" \
    "${url}/metrics/job/env-drift-check" >/dev/null 2>&1; then
    echo -e "${GREEN}Metrics pushed to Pushgateway${NC}" >&2
  else
    echo -e "${YELLOW}Warning: Failed to push metrics to Pushgateway${NC}" >&2
  fi
}

# --- Slack Notification ---
send_slack_notification() {
  local img_drifts="$1" rep_drifts="$2" pod_issues="$3" ep_fails="$4" tls_warns="$5"
  local total=$((img_drifts + rep_drifts + pod_issues + ep_fails + tls_warns))

  # Source AI Factory notification library if available
  local notify_script
  notify_script="$(dirname "$0")/../ai-ops/ai-factory-notify.sh"
  if [ -f "$notify_script" ]; then
    # shellcheck source=/dev/null
    source "$notify_script"
    local status="ok"
    [ "$total" -gt 0 ] && status="drift ($total issues)"
    local detail="Images: $img_drifts | Replicas: $rep_drifts | Pods: $pod_issues | Endpoints: $ep_fails | TLS: $tls_warns"
    notify_scheduled "env-drift" "$status" "$detail"
  fi
}

# --- Main ---
main() {
  check_prerequisites

  echo -e "${CYAN}Running drift checks...${NC}" >&2

  local img_drifts rep_drifts pod_issues ep_fails tls_warns
  img_drifts=$(check_image_drift)
  rep_drifts=$(check_replica_count)
  pod_issues=$(check_pod_health)
  ep_fails=$(check_endpoints)
  tls_warns=$(check_tls_expiry)

  case "$OUTPUT_MODE" in
    json)  print_json "$img_drifts" "$rep_drifts" "$pod_issues" "$ep_fails" "$tls_warns" ;;
    table) print_table "$img_drifts" "$rep_drifts" "$pod_issues" "$ep_fails" "$tls_warns" ;;
  esac

  if $PUSH_METRICS; then
    push_metrics "$img_drifts" "$rep_drifts" "$pod_issues" "$ep_fails" "$tls_warns"
  fi

  # Send Slack notification (best effort, never fails)
  send_slack_notification "$img_drifts" "$rep_drifts" "$pod_issues" "$ep_fails" "$tls_warns" || true

  # Exit with non-zero if any drift found
  local total=$((img_drifts + rep_drifts + pod_issues + ep_fails + tls_warns))
  if [ "$total" -gt 0 ]; then
    exit 1
  fi
}

main "$@"
