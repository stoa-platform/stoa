# write-summary

Write a GitHub Actions Job Summary block for an AI-Factory stage.

## Use case

Each job of `claude-issue-to-pr` ends with a step that appends a small
table to `$GITHUB_STEP_SUMMARY`: ticket link, outcome, duration, model,
run number, and an optional error excerpt. This composite factors out
the call to `scripts/ai-ops/ai-factory-notify.sh::write_job_summary`.

## Contract

### Inputs

| Input              | Required | Default | Description                                |
|--------------------|----------|---------|--------------------------------------------|
| `ticket`           | yes      | —       | Linear ticket id or fallback identifier.   |
| `outcome`          | yes      | —       | `success` / `failure` / `skipped` / `cancelled`. |
| `stage`            | yes      | —       | `council-s1` / `council-s2` / `L1-implement`. |
| `model`            | no       | `""`    | Claude model name rendered in the table.   |
| `pr-num`           | no       | `""`    | Rendered as `#NN` in the PR row if set.    |
| `duration-seconds` | no       | `""`    | Converted to `Xm Ys` by `_format_duration`. |
| `error-excerpt`    | no       | `""`    | Rendered in a fenced block on failure.     |

### Outputs

None — the composite writes to `$GITHUB_STEP_SUMMARY` as a side effect.

## Dependencies

- `scripts/ai-ops/ai-factory-notify.sh` (existing shared helper
  consumed by 10 AI-Factory workflows).
- GitHub Actions runtime must expose `$GITHUB_STEP_SUMMARY` — the
  underlying function no-ops with a `::notice::` when unset.

## Example

```yaml
- uses: ./.github/actions/write-summary
  if: always()
  with:
    ticket: ${{ env.TICKET_ID }}
    outcome: ${{ steps.implement.outcome }}
    stage: L1-implement
    model: ${{ steps.route.outputs.model }}
    duration-seconds: ${{ env.DURATION }}
```
