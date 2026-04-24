# council-run

Invoke `anthropics/claude-code-action@v1` with a Council prompt and
parse the raw execution output into structured score / verdict / mode
/ estimate fields.

## Use case

Both the `council-validate` (S1) and `plan-validate` (S2) jobs of
`claude-issue-to-pr` invoke the same shape: feed Claude a prompt,
let it write a Markdown report with a "Council Score: X/10" line,
then downstream steps `grep` the execution JSON for that score. This
composite factors out the invocation + parsing so the caller only
passes the prompt and reads structured outputs.

## Contract

### Inputs

| Input                    | Required | Default                | Description |
|--------------------------|----------|------------------------|-------------|
| `stage`                  | yes      | —                      | `s1` (pertinence) or `s2` (plan). Changes the primary regex used by the parser. |
| `prompt`                 | yes      | —                      | Full Council prompt (caller inlines issue title/body). |
| `anthropic-api-key`      | yes      | —                      | Anthropic API key. |
| `model`                  | no       | `claude-sonnet-4-6`    | Claude model id. |
| `max-turns`              | no       | `5`                    | Turn budget for the Council agent. |
| `allowed-tools`          | no       | `Bash,Read,Glob,Grep`  | Tools permitted for the Council agent. |
| `fallback-comment-file`  | no       | `""`                   | Markdown file parsed if the execution output is missing. |

### Outputs

| Output             | Description |
|--------------------|-------------|
| `outcome`          | `success` / `failure` from the inner claude-code-action step. |
| `execution-file`   | Resolved path to `claude-execution-output.json`. |
| `score`            | Council score as a float string (`""` when absent). |
| `verdict`          | `go` / `fix` / `redo` / `""` (derived from score). |
| `mode`             | `ship` / `show` / `ask` (default `ask`). |
| `estimate-points`  | Integer as string (default `0`). |
| `source`           | `structured_json` / `regex` / `fallback` — where the values came from. |

## Dependencies

- `anthropics/claude-code-action@v1` (pinned to commit
  `e58dfa55559035499a4982426bb73605e8b5ad8e`).
- `scripts/ci/parse_council_report.py` (Phase 2a).
- Python 3 interpreter on the runner (pre-installed on
  `ubuntu-latest`).

## Example

```yaml
- uses: ./.github/actions/council-run
  id: council
  with:
    stage: s1
    prompt: |
      You are the STOA Council Gate (Stage 1 — Ticket Pertinence).
      Issue title: ${{ github.event.issue.title }}
      Issue body:  ${{ github.event.issue.body }}
      …
    anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
    model: claude-sonnet-4-6
    max-turns: 5

- name: Fan out based on verdict
  run: echo "verdict=${{ steps.council.outputs.verdict }} score=${{ steps.council.outputs.score }}"
```

## Notes

### `continue-on-error: true` preserved

The inner `anthropics/claude-code-action` step runs with
`continue-on-error: true` on purpose — even a `failure` outcome
(max_turns hit, transient infra error) may have produced a partially
useful execution file. Downstream steps inspect `outcome` and the
parsed fields separately; the caller is expected to decide whether to
treat `failure` as a hard stop or a partial success. This matches the
legacy workflow behaviour.

### Parsing order

The parser tries, in order:

1. A fenced ` ```json { … "score": … } ``` ` block in the assistant
   text — the new "structured contract" any future Council prompt can
   opt into.
2. Legacy regex: `Council Score: X/10` for s1, `Plan Score: X/10`
   (then fallback generic `Score: X/10`) for s2.
3. If the execution file is absent and `fallback-comment-file` is set,
   re-runs 1–2 against that file.

See `source` output for which path produced the values.

### Pinning policy

The third-party action is pinned to its commit SHA per decision K2 of
the rewrite plan: new composites consume actions at a fixed commit to
avoid version drift during the CI-1 rollout. The legacy workflow
continues to use `@v1` (floating tag) until CI-2 aligns the whole
repo.
