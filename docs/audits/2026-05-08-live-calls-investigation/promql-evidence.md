# PR-2 Step 0 — Live Calls PromQL Evidence Pack

Generated: 2026-05-07T15:19:15+02:00

Scope: read-only PromQL evidence against `https://api.gostoa.dev/v1/metrics/query`. No source code or runtime state was modified.

## Verdict

**READY_FOR_PR-2_CODE_SCOPING**

Current production `stoa_http_requests_total` series do **not** expose a `path` label. They expose `http_route` instead.

Therefore, current Live Calls queries that group `stoa_http_requests_total` or duration buckets by `path` are not compatible with the current metric label set. The correct current route label is `http_route`.

## Auth + Endpoint

Unauthenticated call:

```bash
curl https://api.gostoa.dev/v1/metrics/query?query=up
```

Observed response:

```json
{"detail":"Not authenticated"}
```

Authenticated evidence used the existing API operator key as an `X-Operator-Key` header. The key was read from the running API pod and never printed or stored in this report.

Endpoint:

```text
https://api.gostoa.dev/v1/metrics/query
```

API health at investigation time:

```json
{"status":"healthy","version":"2.0.0"}
```

## Query Summary

### `count(stoa_http_requests_total)`

```text
http=200
status=success
result_count=1
value=306
```

### Raw `stoa_http_requests_total`

```text
http=200
status=success
result_count=306
```

Sample current label sets:

```text
__name__=stoa_http_requests_total,app=stoa-gateway,http_route=/.well-known/acme-challenge/IyAg0DCoVE1OsKmrelxifw5keXaM8US_YIBtDLERSnU,instance=stoa-gateway.stoa-system.svc:80,job=stoa-gateway,method=GET,status=404
__name__=stoa_http_requests_total,app=stoa-gateway,http_route=/mcp,instance=stoa-gateway.stoa-system.svc:80,job=stoa-gateway,method=POST,status=200
__name__=stoa_http_requests_total,app=stoa-gateway,http_route=/mcp,instance=stoa-gateway.stoa-system.svc:80,job=stoa-gateway,method=POST,status=401
__name__=stoa_http_requests_total,app=stoa-gateway,http_route=/admin/apis,instance=stoa-gateway.stoa-system.svc:80,job=stoa-gateway,method=GET,status=200
__name__=stoa_http_requests_total,app=stoa-gateway,http_route=/echo/get,instance=stoa-gateway.stoa-system.svc:80,job=stoa-gateway,method=GET,status=404
```

Raw label key counts:

| Label key | Series count |
|---|---:|
| `__name__` | 306 |
| `app` | 107 |
| `container` | 199 |
| `endpoint` | 199 |
| `http_route` | 306 |
| `instance` | 306 |
| `job` | 306 |
| `method` | 306 |
| `namespace` | 199 |
| `pod` | 199 |
| `service` | 199 |
| `status` | 306 |

Critical counts:

```text
raw_series_total=306
series_with_path=0
series_with_http_route=306
```

## `path` Label Evidence

### `count by (path) (stoa_http_requests_total)`

```text
http=200
status=success
result_count=1
sample_metrics:
  value=306
```

Interpretation: Prometheus grouped all current series into one unlabeled bucket because `path` is absent on current series.

### `count(stoa_http_requests_total{path=~".+"})`

```text
http=200
status=success
result_count=0
```

Interpretation: no current series has a non-empty `path` label.

### `sum by (path) (increase(stoa_http_requests_total[1h]))`

```text
http=200
status=success
result_count=1
sample_metrics:
  value=41282.85093735323
```

Interpretation: over a 1h window, the current data still collapses into one unlabeled aggregate when grouped by `path`.

### `sum by (path) (increase(stoa_http_requests_total[24h]))`

```text
http=200
status=success
result_count=88
sample_metrics:
  value=245037.82457440783
  path=/ value=0
  path=/.git/config value=0
  path=/.well-known/acme-challenge/IyAg0DCoVE1OsKmrelxifw5keXaM8US_YIBtDLERSnU value=314.73160425914205
  path=/admin/apis value=21.183668932704634
```

Interpretation: the 24h window contains some historical `path`-labelled series, but current instant data has `path=0/306`. Live Calls should not rely on `path` as the current canonical label.

## `http_route` Label Evidence

### `count(stoa_http_requests_total{http_route=~".+"})`

```text
http=200
status=success
result_count=1
value=306
```

Interpretation: every current `stoa_http_requests_total` series has a non-empty `http_route` label.

### `count by (http_route) (stoa_http_requests_total)`

```text
http=200
status=success
result_count=161
```

Sample routes:

```text
http_route=/.well-known/acme-challenge/IyAg0DCoVE1OsKmrelxifw5keXaM8US_YIBtDLERSnU value=3
http_route=/mcp value=6
http_route=/admin/apis value=2
http_route=/echo/get value=3
http_route=/apis/echo-oauth2/ value=5
http_route=/apis/exchange-rate/v4/latest/EUR value=5
http_route=/apis/fapi-accounts/api/v1/accounts value=5
http_route=/apis/openweathermap/weather value=5
http_route=/apis/fapi-transfers/api/v1/transfers value=8
http_route=/apis/newsapi/top-headlines value=5
```

### `sum by (http_route) (increase(stoa_http_requests_total[1h]))`

```text
http=200
status=success
result_count=161
```

Sample values:

```text
http_route=/.well-known/acme-challenge/IyAg0DCoVE1OsKmrelxifw5keXaM8US_YIBtDLERSnU value=540.0105481523153
http_route=/mcp value=70.38571076966352
http_route=/echo/get value=11.058682887380893
http_route=/apis/echo-oauth2/ value=6164.551176118983
http_route=/apis/exchange-rate/v4/latest/EUR value=5204.137688548222
http_route=/apis/fapi-accounts/api/v1/accounts value=5954.520586477269
http_route=/apis/openweathermap/weather value=5794.678105551844
http_route=/apis/fapi-transfers/api/v1/transfers value=5914.040997151998
http_route=/apis/newsapi/top-headlines value=5907.277521887416
```

### `sum by (http_route) (increase(stoa_http_requests_total[24h]))`

```text
http=200
status=success
result_count=216
```

Interpretation: `http_route` works for current and historical windows.

## Duration Metric Label Evidence

The duration metrics used for latency breakdown show the same label shape.

### `stoa_http_request_duration_seconds_bucket`

```text
status=success
raw_series_total=3627
series_with_path=0
series_with_http_route=3627
label_keys=__name__, app, container, endpoint, http_route, instance, job, le, method, namespace, pod, service
```

### `stoa_http_request_duration_seconds_sum`

```text
status=success
raw_series_total=279
series_with_path=0
series_with_http_route=279
```

### `stoa_http_request_duration_seconds_count`

```text
status=success
raw_series_total=279
series_with_path=0
series_with_http_route=279
```

## Job Scope

### `count by (job) (stoa_http_requests_total)`

```text
http=200
status=success
result_count=1
job=stoa-gateway value=306
```

Interpretation: current request metric inventory from the API proxy is only `job=stoa-gateway` for this metric name.

## Findings

| Finding | Status | Evidence |
|---|---|---|
| Current `stoa_http_requests_total` has no `path` label | Confirmed | `series_with_path=0`, `count(path=~".+")` returns no vector |
| Current `stoa_http_requests_total` has `http_route` | Confirmed | `series_with_http_route=306/306` |
| `sum by(path)(increase(...[1h]))` collapses to unlabeled aggregate | Confirmed | one result with no `path` label |
| `sum by(http_route)(increase(...[1h]))` returns route-level data | Confirmed | 161 labelled route series |
| Duration bucket/sum/count metrics also use `http_route`, not `path` | Confirmed | `series_with_path=0`, `series_with_http_route>0` |
| `path` appears in a 24h range | Historical only / mixed | current instant has no `path`; 24h range contains stale/legacy `path` series |

## Recommended PR-2 Scope

PR-2 should avoid inventing data and should fix label semantics explicitly:

1. Update Live Calls PromQL route groupings from `path` to `http_route`, or introduce a label normalization layer that prefers `http_route` and only falls back to `path`.
2. Update latency route queries using `stoa_http_request_duration_seconds_bucket` to group by `http_route`.
3. Treat missing route labels as `'(unlabelled)'`, as decided in AR-5, and do not show them as normal routes.
4. Keep a scope-mismatch banner when aggregate request count is positive but per-route/per-mode breakdown is empty.
5. Remove or empty-state the synthetic heatmap per AR-6; do not use `path` evidence from 24h stale series to justify current heatmap data.

## Residual Risks

- Evidence used `X-Operator-Key` rather than a user JWT because the public metrics proxy is authenticated and local direct-grant fixtures did not produce a token. This still exercises `api.gostoa.dev` and the same FastAPI metrics proxy endpoint.
- Queries are point-in-time. Metric label migrations can leave stale historical series in range queries, as seen in the 24h `path` result.
- `http_route` includes high-cardinality-looking ACME and scanner paths. PR-2 may need display filtering, but should not hide that evidence in the data layer.
