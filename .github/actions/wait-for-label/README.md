# wait-for-label

Poll a GitHub issue until a label (or a fallback comment pattern)
appears. Returns `validated=true` on hit, `validated=false` on timeout.

## Use case

The `implement` job of `claude-issue-to-pr` is triggered by a
`/go-plan` comment but must not start coding until the `plan-validate`
job has finished. Those two jobs talk through labels — but GitHub can
propagate the `/go-plan` comment event and the `plan-validated` label
mutation in either order. This composite reproduces the 10 × 30s
polling loop of the legacy workflow without attempting to fix the
root-cause ordering (out of scope for CI-1 per decision K3).

## Contract

### Inputs

| Input                      | Required | Default | Description |
|----------------------------|----------|---------|-------------|
| `issue-number`             | yes      | —       | GitHub issue number. |
| `label-name`               | yes      | —       | Label that must appear. |
| `max-attempts`             | no       | `10`    | Maximum polling attempts. |
| `interval-seconds`         | no       | `30`    | Seconds between attempts. |
| `fallback-comment-pattern` | no       | `""`    | Optional substring; any comment body containing it triggers success. |
| `github-token`             | yes      | —       | Token with `issues:read`. |

### Outputs

| Output      | Description                                            |
|-------------|--------------------------------------------------------|
| `validated` | `"true"` on hit (label or fallback), `"false"` on timeout. |

The composite does not fail the job on timeout — it emits
`validated=false` and the caller decides how to react (legacy workflow
posts a helpful comment then `exit 1`).

## Dependencies

- `scripts/ci/wait_for_label.sh` (Phase 2a).
- `gh` CLI, pre-installed on GitHub-hosted runners.

## Example

```yaml
- uses: ./.github/actions/wait-for-label
  id: wait
  with:
    issue-number: ${{ github.event.issue.number }}
    label-name: plan-validated
    fallback-comment-pattern: 'Plan Score'
    github-token: ${{ github.token }}

- name: Abort if no plan validation
  if: steps.wait.outputs.validated != 'true'
  run: |
    gh issue comment "${{ github.event.issue.number }}" \
      --body "Implementation requires plan validation (Stage 2)."
    exit 1
```

## Notes

- The underlying script swallows transient `gh` errors inside the
  polling loop — one failed call does not abort the wait.
- Label match is strict (`grep -Fxq`, same as `label-guard`).
- The composite step uses `|| true` so the non-zero exit from the
  script (on timeout) does not automatically fail the job; the
  `validated` output is the authoritative signal.
