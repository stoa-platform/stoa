# PR-3 runtime evidence — Security & Guardrails

Captured 2026-05-09 between 07:39 and 07:40 UTC, on production OVH cluster, after:

- **PR-3B1 backend** [stoa#2742](https://github.com/stoa-platform/stoa/pull/2742) merged 05:21 UTC, image `dev-ae52ff9c...` deployed.
- **stoa-infra#76 activation** merged 06:47 UTC, 6 `STOA_GUARDRAILS_*` / `STOA_RATE_LIMIT_ENABLED` / `STOA_POLICY_ENABLED` env vars injected into cp-api pods.
- **PR-3B2 UI** [stoa#2743](https://github.com/stoa-platform/stoa/pull/2743) merged 07:25 UTC, image `dev-97a5ee70e48fe32df0bd60e3e8cf4471fc402e91` reconciled by ArgoCD ~07:35 UTC.

## Verdict

**VERDICT: PR-3_RUNTIME_PASS.**

`/observability/security` renders the AR-1/AR-2-compliant runtime truth in production. The 5-state contract is honoured: the page distinguishes config disabled, healthy+0/N, no-sample, stale, and metrics-unavailable instead of collapsing them into a deceptive `0`. The current production state (config enabled across the board, but Prometheus guardrails counters are not yet populated) is rendered as **"No metrics sample"** on 5 cards — the bug we were protecting against (silent `|| 0`) is gone.

## 1. Deployment

- control-plane-ui image: `ghcr.io/stoa-platform/control-plane-ui:dev-97a5ee70e48fe32df0bd60e3e8cf4471fc402e91` (squash of #2743).
- control-plane-ui pods (post-rollout): 2 × Running, age ~30 s at capture time.
- ArgoCD `control-plane-ui` Application: `sync=Synced`, `health=Healthy`.
- control-plane-api image: `ghcr.io/stoa-platform/control-plane-api:dev-ae52ff9cbcd142eb9965fb22d7a53599398c5f6e` (post-#2742).
- 6 env vars on cp-api pod (verified post-#76 rollout):
  - `STOA_GUARDRAILS_PII_ENABLED=true`
  - `STOA_GUARDRAILS_INJECTION_ENABLED=true`
  - `STOA_PROMPT_GUARD_ENABLED=true`
  - `STOA_GUARDRAILS_CONTENT_FILTER_ENABLED=true`
  - `STOA_RATE_LIMIT_ENABLED=true`
  - `STOA_POLICY_ENABLED=true`
- Console health (`https://console.gostoa.dev/`): HTTP 200.
- URL exercised: `https://console.gostoa.dev/observability/security`.
- Logged-in user: CPI Admin, workspace `aech's workspace` (Keycloak SSO).
- Browser console: 0 errors, 0 warnings during page load.

Screenshots:
- [`01-fullpage-1h.png`](01-fullpage-1h.png) — default 1h time range
- [`02-fullpage-24h.png`](02-fullpage-24h.png) — after time range switched to 24h

## 2. Backend contract live

In-pod curl with operator key:

### `GET /v1/admin/gateways/guardrails/config`

```json
{
  "pii_enabled": true,
  "injection_detection_enabled": true,
  "prompt_guard_enabled": true,
  "content_filter_enabled": true,
  "rate_limit_enabled": true,
  "opa_policy_enabled": true,
  "source": "env",
  "updated_at": "2026-05-09T06:49:12.923678Z"
}
```

HTTP 200. `source=env` confirms #76 activation: env vars are the authority for the config booleans.

### `GET /v1/admin/gateways/metrics?range=1h` (guardrails block)

```json
{
  "guardrails": {
    "pii_detections": null,
    "injection_blocks": null,
    "prompt_guard_blocks": null,
    "content_filter_blocks": null,
    "rate_limit_blocks": null,
    "last_sample_at": null,
    "metrics_age_seconds": null,
    "source_healthy": true
  }
}
```

`source_healthy=true` (Prometheus reachable) but all counters and freshness are `null` (no guardrail metric series populated yet). **The backend correctly preserves `null` instead of returning `0` — the contract holds.**

### `GET /v1/admin/gateways/metrics/guardrails/events?range=1h&limit=50`

HTTP 200, 0 events.

## 3. UI

### Header + AR-1 wording

- `<h1>` reads exactly **`Security & Guardrails`**.
- Subtitle reads exactly **`Runtime events — guardrail decisions, PII/prompt/content/rate-limit monitoring`** — the AR-1 string verbatim.
- Breadcrumb: `Dashboard > Observability > Security & Guardrails`.
- Sub-navigation: `Gateway Health | Live Calls | Security & Guardrails (active) | Expert Mode`.

### Time range selector

- Buttons: `1h / 6h / 24h / 7d`. Default selected: `1h`.
- Click `24h` triggered network requests:
  - `GET /v1/admin/gateways/metrics?range=24h` ✅
  - `GET /v1/admin/gateways/metrics/guardrails/events?range=24h&limit=50` ✅
  - **No re-fetch of `/v1/admin/gateways/guardrails/config`** ✅ — per contract.

### Six guardrail cards

| Card | Rendered | UI state per contract |
|---|---|---|
| PII Detection | `No metrics sample` | enabled + `last_sample_at=null` → **no-sample** |
| Injection Blocks | `No metrics sample` | enabled + `last_sample_at=null` → **no-sample** |
| Prompt Guard | `No metrics sample` | enabled + `last_sample_at=null` → **no-sample** |
| Content Filter | `No metrics sample` | enabled + `last_sample_at=null` → **no-sample** |
| Rate Limit | `No metrics sample` | enabled + `last_sample_at=null` → **no-sample** |
| OPA Policy | `Enabled` | config-only per contract (no metric counter), shows config state |

The 5 cards driven by metrics show the **honest "No metrics sample" state** — the historical bug `metrics?.guardrails?.x \|\| 0` is gone. The UI distinguishes "feature enabled but no Prometheus sample" from "feature returning 0 events" — exactly the precedence rule from the contract.

### Recent Events section

- Header: `Recent Events · 0 events`.
- Body: `No guardrail events in the selected 1h window`.

Honest empty state, no synthetic placeholder.

### Guardrail Configuration section

- Header: `Source: env · Updated 0s ago` — reflects `/guardrails/config` response exactly.
- 6 features all rendered as `Enabled`:
  - PII Detection · Enabled
  - Injection Detection · Enabled
  - Prompt Guard · Enabled
  - Content Filter · Enabled
  - Rate Limit · Enabled
  - OPA Policy · Enabled

This panel is the **runtime config truth** that PR-3A required and PR-3B1+B2+#76 delivered.

### No banner

- No "Audit backend unavailable" / "Source: demo" warning rendered.
- No HTTP error banner.
- `source=env` (not `demo`), `source_healthy=true`, no `warning` field set on any response.

## 4. Network capture

```text
GET /v1/admin/gateways/guardrails/config        => 200 (once on mount)
GET /v1/admin/gateways/metrics?range=1h         => 200 (initial)
GET /v1/admin/gateways/metrics/guardrails/events?limit=50&range=1h => 200 (initial)
GET /v1/admin/gateways/metrics?range=24h        => 200 (after time range switch)
GET /v1/admin/gateways/metrics/guardrails/events?limit=50&range=24h => 200 (after switch)
```

`/guardrails/config` was called **exactly once** on mount and was NOT re-fetched when the time range changed — per the contract section "Time range behavior".

## 5. Verdict

**VERDICT: PR-3_RUNTIME_PASS.**

| Acceptance criterion (from PR-3B2 prompt) | Status |
|---|---|
| h1 = "Security & Guardrails", subtitle = AR-1 wording | ✅ §3 |
| /guardrails/config drives per-card disabled state | ✅ Configuration section shows 6× Enabled with `Source: env` |
| /metrics guardrails block consumed with all freshness fields | ✅ §2 + UI rendered "No metrics sample" using `last_sample_at=null` precedence |
| `null` preserved end-to-end; no `\|\| 0` fallback | ✅ Cards show "No metrics sample" not "0 events" |
| Five UI states visible per the contract precedence | ✅ Currently visible: enabled+no-sample (×5) and config-only (OPA × 1). Other states (disabled, healthy+N, stale, unavailable) are covered by 13 unit tests in `guardrailCardState.test.ts` |
| TimeRangeSelector exists, propagates to metrics endpoints, NOT refetch config | ✅ §3 + §4 |
| Rate Limit card NEVER uses a synthetic `all` filter | ✅ Tests in #2743 + AR-2 contract enforced |
| AR-1 / AR-2 wording exact | ✅ §3 |
| Browser console clean | ✅ 0 errors, 0 warnings |
| Backend returns `source: "env"` (not silent demo) | ✅ §2 |

PR-3 (Security & Guardrails runtime truth) is closed runtime-side. The MEGA-B Phase 2 dependency on PR-3 is met. PR-4 (sidebar IA cleanup) — the last MEGA-B item — can now start, with the AR-1 wording locked in production.

## Cross-references

- Plan: [docs/plans/2026-05-07-observability-data-integrity.md](https://github.com/stoa-platform/stoa/blob/main/docs/plans/2026-05-07-observability-data-integrity.md)
- Contract PR-3A: [docs/plans/2026-05-10-guardrails-runtime-truth-contract.md](https://github.com/stoa-platform/stoa/blob/main/docs/plans/2026-05-10-guardrails-runtime-truth-contract.md) ([#2741](https://github.com/stoa-platform/stoa/pull/2741))
- Backend PR-3B1: [stoa#2742](https://github.com/stoa-platform/stoa/pull/2742)
- UI PR-3B2: [stoa#2743](https://github.com/stoa-platform/stoa/pull/2743)
- Activation A1c (env vars): [stoa-infra#76](https://github.com/PotoMitan/stoa-infra/pull/76)
- AR-1 + AR-2 decisions: inline in plan canon, validated 2026-05-07.

## Residual notes

- **Prometheus guardrail counters are not yet populated**: `pii_detections`, `injection_blocks`, etc. are all `null`. This is not a UI bug; the metric exporters in the gateway are not yet emitting these series. Adding the exporters is a separate work item, **NOT** in scope for MEGA-B observability data integrity. When counters arrive, the UI will automatically transition from "No metrics sample" to "0 events · last sample Xs ago" or "<N> events · last sample Xs ago" without code change.
- **Rate Limit card** shows the contract path correctly — currently in the same `no-sample` state as the others. When `rate_limit_blocks` becomes a real counter, the card will be clickable and will filter the Recent Events table to `rate-limit` action only (test in #2743 confirms the wiring).
- **OPA Policy card** is the one config-only card per contract. It correctly displays `Enabled` straight from the `/guardrails/config` response without expecting a metric counter. If OPA runtime counters are added later, that's a contract change and a new mini-spec — explicitly forbidden in PR-3 per AR-1/AR-2 scope.
- **Console UI tests in #2743** (14 integration + 13 unit on the pure function) cover the states not visible in this current production snapshot (disabled, healthy+N, stale, unavailable). Runtime evidence here proves the no-sample and enabled-config paths; tests cover the rest.
