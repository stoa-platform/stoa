# council-notify-slack

Post a Council Stage 1 report to Slack, react with the `:mag:` emoji,
and push verdict metrics to the Prometheus Pushgateway.

## Scope

This composite targets **Stage 1** (`council-validate` job —
`notify_council`). Stage 2 uses `notify_plan`, which takes a different
signature (status-driven, no score) and is kept as an inline step in
the v2 workflow per rewrite plan §D.2 (one call, little logic).

## Contract

### Inputs

| Input              | Required | Default          | Description |
|--------------------|----------|------------------|-------------|
| `ticket`           | yes      | —                | Linear id or fallback. |
| `issue-title`      | yes      | —                | GitHub issue title. |
| `issue-url`        | yes      | —                | Permalink to the issue. |
| `issue-number`     | yes      | —                | GitHub issue number. |
| `score`            | yes      | —                | Council score; empty renders `"?"`. |
| `verdict`          | yes      | —                | `go` / `fix` / `redo` (any case). |
| `mode`             | no       | `""`             | Ship/Show/Ask classification for the Slack card. |
| `slack-webhook`    | yes      | —                | Slack incoming webhook URL. |
| `slack-bot-token`  | yes      | —                | Slack Bot API token. |
| `slack-channel-id` | yes      | —                | Slack channel id. |
| `pushgateway-url`  | yes      | —                | Prometheus Pushgateway URL. |
| `pushgateway-auth` | yes      | —                | Pushgateway basic-auth credential. |
| `workflow-label`   | no       | `issue-to-pr`    | Metric label `workflow="..."`. |

### Outputs

| Output     | Description                                                    |
|------------|----------------------------------------------------------------|
| `slack-ts` | Slack message timestamp (used by callers that want to thread). |

## Dependencies

- `scripts/ai-ops/ai-factory-notify.sh::notify_council`,
  `push_metrics_council`, `_react_slack`.
- Network access to Slack and the Pushgateway.

## Example

```yaml
- uses: ./.github/actions/council-notify-slack
  if: always()
  with:
    ticket:         ${{ env.TICKET_ID }}
    issue-title:    ${{ github.event.issue.title }}
    issue-url:      ${{ github.event.issue.html_url }}
    issue-number:   ${{ github.event.issue.number }}
    score:          ${{ steps.council.outputs.score }}
    verdict:        ${{ steps.council.outputs.verdict }}
    mode:           ${{ steps.council.outputs.mode }}
    slack-webhook:  ${{ secrets.SLACK_WEBHOOK_URL }}
    slack-bot-token: ${{ secrets.SLACK_BOT_TOKEN }}
    slack-channel-id: ${{ secrets.SLACK_CHANNEL_ID }}
    pushgateway-url:  ${{ vars.PUSHGATEWAY_URL }}
    pushgateway-auth: ${{ secrets.PUSHGATEWAY_AUTH }}
```

## Notes

- `score` is rendered as `"?"` in the Slack card when empty (legacy
  behaviour) and as `0` in the Pushgateway metric (legacy default).
- `verdict` is accepted in any case: the composite displays it
  title-case in the Slack card (`Go` / `Fix` / `Redo`) and lowers it
  for the metric value. An unknown verdict defaults to `Go` to match
  the legacy fallback that never left the card blank.
- Every helper invocation uses `|| true` — Slack or Pushgateway
  unreachable never fails the calling job.
- Secrets are passed via `with:` inputs to keep them out of the
  workflow-level `env:` block per the Phase 2b hygiene rule.
