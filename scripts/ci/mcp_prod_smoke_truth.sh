#!/usr/bin/env bash
# CAB-2612 — classify the prod MCP SDK smoke. A skip is never PASS.
# No DNS lookup and no publish. Required: input > repo var > default true.
# SKIP exits 1 when required, else warns NON VÉRIFIÉ. FAIL exits 1. PASS exits 0.
set -euo pipefail

PROD_MCP_HOST="mcp.gostoa.dev"

normalize_bool() {
  local raw="${1:-}"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  raw="${raw,,}"
  case "$raw" in
    "" | null | "~") printf '' ;;
    true | 1 | yes) printf 'true' ;;
    false | 0 | no) printf 'false' ;;
    *) return 2 ;;
  esac
}
event="${MCP_SMOKE_EVENT:-unknown}"
commit="${MCP_COMMIT:-unknown}"
environment="${MCP_ENVIRONMENT:-prod}"
dns="${MCP_SMOKE_DNS:-}"
ran="${MCP_SMOKE_RAN:-}"
smoke_exit="${MCP_SMOKE_EXIT:-}"
setup="${MCP_SMOKE_SETUP:-}"
reason_override="${MCP_SMOKE_REASON:-}"
if ! input="$(normalize_bool "${MCP_SMOKE_REQUIRED_INPUT:-}")"; then
  echo "::error::MCP_PROD_SMOKE_REQUIRED input is not a boolean; refusing to report PASS"
  exit 1
fi
if ! var="$(normalize_bool "${MCP_SMOKE_REQUIRED_VAR:-}")"; then
  echo "::error::MCP_PROD_SMOKE_REQUIRED variable is not a boolean; refusing to report PASS"
  exit 1
fi

required="true"
if [ -n "$input" ]; then
  required="$input"
elif [ -n "$var" ]; then
  required="$var"
fi
if [ "$ran" = "true" ] && [ "$smoke_exit" = "0" ]; then
  status="PASS"
  reason="MCP SDK smoke executed"
elif [ "$ran" = "true" ]; then
  status="FAIL"
  reason="MCP SDK smoke failed (exit ${smoke_exit:-unknown})"
elif [ "$dns" = "true" ] && { [ "$setup" = "failure" ] || [ "$setup" = "cancelled" ]; }; then
  status="FAIL"
  reason="MCP SDK install failed; smoke did not run"
elif [ "$dns" = "false" ]; then
  status="SKIP"
  reason="DNS non résolu (${PROD_MCP_HOST})"
elif [ "$dns" = "true" ]; then
  status="SKIP"
  reason="endpoint absent"
else
  status="SKIP"
  reason="smoke non exécuté"
fi
if [ "$status" = "SKIP" ] && [ -n "$reason_override" ]; then
  reason="$reason_override"
fi
case "$status" in
  PASS) exit_code=0 ;;
  FAIL) exit_code=1 ;;
  SKIP) [ "$required" = "true" ] && exit_code=1 || exit_code=0 ;;
esac
if [ "$status" = "SKIP" ]; then
  state_label="SKIP — NON VÉRIFIÉ"
else
  state_label="$status"
fi
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "mcp_prod_status=${status}" >> "${GITHUB_OUTPUT}"
fi
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  cat >> "${GITHUB_STEP_SUMMARY}" <<EOF
### MCP prod smoke

| Field | Value |
| --- | --- |
| State | ${state_label} |
| Reason | ${reason} |
| Commit | \`${commit}\` |
| Environment | ${environment} |
| Required | ${required} |
EOF
fi

echo "mcp_prod_status=${status}"
if [ "$status" = "SKIP" ]; then
  message="NON VÉRIFIÉ — ${reason} (commit ${commit}, environment ${environment}, event ${event})"
  if [ "$required" = "true" ]; then
    echo "::error::${message}"
  else
    echo "::warning::${message}"
  fi
elif [ "$status" = "FAIL" ]; then
  echo "::error::FAIL — ${reason} (commit ${commit}, environment ${environment})"
fi

exit "${exit_code}"
