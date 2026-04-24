#!/usr/bin/env bash
# Poll an issue until a label appears (with optional fallback comment).
#
# Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.6 and C.2). Extracts
# the 31-line polling loop of the `implement` job step "Verify Plan
# validation" in .github/workflows/claude-issue-to-pr.yml, preserving
# the race-protection behaviour without attempting to fix the
# root-cause ordering of label/comment in the plan-validate job (per
# decision K3 of the plan, fix ordering is explicitly out of scope).
#
# Usage:
#   wait_for_label.sh <issue-number> <label-name>
#                     [<max-attempts>=10] [<interval-seconds>=30]
#                     [<fallback-comment-pattern>]
#
# Behaviour:
#   - Polls `gh issue view --json labels --jq '.labels[].name'` each
#     attempt and succeeds if the label is present.
#   - If <fallback-comment-pattern> is given (e.g. "Plan Score"), also
#     polls `gh issue view --json comments` and succeeds if any
#     comment body contains the pattern. This mirrors the legacy
#     fallback that tolerates a race between posting a comment and
#     applying a label.
#   - Emits `::notice::` lines between attempts, `::error::` on
#     timeout, and always prints a final `validated=true|false` line
#     to stdout.
#   - Appends `validated=<bool>` to $GITHUB_OUTPUT if the env var is
#     set (GitHub Actions composite convenience).
#   - Exit 0 on validated, 1 on timeout, 2 on bad args.
#
# Test hooks:
#   GH   — path to gh binary (default: gh)
#   SLEEP — path to sleep binary (default: sleep); tests pass `true`.

set -uo pipefail

: "${GH:=gh}"
: "${SLEEP:=sleep}"

_emit_output() {
    local value="$1"
    printf 'validated=%s\n' "$value"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
        printf 'validated=%s\n' "$value" >> "$GITHUB_OUTPUT"
    fi
}

wait_for_label() {
    local issue_num="${1:-}"
    local label_name="${2:-}"
    local max_attempts="${3:-10}"
    local interval="${4:-30}"
    local fallback_pattern="${5:-}"

    if [ -z "$issue_num" ] || [ -z "$label_name" ]; then
        echo "wait_for_label: usage: wait_for_label <issue> <label> [max] [interval] [fallback]" >&2
        return 2
    fi

    local attempt
    for attempt in $(seq 1 "$max_attempts"); do
        local labels
        labels=$("$GH" issue view "$issue_num" --json labels --jq '.labels[].name' 2>/dev/null || true)
        if printf '%s\n' "$labels" | grep -Fxq "$label_name"; then
            echo "$label_name found on issue $issue_num (attempt ${attempt}/${max_attempts})"
            _emit_output "true"
            return 0
        fi

        if [ -n "$fallback_pattern" ]; then
            local count
            # Pipe gh's raw JSON to external jq with --arg so the pattern
            # is bound as a string variable rather than interpolated
            # into the filter body (Council S3 finding A2: bash string
            # interpolation into a jq filter is a jq-injection surface
            # if the pattern ever carries quotes or special chars).
            count=$("$GH" issue view "$issue_num" --json comments 2>/dev/null \
                | jq --arg p "$fallback_pattern" \
                    '[.comments[].body | select(contains($p))] | length' \
                2>/dev/null || echo 0)
            if [ "${count:-0}" -gt 0 ] 2>/dev/null; then
                echo "fallback comment '${fallback_pattern}' found on issue $issue_num (attempt ${attempt}/${max_attempts})"
                _emit_output "true"
                return 0
            fi
        fi

        if [ "$attempt" -lt "$max_attempts" ]; then
            echo "::notice::${label_name} not found yet (attempt ${attempt}/${max_attempts}). Waiting ${interval}s..."
            "$SLEEP" "$interval"
        fi
    done

    local total=$((max_attempts * interval))
    echo "::error::Timed out waiting for ${label_name} on issue ${issue_num} after ${max_attempts} attempts (~${total}s)."
    _emit_output "false"
    return 1
}

# Allow direct invocation.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    wait_for_label "$@"
    exit $?
fi
