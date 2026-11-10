# Required CI probes (CAB-2618)

Scope: criterion 1 of CAB-2612, based on `main` at
`93ed7df1bcb6144ee058eb3c0965aa51437da653`.
The [32-control inventory](controls-truth-inventory.md) retains its dated
2026-11-09 observations. They are not a statement of current service health.

## Enforced checks

| Control | Environment | Required evidence | Failure behavior |
| --- | --- | --- | --- |
| MCP SDK pre-merge | Gateway built from the run's commit on the GitHub runner | Checkout, SDK installation, build, authenticated smoke all executed successfully | Missing, skipped, failed, or cancelled step fails the final guard |
| MCP SDK production | `mcp.gostoa.dev`, read-only probe | DNS, SDK installation, smoke and verdict all executed successfully | Unresolved DNS or unavailable endpoint fails; no service is republished |
| Health smoke | Selected dev/prod target | Explicit target and successful endpoint checks | Missing dev target and unavailable endpoints fail; no fallback to prod |
| GitOps endpoint verification | Selected dev/prod target | Explicit endpoint returns HTTP 200 within the existing deadline | Missing endpoint and timeout fail the verdict |

The last MCP step checks both `outcome` and `conclusion`, so even a failure
masked by `continue-on-error` is rejected. The selected probes force the
required input to true; legacy repository variables cannot disable them.
Deployment kill-switches and job selection by event are unchanged.

States remain distinct: **PASS réel** requires execution; **FAIL** records an
unsuccessful probe; **SKIP** records no execution; **NON VÉRIFIÉ** describes
missing evidence. **NON APPLICABLE** requires an explicit scope decision.
The public MCP service has no retirement decision in this change. An absent
endpoint is therefore not classified as non-applicable.

## Reproduce without deploying

Use the pull request branch and the same commit for both runs:

```bash
gh workflow run mcp-sdk-smoke.yml --ref BRANCH -f target=prod
gh workflow run mcp-sdk-smoke.yml --ref BRANCH -f target=local
```

Wait for the first run before dispatching the second: branch concurrency
cancels an older run. The production run must fail if the expected endpoint
is absent. The local run builds the gateway and executes the authenticated
SDK smoke; it is not evidence of production availability. PR events also
execute that local smoke. Regression tests run in `AI-Factory Scripts Tests`.

Record each run URL, commit, environment, UTC date, job conclusion and smoke
step conclusion in the PR. The original false positive is
[42583971143](https://github.com/stoa-platform/stoa/actions/runs/42583971143)
(2026-11-09, `c4b1ea7bc801b0f6858f1e043ac3c710deae88fb`): job success,
production smoke skipped.

Rollback: revert this PR. That restores the previous permissive probe
behavior. No environment, deployment, DNS or secret change is included.
Other advisory/disabled controls in the inventory are outside this fix;
this PR does not certify all CI or close the CAB-2612 recovery lock.
