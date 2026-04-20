# CAB-2123 — Post-merge verification

- **Date**: 2026-04-19
- **PR**: https://github.com/stoa-platform/stoa/pull/2426
- **Squash commit**: `3a0614bc`
- **Cluster**: OVH MKS GRA9 (`config-stoa-ovh`)
- **Deployment**: `stoa-system/stoa-gateway`

## Rollout confirmation

- Image on live deployment: `ghcr.io/stoa-platform/stoa-gateway:dev-3a0614bcadb86b032eb487d03be7f57512db1c34`
- `observedGeneration` / `generation`: `488 / 488`
- Pods post-rollout: `stoa-gateway-9dc9bcd77-8zr4r`, `stoa-gateway-9dc9bcd77-gf42s` — both `Running 1/1`, `0` restarts

## Baseline (pre-merge, anonymous call)

```
$ curl -sS https://mcp.gostoa.dev/mcp/v1/tools | jq '.tools | length'
15
```

All 15 tools were `stoa_*` platform tools. Zero banking tools visible.

## Post-merge (anonymous call, same endpoint)

```
$ curl -sS https://mcp.gostoa.dev/mcp/v1/tools | jq '.tools | length'
89
```

7/7 banking per-op tools now visible via standard discovery:

- `demo:banking-services-v1-2:getaccountbalance`
- `demo:banking-services-v1-2:getaccounttransactions`
- `demo:banking-services-v1-2:getcustomerbynumber`
- `demo:banking-services-v1-2:gettransferstatus`
- `demo:banking-services-v1-2:initiateinternationaltransfer`
- `demo:banking-services-v1-2:initiatesepatransfer`
- `demo:banking-services-v1-2:listaccountsbycustomer`

## DoD

| Criterion | Status |
|---|---|
| `into_public()` tool → `definition().tenant_id == None` | PASS (regression_cab_2123_public_dynamic_tool_has_no_tenant_in_definition) |
| `registry.list(Some("any-tenant"))` includes public DynamicTool | PASS (regression_cab_2123_registry_list_includes_public_dynamic_tool_for_any_tenant) |
| Non-public DynamicTool stays tenant-scoped | PASS (regression_cab_2123_registry_list_keeps_private_dynamic_tool_tenant_scoped) |
| api_bridge per-op integration shape | PASS (regression_cab_2123_public_per_op_tool_surfaces_via_standard_list) |
| `cargo clippy --all-targets -- -D warnings` green | PASS |
| Post-merge prod: banking tools visible via standard discovery | **PASS — 7/7 tools visible** |

## Conclusion

CAB-2088 demo acte 1 standard-client path unblocked. Generic MCP clients (Claude Connector, Codex Custom MCP) can now discover the banking catalog through `tools/list` without relying on the bricolé `stoa_tools action=list` path.
