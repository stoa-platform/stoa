# Agent role refusal catalogue

The cases use the synthetic tenant `acme` and role `reader` from the [signed fixture generator](../scripts/gen_fixtures.py). The gateway origin inside Compose is `http://stoa-gateway:8080`. Each protected request uses the indicated session token with a fresh DPoP proof. The requests below use JSON bodies. To expand an MCP row, send `{"jsonrpc":"2.0","id":1,"method":"<method>","params":<params>}` to `POST /mcp/poc`. The ID is a correlation value.

## 1. Tool access

| ID | Situation | Identity | Request | Exact response | Code / compose |
| --- | --- | --- | --- | --- | --- |
| 01 | The tenant permits a tool outside the signed role | Parent, policy v1 | `tools/call` with `{"name":"payments_hidden","arguments":{}}` and `X-Stoa-Source: control-plane` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Role check][call] · [Jalon 3][j3] |
| 02 | A permitted subcall is followed by an out-of-role step | Parent, policy v1 | `poc/subcalls` with `{"steps":[{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-j3-1","limit":20}},{"name":"payments_hidden","arguments":{}}]}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Subcall dispatcher][subcalls] and [role check][call] · [Jalon 3][j3] |
| 09 | OPA rejects a tool included in the role | Parent, policy v1 | `tools/call` with `{"name":"payments_opa_denied","arguments":{}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by policy"` | [OPA check][opa] · [Jalon 2][j2parent] |
| 10 | The child targets a tool outside its resource audience | Child, depth 1, policy v1, `aud=mcp-tool:acme:payments_list` | `tools/call` with `{"name":"payments_redirect","arguments":{}}` | HTTP 401, `error.code = -32001`, `error.message = "Unauthorized"` | [MCP audience validation][auth] · [Jalon 2][j2child] |

Case 10 fails during authentication, before JSON-RPC method dispatch. The gateway returns the JSON-RPC error with HTTP 401. The MCP cases that reach dispatch return HTTP 200.

## 2. Argument constraints and delegation

| ID | Situation | Identity | Request | Exact response | Code / compose |
| --- | --- | --- | --- | --- | --- |
| 03 | `allowed_values` excludes USD | Child, depth 1, policy v1, EUR only | `tools/call` with `{"name":"payments_list","arguments":{"currency":"USD","account":"acct-1","limit":20}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Constraint evaluation][constraints] and [role check][call] · [Jalon 2][j2child] |
| 04 | `prefix` requires `acct-` | Child, depth 1, policy v1 | `tools/call` with `{"name":"payments_list","arguments":{"currency":"EUR","account":"other-1","limit":20}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Constraint evaluation][constraints] and [role check][call] · [Jalon 2][j2child] |
| 05 | `max_number` caps the child's limit at 25 | Child, depth 1, policy v1 | `tools/call` with `{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-1","limit":50}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Constraint evaluation][constraints] and [role check][call] · [Jalon 2][j2child] |
| 06 | Delegation requests a maximum of 250 from a parent capped at 100 | Parent, policy v1 | `POST /mcp/poc/delegate` with `{"sub":"agent-child","target_tool":"payments_list","child_dpop_jwk":<child public JWK>,"allowed_tools":["payments_list"],"arg_constraints":{"limit":{"type":"max_number","max":250.0}},"ttl_secs":90}` | HTTP 403, `error = "child argument constraint widens parent constraint"` | [Delegation subset check][subset] and [REST response][delegate] · [Jalon 2][j2parent] |
| 11 | Delegation would create a child at depth 4 | Child, depth 3, policy v1, `aud=mcp-tool:acme:payments_list` | `POST /mcp/poc/delegate` with `{"sub":"agent-child-d4","target_tool":"payments_list","child_dpop_jwk":<child public JWK>,"allowed_tools":["payments_list"],"ttl_secs":30}` | HTTP 403, `error = "delegation depth exceeds maximum of 3"` | [Depth check][depth] and [REST response][delegate] · [Jalon 2][j2child] |

## 3. Changes during an active session

Jalon 2 first calls `payments_list` successfully, then atomically replaces the v1 role file with signed v2 in the live gateway. Version 2 withdraws `payments_list` and adds `payments_hidden`. The parent retains its original token and DPoP key. A fresh v2 token lists the added tool as a positive control.

| ID | Situation | Identity | Request | Exact response | Code / compose |
| --- | --- | --- | --- | --- | --- |
| 07 | First call after a policy update withdraws a previously callable tool | Parent, issued under v1, active policy v2 | `tools/call` with `{"name":"payments_list","arguments":{"currency":"USD","account":"acct-parent-1","limit":80}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Monotonic session policy][intersection] and [role check][call] · [Jalon 2 reload][reload] |
| 08 | A tool added in v2 stays outside the original token's scope | Same parent token as 07 | `tools/call` with `{"name":"payments_hidden","arguments":{}}` | HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Monotonic session policy][intersection] and [role check][call] · [Jalon 2 reload][reload] |

## 4. Limits reported to the caller

| ID | Situation | Identity | Request | Exact response | Code / compose |
| --- | --- | --- | --- | --- | --- |
| 12 | The child calls above the maximum of 25 returned by its own limits tool | Child, depth 1, policy v1, `aud=mcp-tool:acme:payments_list` | First `tools/call` with `{"name":"stoa_security","arguments":{"action":"get_my_limits"}}`. Then `tools/call` with `{"name":"payments_list","arguments":{"currency":"EUR","account":"acct-child-1","limit":26}}` | For the second request, HTTP 200, `error.code = -32003`, `error.message = "Tool call rejected by role policy"` | [Limits projection][limits], [constraint evaluation][constraints] and [role check][call] · [Jalon 2 limits check][j2limits] |

[auth]: ../../../stoa-gateway/src/mcp/poc.rs#L616
[call]: ../../../stoa-gateway/src/mcp/poc.rs#L1033
[constraints]: ../../../stoa-gateway/src/control_plane/role_policy.rs#L1038
[delegate]: ../../../stoa-gateway/src/mcp/poc.rs#L483
[depth]: ../../../stoa-gateway/src/auth/local_agent_token.rs#L367
[intersection]: ../../../stoa-gateway/src/control_plane/role_policy.rs#L475
[limits]: ../../../stoa-gateway/src/mcp/poc.rs#L894
[opa]: ../../../stoa-gateway/src/mcp/poc.rs#L948
[subcalls]: ../../../stoa-gateway/src/mcp/poc.rs#L1156
[subset]: ../../../stoa-gateway/src/auth/local_agent_token.rs#L420
[j2child]: ../agent_harness.py#L409
[j2limits]: ../agent_harness.py#L564
[j2parent]: ../agent_harness.py#L196
[j3]: ../agent_harness.py#L599
[reload]: ../agent_harness.py#L579
