#!/usr/bin/env bash
# Aggregate the ci-gate needs object.
# changes and security must be success.
# Every detector output must be present and exactly true or false.
# true requires that component job to be success.
# false requires that component job to be skipped.
# Any other result, a missing output, or empty needs fails.
set -euo pipefail

COMPONENTS=(
  control-plane-api
  stoa-gateway
  control-plane-ui
  portal
  stoa-go
  stoa-operator
  helm
)

fail() {
  echo "::error::CI Gate failed: $*"
  exit 1
}

if [[ -z "${NEEDS:-}" ]]; then
  fail "empty needs"
fi

if ! printf '%s' "$NEEDS" | jq -e 'type == "object" and length > 0' >/dev/null 2>&1; then
  fail "empty needs"
fi

job_result() {
  local job="$1"
  printf '%s' "$NEEDS" | jq -r --arg job "$job" '
    if has($job) and (.[$job] | type == "object") and (.[$job].result | type == "string")
    then .[$job].result
    else ""
    end
  '
}

detector_output() {
  local name="$1"
  printf '%s' "$NEEDS" | jq -r --arg name "$name" '
    if (.changes | type == "object")
       and (.changes.outputs | type == "object")
       and (.changes.outputs | has($name))
       and (.changes.outputs[$name] | type == "string")
    then .changes.outputs[$name]
    else ""
    end
  '
}

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## CI Gate"
    echo "| Job | Result |"
    echo "| --- | --- |"
    printf '%s' "$NEEDS" | jq -r '
      to_entries[]
      | "| \(.key) | \(if (.value | type) == "object" and (.value.result | type) == "string" then .value.result else "missing" end) |"
    '
  } >> "$GITHUB_STEP_SUMMARY"
fi

changes_result="$(job_result changes)"
security_result="$(job_result security)"

if [[ "$changes_result" != "success" ]]; then
  fail "changes result is '${changes_result:-missing}', expected success"
fi
if [[ "$security_result" != "success" ]]; then
  fail "security result is '${security_result:-missing}', expected success"
fi

for name in "${COMPONENTS[@]}"; do
  output="$(detector_output "$name")"
  result="$(job_result "$name")"
  if [[ "$output" != "true" && "$output" != "false" ]]; then
    fail "detector output ${name} is '${output:-missing}', expected true or false"
  fi
  if [[ "$output" == "true" ]]; then
    if [[ "$result" != "success" ]]; then
      fail "${name} is expected but result is '${result:-missing}'"
    fi
  elif [[ "$result" != "skipped" ]]; then
    fail "${name} is not expected but result is '${result:-missing}', expected skipped"
  fi
done

echo "CI Gate passed."
