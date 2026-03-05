# ADR-054: Git Worktree Isolation for Parallel Claude Code Instances

- **Status**: Accepted
- **Date**: 2026-03-05
- **Decision Makers**: Christophe Aboulicam
- **Ticket**: CAB-1676

## Context

STOA's AI Factory runs up to 6 parallel Claude Code instances via `stoa-parallel` (tmux 7-pane layout). Each pane is scoped to a component (BACKEND, FRONTEND, AUTH, MCP, QA) with an ORCHESTRE dispatcher.

**Current architecture**: All panes share the same git working directory (`/Users/torpedo/hlfh-repos/stoa`). Conflict prevention relies on:
- PocketBase claims (prevent two panes from taking the same ticket)
- PreToolUse deny matrix (prevent cross-scope file edits)
- Linear instance labels (route tickets to correct pane)

**Problem**: These mitigations prevent *ticket* collisions but NOT *filesystem* collisions. When two panes run `git checkout` simultaneously:
1. They overwrite each other's `HEAD` (last checkout wins)
2. Uncommitted files from pane A appear in pane B's `git status`
3. `git add` in one pane can accidentally stage another pane's changes
4. `git stash` conflicts across panes

This is a fundamental limitation of sharing a single git working directory across concurrent processes.

## Decision

Adopt `git worktree` to give each Claude Code instance its own isolated working copy of the repository.

### Layout

```
/Users/torpedo/hlfh-repos/stoa           → main (ORCHESTRE — read-only dispatcher)
/Users/torpedo/hlfh-repos/stoa-backend   → worktree (BACKEND instance)
/Users/torpedo/hlfh-repos/stoa-frontend  → worktree (FRONTEND instance)
/Users/torpedo/hlfh-repos/stoa-auth      → worktree (AUTH instance)
/Users/torpedo/hlfh-repos/stoa-mcp       → worktree (MCP instance)
/Users/torpedo/hlfh-repos/stoa-qa        → worktree (QA instance)
```

### Lifecycle

1. **Create**: `stoa-parallel` runs `git worktree add ../stoa-<role> main` for each role on startup
2. **Reuse**: If worktree already exists (idempotent), skip creation
3. **Work**: Each pane `cd` into its worktree, creates feature branches independently
4. **Cleanup**: `stoa-parallel --kill` runs `git worktree remove` for clean worktrees, warns on dirty ones
5. **GC**: `stoa-gc` prunes orphaned worktrees (no tmux session, no uncommitted work)

### Key Properties

- Each worktree has its own `HEAD`, `index`, and working files
- All worktrees share the same `.git/objects` store (no disk duplication)
- `.claude/` rules and hooks are accessible from worktrees (shared via git)
- A branch can only be checked out in ONE worktree at a time (git enforces this)

## Alternatives Considered

### 1. Full Repository Clones

Each pane gets a complete `git clone` of the repo.

- **Pro**: Complete isolation, no shared state
- **Con**: 5x disk usage, 5x fetch time, divergent `.git/objects`, complex sync
- **Rejected**: Overkill — worktrees provide the same isolation with shared objects

### 2. Docker-per-Instance

Each pane runs in a Docker container with its own filesystem.

- **Pro**: Total isolation including system-level
- **Con**: Heavy overhead, complex setup, breaks macOS GUI tools, breaks Homebrew paths
- **Rejected**: Too complex for the problem being solved

### 3. Keep Shared Directory + Stronger Locking

Enhance the claim system to serialize all git operations via a mutex.

- **Pro**: No architecture change
- **Con**: Serializes all git ops (huge performance hit), doesn't solve uncommitted file leakage, fragile
- **Rejected**: Treats symptoms, not root cause

### 4. Stacked Branches (git-branchless / git-town)

Use branch stacking tools to manage parallel development on one worktree.

- **Pro**: Advanced git workflows
- **Con**: Requires all panes to coordinate branch order, doesn't solve concurrent checkout
- **Rejected**: Designed for sequential workflows, not parallel independent agents

## Consequences

### Positive

- **Zero filesystem collisions**: Each pane has independent HEAD/index/working files
- **No behavior change for Claude**: Each instance sees a normal git repo
- **Minimal disk overhead**: Worktrees share `.git/objects` (only working files are duplicated)
- **Idempotent**: `stoa-parallel` can be restarted without losing worktree state
- **Git-native**: Uses built-in git feature, no external tooling

### Negative

- **One branch per worktree constraint**: Git prevents the same branch from being checked out in two worktrees. If two panes need the same branch, one must use a tracking branch.
- **Disk usage**: ~5x working tree files (but NOT 5x `.git/objects`). For stoa (~200MB working tree), this means ~1GB total — acceptable.
- **Worktree cleanup**: Requires explicit cleanup on `--kill`. Orphaned worktrees waste disk until `git worktree prune`.
- **Hook paths**: Hooks that use hardcoded paths must be updated to resolve dynamically via `git rev-parse --show-toplevel`.

### Risks

- **Dropbox interference**: If the repo is in a Dropbox-synced directory, worktrees in sibling directories may also get synced. Mitigation: worktree directories should be in `.gitignore` of the parent or excluded from Dropbox.
- **npm/pip install divergence**: Each worktree has its own `node_modules/` and `.venv/`. First run in a new worktree requires `npm install` / `pip install`. Mitigation: `stoa-parallel` can run installs on creation.

## References

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- Boris Cherny's parallel agent pattern (Claude Code creator)
- CAB-1513: PocketBase shared state for parallel instances
- `.claude/rules/instance-dispatch.md`: Current tmux layout documentation
- `.claude/rules/phase-ownership.md`: Phase claiming protocol (complementary, not replaced)
