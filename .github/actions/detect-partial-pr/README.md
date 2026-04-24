# detect-partial-pr

Find a Pull Request opened by an AI-Factory run for a given issue,
even when the run itself failed (partial success) — with a
false-positive guard.

## Use case

The `implement` job of `claude-issue-to-pr` is allowed to fail (the
Claude action may hit its `max_turns` budget). Before declaring the
run a total loss, the workflow searches for a PR that Claude might
have opened partway through. This composite factors out the 42-line
inline bash that does the search with the critical guard: the PR
branch name or title must contain the ticket id or `issue-${N}`, to
avoid matching unrelated PRs that happen to mention the search term.

## Contract

### Inputs

| Input          | Required | Default | Description |
|----------------|----------|---------|-------------|
| `issue-number` | yes      | —       | Issue the run targeted. |
| `ticket-id`    | no       | `""`    | Tightens the search; auto-extracted when empty. |
| `issue-title`  | no       | `""`    | Used for auto-extraction. |
| `issue-body`   | no       | `""`    | Used for auto-extraction. |
| `github-token` | yes      | —       | Token with `pull-requests:read`. |

### Outputs

| Output     | Description                                       |
|------------|---------------------------------------------------|
| `pr-found` | `"true"` on match, `"false"` otherwise.           |
| `pr-num`   | PR number (empty string when no match).           |
| `pr-url`   | PR URL.                                           |
| `pr-state` | `OPEN` / `MERGED` / `CLOSED`.                     |

## Dependencies

- `scripts/ci/detect_pr_for_issue.py` (Phase 2a).
- `scripts/ci/gh_helpers.sh::extract_ticket_id`.
- `gh` CLI, pre-installed on runners.

## Example

```yaml
- uses: ./.github/actions/detect-partial-pr
  id: detect
  if: always()   # still run even if the Claude action failed
  with:
    issue-number: ${{ github.event.issue.number }}
    issue-title:  ${{ github.event.issue.title }}
    issue-body:   ${{ github.event.issue.body }}
    github-token: ${{ github.token }}

- name: Notify partial success
  if: steps.implement.outcome == 'failure' && steps.detect.outputs.pr-found == 'true'
  run: |
    echo "Claude hit max_turns but opened PR #${{ steps.detect.outputs.pr-num }}"
```

## Notes

The false-positive guard is deliberately strict: a PR matches only if
its `headRefName` **or** `title` contains the ticket id or
`issue-${N}` (case-insensitive). If neither matches, the composite
emits `pr-found=false` and a `::warning::` noting the rejected
candidate.

The step returns `pr-found=false` on any error from the underlying
script — it never fails the calling job.
