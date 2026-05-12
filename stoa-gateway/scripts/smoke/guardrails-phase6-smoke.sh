#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/guardrails-smoke}"
SMOKE_ENV="${SMOKE_ENV:-dev-k3d}"
EXPECTED_STATE="${EXPECTED_STATE:-no_evaluations}"
SMOKE_RANGE="${SMOKE_RANGE:-1h}"
GATEWAY_URL="${GATEWAY_URL:-http://localhost:8081}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
CONTROL_PLANE_API_URL="${CONTROL_PLANE_API_URL:-http://localhost:8000}"
FIXTURES_DOC="${FIXTURES_DOC:-docs/observability/phase-6-smoke-fixtures.md}"
OPERATOR_OPT_IN="${OPERATOR_OPT_IN:-}"
AR1_STATUS="${AR1_STATUS:-not-run}"

mkdir -p "${ARTIFACT_DIR}"
FINDINGS="${ARTIFACT_DIR}/findings.md"
UTC_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[FAIL] $*" >&2; exit 1; }
note() { echo "[OK] $*"; }
need() { command -v "$1" >/dev/null 2>&1 || fail "missing required tool: $1"; }

need curl
need jq
need grep

case "${SMOKE_ENV}" in
  dev-k3d|prod) ;;
  *) fail "SMOKE_ENV must be dev-k3d or prod" ;;
esac

case "${EXPECTED_STATE}" in
  metrics_unavailable|no_evaluations|evaluations_zero_trips|trips_observed|stale_data) ;;
  *) fail "EXPECTED_STATE is not a Phase 6 guardrails state" ;;
esac

if [[ "${SMOKE_ENV}" == "prod" ]]; then
  case "${EXPECTED_STATE}" in
    evaluations_zero_trips|trips_observed) ;;
    *) fail "prod smoke may only validate evaluations_zero_trips or trips_observed" ;;
  esac
  [[ "${OPERATOR_OPT_IN}" =~ ^[A-Za-z][A-Za-z0-9_-]{1,15}$ ]] \
    || fail "prod smoke requires OPERATOR_OPT_IN with operator initials"
fi

if [[ "${SMOKE_ENV}" == "dev-k3d" && "${AR1_STATUS}" != "green" ]]; then
  fail "dev-k3d smoke requires AR1_STATUS=green"
fi

FIXTURES_PATH="${ROOT_DIR}/${FIXTURES_DOC}"
[[ -f "${FIXTURES_PATH}" ]] || fail "fixture document missing: ${FIXTURES_DOC}"
if grep -En '([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|[0-9]{3}-[0-9]{2}-[0-9]{4}|[0-9]{3}[ -][0-9]{3}[ -][0-9]{4}|[0-9]{4}([ -][0-9]{4}){3})' "${FIXTURES_PATH}"; then
  fail "fixture document contains a known PII-shaped pattern"
fi
note "synthetic fixture document has no known PII-shaped pattern"

METRICS_TXT="${ARTIFACT_DIR}/gateway-metrics.txt"
curl -fsS "${GATEWAY_URL%/}/metrics" > "${METRICS_TXT}"
guardrail_lines="$(grep -E '^stoa_guardrails_(evaluations|decisions)_total\{' "${METRICS_TXT}" || true)"
[[ -n "${guardrail_lines}" ]] || fail "gateway /metrics exposes no full guardrails series"

if printf '%s\n' "${guardrail_lines}" | grep -E '(tenant_id|tenant|route|path|url|tool|trace_id|span_id|request_id|user_id|consumer)="'; then
  fail "forbidden label found on full guardrails metrics"
fi

series_count="$(printf '%s\n' "${guardrail_lines}" | grep -Ec '^stoa_guardrails_(evaluations|decisions)_total\{')"
[[ "${series_count}" -ge 100 ]] || fail "A13 producer presence expected at least 100 bounded series, got ${series_count}"

if [[ "${EXPECTED_STATE}" == "no_evaluations" ]]; then
  non_zero="$(printf '%s\n' "${guardrail_lines}" | awk '$NF + 0 != 0 { print; exit 0 }')"
  [[ -z "${non_zero}" ]] || fail "no_evaluations scenario must use fresh zero-traffic gateway series"
fi
note "gateway full guardrails labels are bounded and producer presence exists"

PROM_SERIES="${ARTIFACT_DIR}/prometheus-series.json"
if curl -fsS --get \
  --data-urlencode 'match[]=stoa_guardrails_evaluations_total' \
  --data-urlencode 'match[]=stoa_guardrails_decisions_total' \
  "${PROMETHEUS_URL%/}/api/v1/series" > "${PROM_SERIES}"; then
  jq -e '
    .status == "success" and
    (.data | length > 0) and
    all(.data[]; ((keys - ["__name__","deployment_mode","surface","guardrail","decision"]) | length) == 0)
  ' "${PROM_SERIES}" >/dev/null \
    || fail "Prometheus series include forbidden/unbounded full-guardrails labels"
  note "Prometheus full guardrails series use bounded labels only"
else
  [[ "${SMOKE_ENV}" == "dev-k3d" && "${EXPECTED_STATE}" == "metrics_unavailable" ]] \
    || fail "Prometheus series query failed outside the dev metrics_unavailable scenario"
  note "Prometheus unavailable as expected for dev metrics_unavailable scenario"
fi

CP_JSON="${ARTIFACT_DIR}/control-plane-metrics.json"
if [[ -n "${CP_API_BEARER_TOKEN:-}" ]]; then
  curl -fsS -H "Authorization: Bearer ${CP_API_BEARER_TOKEN}" \
    "${CONTROL_PLANE_API_URL%/}/v1/admin/gateways/metrics?range=${SMOKE_RANGE}" > "${CP_JSON}"
else
  curl -fsS \
    "${CONTROL_PLANE_API_URL%/}/v1/admin/gateways/metrics?range=${SMOKE_RANGE}" > "${CP_JSON}"
fi
ACTUAL_STATE="$(jq -r '.guardrails.state // empty' "${CP_JSON}")"
[[ -n "${ACTUAL_STATE}" ]] || fail "control-plane metrics response has no guardrails.state"
[[ "${ACTUAL_STATE}" == "${EXPECTED_STATE}" ]] \
  || fail "expected guardrails.state=${EXPECTED_STATE}, got ${ACTUAL_STATE}"
note "control-plane guardrails state matched ${EXPECTED_STATE}"

cat > "${FINDINGS}" <<REPORT
# Phase 6.6 Guardrails Smoke Findings

- UTC timestamp: ${UTC_TS}
- Environment: ${SMOKE_ENV}
- Expected state: ${EXPECTED_STATE}
- Actual state: ${ACTUAL_STATE}
- Operator opt-in: ${OPERATOR_OPT_IN:-n/a}
- AR-1 status: ${AR1_STATUS}
- Gateway URL: ${GATEWAY_URL}
- Control Plane API URL: ${CONTROL_PLANE_API_URL}
- Prometheus URL: ${PROMETHEUS_URL}
- Verdict: PASS

Evidence files: gateway-metrics.txt, prometheus-series.json, control-plane-metrics.json.
REPORT

note "wrote ${FINDINGS}"
