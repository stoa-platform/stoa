#!/usr/bin/env bash
# =============================================================================
# CAB-2150 (parent CAB-2148): Cold full-path dry-run.
# =============================================================================
# Executes the full demo harness in order (reset -> check) with per-step
# timing and captures all output + metadata into a timestamped evidence
# archive under docs/audits/demo-dryrun-<UTC>/.
#
# Exits 0 ONLY if every step succeeded.
#
# Usage: ./demo-dry-run.sh [--skip-reset]
# Env (inherited by sub-scripts):
#   STOA_API_URL, STOA_API_TOKEN, STOA_GATEWAY_URL, STOA_DEMO_MIN_TENANTS
# =============================================================================

set -euo pipefail

SKIP_RESET=0
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-reset) SKIP_RESET=1; shift ;;
        -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${REPO_ROOT}/docs/audits/demo-dryrun-${STAMP}"
mkdir -p "$ARTIFACT_DIR"

SUMMARY="${ARTIFACT_DIR}/summary.md"
META="${ARTIFACT_DIR}/metadata.json"

TOTAL_START=$(date +%s)
STATUS="success"

run_step() {
    local name="$1"; shift
    local logfile="${ARTIFACT_DIR}/${name}.log"
    local step_start step_end elapsed rc
    step_start=$(date +%s)
    printf '\n=== [%s] starting ===\n' "$name"
    rc=0
    "$@" > "$logfile" 2>&1 || rc=$?
    step_end=$(date +%s)
    elapsed=$((step_end - step_start))
    if [ "$rc" -eq 0 ]; then
        printf '=== [%s] OK (%ds) ===\n' "$name" "$elapsed"
        printf -- '- %s: PASS (%ds)\n' "$name" "$elapsed" >> "$SUMMARY"
    else
        printf '=== [%s] FAIL rc=%d (%ds) ===\n' "$name" "$rc" "$elapsed" >&2
        printf -- '- %s: FAIL rc=%d (%ds)\n' "$name" "$rc" "$elapsed" >> "$SUMMARY"
        STATUS="failed"
    fi
    return "$rc"
}

{
    printf '# Demo dry-run — %s\n\n' "$STAMP"
    printf '## Steps\n\n'
} > "$SUMMARY"

# Step 1: reset (optional skip for read-only dry runs)
if [ "$SKIP_RESET" -eq 0 ]; then
    run_step reset "${SCRIPT_DIR}/reset-demo.sh" || true
else
    printf -- '- reset: SKIPPED (--skip-reset)\n' >> "$SUMMARY"
fi

# Step 2: preflight binary gate (only if reset passed or was skipped)
if [ "$STATUS" = "success" ]; then
    run_step pre-demo-check "${SCRIPT_DIR}/pre-demo-check.sh" || true
else
    printf -- '- pre-demo-check: SKIPPED (upstream failure)\n' >> "$SUMMARY"
fi

TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$((TOTAL_END - TOTAL_START))

{
    printf '\n## Result\n\n'
    printf -- '- status: **%s**\n' "$STATUS"
    printf -- '- elapsed: %ds\n' "$TOTAL_ELAPSED"
    printf -- '- skip_reset: %s\n' "$SKIP_RESET"
} >> "$SUMMARY"

cat > "$META" <<EOF
{
  "ticket": "CAB-2150",
  "parent": "CAB-2148",
  "timestamp_utc": "${STAMP}",
  "status": "${STATUS}",
  "elapsed_seconds": ${TOTAL_ELAPSED},
  "skip_reset": ${SKIP_RESET},
  "api_url": "${STOA_API_URL:-}",
  "gateway_url": "${STOA_GATEWAY_URL:-}"
}
EOF

printf '\nArtifacts: %s\n' "$ARTIFACT_DIR"
[ "$STATUS" = "success" ] || exit 1
exit 0
