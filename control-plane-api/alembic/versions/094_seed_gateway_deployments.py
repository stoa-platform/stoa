"""Seed gateway_deployments for catalog APIs with target_gateways (CAB-2034).

Migrations 074/075 seeded 12 APIs into api_catalog with
target_gateways = '["stoa-gateway-prod"]' but never created
gateway_deployments rows. Without deployments, the gateway route
table stays empty and the traffic seeder gets 100% 404s.

This migration creates a PENDING deployment for each api_catalog
entry whose target_gateways references a live gateway instance,
so the SyncEngine picks them up on the next reconciliation cycle.

Idempotent: skips APIs that already have a deployment on the
target gateway (ON CONFLICT DO NOTHING).

Revision ID: 094
Revises: 093
Create Date: 2026-04-09
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "094_seed_gateway_deployments"
down_revision = "093_add_security_posture_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find all api_catalog entries with non-empty target_gateways
    apis = conn.execute(sa.text("""
            SELECT id, api_id, api_name, version, tenant_id, metadata, target_gateways
            FROM api_catalog
            WHERE deleted_at IS NULL
              AND target_gateways IS NOT NULL
              AND target_gateways != '[]'::jsonb
        """)).fetchall()

    if not apis:
        print("No APIs with target_gateways found — skipping")
        return

    # Build a map of gateway name → ID
    gateways = conn.execute(sa.text("""
            SELECT id, name FROM gateway_instances
            WHERE deleted_at IS NULL
        """)).fetchall()
    gw_map = {row[1]: str(row[0]) for row in gateways}

    inserted = 0
    for api in apis:
        api_id_uuid = str(api[0])
        api_id = api[1]
        api_name = api[2]
        version = api[3]
        tenant_id = api[4]
        metadata = api[5] if isinstance(api[5], dict) else json.loads(api[5]) if api[5] else {}
        target_gateways = api[6] if isinstance(api[6], list) else json.loads(api[6]) if api[6] else []

        backend_url = metadata.get("backend_url", "")
        methods = metadata.get("methods", ["GET"])

        for gw_name in target_gateways:
            gw_id = gw_map.get(gw_name)
            if not gw_id:
                print(f"  SKIP {api_name}: gateway '{gw_name}' not found")
                continue

            desired_state = json.dumps(
                {
                    "api_catalog_id": api_id_uuid,
                    "api_id": api_id,
                    "api_name": api_name,
                    "version": version,
                    "tenant_id": tenant_id,
                    "backend_url": backend_url,
                    "methods": methods,
                    "activated": True,
                }
            )

            result = conn.execute(
                sa.text("""
                    INSERT INTO gateway_deployments
                        (id, api_catalog_id, gateway_instance_id, desired_state,
                         desired_at, sync_status, sync_attempts)
                    VALUES
                        (gen_random_uuid(), :api_catalog_id, :gateway_id,
                         :desired_state::jsonb, NOW(), 'pending', 0)
                    ON CONFLICT ON CONSTRAINT uq_deployment_api_gateway DO NOTHING
                """),
                {
                    "api_catalog_id": api_id_uuid,
                    "gateway_id": gw_id,
                    "desired_state": desired_state,
                },
            )
            if result.rowcount > 0:
                inserted += 1
                print(f"  CREATED deployment: {api_name} → {gw_name}")
            else:
                print(f"  EXISTS: {api_name} → {gw_name}")

    print(f"\nSeeded {inserted} gateway deployments")


def downgrade() -> None:
    # Remove only the seeded deployments (those with demo tenant APIs)
    op.execute(sa.text("""
            DELETE FROM gateway_deployments
            WHERE api_catalog_id IN (
                SELECT id FROM api_catalog WHERE tenant_id = 'demo'
            )
            AND sync_status = 'pending'
        """))
