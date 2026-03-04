#!/usr/bin/env bash
# Arena — Multi-Environment Health Verification
#
# Fetches environment list from GET /v1/environments/public (no auth),
# then health-checks each environment's API endpoint.
#
# Results pushed to Pushgateway as Prometheus metrics.
# Pings Healthchecks dead man's switch on completion.
#
# Env vars:
#   PUBLIC_ENVIRONMENTS_URL — URL to GET /v1/environments/public
#   PUSHGATEWAY_URL         — Pushgateway URL (default: http://pushgateway.monitoring.svc:9091)
#   PUSHGATEWAY_AUTH        — Basic auth user:pass (optional)
#   HEALTHCHECKS_URL        — Healthchecks ping URL (optional, dead man's switch)
#   ARENA_INSTANCE          — Instance label (default: "k8s")
#   TIMEOUT                 — Request timeout in seconds (default: 5)
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PUSHGATEWAY_URL="${PUSHGATEWAY_URL:-http://pushgateway.monitoring.svc:9091}"
ARENA_INSTANCE="${ARENA_INSTANCE:-k8s}"
TIMEOUT="${TIMEOUT:-5}"
WORK_DIR="/tmp/env-verify"
METRICS_FILE="$WORK_DIR/metrics.txt"

log_json() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  echo "{\"time\":\"${ts}\",\"level\":\"INFO\",\"msg\":$1}"
}

log_json "\"Multi-environment health verification starting\""

if [ -z "${PUBLIC_ENVIRONMENTS_URL:-}" ]; then
  echo "ERROR: PUBLIC_ENVIRONMENTS_URL env var not set" >&2
  exit 1
fi

rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

# ---------------------------------------------------------------------------
# Step 1: Fetch environment list
# ---------------------------------------------------------------------------
HTTP_CODE=$(curl -s -o "$WORK_DIR/envs.json" -w "%{http_code}" \
  --max-time "$TIMEOUT" "$PUBLIC_ENVIRONMENTS_URL" 2>&1)

if [ "$HTTP_CODE" -lt 200 ] || [ "$HTTP_CODE" -ge 300 ]; then
  log_json "\"FAIL: /v1/environments/public returned HTTP ${HTTP_CODE}\""
  # Push failure metric and exit
  cat > "$METRICS_FILE" <<EOF
# HELP env_verify_status Environment health check status (1=pass, 0=fail)
# TYPE env_verify_status gauge
env_verify_status{env="discovery"} 0
# HELP env_verify_total Total environments checked
# TYPE env_verify_total gauge
env_verify_total 0
# HELP env_verify_passed Environments passing health check
# TYPE env_verify_passed gauge
env_verify_passed 0
# HELP env_verify_last_run_timestamp Unix timestamp of last run
# TYPE env_verify_last_run_timestamp gauge
env_verify_last_run_timestamp $(date +%s)
EOF
  # Push and exit with error
  if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
    curl -s -o /dev/null --max-time 10 -X PUT --data-binary @"$METRICS_FILE" \
      -H "Content-Type: text/plain" -u "$PUSHGATEWAY_AUTH" \
      "${PUSHGATEWAY_URL}/metrics/job/env_verify/instance/${ARENA_INSTANCE}" 2>/dev/null || true
  else
    curl -s -o /dev/null --max-time 10 -X PUT --data-binary @"$METRICS_FILE" \
      -H "Content-Type: text/plain" \
      "${PUSHGATEWAY_URL}/metrics/job/env_verify/instance/${ARENA_INSTANCE}" 2>/dev/null || true
  fi
  [ -n "${HEALTHCHECKS_URL:-}" ] && curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}/fail" 2>/dev/null || true
  exit 1
fi

log_json "\"Fetched environment list (HTTP ${HTTP_CODE})\""

# Parse environment names and health URLs
ENV_COUNT=$(jq -r '.environments | length' "$WORK_DIR/envs.json")
CURRENT=$(jq -r '.current' "$WORK_DIR/envs.json")
log_json "\"Found ${ENV_COUNT} environments, current=${CURRENT}\""

# ---------------------------------------------------------------------------
# Step 2: Health-check each environment
# ---------------------------------------------------------------------------
TOTAL=0
PASSED=0

for i in $(seq 0 $((ENV_COUNT - 1))); do
  ENV_NAME=$(jq -r ".environments[$i].name" "$WORK_DIR/envs.json")
  HEALTH_URL=$(jq -r ".environments[$i].health_url" "$WORK_DIR/envs.json")

  TOTAL=$((TOTAL + 1))

  if [ -z "$HEALTH_URL" ] || [ "$HEALTH_URL" = "" ]; then
    log_json "\"SKIP: ${ENV_NAME} — no health_url\""
    echo "{\"env\":\"${ENV_NAME}\",\"status\":0,\"http_code\":\"0\",\"latency_ms\":0}" \
      > "$WORK_DIR/env_${ENV_NAME}.json"
    continue
  fi

  START_NS=$(date +%s%N 2>/dev/null || echo "0")
  ENV_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$TIMEOUT" "$HEALTH_URL" 2>&1) || ENV_CODE="0"
  END_NS=$(date +%s%N 2>/dev/null || echo "0")

  if [ "$START_NS" != "0" ] && [ "$END_NS" != "0" ]; then
    LATENCY_MS=$(( (END_NS - START_NS) / 1000000 ))
  else
    LATENCY_MS=0
  fi

  if [ "$ENV_CODE" -ge 200 ] 2>/dev/null && [ "$ENV_CODE" -lt 300 ] 2>/dev/null; then
    STATUS=1
    PASSED=$((PASSED + 1))
    log_json "\"PASS: ${ENV_NAME} (HTTP ${ENV_CODE}, ${LATENCY_MS}ms)\""
  else
    STATUS=0
    log_json "\"FAIL: ${ENV_NAME} (HTTP ${ENV_CODE}, ${LATENCY_MS}ms)\""
  fi

  echo "{\"env\":\"${ENV_NAME}\",\"status\":${STATUS},\"http_code\":\"${ENV_CODE}\",\"latency_ms\":${LATENCY_MS}}" \
    > "$WORK_DIR/env_${ENV_NAME}.json"
done

log_json "\"Environment verification: ${PASSED}/${TOTAL} passed\""

# ---------------------------------------------------------------------------
# Step 3: Generate Prometheus metrics
# ---------------------------------------------------------------------------
cat > "$METRICS_FILE" <<EOF
# HELP env_verify_status Environment health check status (1=pass, 0=fail)
# TYPE env_verify_status gauge
EOF

for i in $(seq 0 $((ENV_COUNT - 1))); do
  ENV_NAME=$(jq -r ".environments[$i].name" "$WORK_DIR/envs.json")
  STATUS=$(jq -r '.status' "$WORK_DIR/env_${ENV_NAME}.json")
  echo "env_verify_status{env=\"${ENV_NAME}\"} ${STATUS}" >> "$METRICS_FILE"
done

cat >> "$METRICS_FILE" <<EOF
# HELP env_verify_latency_seconds Environment health check latency
# TYPE env_verify_latency_seconds gauge
EOF

for i in $(seq 0 $((ENV_COUNT - 1))); do
  ENV_NAME=$(jq -r ".environments[$i].name" "$WORK_DIR/envs.json")
  LATENCY_MS=$(jq -r '.latency_ms' "$WORK_DIR/env_${ENV_NAME}.json")
  LATENCY_S=$(echo "scale=3; ${LATENCY_MS}/1000" | bc 2>/dev/null || echo "0")
  echo "env_verify_latency_seconds{env=\"${ENV_NAME}\"} ${LATENCY_S}" >> "$METRICS_FILE"
done

cat >> "$METRICS_FILE" <<EOF
# HELP env_verify_total Total environments checked
# TYPE env_verify_total gauge
env_verify_total ${TOTAL}
# HELP env_verify_passed Environments passing health check
# TYPE env_verify_passed gauge
env_verify_passed ${PASSED}
# HELP env_verify_last_run_timestamp Unix timestamp of last run
# TYPE env_verify_last_run_timestamp gauge
env_verify_last_run_timestamp $(date +%s)
EOF

# ---------------------------------------------------------------------------
# Step 4: Push to Pushgateway
# ---------------------------------------------------------------------------
PUSH_URL="${PUSHGATEWAY_URL}/metrics/job/env_verify/instance/${ARENA_INSTANCE}"
CURL_AUTH=""
if [ -n "${PUSHGATEWAY_AUTH:-}" ]; then
  CURL_AUTH="-u ${PUSHGATEWAY_AUTH}"
fi

PUSH_CODE=$(curl -s -o "$WORK_DIR/push_response.txt" -w "%{http_code}" --max-time 10 -X PUT \
  --data-binary @"$METRICS_FILE" \
  -H "Content-Type: text/plain" $CURL_AUTH "$PUSH_URL" 2>/dev/null)
[ -z "$PUSH_CODE" ] && PUSH_CODE="000"

if [ "$PUSH_CODE" -lt 300 ] && [ "$PUSH_CODE" != "000" ]; then
  METRIC_LINES=$(wc -l < "$METRICS_FILE" | tr -d ' ')
  log_json "\"Pushed ${METRIC_LINES} metric lines to Pushgateway (HTTP ${PUSH_CODE})\""
else
  RESP_BODY=$(head -c 500 "$WORK_DIR/push_response.txt" 2>/dev/null | tr '"' "'" || echo "")
  log_json "\"WARNING: Pushgateway returned HTTP ${PUSH_CODE}: ${RESP_BODY}\""
fi

# ---------------------------------------------------------------------------
# Step 5: Ping Healthchecks (dead man's switch)
# ---------------------------------------------------------------------------
if [ -n "${HEALTHCHECKS_URL:-}" ]; then
  if [ "$PASSED" -eq "$TOTAL" ]; then
    curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}" 2>/dev/null || true
    log_json "\"Healthchecks pinged (all environments healthy)\""
  else
    curl -s -o /dev/null --max-time 5 "${HEALTHCHECKS_URL}/fail" 2>/dev/null || true
    log_json "\"Healthchecks pinged /fail (${PASSED}/${TOTAL} environments healthy)\""
  fi
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rm -rf "$WORK_DIR"
log_json "\"Multi-environment verification finished (${PASSED}/${TOTAL})\""
