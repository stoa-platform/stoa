#!/usr/bin/env bash
# =============================================================================
# STOA Demo Smoke Test — contrat minimal exécutable
# =============================================================================
# Canonical source: specs/demo-scope.md + specs/demo-acceptance-tests.md
#
# Usage:
#   ./scripts/demo-smoke-test.sh                      # verbose summary
#   ./scripts/demo-smoke-test.sh --quiet              # only exit code + 1-line verdict
#   ./scripts/demo-smoke-test.sh --dry-run-contract   # validate script/spec flow without a live stack
#   MOCK_MODE=all ./scripts/demo-smoke-test.sh        # run explicit mocks; verdict MOCK_PASS, not DEMO READY
#   AT=1,2,3 ./scripts/demo-smoke-test.sh             # run subset of AT steps
#
# Env vars (with defaults):
#   API_URL              http://localhost:8000
#   GATEWAY_URL          http://localhost:8081
#   GATEWAY_METRICS_URL  ${GATEWAY_URL}/metrics
#   MOCK_BACKEND_URL     http://localhost:9090
#   MOCK_BACKEND_UPSTREAM_URL http://mock-backend:9090
#   DEMO_UAC_CONTRACT    (empty → legacy fallback; set specs/uac/demo-httpbin.uac.json for UAC-driven smoke)
#   DEMO_GATEWAY_PATH    /apis/${DEMO_API_NAME}/get (derived from UAC when DEMO_UAC_CONTRACT is set)
#   TENANT_ID            demo
#   GATEWAY_ID           gateway-demo
#   DEMO_ADMIN_TOKEN     (empty → bypass via ?demo-admin header if cp-api allows)
#   DEMO_MODE_HEADER     true (sends X-Demo-Mode: true to bounded demo endpoints)
#   ROUTE_SYNC_GRACE_SECS 30
#   DEMO_DEPLOY_ENV      dev
#   DEMO_API_NAME        demo-api-smoke
#   DEMO_APP_NAME        demo-app-smoke
#   OBS_VISIBILITY_CHECK auto (auto | off)
#   GRAFANA_URL          http://localhost:3001
#   GRAFANA_USER         admin
#   GRAFANA_PASSWORD     admin
#   CONSOLE_URL          http://localhost:3000
#   PORTAL_URL           http://localhost:3002
#
# Exit codes:
#   0 — REAL_PASS, CONTRACT_DRY_RUN, or MOCK_PASS (see verdict label)
#   1 — at least one AT FAIL (demo NOT ready)
#   2 — pre-conditions failed (cannot run)
#
# =============================================================================

set -uo pipefail

SCRIPT_NAME="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Config ───────────────────────────────────────────────────────────────────
API_URL="${API_URL:-http://localhost:8000}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8081}"
GATEWAY_METRICS_URL="${GATEWAY_METRICS_URL:-${GATEWAY_URL}/metrics}"
MOCK_BACKEND_URL="${MOCK_BACKEND_URL:-http://localhost:9090}"
MOCK_BACKEND_UPSTREAM_URL="${MOCK_BACKEND_UPSTREAM_URL:-http://mock-backend:9090}"
DEMO_UAC_CONTRACT="${DEMO_UAC_CONTRACT:-}"
TENANT_ID="${TENANT_ID:-demo}"
GATEWAY_ID="${GATEWAY_ID:-gateway-demo}"
DEMO_ADMIN_TOKEN="${DEMO_ADMIN_TOKEN:-}"
DEMO_MODE_HEADER="${DEMO_MODE_HEADER:-true}"
ROUTE_SYNC_GRACE_SECS="${ROUTE_SYNC_GRACE_SECS:-30}"
DEMO_DEPLOY_ENV="${DEMO_DEPLOY_ENV:-dev}"
DEMO_API_NAME="${DEMO_API_NAME:-demo-api-smoke}"
DEMO_APP_NAME="${DEMO_APP_NAME:-demo-app-smoke}"
DEMO_ENDPOINT_PATH="${DEMO_ENDPOINT_PATH:-/get}"
DEMO_ENDPOINT_METHOD="${DEMO_ENDPOINT_METHOD:-GET}"
DEMO_OPERATION_ID="${DEMO_OPERATION_ID:-}"
DEMO_GATEWAY_PATH="${DEMO_GATEWAY_PATH:-/apis/${DEMO_API_NAME}/get}"
MOCK_MODE="${MOCK_MODE:-none}"     # none | all | auto (auto is treated as none)
DRY_RUN_CONTRACT="${DRY_RUN_CONTRACT:-0}"
OBS_VISIBILITY_CHECK="${OBS_VISIBILITY_CHECK:-auto}" # auto | off
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3001}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-admin}"
CONSOLE_URL="${CONSOLE_URL:-http://localhost:3000}"
PORTAL_URL="${PORTAL_URL:-http://localhost:3002}"
QUIET="${QUIET:-0}"
AT_FILTER="${AT:-1,2,3,4,5}"       # comma-separated AT numbers to run

for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=1 ;;
        --dry-run-contract) DRY_RUN_CONTRACT=1; MOCK_MODE=all ;;
        --mock-all) MOCK_MODE=all ;;
        --mock-none) MOCK_MODE=none ;;
        --no-observability-ui) OBS_VISIBILITY_CHECK=off ;;
    esac
done

# ── State ────────────────────────────────────────────────────────────────────
declare -a RESULTS=()
declare -a NOTES=()
TOTAL=0
PASSED=0
FAILED=0
MOCK_USED=0

# Collected during steps, used by later steps
API_ID=""
APP_ID=""
SUBSCRIPTION_ID=""
API_KEY=""
DEPLOYMENT_ID=""
LAST_REQUEST_ID=""
HTTP_BODY=""
HTTP_STATUS=""

# ── Helpers ──────────────────────────────────────────────────────────────────

log() {
    if [[ "$QUIET" == "0" ]]; then echo "$@"; fi
}

die() {
    echo "ERROR: $*" >&2
    exit 2
}

check_deps() {
    local missing=0
    for cmd in curl jq; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo "missing: $cmd" >&2
            missing=1
        fi
    done
    [[ "$missing" == "1" ]] && die "install missing dependencies (curl, jq)"
}

at_filter_match() {
    local n="$1"
    [[ ",${AT_FILTER}," == *",${n},"* ]]
}

record() {
    # record ID STATUS DETAIL
    local id="$1" status="$2" detail="${3:-}"
    TOTAL=$((TOTAL + 1))
    if [[ "$status" == "PASS" ]]; then
        PASSED=$((PASSED + 1))
        RESULTS+=("[PASS] $id $detail")
    elif [[ "$status" == "MOCK" ]]; then
        MOCK_USED=1
        PASSED=$((PASSED + 1))
        RESULTS+=("[MOCK] $id $detail")
    else
        FAILED=$((FAILED + 1))
        RESULTS+=("[FAIL] $id $detail")
    fi
}

mock_allowed() {
    [[ "$MOCK_MODE" == "all" || "$DRY_RUN_CONTRACT" == "1" ]]
}

note() {
    # note LEVEL DETAIL
    local level="$1" detail="$2"
    NOTES+=("[${level}] ${detail}")
}

# HTTP with auth header injection. Sets $HTTP_BODY and $HTTP_STATUS.
http_call() {
    local method="$1" url="$2" body="${3:-}"
    local tmp
    tmp="$(mktemp)"
    local curl_args=(-sS -o "$tmp" -w '%{http_code}' --max-time 15 -X "$method" "$url")
    if [[ -n "$DEMO_ADMIN_TOKEN" ]]; then
        curl_args+=(-H "Authorization: Bearer $DEMO_ADMIN_TOKEN")
    fi
    if [[ "$DEMO_MODE_HEADER" == "true" ]]; then
        curl_args+=(-H "X-Demo-Mode: true")
    fi
    if [[ -n "$body" ]]; then
        curl_args+=(-H "Content-Type: application/json" --data "$body")
    fi

    HTTP_STATUS="$(
        curl "${curl_args[@]}" 2>/dev/null || echo 000
    )"
    HTTP_BODY="$(cat "$tmp")"
    rm -f "$tmp"
}

load_uac_contract() {
    if [[ -z "$DEMO_UAC_CONTRACT" ]]; then
        log "WARN — smoke not UAC-driven"
        note "WARN" "smoke not UAC-driven; using legacy fallback DEMO_API_NAME=${DEMO_API_NAME}, path=${DEMO_ENDPOINT_PATH}"
        return 0
    fi

    local contract_path="$DEMO_UAC_CONTRACT"
    if [[ "$contract_path" != /* ]]; then
        contract_path="${REPO_ROOT}/${contract_path}"
    fi

    if [[ ! -f "$contract_path" ]]; then
        record "UAC" "FAIL" "contract not found: ${DEMO_UAC_CONTRACT}"
        return 1
    fi

    if ! jq -e . "$contract_path" >/dev/null 2>&1; then
        record "UAC" "FAIL" "contract is not valid JSON: ${DEMO_UAC_CONTRACT}"
        return 1
    fi

    local endpoint_count contract_status contract_name contract_version contract_tenant
    local endpoint_path endpoint_method endpoint_backend operation_id
    endpoint_count="$(jq -r '.endpoints | if type == "array" then length else 0 end' "$contract_path")"
    contract_status="$(jq -r '.status // empty' "$contract_path")"
    contract_name="$(jq -r '.name // empty' "$contract_path")"
    contract_version="$(jq -r '.version // empty' "$contract_path")"
    contract_tenant="$(jq -r '.tenant_id // empty' "$contract_path")"
    endpoint_path="$(jq -r '.endpoints[0].path // empty' "$contract_path")"
    endpoint_method="$(jq -r '.endpoints[0].methods[0] // empty' "$contract_path")"
    endpoint_backend="$(jq -r '.endpoints[0].backend_url // empty' "$contract_path")"
    operation_id="$(jq -r '.endpoints[0].operation_id // empty' "$contract_path")"

    if [[ "$endpoint_count" -lt 1 ]]; then
        record "UAC" "FAIL" "contract has no endpoints: ${DEMO_UAC_CONTRACT}"
        return 1
    fi
    if [[ "$contract_status" != "published" ]]; then
        record "UAC" "FAIL" "contract status=${contract_status:-empty}; expected published for real smoke"
        return 1
    fi
    if [[ -z "$contract_name" || -z "$contract_version" || -z "$contract_tenant" ]]; then
        record "UAC" "FAIL" "contract name/version/tenant_id must be non-empty"
        return 1
    fi
    if [[ -z "$endpoint_method" || -z "$endpoint_path" || -z "$endpoint_backend" ]]; then
        record "UAC" "FAIL" "endpoint method/path/backend_url must be non-empty"
        return 1
    fi
    if [[ "$endpoint_path" != /* ]]; then
        record "UAC" "FAIL" "endpoint path must start with / (got ${endpoint_path})"
        return 1
    fi

    DEMO_API_NAME="$contract_name"
    TENANT_ID="$contract_tenant"
    DEMO_ENDPOINT_PATH="$endpoint_path"
    DEMO_ENDPOINT_METHOD="$endpoint_method"
    DEMO_OPERATION_ID="$operation_id"
    MOCK_BACKEND_UPSTREAM_URL="$endpoint_backend"
    DEMO_GATEWAY_PATH="/apis/${DEMO_API_NAME}${DEMO_ENDPOINT_PATH}"

    record "UAC" "PASS" "contract loaded ${DEMO_API_NAME} v${contract_version}"
    record "UAC" "PASS" "endpoint ${DEMO_ENDPOINT_METHOD} ${DEMO_ENDPOINT_PATH} selected operation_id=${DEMO_OPERATION_ID:-n/a}"
    record "UAC" "PASS" "Gateway call derived from UAC ${DEMO_GATEWAY_PATH}"
    return 0
}

# ── AT-0 pré-conditions ─────────────────────────────────────────────────────

at0_preconditions() {
    log ""
    log "=== AT-0  Pre-conditions ==="
    local ok=1
    local detail=""

    # cp-api health
    local code
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${API_URL}/health" 2>/dev/null || echo 000)"
    if [[ "$code" != "200" ]]; then
        ok=0; detail="${detail}cp-api=${code} "
    fi

    # gateway health
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${GATEWAY_URL}/health" 2>/dev/null || echo 000)"
    if [[ "$code" != "200" ]]; then
        ok=0; detail="${detail}gateway=${code} "
    fi

    # mock backend
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${MOCK_BACKEND_URL}/ping" 2>/dev/null || echo 000)"
    if [[ "$code" != "200" ]]; then
        ok=0; detail="${detail}mock=${code} "
    fi

    if [[ "$ok" == "1" ]]; then
        record "AT-0" "PASS" "cp-api+gateway+mock reachable"
        return 0
    elif mock_allowed; then
        record "AT-0" "MOCK" "preconditions mocked for explicit non-real mode (${detail})"
        return 0
    else
        record "AT-0" "FAIL" "$detail"
        return 1
    fi
}

# ── AT-1 Declare API ────────────────────────────────────────────────────────

at1_declare_api() {
    log ""
    log "=== AT-1  Declare API ==="
    at_filter_match 1 || { log "  (skipped by AT filter)"; return 0; }

    local body
    body="$(
        jq -n \
            --arg name "$DEMO_API_NAME" \
            --arg backend_url "$MOCK_BACKEND_UPSTREAM_URL" \
            --arg path "$DEMO_ENDPOINT_PATH" \
            --arg method "$DEMO_ENDPOINT_METHOD" \
            '{
              name: $name,
              display_name: $name,
              version: "1.0.0",
              protocol: "http",
              backend_url: $backend_url,
              paths: [{path: $path, methods: [$method]}]
            }'
    )"

    local resp
    http_call POST "${API_URL}/v1/tenants/${TENANT_ID}/apis" "$body"
    resp="$HTTP_BODY"
    if [[ "$HTTP_STATUS" != "201" && "$HTTP_STATUS" != "200" && "$HTTP_STATUS" != "409" ]]; then
        if mock_allowed; then
            API_ID="mock-api-id-00000000"
            record "AT-1" "MOCK" "HTTP=${HTTP_STATUS}, mocked API_ID=${API_ID}"
            return 0
        fi
        record "AT-1" "FAIL" "HTTP=${HTTP_STATUS}, body=${resp:0:200}"
        return 1
    fi

    # 409 conflict = already exists → fetch
    if [[ "$HTTP_STATUS" == "409" ]]; then
        http_call GET "${API_URL}/v1/tenants/${TENANT_ID}/apis?name=${DEMO_API_NAME}" ""
        resp="$HTTP_BODY"
        API_ID="$(
            echo "$resp" \
                | jq -r --arg name "$DEMO_API_NAME" \
                    '(.items // .apis // [])[] | select(.name == $name or .id == $name) | .id' \
                    2>/dev/null \
                | head -n 1
        )"
    else
        API_ID="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null || true)"
    fi

    if [[ -z "$API_ID" ]]; then
        record "AT-1" "FAIL" "no id in response (HTTP=${HTTP_STATUS})"
        return 1
    fi

    record "AT-1" "PASS" "API_ID=${API_ID}"
    return 0
}

# ── AT-2 Provision route ────────────────────────────────────────────────────

at2_provision_route() {
    log ""
    log "=== AT-2  Provision gateway route ==="
    at_filter_match 2 || { log "  (skipped by AT filter)"; return 0; }

    if [[ -z "$API_ID" ]]; then
        record "AT-2" "FAIL" "API_ID empty (AT-1 skipped?)"
        return 1
    fi

    local body resp
    body="$(cat <<JSON
{
  "api_id": "${API_ID}",
  "environment": "${DEMO_DEPLOY_ENV}",
  "gateway_id": "${GATEWAY_ID}"
}
JSON
)"
    http_call POST "${API_URL}/v1/tenants/${TENANT_ID}/deployments" "$body"
    resp="$HTTP_BODY"

    if [[ "$HTTP_STATUS" != "201" && "$HTTP_STATUS" != "200" ]]; then
        if mock_allowed; then
            DEPLOYMENT_ID="mock-deploy-id"
            record "AT-2" "MOCK" "HTTP=${HTTP_STATUS}, mocked deployment"
            return 0
        fi
        record "AT-2" "FAIL" "HTTP=${HTTP_STATUS}, body=${resp:0:200}"
        return 1
    fi

    DEPLOYMENT_ID="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null || true)"

    # Wait for route to appear in gateway route table (polling via cp-api internal)
    local elapsed=0
    local route_ready=0
    while [[ $elapsed -lt $ROUTE_SYNC_GRACE_SECS ]]; do
        local routes_resp
        http_call GET "${API_URL}/v1/internal/gateways/routes?gateway_name=${GATEWAY_ID}" ""
        routes_resp="$HTTP_BODY"
        if [[ "$HTTP_STATUS" == "200" ]] && echo "$routes_resp" | jq -e --arg id "$API_ID" '.[]? | select(.api_id == $id)' >/dev/null 2>&1; then
            route_ready=1
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    if [[ "$route_ready" != "1" ]]; then
        if mock_allowed; then
            record "AT-2" "MOCK" "deployment 201 but route not synced in ${ROUTE_SYNC_GRACE_SECS}s (accepted in mock_mode=${MOCK_MODE})"
            return 0
        fi
        record "AT-2" "FAIL" "route not synced in ${ROUTE_SYNC_GRACE_SECS}s"
        return 1
    fi

    record "AT-2" "PASS" "DEPLOYMENT_ID=${DEPLOYMENT_ID}, route synced in ~${elapsed}s"
    return 0
}

# ── AT-3 Subscription ───────────────────────────────────────────────────────

at3_subscription() {
    log ""
    log "=== AT-3  Create subscription ==="
    at_filter_match 3 || { log "  (skipped by AT filter)"; return 0; }

    if [[ -z "$API_ID" ]]; then
        record "AT-3" "FAIL" "API_ID empty"
        return 1
    fi

    # Step 1: application
    local resp body
    body="$(cat <<JSON
{
  "name": "${DEMO_APP_NAME}",
  "display_name": "${DEMO_APP_NAME}"
}
JSON
)"
    http_call POST "${API_URL}/v1/tenants/${TENANT_ID}/applications" "$body"
    resp="$HTTP_BODY"
    if [[ "$HTTP_STATUS" != "201" && "$HTTP_STATUS" != "200" && "$HTTP_STATUS" != "409" ]]; then
        if mock_allowed; then
            APP_ID="mock-app-id"
            SUBSCRIPTION_ID="mock-sub-id"
            API_KEY="stoa_mock_demokey"
            record "AT-3" "MOCK" "HTTP=${HTTP_STATUS}, mocked app+sub+key"
            return 0
        fi
        record "AT-3" "FAIL" "applications HTTP=${HTTP_STATUS}, body=${resp:0:200}"
        return 1
    fi
    APP_ID="$(echo "$resp" | jq -r '.id // empty' 2>/dev/null)"
    if [[ -z "$APP_ID" && "$HTTP_STATUS" == "409" ]]; then
        http_call GET "${API_URL}/v1/tenants/${TENANT_ID}/applications?name=${DEMO_APP_NAME}" ""
        resp="$HTTP_BODY"
        APP_ID="$(
            echo "$resp" \
                | jq -r --arg name "$DEMO_APP_NAME" \
                    '(.items // .applications // [])[] | select(.name == $name or .id == $name or .client_id == $name) | .id' \
                    2>/dev/null \
                | head -n 1
        )"
    fi
    if [[ -z "$APP_ID" ]]; then
        record "AT-3" "FAIL" "no application id"
        return 1
    fi

    # Step 2: subscribe (single-shot endpoint)
    http_call POST "${API_URL}/v1/tenants/${TENANT_ID}/applications/${APP_ID}/subscribe/${API_ID}" ""
    resp="$HTTP_BODY"
    if [[ "$HTTP_STATUS" != "201" && "$HTTP_STATUS" != "200" ]]; then
        # fallback to /v1/subscriptions
        body="{\"application_id\":\"${APP_ID}\",\"api_id\":\"${API_ID}\",\"plan\":\"free\"}"
        http_call POST "${API_URL}/v1/subscriptions" "$body"
        resp="$HTTP_BODY"
    fi

    if [[ "$HTTP_STATUS" != "201" && "$HTTP_STATUS" != "200" ]]; then
        if mock_allowed; then
            SUBSCRIPTION_ID="mock-sub-id"
            API_KEY="stoa_mock_demokey"
            record "AT-3" "MOCK" "HTTP=${HTTP_STATUS}, mocked sub+key"
            return 0
        fi
        record "AT-3" "FAIL" "subscribe HTTP=${HTTP_STATUS}, body=${resp:0:200}"
        return 1
    fi

    SUBSCRIPTION_ID="$(echo "$resp" | jq -r '.id // .subscription_id // empty' 2>/dev/null)"
    API_KEY="$(echo "$resp" | jq -r '.api_key // .new_api_key // empty' 2>/dev/null)"
    local prefix
    prefix="$(echo "$resp" | jq -r '.api_key_prefix // empty' 2>/dev/null)"

    if [[ -z "$API_KEY" ]]; then
        # prefix-only response: accept with mock warning
        if [[ -n "$prefix" ]]; then
            record "AT-3" "MOCK" "only api_key_prefix returned (${prefix}), cleartext unavailable. Demo must surface full key."
            API_KEY="__NO_CLEARTEXT_AVAILABLE__"
            return 0
        fi
        record "AT-3" "FAIL" "no api_key/prefix in response"
        return 1
    fi

    record "AT-3" "PASS" "SUBSCRIPTION_ID=${SUBSCRIPTION_ID}, API_KEY acquired"
    return 0
}

# ── AT-4 Gateway call ───────────────────────────────────────────────────────

at4_gateway_call() {
    log ""
    log "=== AT-4  Call API via gateway ==="
    at_filter_match 4 || { log "  (skipped by AT filter)"; return 0; }

    if [[ "$DRY_RUN_CONTRACT" == "1" || ( "$MOCK_MODE" == "all" && "$API_KEY" == stoa_mock* ) ]]; then
        LAST_REQUEST_ID="mock-req-id"
        record "AT-4" "MOCK" "gateway call skipped for explicit non-real mode"
        return 0
    fi

    if [[ -z "$API_KEY" || "$API_KEY" == "__NO_CLEARTEXT_AVAILABLE__" ]]; then
        if mock_allowed; then
            LAST_REQUEST_ID="mock-req-id"
            record "AT-4" "MOCK" "no real API_KEY, call skipped (mock_mode=all)"
            return 0
        fi
        record "AT-4" "FAIL" "no usable API_KEY"
        return 1
    fi

    # Canonical demo gateway mapping (B3): one official path, no shape probing.
    local hdr_file body_file
    hdr_file="$(mktemp)"; body_file="$(mktemp)"
    local attempt=0 status=""
    while [[ $attempt -lt 5 ]]; do
        status="$(
            curl -sS -o "$body_file" -D "$hdr_file" -w '%{http_code}' --max-time 10 \
                 -X "$DEMO_ENDPOINT_METHOD" \
                 -H "X-Api-Key: ${API_KEY}" \
                 "${GATEWAY_URL}${DEMO_GATEWAY_PATH}" 2>/dev/null || echo 000
        )"
        if [[ "$status" == "200" ]]; then break; fi
        attempt=$((attempt + 1))
        sleep 2
    done

    if [[ "$status" == "200" ]]; then
        LAST_REQUEST_ID="$(grep -i '^x-stoa-request-id:' "$hdr_file" | awk '{print $2}' | tr -d '\r' || true)"
        record "AT-4" "PASS" "${DEMO_ENDPOINT_METHOD} ${DEMO_GATEWAY_PATH} HTTP 200, request_id=${LAST_REQUEST_ID:-n/a}"
        rm -f "$hdr_file" "$body_file"
        return 0
    fi

    if mock_allowed; then
        record "AT-4" "MOCK" "canonical gateway path ${DEMO_GATEWAY_PATH} returned ${status}"
        rm -f "$hdr_file" "$body_file"
        return 0
    fi

    record "AT-4" "FAIL" "canonical gateway path ${DEMO_GATEWAY_PATH} returned ${status}"
    rm -f "$hdr_file" "$body_file"
    return 1
}

# ── AT-5 Observable proof ───────────────────────────────────────────────────

at5_observable() {
    log ""
    log "=== AT-5  Observable proof ==="
    at_filter_match 5 || { log "  (skipped by AT filter)"; return 0; }

    local metrics="" counter="" value=""
    for _ in 1 2 3; do
        metrics="$(curl -sS --max-time 5 "${GATEWAY_METRICS_URL}" 2>/dev/null || true)"
        counter="$(echo "$metrics" | grep -E '^proxy_requests_total\{' | head -1 || true)"
        if [[ -n "$counter" ]]; then
            value="$(echo "$counter" | awk '{print $NF}')"
            if echo "$value" | grep -Eq '^[0-9]+(\.[0-9]+)?$' && [[ "${value%.*}" != "0" ]]; then
                break
            fi
        fi
        sleep 1
    done
    if [[ -z "$metrics" ]]; then
        if mock_allowed; then
            record "AT-5" "MOCK" "no /metrics body; observable proof skipped in mock/contract mode"
            return 0
        fi
        record "AT-5" "FAIL" "no /metrics body"
        return 1
    fi

    if [[ -z "$counter" ]]; then
        if mock_allowed; then
            record "AT-5" "MOCK" "no proxy_requests_total counter. Either names diverged or no traffic. Spec requires it."
            return 0
        fi
        record "AT-5" "FAIL" "no counter proxy_requests_total"
        return 1
    fi

    # Extract value (last field on the line)
    if ! echo "$value" | grep -Eq '^[0-9]+(\.[0-9]+)?$' || [[ "${value%.*}" == "0" ]]; then
        if mock_allowed; then
            record "AT-5" "MOCK" "counter found but value=${value} (likely no traffic in AT-4). Spec expects >0."
            return 0
        fi
        record "AT-5" "FAIL" "counter value=${value} (expected >0)"
        return 1
    fi

    local log_proof="no-log-check"
    # If running in compose, try to correlate with docker logs
    if command -v docker >/dev/null 2>&1 && [[ -n "$LAST_REQUEST_ID" ]]; then
        if docker logs stoa-gateway 2>&1 | grep -q "$LAST_REQUEST_ID"; then
            log_proof="request_id matched in docker logs"
        fi
    fi

    record "AT-5" "PASS" "counter=${counter%%\{*}, value=${value}, log=${log_proof}"
    return 0
}

# ── AT-5b Optional observability visibility ─────────────────────────────────

at5b_observability_visibility() {
    log ""
    log "=== AT-5b Observability visibility (nice-to-have) ==="

    if [[ "$OBS_VISIBILITY_CHECK" == "off" ]]; then
        note "INFO" "AT-5b skipped (OBS_VISIBILITY_CHECK=off)"
        return 0
    fi

    local grafana_code
    grafana_code="$(
        curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
             -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
             "${GRAFANA_URL}/api/health" 2>/dev/null || echo 000
    )"
    if [[ "$grafana_code" != "200" ]]; then
        note "WARN" "AT-5b Grafana not reachable at ${GRAFANA_URL} (HTTP=${grafana_code}); UI visibility not proven"
        return 0
    fi

    local prom_code traces_code tempo_code
    prom_code="$(
        curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
             -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
             "${GRAFANA_URL}/api/datasources/uid/prometheus" 2>/dev/null || echo 000
    )"
    traces_code="$(
        curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
             -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
             "${GRAFANA_URL}/api/datasources/uid/opensearch-traces" 2>/dev/null || echo 000
    )"
    tempo_code="$(
        curl -sS -o /dev/null -w '%{http_code}' --max-time 5 \
             -u "${GRAFANA_USER}:${GRAFANA_PASSWORD}" \
             "${GRAFANA_URL}/api/datasources/uid/tempo" 2>/dev/null || echo 000
    )"

    local console_code portal_code
    console_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${CONSOLE_URL}/monitoring" 2>/dev/null || echo 000)"
    portal_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "${PORTAL_URL}/usage" 2>/dev/null || echo 000)"

    local detail
    detail="Grafana=${grafana_code}, prometheus-ds=${prom_code}, opensearch-traces-ds=${traces_code}, tempo-ds=${tempo_code}, console=/monitoring:${console_code}, portal=/usage:${portal_code}"

    if [[ "$prom_code" == "200" && ( "$traces_code" == "200" || "$tempo_code" == "200" ) ]]; then
        note "PASS" "AT-5b observability UI reachable (${detail})"
    else
        note "WARN" "AT-5b observability UI partial (${detail}); OTEL visibility remains nice-to-have"
    fi
    return 0
}

# ── Report ──────────────────────────────────────────────────────────────────

print_report() {
    echo ""
    echo "================================================================"
    echo "  STOA Demo Smoke Test — Results"
    echo "  Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
    echo "  API_URL=${API_URL}"
    echo "  GATEWAY_URL=${GATEWAY_URL}"
    echo "  DEMO_UAC_CONTRACT=${DEMO_UAC_CONTRACT:-<none>}"
    echo "  DEMO_GATEWAY_PATH=${DEMO_GATEWAY_PATH}"
    echo "  MOCK_MODE=${MOCK_MODE}"
    echo "  DRY_RUN_CONTRACT=${DRY_RUN_CONTRACT}"
    echo "================================================================"
    for line in "${RESULTS[@]}"; do
        echo "  $line"
    done
    if [[ ${#NOTES[@]} -gt 0 ]]; then
        echo "----------------------------------------------------------------"
        for line in "${NOTES[@]}"; do
            echo "  $line"
        done
    fi
    echo "----------------------------------------------------------------"
    echo "  Score: ${PASSED}/${TOTAL}"
    if [[ $FAILED -ne 0 ]]; then
        echo "  Verdict: FAIL — DEMO NOT READY (${FAILED} fail)"
    elif [[ "$DRY_RUN_CONTRACT" == "1" ]]; then
        echo "  Verdict: CONTRACT_DRY_RUN — contract validated, demo not proven"
    elif [[ "$MOCK_USED" == "1" ]]; then
        echo "  Verdict: MOCK_PASS — script coherent, demo not proven"
    else
        echo "  Verdict: REAL_PASS — DEMO READY"
    fi
    echo "================================================================"
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
    check_deps

    if [[ "$MOCK_MODE" == "auto" ]]; then
        note "INFO" "MOCK_MODE=auto is treated as strict real mode; blockers will FAIL, not mock-pass"
        MOCK_MODE="none"
    fi

    if ! load_uac_contract; then
        print_report
        exit 2
    fi

    if ! at0_preconditions; then
        print_report
        exit 2
    fi

    at1_declare_api      || true
    at2_provision_route  || true
    at3_subscription     || true
    at4_gateway_call     || true
    at5_observable       || true
    at5b_observability_visibility || true

    print_report

    if [[ $FAILED -eq 0 ]]; then
        exit 0
    else
        exit 1
    fi
}

main "$@"
