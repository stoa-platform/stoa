#!/usr/bin/env bash
# Shell helpers for claude-issue-to-pr.yml composite actions.
#
# Phase 2a of CI-1 rewrite (CI-1-REWRITE-PLAN.md B.5). Factors out the
# small bash snippets that are repeated across the workflow: ticket id
# extraction (7 occurrences), label presence check (4), idempotent
# label create (3), add-label on an issue (3).
#
# Usage: source this file from a step or composite action:
#     source "${GITHUB_WORKSPACE:-.}/scripts/ci/gh_helpers.sh"
#
# Every gh invocation goes through the ${GH:-gh} variable so tests can
# inject a fake binary on PATH without patching the functions.

set -uo pipefail  # no -e on purpose: callers use `if has_label ...`

# Path to the gh binary. Tests override via env GH=/tmp/fake-gh.
: "${GH:=gh}"

# extract_ticket_id "<text>"
# Echoes the first CAB-NNNN token found, or the empty string.
# Always exits 0.
extract_ticket_id() {
    local text="${1:-}"
    local match
    match=$(printf '%s' "$text" | grep -oE 'CAB-[0-9]+' | head -1 || true)
    printf '%s' "$match"
}

# has_label <issue-number> <label-name>
# Exit 0 if the issue carries the label, 1 otherwise, 2 on bad args.
has_label() {
    if [ "$#" -lt 2 ]; then
        echo "has_label: usage: has_label <issue-number> <label-name>" >&2
        return 2
    fi
    local issue_num="$1"
    local label_name="$2"
    local labels
    labels=$("$GH" issue view "$issue_num" --json labels --jq '.labels[].name' 2>/dev/null || true)
    # grep -Fx: fixed-string + full-line match, safe for labels containing : or -
    if printf '%s\n' "$labels" | grep -Fxq "$label_name"; then
        return 0
    fi
    return 1
}

# ensure_label <label-name> <color-hex> <description>
# Idempotent: runs `gh label create --force`, swallows "already exists".
# Exit 0 on success, non-zero on gh failure.
ensure_label() {
    if [ "$#" -lt 3 ]; then
        echo "ensure_label: usage: ensure_label <name> <color> <description>" >&2
        return 2
    fi
    local name="$1"
    local color="$2"
    local description="$3"
    "$GH" label create "$name" \
        --color "$color" \
        --description "$description" \
        --force >/dev/null 2>&1 || return 0
}

# add_label <issue-number> <label-name>
# Adds the label to the issue. Uses `gh issue edit --add-label`,
# which is idempotent: adding an already-present label is a no-op.
add_label() {
    if [ "$#" -lt 2 ]; then
        echo "add_label: usage: add_label <issue-number> <label-name>" >&2
        return 2
    fi
    local issue_num="$1"
    local label_name="$2"
    "$GH" issue edit "$issue_num" --add-label "$label_name" >/dev/null
}

# If sourced, do nothing. If executed directly, print usage.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    cat <<'EOF'
gh_helpers.sh — source this file, do not execute.

Example:
    source scripts/ci/gh_helpers.sh
    TICKET=$(extract_ticket_id "$ISSUE_TITLE $ISSUE_BODY")
    if has_label "$ISSUE_NUM" "council-validated"; then ...; fi
    ensure_label "council-validated" "0e8a16" "Council validation passed"
    add_label "$ISSUE_NUM" "council-validated"
EOF
    exit 0
fi
