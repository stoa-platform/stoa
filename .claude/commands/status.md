Quick project status snapshot.

Gather and display:

1. **Git**: current branch, last 3 commits (`git log --oneline -3`), uncommitted changes (`git status --short`)
2. **PRs**: open PRs (`gh pr list --limit 5`)
3. **CI**: last 5 workflow runs on main (`gh run list --branch main --limit 5`)
4. **Pods**: `kubectl get pods -n stoa-system --no-headers` (skip if kubectl unavailable)
5. **Ops log**: last 5 entries from `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/operations.log`
6. **Tokens today**: parse `~/.claude/stats-cache.json` for today's usage

Format as a compact table. One-liner per section. No commentary.
