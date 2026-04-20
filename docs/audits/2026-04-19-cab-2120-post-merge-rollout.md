# CAB-2120 Post-Merge Rollout Verification

- UTC timestamp: `2026-04-19T16:02:00Z`
- Local repo: `stoa`
- Local HEAD: `c73fd58b21f23eaf6074c9f3e5d7c24245c57ebe`
- Infra change: `PotoMitan/stoa-infra#45`
- Verification scope: live state after merge and gateway rollout of `STOA_TOOL_EXPANSION_MODE=per-op`

## Verdict

`PARTIAL GO`

The prod gateway rollout for `per-op` is live and verified.

What is confirmed:

- new gateway pods are running
- the deployment now injects `STOA_TOOL_EXPANSION_MODE=per-op`
- the rollout completed successfully

What is still missing:

- authenticated `tools/list` with a real `stoa-demo` JWT
- authenticated invoke of `get-customer-by-number`

`CAB-2120` is therefore **not closed yet**, but the deployment-side blocker is lifted.

## Independently verified live evidence

### 1. Gateway rollout

Observed live pods:

- `stoa-gateway-59b7f479c6-57vsp` — `Running`, `0` restarts
- `stoa-gateway-59b7f479c6-zkwl6` — `Running`, `0` restarts

Rollout status:

```text
deployment "stoa-gateway" successfully rolled out
```

### 2. Deployment env injection

The live deployment now includes:

```text
STOA_TOOL_EXPANSION_MODE=per-op
```

This confirms the chart change is no longer just in Git; it is present in the running deployment spec.

### 3. Live gateway image

Current deployed image:

```text
ghcr.io/stoa-platform/stoa-gateway:dev-cd9941741c234f3b6fd0b6bde4afad480615aa27
```

This is consistent with the CAB-2113 code path previously identified.

## Operator-reported but not independently re-verified in this pass

The following signal was reported by the operator run after merge:

- gateway logs include:
  - `"API catalog tools registered","count":74,"mode":"PerOp"`
  - followed by a warning fallback:
    - `"No expanded tools found for gateway — falling back to unfiltered catalog"`
    - `gateway_id="c97f041a-7916-4508-85cf-4e8bed8bf965"`

I did not independently re-capture this log line in this pass.

Interpretation if accurate:

- `per-op` is active
- gateway-scoped expansion may be empty for this gateway id
- fallback still serves expanded tools from the unfiltered catalog
- this is a follow-up concern, not yet proof of demo failure

## Current blocking condition

The remaining blocker is now purely **audience-path verification**:

1. get a real `stoa-demo` JWT
2. run authenticated `tools/list`
3. run authenticated invoke of `get-customer-by-number` with `CUST-2026-0001`

Until that happens:

- deployment status = green
- demo path status = partial

## Next step

Run these checks immediately with a real `stoa-demo` token:

1. authenticated `GET /mcp/v1/tools`
2. authenticated invoke of `get-customer-by-number`

Decision rule:

- `tools/list` green + invoke green -> `CAB-2120` can move toward done
- `tools/list` green + invoke fails upstream -> investigate upstream/auth path, not chart wiring
- `tools/list` missing expected tool -> investigate the fallback warning / gateway assignment path
