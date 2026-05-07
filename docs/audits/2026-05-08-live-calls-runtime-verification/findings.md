# PR-2 Live Calls — `http_route` runtime verification

Date: 2026-05-08
Scope: post-merge runtime evidence pack for PR #2727
(`fix(ui): align live calls metrics on http_route`, squash `87b1a4f9`).
Method: kubectl + curl + Prometheus HTTP API queries from inside `stoa-system`
via `kubectl exec` on the live `stoa-control-plane-api` pod.

---

## 1. Deployment evidence

| Item | Value |
|---|---|
| Stoa squash commit on `main` | `87b1a4f93c00cd852e6bedee16ef11c9ba8cc20b` |
| stoa-infra image-bump commit | `4bb7507545…` ("chore(control-plane-ui): update image tag to dev-87b1a4f93c00…") |
| ArgoCD app `control-plane-ui` synced revision | `4bb7507545…` |
| ArgoCD `control-plane-ui` sync / health | `Synced` / `Healthy` |
| ArgoCD apps overall | 15/15 `Synced` + `Healthy` |
| Live `control-plane-ui` deployment image | `ghcr.io/stoa-platform/control-plane-ui:dev-87b1a4f93c00cd852e6bedee16ef11c9ba8cc20b` |
| Pods | `control-plane-ui-9b57596b9-mb6vn` (Running, 0 restarts) and `control-plane-ui-9b57596b9-p775g` (Running, 0 restarts), old `54fc966d8f-*` ReplicaSet terminated |
| `https://api.gostoa.dev/health` | `200` |
| `https://mcp.gostoa.dev/health` | `200` |
| `https://console.gostoa.dev` | `200` |
| `https://portal.gostoa.dev` | `200` |
| Cluster | OVH MKS GRA9, namespace `stoa-system`, kubeconfig context `ovh-prod` |

CI on `main` for `87b1a4f9`:

| Check | Status |
|---|---|
| Required Checks | success |
| Release Please | success |
| Security Scan | success |
| OpenSSF Scorecard | success |
| Control Plane UI CI/CD (Build, Docker, GitOps Deploy, Smoke, Notify) | success |
| E2E Tests | in progress (not required, flake-tolerant per CLAUDE.md) |

---

## 2. UI evidence on `/observability/live-calls`

The runtime UI assertions below are validated by **a combination of**:
- the deployed image SHA (`dev-87b1a4f93c00…`) matching PR #2727 squash commit (`87b1a4f9`);
- the source code at that commit, which mechanically constrains the UI behavior;
- the live PromQL evidence in section 3 (which determines which UI branch will be hit).

Authenticated headless screenshots of the Console UI at
`https://console.gostoa.dev/observability/live-calls` were not captured in this
pack (Keycloak SSO required). The UI assertions are therefore code-level +
data-level; section 4 lists what can be added with an authenticated browser
session.

| Assertion | How it is enforced | Status on prod |
|---|---|---|
| `h1` is `Live Calls` | `control-plane-ui/src/pages/CallFlow/CallFlowDashboard.tsx` (page header in `87b1a4f9`) | PASS (image SHA confirmed) |
| Route panels do not render `unknown` as a normal route | `metrics.ts::ROUTE_LABEL_FILTER` adds `http_route!="unknown"` server-side; `filterRenderableRoutes` in `components/TopRoutes.tsx` strips client-side. PromQL §3.5 confirms 0 series have `http_route="unknown"` | PASS |
| Route panels do not render `(unlabelled)` as a normal route | Same dual filter (server PromQL + UI `filterRenderableRoutes`). PromQL §3.5 confirms 0 series have `http_route="(unlabelled)"` | PASS |
| Route panels do not render empty `http_route` | PromQL filter `http_route!=""`. PromQL §3.5 confirms 0 series have `http_route=""` | PASS |
| Top Routes shows valid `http_route` rows | PromQL §3.3 returns 8 distinct real `http_route` values (e.g. `/mcp`, `/mcp/tools/call`, `/apis/exchange-rate/v4/latest/EUR`) | PASS |
| Top Routes EmptyState shown only when no usable label | `TopRoutes.tsx:38-46` returns `ROUTE_LABELS_UNAVAILABLE_MESSAGE` only if `routes.length>0 && filterRenderableRoutes is empty`; otherwise `'No route data available'` | PASS (real routes available) |
| Traffic Heatmap no longer shows synthetic / hash / business-hours data | `CallFlowDashboard.tsx` `heatmapCells = useMemo(() => ({ cells: [], routes: [] }), [])`; old hash + `businessHour` block removed (verified in PR #2727 diff) | PASS |
| Heatmap shows the unavailable EmptyState until real `query_range` is wired | `TrafficHeatmap.tsx:40-42` returns `HEATMAP_UNAVAILABLE_MESSAGE` when `cells.length===0 || routes.length===0` | PASS |
| Active Modes does not count routes | `metrics.ts::activeModes = count(count by (job) (stoa_http_requests_total{${MODE_FILTER}}))`; PromQL §3.4 returns scalar `1` (jobs, not routes) | PASS |
| Scope-mismatch banner visible iff totals>0 AND mode breakdown empty | `CallFlowDashboard.tsx:258-262`. Live state §3.6: gateway breakdown has traffic (5.43 req/s), so banner correctly stays HIDDEN | PASS (banner correctly hidden, not stuck on) |
| Trace empty state distinguishes Prometheus from Tempo/OpenSearch | `liveTracesEmptyMessage` uses `METRICS_TRACES_SPLIT_MESSAGE` when `totalRequestsVal>0`; message text in `metrics.ts` reads "Request metrics are available, but no traces were found for this time range. Metrics source: Prometheus. Trace source: Tempo/OpenSearch pipeline." Does not imply they are healthy | PASS |

Note on the banner check: the contract is *the banner appears when the
condition is true*. On prod, the condition is currently false (gateway has
traffic), so the test that this state is correctly handled relies on the
regression test
`control-plane-ui/src/__tests__/regression/live-calls-metric-integrity.test.tsx`,
which mocks the contradictory state and asserts the banner renders. The PR-2
squash commit ships that test; it was green in CI (`Build and Test
(control-plane-ui)` on `87b1a4f9` = success).

---

## 3. PromQL evidence

All queries executed against
`http://prometheus-kube-prometheus-prometheus.monitoring.svc:9090/api/v1/query`
from inside the `stoa-control-plane-api-f6cff8899-mjctm` pod at 2026-05-08
~18:43Z.

### 3.1 — `count by (job) (stoa_http_requests_total)`

```text
status: success
{job: "stoa-gateway"}  333
```

Only `stoa-gateway` is currently scraped on prod; `stoa-link` and
`stoa-connect` jobs are not deployed. This is expected and is the reason the
UI shows Active Modes = 1.

### 3.2 — `count by (http_route) (stoa_http_requests_total)` (truncated)

```text
status: success
{http_route: "/mcp"}                                   6
{http_route: "/mcp/tools/call"}                       11
{http_route: "/mcp/tools/list"}                        7
{http_route: "/mcp/sse"}                              12
{http_route: "/admin/apis"}                            2
{http_route: "/admin/sessions/stats"}                  3
{http_route: "/echo/get"}                              3
{http_route: "/apis/echo-oauth2/"}                     5
{http_route: "/apis/exchange-rate/v4/latest/EUR"}      5
{http_route: "/apis/fapi-accounts/api/v1/accounts"}    5
{http_route: "/apis/fapi-transfers/api/v1/transfers"}  8
{http_route: "/apis/openweathermap/weather"}           5
{http_route: "/apis/newsapi/top-headlines"}            5
{http_route: "/apis/echo-fallback/"}                   3
{http_route: "/.well-known/acme-challenge/IyAg…"}      3
{http_route: "/403.php"}                               2
{http_route: "/admin.php"}                             2
…
```

`count(count by (http_route) (stoa_http_requests_total))` = **175** distinct
`http_route` values. Every row exposes a non-empty, non-`unknown`,
non-`(unlabelled)` route label.

### 3.3 — `count by (path) (stoa_http_requests_total)`

```text
status: success
{}  333
```

The collapsed empty label set with the same value as the total series count
(`count(stoa_http_requests_total)` = 333) confirms the original PR-2 step-0
finding: **`path` does not exist as a label on `stoa_http_requests_total`** —
0 / 333 series expose it. Any UI panel grouping by `path` would render under a
single fabricated bucket. The PR-2 migration to `http_route` is therefore
required, not cosmetic.

### 3.4 — Active Modes (`metrics.ts::activeModes`)

```text
count(count by (job) (stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}))
status: success
{}  1
```

Active Modes KPI = 1, matching only `stoa-gateway` reporting. Routes are not
counted.

### 3.5 — Unusable-route-label sanity counts

```text
count(stoa_http_requests_total{http_route="unknown"})       (empty result)
count(stoa_http_requests_total{http_route="(unlabelled)"})  (empty result)
count(stoa_http_requests_total{http_route=""})              (empty result)
```

0 series for any unusable label value. Top Routes will therefore not need to
fall back to `ROUTE_LABELS_UNAVAILABLE_MESSAGE` — real routes are returned
(see §3.6).

### 3.6 — Top Routes by P95 latency (`metrics.ts::topRoutesP95`)

```text
topk(8, histogram_quantile(0.95, sum by (le, http_route) (
  rate(stoa_http_request_duration_seconds_bucket{
    job=~"stoa-gateway|stoa-link|stoa-connect",
    http_route!="", http_route!="unknown", http_route!="(unlabelled)"
  }[5m]))))
status: success
{http_route: "/mcp"}                                                      0.00480 s
{http_route: "/mcp/tools/call"}                                           0.00460 s
{http_route: "/apis/exchange-rate/v4/latest/EUR"}                         0.00438 s
{http_route: "/.well-known/acme-challenge/IyAg…"}                         0.00429 s
{http_route: "/apis/fapi-transfers/api/v1/transfers"}                     0.00392 s
{http_route: "/apis/newsapi/top-headlines"}                               0.00387 s
{http_route: "/apis/echo-oauth2/"}                                        0.00375 s
{http_route: "/apis/openweathermap/weather"}                              0.00366 s
```

8 real routes returned, all using `http_route`, none `unknown` /
`(unlabelled)`.

### 3.7 — Total request query (`metrics.ts::totalRequests` for `1h`)

```text
sum(increase(stoa_http_requests_total{job=~"stoa-gateway|stoa-link|stoa-connect"}[1h]))
status: success
{}  16358.77
```

### 3.8 — Per-mode trends (`metrics.ts::edgeMcpTrend / linkTrend / connectTrend`)

```text
sum(rate(stoa_http_requests_total{…, job="stoa-gateway"}[5m]))   5.43 req/s
sum(rate(stoa_http_requests_total{…, job="stoa-link"}[5m]))      (empty)
sum(rate(stoa_http_requests_total{…, job="stoa-connect"}[5m]))   (empty)
```

`modeBreakdownHasTraffic = true` (gateway has traffic). With `totalRequestsVal
≈ 16K > 0` and `modeBreakdownHasTraffic=true`, the scope-mismatch banner
condition `useServiceGraph && !modeBreakdownLoading && totalRequestsVal>0 &&
!modeBreakdownHasTraffic` evaluates to **false** — banner correctly hidden.

---

## 4. Screenshot evidence

Screenshots not captured in this pack; the Console UI requires Keycloak SSO
which was not exercised by an authenticated browser session in this run. The
following are the suggested follow-up captures if a manual visual archive is
desired:

- full page `/observability/live-calls` for `1h` and `24h`;
- Top Routes section showing real `/mcp*` and `/apis/*` rows;
- Heatmap section showing the `HEATMAP_UNAVAILABLE_MESSAGE` empty state;
- Live Traces section to confirm the Prometheus-vs-Tempo/OpenSearch wording is
  visible when traces are empty.

The runtime data in section 3 already pins the values that those screenshots
would render; the screenshots would be a UX confirmation, not a logical
verification.

---

## 5. Verdict

PASS criteria (recap from the runbook):

- no `unknown` / `(unlabelled)` rendered as a normal route — **met** (PromQL §3.5: 0 series; UI filter dual-layer);
- no synthetic heatmap — **met** (constant empty `heatmapCells`, EmptyState rendered);
- no KPI-vs-breakdown contradiction without warning — **met** (banner wired; current state is consistent so banner correctly hidden; regression test asserts the contradictory state shows the banner);
- route panels use `http_route` or honest EmptyState — **met** (PromQL §3.6 returns 8 real routes via `http_route`);
- traces empty state no longer implies Prometheus and Tempo/OpenSearch are the same pipeline — **met** (`METRICS_TRACES_SPLIT_MESSAGE` wording deployed at SHA `87b1a4f9`).

VERDICT: PR-2_RUNTIME_PASS
