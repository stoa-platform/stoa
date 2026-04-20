# CAB-2120 Rollout Verification

- UTC timestamp: `2026-04-19T15:54:46Z`
- Local repo: `stoa`
- Local HEAD: `c73fd58b21f23eaf6074c9f3e5d7c24245c57ebe`
- Target infra PR: `PotoMitan/stoa-infra#45`
- Verification scope: post-PR live state of the prod gateway rollout for `STOA_TOOL_EXPANSION_MODE=per-op`

## Verdict

`BLOCKED`

The runtime verification cannot proceed yet because the infra change is **not deployed**:

- PR `#45` is still `open`
- `merged=false`
- the live deployment does **not** expose `STOA_TOOL_EXPANSION_MODE`
- the gateway is still serving the pre-change coarse tool shape

This is a deployment-state blocker, not a runtime failure of the `per-op` path.

## Evidence

### 1. Infra PR status

GitHub state at verification time:

- PR: `https://github.com/PotoMitan/stoa-infra/pull/45`
- state: `open`
- merged: `false`
- mergeable: `true`
- head SHA: `4c98d6a459f2645f7d023892d3767c36c460ff70`

### 2. Live gateway deployment

Observed live deployment state:

- rollout status: `deployment "stoa-gateway" successfully rolled out`
- deployment generation: `486`
- observedGeneration: `486`
- image: `ghcr.io/stoa-platform/stoa-gateway:dev-cd9941741c234f3b6fd0b6bde4afad480615aa27`

Targeted deployment inspection shows no injected `STOA_TOOL_EXPANSION_MODE` env var. The only matching deployment snippet found was the image line:

```text
132:        image: ghcr.io/stoa-platform/stoa-gateway:dev-cd9941741c234f3b6fd0b6bde4afad480615aa27
```

### 3. Live gateway pods

Current pods at verification time:

- `stoa-gateway-fcdd94774-mqllz` — `Running`, `0` restarts
- `stoa-gateway-fcdd94774-rf246` — `Running`, `0` restarts

This confirms the gateway is healthy, but it does **not** confirm the `per-op` overlay was applied.

### 4. Current tool shape on the public MCP endpoint

Anonymous `GET https://mcp.gostoa.dev/mcp/v1/tools` still exposes coarse banking/catalog entries such as:

- `banking-services-v1-2`
- `customer-360-api`

No `get-customer-by-number` name was observed during this verification pass.

This is consistent with the gateway still serving the pre-flip coarse expansion mode.

## What was intentionally not attempted

Authenticated checks were **not** executed in this pass:

- authenticated `tools/list`
- invoke `get-customer-by-number`

Reason:

- PR `#45` is not merged yet, so the rollout target state is absent
- running auth-dependent checks now would only reconfirm the old state and muddy the report

## Operational conclusion

The next valid step is:

1. merge `PotoMitan/stoa-infra#45`
2. allow ArgoCD to sync the `stoa-gateway` application
3. re-run verification in this order:
   - confirm `STOA_TOOL_EXPANSION_MODE=per-op` is injected
   - check rollout health
   - authenticated `tools/list`
   - authenticated invoke `get-customer-by-number`

## Go / No-Go

- `NO-GO` for claiming CAB-2120 is fixed
- `GO` to merge PR `#45` and continue with post-rollout verification immediately after sync
