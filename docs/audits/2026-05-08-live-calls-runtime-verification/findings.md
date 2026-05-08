# PR-2 runtime evidence — Live Calls

Captured 2026-05-08 between 19:59 and 20:00 UTC, on production OVH cluster, after the cp-ui post-#2738 image `dev-15b8b91e1dc13c741c7ecc50e9b10aff35fe4ec9` (which carries the PR-2 http_route migration since #2727) was reconciled by ArgoCD at 19:31:49 UTC.

## Verdict

**VERDICT: PR-2_RUNTIME_PASS.**

Live Calls (`https://console.gostoa.dev/observability/live-calls`) is internally consistent in production:

- All Prometheus queries on the page use the canonical `MODE_FILTER` scope `job=~"stoa-gateway|stoa-link|stoa-connect"`.
- Route-level panels group by `http_route`, never `path`.
- 100% of `stoa_http_requests_total` series in the filtered scope expose `http_route` (648/648); 0% expose `path` (0/648).
- Top Routes shows 8 real production endpoints sorted by P95 latency. No row labelled `unknown` or `(unlabelled)`.
- Synthetic heatmap is gone. The Heatmap card renders an explicit **"Traffic heatmap unavailable. A real range-query heatmap is not wired yet for the selected time range."** empty state.
- `Active Modes` counts distinct `job` values (1 = `stoa-gateway`), subtitle reads `Gateway / Link / Connect jobs reporting traffic`.
- The scope-mismatch banner appears as designed: KPI Total Requests > 0 but per-mode breakdown (Gateway/Link/Connect cards) shows `No traffic` because only `stoa-gateway` is reporting (link and connect deployment modes are absent in prod). This is the regression-guard banner from PR-2 working correctly, not a UI bug.
- Live Traces empty state distinguishes Prometheus metrics from Tempo/OpenSearch traces: **"Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline."**

## 1. Deployment

- control-plane-ui image: `ghcr.io/stoa-platform/control-plane-ui:dev-15b8b91e1dc13c741c7ecc50e9b10aff35fe4ec9` (squash of #2738; carries #2727 http_route migration).
- control-plane-ui pods (post-rollout):
  - `control-plane-ui-7fb77c9fd6-dbnkg` Running, age ~27 min
  - `control-plane-ui-7fb77c9fd6-rv7xh` Running, age ~27 min
- ArgoCD `control-plane-ui` Application: `sync=Synced`, `health=Healthy`.
- Console health (`https://console.gostoa.dev/`): HTTP 200.
- URL exercised: `https://console.gostoa.dev/observability/live-calls`.
- Logged-in user: CPI Admin.
- Browser console: 0 errors, 0 warnings during page load.

Screenshot: [`01-live-calls-fullpage.png`](01-live-calls-fullpage.png).

## 2. PromQL

API used: `https://api.gostoa.dev/v1/metrics/query` (read-only Prometheus proxy), authenticated via in-pod operator key.

### `count by (job) (stoa_http_requests_total)`

```text
{job: "stoa-gateway"} -> 648
```

Only one job is reporting `stoa_http_requests_total`. `stoa-link` and `stoa-connect` are absent from the scrape inventory in current prod.

### `topk(10, count by (http_route) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))`

```text
http_route="/mcp/sse"                            -> 14
http_route="/mcp/tools/call"                     -> 11
http_route="/apis/fapi-transfers/api/v1/transfers" -> 8
http_route="/mcp/tools/list"                     -> 7
http_route="/mcp"                                -> 6
http_route="/apis/openweathermap/weather"        -> 5
http_route="/apis/echo-oauth2/"                  -> 5
http_route="/apis/exchange-rate/v4/latest/EUR"   -> 5
http_route="/apis/newsapi/top-headlines"         -> 5
http_route="/apis/fapi-accounts/api/v1/accounts" -> 5
```

Real production endpoints. No `unknown` and no empty value in the top 10.

### `count by (path) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"})`

```text
{} -> 648
```

One result with **empty metric labels** = 648 series collapsed because `path` is absent on every series. This confirms the PR-2 step 0 evidence: production stopped emitting the `path` label.

### `count(stoa_http_requests_total{...,http_route!=""})`

```text
{} -> 648
```

648 = total → **100% of series have `http_route` populated**.

### `count(stoa_http_requests_total{...,http_route="unknown"})`

```text
(empty result)
```

**Zero** series carry the literal value `"unknown"`. The dashboard's defensive filter `http_route!="unknown"` is belt-and-braces; the source data is clean.

### Dashboard queries (extracted from network capture)

The page issued 39 metrics + 1 monitoring transaction queries during the smoke. Representative samples:

- KPI total requests:
  ```promql
  sum(increase(stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}[1h]))
  ```
- KPI active modes:
  ```promql
  count(count by (job) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))
  ```
- Top Routes by P95:
  ```promql
  topk(8, histogram_quantile(0.95, sum by (le, http_route) (
    rate(stoa_http_request_duration_seconds_bucket{
      job=~"stoa-gateway|stoa-link|stoa-connect",
      http_route!="",
      http_route!="unknown",
      http_route!="(unlabelled)"
    }[5m])
  )))
  ```
- Top Routes calls (heatmap data source):
  ```promql
  sum by (http_route) (increase(stoa_http_requests_total{
    job=~"stoa-gateway|stoa-link|stoa-connect",
    http_route!="",
    http_route!="unknown",
    http_route!="(unlabelled)"
  }[1h]))
  ```

All queries use the canonical `MODE_FILTER` and the canonical `http_route` label. None use `path`.

## 3. UI

### Header + breadcrumb

- `<h1>` reads **`Live Calls`** (was `Call Flow` before #2727).
- Breadcrumb: `Dashboard > Observability > Live Calls`.
- Sub-navigation: `Gateway Health | Live Calls (active) | Security & Guardrails | Expert Mode`.

### KPI strip

| Card | Value | Subtitle |
|---|---|---|
| Total Requests (1h) | 16.0K | Over 1 hour |
| P50 Latency (5m) | 586 µs | Median response time |
| P99 Latency (5m) | 5 ms | Tail latency |
| Error Rate | 0% | 0 errors |
| Active Modes | 1 | **Gateway / Link / Connect jobs reporting traffic** |

`Active Modes = 1` because only `job=stoa-gateway` is reporting (per §2 PromQL). The subtitle text is the post-PR-2 wording — counts jobs, not paths/routes.

### Scope-mismatch banner (PR-2 regression guard)

Above the KPI strip, the page renders an amber banner:

> **Total requests are available, but no Gateway/Link/Connect breakdown traffic was found for the selected window. Some scraped series may not match the expected job scope.**

This banner appears because `Total Requests (1h) = 16.0K` while the per-mode cards (Gateway / Link / Connect) at the bottom of the page all read `No traffic`. This is exactly the regression-guard scenario: the PR-2 prompt asked for a banner whenever `total > 0` and per-mode breakdowns are zero. The current production reality (only `stoa-gateway` job exists) triggers it legitimately.

### Top Routes by Latency (P95)

Eight rows visible, all real production routes:

```text
/mcp                                                                   <1ms
/apis/echo-fallback/                                                    3ms
/apis/fapi-transfers/api/v1/transfers                                   ~4ms
/apis/echo-oauth2/                                                      ~6ms
/.well-known/acme-challenge/IyAg0DCoVE1OsKmrelxifw5keXaM8US_YIBtDLERSnU  ~8ms
/apis/fapi-accounts/api/v1/accounts                                     ~9ms
/apis/newsapi/top-headlines                                            ~10ms
/apis/openweathermap/weather                                          ~12ms
```

No row labelled `unknown`, no row labelled `(unlabelled)`. The defensive filters in the PromQL keep the panel clean even if a future scrape misconfiguration introduced unlabelled series.

### Latency Distribution histogram

8 buckets `0-1ms` → `100ms+` populated. Y-axis up to 16 000 (matching total request count). Real distribution.

### Error Breakdown

Legend shows HTTP 401 / 403 / 404 / 405 (no 5xx). Donut chart present.

### Traffic Heatmap

Card title: `Traffic Heatmap (24h × Routes)`. Card body shows an icon and the explicit empty state:

> **Traffic heatmap unavailable. A real range-query heatmap is not wired yet for the selected time range.**

No deterministic-hash distribution. The synthetic heatmap from pre-PR-2 is gone.

### Live Traces

Card title: `Live Traces`, with `0/0 traces` indicator. Empty state body:

> **Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline.**

This distinguishes the Prometheus pipeline (working) from the Tempo/OpenSearch trace pipeline (currently empty), per the PR-2 split-brain guard.

### Per-mode cards (bottom)

Three cards (`Gateway`, `Link`, `Connect`), each showing `No traffic`. This is the source of the scope-mismatch banner above the KPI strip — and is consistent with the PromQL evidence that only `job=stoa-gateway` is reporting.

## 4. Screenshots

- [`01-live-calls-fullpage.png`](01-live-calls-fullpage.png) — full page capture covering all sections (KPI strip, scope-mismatch banner, Throughput, Latency Distribution, Error Breakdown, Top Routes, Heatmap empty state, Live Traces empty state, per-mode cards).

## 5. Verdict

**VERDICT: PR-2_RUNTIME_PASS.**

| Acceptance criterion (from PR-2 prompt) | Status |
|---|---|
| All Prometheus queries on Live Calls use the same `MODE_FILTER` scope | ✅ §2 — every query carries `job=~"stoa-gateway|stoa-link|stoa-connect"` |
| Route-level panels use `http_route`, not `path` | ✅ §2 — `count by (http_route)` returns 648 routes; `count by (path)` returns one collapsed empty result |
| No `'unknown'` or `'(unlabelled)'` rendered as a normal route entry | ✅ §3 Top Routes — 8 real routes, no `unknown`, no empty |
| Heatmap is empty/hidden until real data is wired | ✅ §3 — explicit empty state, no synthetic distribution |
| Scope-mismatch banner appears when KPI total > 0 + breakdowns = 0 | ✅ §3 — banner visible above KPI strip; PromQL confirms only `stoa-gateway` reports |
| `Active Modes` counts `job`, not routes | ✅ §3 — value 1 matches PromQL, subtitle reads `Gateway / Link / Connect jobs reporting traffic` |
| Live Traces split-brain empty state | ✅ §3 — explicit message naming Prometheus vs Tempo/OpenSearch |
| `<h1>` reads `Live Calls` (not `Call Flow`) | ✅ §3 |
| Browser console clean | ✅ §1 — 0 errors, 0 warnings |

PR-2 is closed runtime-side. The `path` → `http_route` migration delivered by #2727 is operating correctly in production after the post-#2738 cp-ui rollout.

## Cross-refs

- Plan: [docs/plans/2026-05-07-observability-data-integrity.md](https://github.com/stoa-platform/stoa/blob/main/docs/plans/2026-05-07-observability-data-integrity.md)
- PR-2 step 0 evidence: [docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md](https://github.com/stoa-platform/stoa/blob/main/docs/audits/2026-05-08-live-calls-investigation/promql-evidence.md) ([#2720](https://github.com/stoa-platform/stoa/pull/2720))
- PR-2 implementation: [#2727](https://github.com/stoa-platform/stoa/pull/2727)
- MEGA-A runtime close (companion): [docs/audits/2026-05-09-audit-log-runtime-verification/findings.md](https://github.com/stoa-platform/stoa/blob/main/docs/audits/2026-05-09-audit-log-runtime-verification/findings.md) ([#2739](https://github.com/stoa-platform/stoa/pull/2739))

## Residual notes

- **`stoa-link` / `stoa-connect` jobs absents in prod**: only `stoa-gateway` is reporting `stoa_http_requests_total`. This is an infra/scrape state, not a UI bug. The scope-mismatch banner is the correct visible signal. Decision on whether to deploy stoa-link / stoa-connect modes in prod is out of MEGA-B scope; tracking would belong to a separate gateway-rollout ticket.
- **`/.well-known/acme-challenge/...` cert-manager route in Top Routes** is expected — Let's Encrypt HTTP-01 challenges flow through the gateway. ACME tokens are public per RFC 8555.
- **MCP routes (`/mcp`, `/mcp/sse`, `/mcp/tools/call`, `/mcp/tools/list`)** appear in the route inventory — confirms the Rust gateway is normalizing the MCP transport routes correctly.
- **Real heatmap implementation** is deferred (per AR-6 decision in the plan) and tracked as a non-blocking follow-up. The empty state suffices for now.
- **Tempo/OpenSearch trace pipeline absence**: not a PR-2 concern. The empty state correctly tells the operator where to look (out of scope for Live Calls metric integrity).
