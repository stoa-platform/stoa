#!/bin/bash
# Stop hook: clean up stale git branches, worktrees, and warn about stash accumulation.
# Runs on every Stop event. Non-blocking (exit 0 always).
# Safe: only deletes branches already merged into main, never force-deletes.

set -o pipefail
REPO_DIR="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -z "$REPO_DIR" ] && exit 0
cd "$REPO_DIR" || exit 0

CLEANED=0
WARNINGS=0

# --- 1. Prune stale worktrees (directories deleted but git refs remain) ---
PRUNED=$(git worktree prune 2>&1)
if [ -n "$PRUNED" ]; then
  echo "GIT CLEANUP: pruned stale worktrees"
  CLEANED=$((CLEANED + 1))
fi

# --- 2. Delete local branches already merged into main ---
# Skip: main, current branch, wt/* (parallel worktree branches), any branch checked out in a worktree
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "")
WORKTREE_BRANCHES=$(git worktree list --porcelain 2>/dev/null | grep '^branch ' | sed 's|branch refs/heads/||')

MERGED_BRANCHES=$(git branch --merged main 2>/dev/null | sed 's/^[* ]*//' | grep -v '^main$')
DELETED_COUNT=0

for branch in $MERGED_BRANCHES; do
  # Skip current branch
  [ "$branch" = "$CURRENT_BRANCH" ] && continue
  # Skip branches checked out in worktrees
  echo "$WORKTREE_BRANCHES" | grep -qx "$branch" && continue
  # Skip wt/* branches (parallel session branches)
  [[ "$branch" == wt/* ]] && continue

  git branch -d "$branch" >/dev/null 2>&1 && DELETED_COUNT=$((DELETED_COUNT + 1))
done

if [ "$DELETED_COUNT" -gt 0 ]; then
  echo "GIT CLEANUP: deleted $DELETED_COUNT merged branch(es)"
  CLEANED=$((CLEANED + DELETED_COUNT))
fi

# --- 2b. Delete branches whose remote was deleted (squash-merged PRs) ---
# These are branches where the remote was deleted after PR merge, but local branch persists.
# Safe: if the remote branch was deleted, the PR was merged or abandoned.
GONE_COUNT=0
for branch in $(git branch --format='%(refname:short) %(upstream:track)' 2>/dev/null | grep '\[gone\]$' | awk '{print $1}'); do
  [ "$branch" = "$CURRENT_BRANCH" ] && continue
  echo "$WORKTREE_BRANCHES" | grep -qx "$branch" && continue
  [[ "$branch" == wt/* ]] && continue
  git branch -D "$branch" >/dev/null 2>&1 && GONE_COUNT=$((GONE_COUNT + 1))
done

if [ "$GONE_COUNT" -gt 0 ]; then
  echo "GIT CLEANUP: deleted $GONE_COUNT branch(es) with deleted remote"
  CLEANED=$((CLEANED + GONE_COUNT))
fi

# --- 2c. Prune stale remote-tracking references ---
git remote prune origin >/dev/null 2>&1

# --- 3. Clean up orphaned agent worktree directories ---
AGENT_WT_DIR="$REPO_DIR/.claude/worktrees"
if [ -d "$AGENT_WT_DIR" ]; then
  ORPHAN_COUNT=0
  for wt_dir in "$AGENT_WT_DIR"/agent-*; do
    [ -d "$wt_dir" ] || continue
    # Check if this worktree is still registered with git
    if ! git worktree list 2>/dev/null | grep -q "$wt_dir"; then
      rm -rf "$wt_dir"
      ORPHAN_COUNT=$((ORPHAN_COUNT + 1))
    fi
  done
  if [ "$ORPHAN_COUNT" -gt 0 ]; then
    echo "GIT CLEANUP: removed $ORPHAN_COUNT orphaned agent worktree dir(s)"
    CLEANED=$((CLEANED + ORPHAN_COUNT))
  fi
fi

# --- 4. Warn about stash accumulation ---
STASH_COUNT=$(git stash list 2>/dev/null | wc -l | tr -d ' ')
if [ "$STASH_COUNT" -gt 10 ]; then
  echo "GIT CLEANUP WARNING: $STASH_COUNT stashes accumulated. Consider: git stash drop (oldest) or git stash clear"
  WARNINGS=$((WARNINGS + 1))
fi

# --- 5. Count remaining unmerged local branches ---
UNMERGED_COUNT=$(git branch --no-merged main 2>/dev/null | wc -l | tr -d ' ')
if [ "$UNMERGED_COUNT" -gt 20 ]; then
  echo "GIT CLEANUP WARNING: $UNMERGED_COUNT unmerged local branches. Review with: git branch --no-merged main"
  WARNINGS=$((WARNINGS + 1))
fi

# --- Summary ---
if [ "$CLEANED" -gt 0 ] || [ "$WARNINGS" -gt 0 ]; then
  echo "GIT CLEANUP: $CLEANED item(s) cleaned, $WARNINGS warning(s)"
fi

exit 0
