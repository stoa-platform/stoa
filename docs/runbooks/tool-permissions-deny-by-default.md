# Roll out explicit tool permissions

The control plane and ADR-070 gateway deny tools without an explicit allow.
Deleting a permission now revokes access. For calls without a server ID, at
least one matching allow is required and any matching deny takes precedence.
Prefer server-scoped calls when different servers expose the same tool name.

## Inventory and approval (before deploying the check change)

An automatic tenant × tool cross join would grant unreviewed access. Historical
invocations alone also miss legitimate but infrequently used tools. There is no
complete offline entitlement source, so this rollout uses an operator-reviewed
manifest instead of an unconditional Alembic data migration.

1. Export existing permission rows and back up the database using the approved
   backup procedure. Keep the export and all manifests outside the repository.
2. Inventory every active tenant and its visible MCP servers and tools, including
   tenants with no permission rows. Reconcile tenant ownership, subscriptions,
   existing permissions, and recent successful calls with each tenant owner.
3. Record **every intended allow** as CSV columns `tenant_id,mcp_server_id,tool_name`
   with a header. Confirm server UUIDs and exact invocation names against the
   catalog. Keep explicit denies excluded; resolve any disputed grants before
   proceeding. Obtain owner sign-off for each tenant, including tenants that
   intentionally have no allows. This signed inventory is the completeness gate;
   SQL cannot infer a missing tenant or tool from an incomplete manifest.
4. Freeze permission/catalog changes through seeding and rollout. Schedule the
   application change only after the SQL assertions below pass. Do not deploy
   first: tenants without rows would immediately lose access.

## Seed and assert

An authorized operator runs this against the intended PostgreSQL database using
an existing secure connection profile. This document does not execute it.
Save the following as a local SQL file beside `approved-tool-allows.csv`, then run
`psql -X --set=ON_ERROR_STOP=1 --file=seed-tool-allows.sql` from that directory.
First rehearse against a restored database. Do not put connection secrets in SQL.

```sql
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE approved_tool_allows (
    tenant_id varchar(255) NOT NULL CHECK (tenant_id <> ''),
    mcp_server_id uuid NOT NULL,
    tool_name varchar(255) NOT NULL CHECK (tool_name <> ''),
    PRIMARY KEY (tenant_id, mcp_server_id, tool_name)
) ON COMMIT DROP;
\copy approved_tool_allows FROM 'approved-tool-allows.csv' WITH (FORMAT csv, HEADER true)

LOCK TABLE tenant_tool_permissions IN EXCLUSIVE MODE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM approved_tool_allows) THEN
        RAISE EXCEPTION 'Empty allow manifest: stop and review the inventory';
    END IF;
    IF EXISTS (
        SELECT 1 FROM approved_tool_allows a
        JOIN tenant_tool_permissions p USING (tenant_id, mcp_server_id, tool_name)
        WHERE p.allowed IS NOT TRUE
    ) THEN
        RAISE EXCEPTION 'Approved manifest conflicts with an explicit deny';
    END IF;
END $$;

INSERT INTO tenant_tool_permissions
    (id, tenant_id, mcp_server_id, tool_name, allowed, created_by, created_at, updated_at)
SELECT gen_random_uuid(), tenant_id, mcp_server_id, tool_name, true,
       'operator-reviewed-allow-seed', now(), now()
FROM approved_tool_allows
ON CONFLICT (tenant_id, mcp_server_id, tool_name) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM approved_tool_allows a
        LEFT JOIN tenant_tool_permissions p USING (tenant_id, mcp_server_id, tool_name)
        WHERE p.allowed IS DISTINCT FROM TRUE
    ) THEN
        RAISE EXCEPTION 'Missing explicit allow: rollout must not proceed';
    END IF;
END $$;
COMMIT;
```

The seed is idempotent and never changes an existing deny. Any assertion failure
aborts the transaction; stop the rollout and reconcile the manifest. Save the
insert count and assertion results with the owner-approved inventory. Validate
UUID generation availability during rehearsal; do not install extensions as part
of this procedure.

## Deploy and verify

Deploy the permission-check change only after the seed succeeds. Allow the
60-second permission cache to expire on every API replica (or restart replicas
through the normal deployment), and refresh signed policy artifacts through the
existing policy delivery procedure. Direct SQL does not invalidate API caches.
Verify one intended allow and one unlisted/explicitly denied tool per tenant via
the control plane and gateway, including both cold and warm cache checks. For
unscoped calls, review duplicate tool names with conflicting server permissions.
Release the change freeze only after these checks succeed.

If verification fails, halt rollout and restore the previous application through
the standard rollback procedure. Retain seed rows for investigation; reverting
the application restores its previous default-allow behavior and therefore needs
security review. Do not bulk-delete seed rows: rows may since have been reviewed
or changed, and deletion under the new check revokes access. Future tenants and
new tools must receive explicit reviewed allows before use.
