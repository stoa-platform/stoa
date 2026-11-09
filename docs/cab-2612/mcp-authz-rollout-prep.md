# CAB-2612 data preparation and rollback

This plan is not executed. It does not connect to PostgreSQL, a cluster, or a deployment. The seed procedure already lives in `docs/runbooks/tool-permissions-deny-by-default.md`. Run that SQL only on an authorized database, after the inventory in `docs/cab-2612/mcp-authz-inventory.md` is marked approved, and only from a restored rehearsal copy first.

Every allow in the manifest is **à approuver par le responsable**. Keep the CSV and the database export outside the repository.

## Prepare

1. Export `tenant_tool_permissions` and take the approved database backup. Do not commit either file.
2. Build `approved-tool-allows.csv` with header `tenant_id,mcp_server_id,tool_name`. One row per intended allow. Include every code-defined tool (inventory T1–T16) and every catalog tool (T17) that must keep working. Tenants that must stay denied are omitted and signed off by name.
3. Freeze permission and catalog writes until verification finishes.
4. Rehearse the runbook SQL on the restored copy. Do not install extensions. Do not put connection secrets in the SQL file.

## Assertions before the application rollout

Stop on any failure. Do not deploy the application first: tenants without a matching allow lose the call.

| Assertion | Expected |
| --- | --- |
| Manifest has at least one row | Empty manifest aborts, as in the runbook |
| No manifest row matches an existing `allowed IS NOT TRUE` row | Abort. Do not flip a deny |
| After the idempotent insert, every manifest row has `allowed = true` | Abort if any row is missing or not true |
| Re-running the script inserts nothing and still passes | Idempotent |
| A tenant absent from the manifest has no new allow | Intentional denies stay denied |
| A tool with an allow on one server and a deny on another | Unscoped call denied; server-scoped allow unchanged |
| Caller tenant A, row exists only for tenant B | Deny on the control plane and the gateway |
| Token or user with no tenant id, including a platform admin | Deny. Do not evaluate tenant `default` |
| Blank tenant id | Deny, and the gateway must not treat a Control Plane allow as authority for that call |
| Cold call, then a second call inside 60 seconds | Same decision. The second control-plane check does not need a new SQL read |
| After the 60-second permission TTL, or after replicas restart | A row changed from allow to deny is denied. The old allow is not kept |
| Control-plane artifact `expires_at` in the past, or signing unavailable | Issuer starts a new window, or returns 503 and not a stale 304 |
| Vérification de l'artefact signé côté gateway : suivie dans Linear (CAB-2612). | Suivi Linear CAB-2612 |
| One intended allow and one unlisted or explicitly denied tool per tenant | Allow succeeds and the other is denied, both through `POST /v1/mcp/tools/{name}/invoke` and through the gateway tool call, on a cold cache and again inside the TTL |

Direct SQL does not invalidate API caches. Wait out the 60-second permission cache on every API replica, or restart those replicas through the normal deployment, and refresh signed artifacts through the existing policy delivery procedure.

## Rollback

1. Stop the rollout. Restore the previous application through the standard rollback. Do not bulk-delete the seeded rows: later edits may be mixed in, and deleting rows under the new check revokes access.
2. Restoring the previous application brings back its default-allow behavior for missing rows. That rollback needs its own security review before it is used.
3. Keep the export, the manifest, and the assertion output. Reconcile before a second attempt.
4. If the blank-tenant deny from this proof branch is already deployed, a platform admin with no tenant claim can no longer invoke tools as tenant `default`. Rolling that edit back restores the `default` fallback and is also a security-reviewed change.

## What local tests already showed

Local SQLite and gateway mocks, with no live environment:

- No row denies. An explicit deny still denies when another server allows the same tool. Tenant A does not receive tenant B's allow. A blank tenant denies even if an allow row is stored for it.
- The hot cache repeats the decision; forcing the cache expiry reloads a deny that replaced an allow.
- Control-plane invoke returns success for an explicit allow and 403 for a deny, a cross-tenant tool, and a missing tenant.
- Existing artifact tests reissue after expiry and refuse to return a body when signing fails.
- Existing gateway tests deny on an empty policy, an explicit deny, a cold miss, a hot cache, and a failed refetch after expiry. Invalid artifact signatures are refused by the verifier.

Vérification de l'artefact signé côté gateway : suivie dans Linear (CAB-2612).
