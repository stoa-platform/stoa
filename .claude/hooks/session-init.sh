#!/bin/bash
# SessionStart hook: generate session brief from HEGEMON state store.
# Replaces full memory.md + plan.md loading with compact context (~500 tokens).
# Falls back gracefully if state.db doesn't exist or heg-state is unavailable.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BRIEF_FILE="${PROJECT_DIR}/.claude/session-brief.json"
STATE_DB="${HOME}/.hegemon/state.db"

# Resolve heg-state CLI
HEG_STATE="${HOME}/.local/bin/heg-state"
if [ ! -x "$HEG_STATE" ]; then
    HEG_STATE="python3 ${PROJECT_DIR}/hegemon/tools/state/heg_state.py"
fi

# Sync tickets from Linear + generate brief (rate-limited, best-effort)
if [ -f "$STATE_DB" ]; then
    # Only sync if brief is older than 5 minutes (avoid hammering Linear API)
    if [ ! -f "$BRIEF_FILE" ] || [ "$(find "$BRIEF_FILE" -mmin +5 2>/dev/null)" ]; then
        $HEG_STATE ticket-sync --from-linear 2>/dev/null || true
        $HEG_STATE cleanup --stale 2h 2>/dev/null || true
    fi
    $HEG_STATE brief --project stoa > "$BRIEF_FILE" 2>/dev/null || true
fi

# Set instance ID via env file (persists for entire session)
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    INSTANCE_ID="t$(( $(date +%s) % 100000 ))-$(openssl rand -hex 2)"
    echo "STOA_INSTANCE_ID=${INSTANCE_ID}" >> "$CLAUDE_ENV_FILE"
fi

# --- Git hygiene: clean up stale branches/worktrees from previous sessions ---
# Runs early, non-blocking (|| true), ~200ms overhead
(
    cd "$PROJECT_DIR" 2>/dev/null || exit 0

    # Prune stale worktrees
    git worktree prune 2>/dev/null

    # Prune stale remote-tracking references
    git remote prune origin 2>/dev/null

    # Delete local branches already merged into main
    CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
    WT_BRANCHES=$(git worktree list --porcelain 2>/dev/null | grep '^branch ' | sed 's|branch refs/heads/||')

    for branch in $(git branch --merged main 2>/dev/null | sed 's/^[* ]*//' | grep -v '^main$'); do
        [ "$branch" = "$CURRENT_BRANCH" ] && continue
        echo "$WT_BRANCHES" | grep -qx "$branch" && continue
        [[ "$branch" == wt/* ]] && continue
        git branch -d "$branch" 2>/dev/null
    done

    # Delete branches whose remote was deleted (squash-merged PRs)
    for branch in $(git branch --format='%(refname:short) %(upstream:track)' 2>/dev/null | grep '\[gone\]$' | awk '{print $1}'); do
        [ "$branch" = "$CURRENT_BRANCH" ] && continue
        echo "$WT_BRANCHES" | grep -qx "$branch" && continue
        [[ "$branch" == wt/* ]] && continue
        git branch -D "$branch" 2>/dev/null
    done

    # Clean up orphaned agent worktree directories
    for wt_dir in "$PROJECT_DIR/.claude/worktrees"/agent-*; do
        [ -d "$wt_dir" ] || continue
        git worktree list 2>/dev/null | grep -q "$wt_dir" || rm -rf "$wt_dir"
    done
) || true

exit 0
