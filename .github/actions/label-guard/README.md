# label-guard

Check whether a GitHub issue already carries a label, for idempotent
workflow steps.

## Use case

The `claude-issue-to-pr` workflow posts `council-validated`,
`plan-validated`, and `ship-fast-path` labels as handshake signals
between its three jobs. Re-labelling an issue — for example when a
user adds the trigger label a second time, or when the workflow is
re-dispatched manually — would otherwise re-run Council S1. This
composite returns the current label state so the caller can skip.

## Contract

### Inputs

| Input          | Required | Description                                      |
|----------------|----------|--------------------------------------------------|
| `issue-number` | yes      | GitHub issue number.                             |
| `label-name`   | yes      | Exact label name (case-sensitive, full-line).    |
| `github-token` | yes      | Token with `issues:read` scope.                  |

### Outputs

| Output        | Description                                            |
|---------------|--------------------------------------------------------|
| `already-set` | `"true"` if the label is present, `"false"` otherwise. |

## Dependencies

- `scripts/ci/gh_helpers.sh` from the repo (requires the caller to
  have run `actions/checkout` first).
- `gh` CLI, pre-installed on GitHub-hosted runners.

## Example

```yaml
- uses: ./.github/actions/label-guard
  id: guard
  with:
    issue-number: ${{ github.event.issue.number }}
    label-name: council-validated
    github-token: ${{ github.token }}

- name: Run council
  if: steps.guard.outputs.already-set != 'true'
  # ...
```

## Notes

Label matching is strict (fixed-string, full-line match via
`grep -Fxq`). `council-validated-old` would NOT match
`council-validated`. This is stricter than the legacy inline bash
(`grep -q`) but behaves identically for every label used by the
workflow today.
