# council-sync-linear

Apply the `council:<namespace>-{go|fix|redo}` label to a Linear issue
and post a completion comment with the Council score + GitHub Actions
run link.

## Use case

The `claude-issue-to-pr` workflow synchronises Council S1 and Plan S2
results back to Linear. The legacy workflow carries two near-identical
~80-line bash blocks that only differ in the label namespace. This
composite replaces both with a single invocation plus a `namespace`
input.

## Contract

### Inputs

| Input            | Required | Default | Description |
|------------------|----------|---------|-------------|
| `ticket-id`      | no       | `""`    | Linear ticket id; auto-extracted from title+body when empty. |
| `issue-title`    | no       | `""`    | Used for ticket-id extraction. |
| `issue-body`     | no       | `""`    | Used for ticket-id extraction. |
| `namespace`      | yes      | —       | `ticket` (S1) or `plan` (S2). |
| `score`          | yes      | —       | Council score as a float string. |
| `run-url`        | yes      | —       | Permalink of the current Actions run. |
| `linear-api-key` | yes      | —       | Linear token; empty => skip. |

### Outputs

| Output            | Description                                            |
|-------------------|--------------------------------------------------------|
| `applied-label`   | Label actually applied, or empty on skip.              |
| `skipped`         | `"true"` if nothing was applied.                       |
| `skipped-reason`  | `no_api_key` / `ticket_not_found` / `label_not_found` / `script_error`. |

## Dependencies

- `scripts/ci/linear_apply_label.py` (Phase 2a, stdlib-only).
- `scripts/ci/gh_helpers.sh::extract_ticket_id` for auto-extraction.

## Example

```yaml
- uses: ./.github/actions/council-sync-linear
  with:
    issue-title: ${{ github.event.issue.title }}
    issue-body:  ${{ github.event.issue.body }}
    namespace:   ticket
    score:       ${{ steps.council-run.outputs.score }}
    run-url:     ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
    linear-api-key: ${{ secrets.LINEAR_API_KEY }}
```

## Notes

### Comment body newlines

The legacy bash wrote `"…text\\n[link](url)"` — the `\n` travelled as
a literal backslash-n through bash interpolation and landed in the
curl JSON payload unescaped, where Linear's JSON parser decoded it as
a real newline. The new Python script expects **real newlines** in its
`--comment-body` argument. This composite builds the body with `$'\n'`
bash ANSI quoting, so the rendered Linear comment is identical to what
the legacy produced.

### Failure modes

The step never fails the job, even on Linear 5xx — it downgrades to
`skipped=true` with an appropriate `skipped-reason`. This mirrors the
legacy `continue-on-error: true` on the equivalent step.

### GraphQL surface

The underlying script preserves verbatim the GraphQL queries the
legacy workflow sends (`issueSearch(filter:)`, `issueLabels(filter:)`,
etc.). Modernising the queries is explicitly out of scope for CI-1
(see §K of the rewrite plan) and will be picked up by CI-2 or a later
iteration once behavioural parity is confirmed.
