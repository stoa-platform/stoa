# hegemon-state-push

Push a session / milestone / cleanup event to the HEGEMON PocketBase
state store.

## Use case

AI-Factory runs publish their lifecycle (session started, milestone
reached, session cleaned up) to an external PocketBase instance so an
external dashboard (and other instances) can observe the state of all
concurrent Claude runs. The legacy `claude-issue-to-pr` workflow calls
three different helper functions (`push_state_session`,
`push_state_milestone`, `push_state_cleanup`) from inline steps; this
composite selects the right one via an `action` input.

## Contract

### Inputs

| Input              | Required | Default | Description |
|--------------------|----------|---------|-------------|
| `action`           | yes      | —       | `session-start` / `milestone` / `cleanup`. |
| `instance`         | yes      | —       | Opaque instance id. |
| `ticket`           | conditional | `""` | Required for session-start and milestone. |
| `step`             | conditional | `""` | Step / milestone label. Required for session-start and milestone. |
| `branch`           | no       | `""`    | session-start only. |
| `pr-num`           | no       | `""`    | session-start / milestone. |
| `sha`              | no       | `""`    | milestone only. |
| `detail`           | no       | `""`    | milestone only. |
| `role`             | no       | `ci`    | session-start only. |
| `source-tag`       | no       | `gha`   | session-start only. |
| `hegemon-url`      | yes      | —       | PocketBase base URL. |
| `hegemon-email`    | yes      | —       | PocketBase user. |
| `hegemon-password` | yes      | —       | PocketBase password. |

### Outputs

None.

## Dependencies

- `scripts/ai-ops/ai-factory-notify.sh` (existing shared helper).
- Network access to the HEGEMON PocketBase host.

## Example

```yaml
- uses: ./.github/actions/hegemon-state-push
  with:
    action:    session-start
    instance:  l1-impl-${{ github.run_id }}
    ticket:    ${{ env.TICKET_ID }}
    step:      implementing
    role:      ci-l1
    source-tag: gha
    hegemon-url:      ${{ secrets.HEGEMON_REMOTE_URL }}
    hegemon-email:    ${{ secrets.HEGEMON_REMOTE_EMAIL }}
    hegemon-password: ${{ secrets.HEGEMON_REMOTE_PASSWORD }}

# …later, after implementation…

- uses: ./.github/actions/hegemon-state-push
  if: always()
  with:
    action:   cleanup
    instance: l1-impl-${{ github.run_id }}
    hegemon-url:      ${{ secrets.HEGEMON_REMOTE_URL }}
    hegemon-email:    ${{ secrets.HEGEMON_REMOTE_EMAIL }}
    hegemon-password: ${{ secrets.HEGEMON_REMOTE_PASSWORD }}
```

## Notes

- The step carries `continue-on-error: true` — HEGEMON unreachable
  never blocks the workflow, matching the legacy behaviour.
- Helper functions authenticate lazily via `_pb_auth()` reading the
  three `HEGEMON_REMOTE_*` env vars; the composite wires them from
  `with:` inputs rather than relying on a workflow-level `env:` block.
