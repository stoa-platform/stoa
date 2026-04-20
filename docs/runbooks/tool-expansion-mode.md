# Runbook: Gateway Tool Expansion Mode

> **Severity**: Medium (flag flip, reversible within one refresh cycle)
> **Last updated**: 2026-04-19
> **Owner**: Platform Team
> **Linear Issue**: CAB-2113

Covers `STOA_TOOL_EXPANSION_MODE` — the CAB-2113 Phase 0 runtime overlay that controls how the gateway exposes catalog APIs as MCP tools. Phase 0.5 (CAB-2116) gates further evolution.

---

## 1. What the flag does

| Value | Canonical | Gateway behaviour |
|-------|-----------|-------------------|
| `coarse` (default) | kebab | One `{action, params}` tool per API. Consumes `GET /v1/internal/catalog/apis`. Legacy behaviour. |
| `per-op` | kebab | One MCP tool per OpenAPI operation. Consumes `GET /v1/internal/catalog/apis/expanded`. Input schema is the per-op params + requestBody; path params substituted server-side by `DynamicTool`. |
| `per_operation` | **deprecated alias** | Same as `per-op`. Accepted for one release to bridge the pre-2026-04-19 doc drift. Emit a warning in your own tooling and migrate to `per-op`. |

Flipping is safe in both directions: the change takes effect at the next refresh tick (≤60s, see `API_TOOL_REFRESH_INTERVAL` in `api_bridge.rs`). Existing `tools/list` results for the previous mode stop being served; in-flight calls finish on whatever tool was registered when the call started.

---

## 2. How to flip per gateway / per tenant

### 2.1 Canary one gateway

Helm value (`values.yaml` for that gateway release only):

```yaml
env:
  - name: STOA_TOOL_EXPANSION_MODE
    value: per-op
```

Roll the deployment — no restart required beyond the usual Helm upgrade. On OVH prod:

```bash
helm -n stoa-system upgrade stoa-gateway charts/stoa-gateway \
  --reuse-values --set env[0].name=STOA_TOOL_EXPANSION_MODE --set env[0].value=per-op
```

Watch `stoa_gateway_tool_expansion_refresh_total{mode="per-op",result="ok"}` tick up within 60s, and `stoa_gateway_tool_expansion_ops_registered{mode="per-op"}` populate with the expected per-op count.

### 2.2 Per-tenant flip

Not directly supported in Phase 0 — the flag is gateway-wide. For a tenant-scoped trial, deploy a dedicated gateway pool for the tenant and set the flag on that pool only. Tenant-scoped flipping is a Phase 1 question, gated on the CAB-2116 outcome.

### 2.3 Rollback

Set the env back to `coarse` (or remove the env — default is coarse) and redeploy. The next refresh tick repopulates the registry with the coarse shape. No pod restart required beyond the Helm upgrade.

```bash
helm -n stoa-system upgrade stoa-gateway charts/stoa-gateway \
  --reuse-values --set env[0].value=coarse
```

Full rollback window: ≤60s (next refresh) from the env change taking effect on the running pod.

---

## 3. Observability

Three Prometheus metrics introduced in CAB-2113 PR3. Scraped from the gateway `/metrics` endpoint (see `charts/stoa-gateway/templates/servicemonitor.yaml`).

| Metric | Type | Labels | Use |
|--------|------|--------|-----|
| `stoa_gateway_tool_expansion_refresh_total` | Counter | `mode`, `result` | Rate of successful / failed refresh cycles per mode. |
| `stoa_gateway_tool_expansion_ops_registered` | Gauge | `mode` | Tools newly registered at the last refresh cycle (0 in steady state once all ops are already registered). |
| `stoa_gateway_tool_expansion_errors_total` | Counter | `reason` | Categorised errors: `transport`, `upstream_status`, `parse`. Pinpoints CP-API vs network vs schema-shape issues. |

### PromQL examples

Refresh success rate per mode (last hour):

```promql
sum by (mode) (rate(stoa_gateway_tool_expansion_refresh_total{result="ok"}[1h]))
/
sum by (mode) (rate(stoa_gateway_tool_expansion_refresh_total[1h]))
```

Error budget — spike on `upstream_status` typically means CP-API is returning 5xx on `/apis/expanded`:

```promql
sum by (reason) (rate(stoa_gateway_tool_expansion_errors_total[5m]))
```

Tool-count drift — gauge goes back to 0 once registry is steady:

```promql
stoa_gateway_tool_expansion_ops_registered{mode="per-op"}
```

### Alerting

No hard alert wired today. Phase 0.5 harness (CAB-2116) will exercise the metrics; alert rules land with Phase 1 if that gate goes GREEN.

---

## 4. Known limitations

- **Path-param vs body-param collision**: when an OpenAPI spec has a parameter with the same name both in the URL path and in the request body (rare in practice), `DynamicTool` routes it to the path and drops it from the body. No disambiguation yet. Track via a dedicated ticket if you hit this on a real spec — not observed on banking-services-v1-2, payment-api, or fapi-accounts as of 2026-04-19.
- **Tool-count scalability** beyond ~200 ops is unmeasured. CAB-2116 Phase 0.5 will test 50/100/200 explicitly; do not run `per-op` on a gateway serving >200 ops in prod until the scalability subset is green.
- **Same-action across APIs**: the `per-op` mode uses `{tenant}:{api}:{op_id}` as tool name, so two APIs sharing the same `operationId` don't collide. `coarse` mode names tools by API slug, so two APIs with the same slug in different tenants is already broken regardless of this flag.
- **Auth translation**: `DynamicTool` forwards the caller's Bearer token. Upstreams requiring X-API-Key / Basic auth (e.g., banking-mock in the demo) need an auth-translation policy layered separately — not part of this flag's behaviour.

---

## 5. Related

- CAB-2113 Phase 0 PR1 (#2415) — CP-API `/apis/expanded` endpoint
- CAB-2113 Phase 0 PR2 (#2420) — gateway consumer + `ExpansionMode` enum + `DynamicTool` path-pattern substitution
- CAB-2113 Phase 0 PR3 (this runbook) — observability + docstring drift fix + `per_operation` serde alias
- CAB-2116 — Phase 0.5 LLM tool-selection benchmark (gate before catalog CRDs)
- CAB-2117 — `stoactl --tenant` vs `--namespace` separation (surfaced during Phase 0 investigation)
- ADR-024 — Gateway 4-mode architecture (edge-mcp, sidecar, proxy, shadow)
