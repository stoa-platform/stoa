#!/usr/bin/env bash
# CAB-2612 — classify a dev post-deploy check. A skip or a swallowed
# failure is never PASS. DEV_POST_DEPLOY_REQUIRED: input > repo var >
# default false. PASS exits 0. FAIL and SKIP exit 1 when required, and
# otherwise warn (NON VÉRIFIÉ or FAIL) without claiming success.
# No cluster access, no deploy, no probe.
set -euo pipefail

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

control="${POST_DEPLOY_CONTROL:-post-deploy}"
ran="${POST_DEPLOY_RAN:-}"
ok="${POST_DEPLOY_OK:-}"
reason="${POST_DEPLOY_REASON:-}"
commit="${POST_DEPLOY_COMMIT:-unknown}"
environment="${POST_DEPLOY_ENVIRONMENT:-dev}"

if ! input="$(normalize_bool "${POST_DEPLOY_REQUIRED_INPUT:-}")"; then
  echo "::error::DEV_POST_DEPLOY_REQUIRED input is not a boolean; refusing to report PASS"
  exit 1
fi
if ! var="$(normalize_bool "${POST_DEPLOY_REQUIRED_VAR:-}")"; then
  echo "::error::DEV_POST_DEPLOY_REQUIRED variable is not a boolean; refusing to report PASS"
  exit 1
fi

required="false"
if [ -n "$input" ]; then
  required="$input"
elif [ -n "$var" ]; then
  required="$var"
fi

if [ "$ran" = "true" ] && [ "$ok" = "true" ]; then
  status="PASS"
  [ -n "$reason" ] || reason="probe executed"
elif [ "$ran" = "true" ]; then
  status="FAIL"
  [ -n "$reason" ] || reason="probe failed"
else
  status="SKIP"
  [ -n "$reason" ] || reason="probe did not run"
fi

if [ "$status" = "PASS" ]; then
  exit_code=0
elif [ "$required" = "true" ]; then
  exit_code=1
else
  exit_code=0
fi

if [ "$status" = "SKIP" ]; then
  state_label="SKIP — NON VÉRIFIÉ"
else
  state_label="$status"
fi

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "post_deploy_status=${status}" >> "${GITHUB_OUTPUT}"
fi
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  cat >> "${GITHUB_STEP_SUMMARY}" <<EOF
### ${control}

| Field | Value |
| --- | --- |
| State | ${state_label} |
| Reason | ${reason} |
| Commit | \`${commit}\` |
| Environment | ${environment} |
| Required | ${required} |
EOF
fi

echo "post_deploy_status=${status}"
if [ "$status" = "SKIP" ]; then
  message="NON VÉRIFIÉ — ${reason} (commit ${commit}, environment ${environment})"
elif [ "$status" = "FAIL" ]; then
  message="FAIL — ${reason} (commit ${commit}, environment ${environment})"
else
  message=""
fi
if [ -n "$message" ]; then
  if [ "$required" = "true" ]; then
    echo "::error::${message}"
  else
    echo "::warning::${message}"
  fi
fi

exit "${exit_code}"
