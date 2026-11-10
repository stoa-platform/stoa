# CAB-2612 MCP authorization inventory

Source change: merged PR [#3125](https://github.com/stoa-platform/stoa/pull/3125) (`a912eea1`). No database, cluster, or rollout was performed for this inventory.

#3125 does not add a fixed tool catalogue. It controls one decision: a tool call is allowed only when an explicit `allowed=true` row matches, and any matching deny wins when the call is not scoped to a server. The rows below are every control-plane operation and every code-defined MCP tool that decision now gates. Catalog and proxy tools are data, so they are one class rather than a name list.

**Approval:** every row is **à approuver par le responsable**. Nothing here is an approved production allow.

**Security review required** for the two authorization edits in this proof branch:

- Control-plane invoke no longer maps a platform admin with no tenant onto the shared tenant id `default` (`control-plane-api/src/routers/mcp_proxy.py`).
- A blank tenant is denied before the permission cache or a Control Plane read (`control-plane-api/src/routers/tenant_tool_permissions.py`, `stoa-gateway/src/control_plane/tool_permissions.rs`).

## How a call is decided

| Rule | Default | Role / tenant | Source |
| --- | --- | --- | --- |
| No matching row | Deny | Caller's tenant only | `control-plane-api/src/routers/tenant_tool_permissions.py:92-97`; gateway `stoa-gateway/src/control_plane/tool_permissions.rs:50-52` |
| Explicit `allowed=true` | Allow for that pair | Caller's tenant, exact `tool_name` | `tenant_tool_permissions.py:92-97`; model `control-plane-api/src/models/tenant_tool_permission.py:16-34` |
| Explicit deny plus an allow for the same tool on another server | Deny for an unscoped call; the server-scoped allow stays allow | Caller's tenant | `tenant_tool_permissions.py:95-97`; gateway folds with AND at `tool_permissions.rs:422-423` |
| Blank or missing tenant | Deny | No substitute tenant | `tenant_tool_permissions.py:87-88`; invoke `mcp_proxy.py:342-351`; gateway `tool_permissions.rs:189-200` and `stoa-gateway/src/auth/tenant.rs:22-27` |
| Other tenant's row | Deny | Identity is the authenticated caller, not a client header | `tenant_tool_permissions.py:62`; gateway cache key is the tenant id (`tool_permissions.rs:277-289`); gateway ignores client tenant headers (`stoa-gateway/src/mcp/handlers.rs:238-263`) |
| Permission cache, cold | Load SQL, then decide. Empty load denies | Per tenant, 60s TTL | `tenant_tool_permissions.py:46`, `55-70` |
| Permission cache, hot | Same decision, no second SQL read | Per tenant | `tenant_tool_permissions.py:58-60` |
| Permission cache, expired | Drop the entry and read SQL again. A previous allow is not kept | Per tenant | `control-plane-api/src/services/cache_service.py:43-45` |
| Gateway cache, cold / hot / expired | Fresh explicit allow required. Expired entry is refetched; a failed refetch denies (`Stale` or `Unavailable`) | Service account must be `private_key_jwt` | `tool_permissions.rs:277-324`, `355-360` |
| Signed artifact issuance | Reissue when `expires_at` has passed or signing fails. A failure is 503, not a stale 304 | Reader must pass tenant access | `tenant_tool_permissions.py:168-188` |
| Signed artifact verification | Invalid signature, issuer, audience, or tenant is refused | Pinned trust set | `stoa-gateway/src/control_plane/policy_artifact.rs:88-150` |

Gateway tool calls also require a verified JWT whose tenant passes `validated_tenant` (`stoa-gateway/src/telemetry/mod.rs:214-229`). That rejects an empty tenant and the literals `default`, `platform`, `__platform__`, and `__unattributed__`.

## Control-plane operations

| ID | Operation | Role / tenant | Default | Source |
| --- | --- | --- | --- | --- |
| P1 | `GET /v1/tenants/{tenant_id}/tool-permissions` | Authenticated caller. `cpi-admin` may name any tenant; `tenant-admin`, `devops`, and `viewer` only their own | Lists stored rows. Absence of rows does not grant use | `tenant_tool_permissions.py:102-141`, access `97-99` and `control-plane-api/src/auth/rbac.py:38-41` |
| P2 | `POST /v1/tenants/{tenant_id}/tool-permissions` | `cpi-admin` or `tenant-admin`, same tenant rule. Body `allowed` true or false | Creates or updates one explicit row | `tenant_tool_permissions.py:202-212` |
| P3 | `DELETE /v1/tenants/{tenant_id}/tool-permissions/{permission_id}` | `cpi-admin` or `tenant-admin`, same tenant rule | Deletes the row. The tool returns to deny | `tenant_tool_permissions.py:263-274` |
| P4 | `GET /v1/tenants/{tenant_id}/tool-permissions/artifact` | Same read access as P1 | Issues a compact Ed25519 JWS for that tenant only. Unknown tenant is 404. Signing failure is 503 | `tenant_tool_permissions.py:144-196`; signer `control-plane-api/src/services/policy_artifact_signer.py:26-55` |
| P5 | `POST /v1/mcp/tools/{tool_name}/invoke` | Authenticated caller with a non-blank `tenant_id`. Non-admins are clamped to their own tenant | Deny unless `check_tool_allowed` is true. Then proxy to the gateway | `mcp_proxy.py:322-363` |

`devops` can read permissions and cannot write them. `viewer` can read and cannot write. Neither role gets a tool call without an explicit allow.

## Code-defined MCP tools gated by that decision

Each tool is denied until an owner-approved row `(tenant_id, mcp_server_id, tool_name, allowed=true)` exists. The gateway action is a second check, not an allow.

| ID | Tool | Gateway action | Registration |
| --- | --- | --- | --- |
| T1 | `stoa_platform_info` | `Read` | `stoa-gateway/src/mcp/tools/native_tool.rs:967` |
| T2 | `stoa_platform_health` | `Read` | `native_tool.rs:990` |
| T3 | `stoa_tools` | `Read` | `native_tool.rs:1017` |
| T4 | `stoa_tenants` | `Read` | `native_tool.rs:1037` |
| T5 | `stoa_catalog` | `Read` | `native_tool.rs:1069` |
| T6 | `stoa_api_spec` | `Read` | `native_tool.rs:1091` |
| T7 | `stoa_subscription` | `Read` | `native_tool.rs:1110` |
| T8 | `stoa_metrics` | `ViewMetrics` | `native_tool.rs:1131` |
| T9 | `stoa_logs` | `ViewLogs` | `native_tool.rs:1151` |
| T10 | `stoa_alerts` | `Read` | `native_tool.rs:1171` |
| T11 | `stoa_uac` | `Read` | `native_tool.rs:1191` |
| T12 | `stoa_security` | `ViewAudit` | `native_tool.rs:1211` |
| T13 | `stoa_cache_load` | `Create` | `native_tool.rs:1232` |
| T14 | `stoa_cache_get` | `Read` | `native_tool.rs:1262` |
| T15 | `stoa_cache_invalidate` | `Delete` | `native_tool.rs:1281` |
| T16 | `stoa_create_api` | `CreateApi` | `stoa-gateway/src/mcp/tools/mod.rs:510` |
| T17 | Catalog, dynamic, and proxy tools | Whatever the registered tool declares | Not a fixed list. Names come from MCP servers and UAC projections. The same explicit-allow rule applies at `stoa-gateway/src/mcp/handlers.rs:160-177` |

**Inventoried count: 24.** That is P1–P5 (5 operations), T1–T17 (17 tools), and two cross-cutting controls from the decision table: blank-tenant deny, and unscoped deny-wins. The other decision rows describe how those 24 are evaluated.

Vérification de l'artefact signé côté gateway : suivie dans Linear (CAB-2612).
