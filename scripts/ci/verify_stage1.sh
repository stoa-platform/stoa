#!/usr/bin/env bash
# Verify Stage 1 Council validation by checking the council-validated
# label on a GitHub issue.
#
# CAB-2177: replaces the legacy inline verify-stage1 logic in
# .github/workflows/claude-issue-to-pr.yml (Phase 2d). The legacy
# version scanned issue comments for "Council Score" without any
# freshness guard, so any prior Council comment satisfied the gate —
# including a comment from a verdict-gated run that did NOT apply the
# label, or a comment left behind after a deliberate label removal
# (redo flow). Result: stale evidence permanently validated the issue
# for Stage 2.
#
# Mirror of CAB-2175's pattern (freshness guard on council-run): the
# label is the single source of truth. A Council comment without a
# corresponding `labeled council-validated` event is stale evidence
# by definition — Phase 2d's verdict gate ensures comment + label
# are atomic for valid runs; label removal afterwards is an explicit
# redo signal.
#
# Usage:
#   verify_stage1.sh <issue-number>
#
# Behaviour:
#   - Calls `gh issue view <issue> --json labels --jq '.labels[].name'`.
#   - Outputs `validated=true` if `council-validated` is present
#     (exact match — `council-validated-old` does NOT count), else
#     `validated=false`.
#   - Writes the same line to $GITHUB_OUTPUT if set.
#   - Exit 0 always (gate state is the output value, not the exit
#     code) except on bad args (exit 2). Failures of `gh` are treated
#     as fail-closed (validated=false).
#
# Test hooks:
#   GH — path to gh binary (default: gh).

set -uo pipefail

: "${GH:=gh}"

_emit_output() {
    local value="$1"
    printf 'validated=%s\n' "$value"
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
        printf 'validated=%s\n' "$value" >> "$GITHUB_OUTPUT"
    fi
}

verify_stage1() {
    local issue_num="${1:-}"
    if [ -z "$issue_num" ]; then
        echo "verify_stage1: usage: verify_stage1 <issue-number>" >&2
        return 2
    fi

    local labels
    labels=$("$GH" issue view "$issue_num" --json labels --jq '.labels[].name' 2>/dev/null || true)
    if printf '%s\n' "$labels" | grep -Fxq "council-validated"; then
        echo "Stage 1 confirmed via council-validated label on issue ${issue_num}"
        _emit_output "true"
        return 0
    fi

    echo "::notice::No council-validated label on issue ${issue_num} — Stage 2 plan validation skipped (CAB-2177: comment fallback removed; re-run Stage 1 if needed)"
    _emit_output "false"
    return 0
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    verify_stage1 "$@"
    exit $?
fi
