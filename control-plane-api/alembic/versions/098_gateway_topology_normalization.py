"""gateway topology normalization

Revision ID: 098_gateway_topology_normalization
Revises: 097_add_catalog_content_hash
Create Date: 2026-05-01

Spec refs:
- specs/gateway-topology-normalization.md
- specs/gateway-sidecar-contract.md

CAB-2173 separates the STOA runtime mode from the deployment topology:
`mode=sidecar` can expose /authz, but `deployment_mode=sidecar` is reserved
for proven same-pod Kubernetes sidecars. Existing unproven link rows are
therefore backfilled as `connect/remote-agent`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "098_gateway_topology_normalization"
down_revision: str | tuple[str, ...] | None = "097_add_catalog_content_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gateway_instances",
        sa.Column(
            "endpoints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("gateway_instances", sa.Column("deployment_mode", sa.String(length=32), nullable=True))
    op.add_column("gateway_instances", sa.Column("target_gateway_type", sa.String(length=64), nullable=True))
    op.add_column("gateway_instances", sa.Column("topology", sa.String(length=64), nullable=True))

    op.create_index("ix_gateway_instances_deployment_mode", "gateway_instances", ["deployment_mode"])
    op.create_index("ix_gateway_instances_target_gateway_type", "gateway_instances", ["target_gateway_type"])
    op.create_index("ix_gateway_instances_topology", "gateway_instances", ["topology"])

    conn = op.get_bind()

    conn.execute(
        sa.text("""
            UPDATE gateway_instances
            SET
              target_gateway_type = CASE
                WHEN gateway_type IN ('webmethods', 'kong', 'gravitee', 'apigee', 'aws_apigateway', 'azure_apim')
                  THEN gateway_type
                WHEN name ILIKE '%agentgateway%' OR base_url ILIKE '%agentgateway%' THEN 'agentgateway'
                WHEN name ILIKE '%gravitee%' OR base_url ILIKE '%gravitee%' THEN 'gravitee'
                WHEN name ILIKE '%webmethods%' OR name ILIKE '%vps-wm%' OR name ILIKE '%stoa-link-wm%'
                  OR base_url ILIKE '%webmethods%' OR target_gateway_url ILIKE '%webmethods%' THEN 'webmethods'
                WHEN name ILIKE '%kong%' OR base_url ILIKE '%kong%' THEN 'kong'
                ELSE 'stoa'
              END,
              deployment_mode = CASE
                WHEN mode IN ('edge-mcp', 'edge', 'mcp') OR gateway_type = 'stoa_edge_mcp' THEN 'edge'
                ELSE 'connect'
              END,
              topology = CASE
                WHEN mode IN ('edge-mcp', 'edge', 'mcp') OR gateway_type = 'stoa_edge_mcp' THEN 'native-edge'
                ELSE 'remote-agent'
              END,
              endpoints = jsonb_strip_nulls(
                jsonb_build_object(
                  'public_url', public_url,
                  'admin_url', base_url,
                  'internal_url', CASE
                    WHEN base_url LIKE 'http://%.svc.cluster.local%' THEN base_url
                    ELSE NULL
                  END,
                  'health_url', CASE
                    WHEN base_url IS NOT NULL THEN concat(rtrim(base_url, '/'), '/health')
                    ELSE NULL
                  END,
                  'ui_url', ui_url
                )
              ),
              updated_at = NOW()
            WHERE deleted_at IS NULL
        """)
    )

    # Known prod edge rows should converge on one logical GatewayInstance with
    # public + internal endpoints. We do not delete possible duplicate rows here;
    # GitOps reconciliation owns that lifecycle after desired state lands.
    conn.execute(
        sa.text("""
            UPDATE gateway_instances
            SET
              deployment_mode = 'edge',
              target_gateway_type = 'stoa',
              topology = 'native-edge',
              endpoints = endpoints || jsonb_strip_nulls(
                jsonb_build_object(
                  'public_url', COALESCE(public_url, 'https://mcp.gostoa.dev'),
                  'internal_url', 'http://stoa-gateway.stoa-system.svc.cluster.local:80',
                  'admin_url', COALESCE(base_url, 'http://stoa-gateway.stoa-system.svc.cluster.local:80'),
                  'health_url', 'http://stoa-gateway.stoa-system.svc.cluster.local:80/health'
                )
              ),
              updated_at = NOW()
            WHERE deleted_at IS NULL
              AND (
                name IN ('stoa-gateway-prod', 'stoa-gateway-production', 'stoa-prod')
                OR public_url = 'https://mcp.gostoa.dev'
                OR base_url LIKE '%stoa-gateway.stoa-system.svc.cluster.local%'
              )
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_gateway_instances_topology", table_name="gateway_instances")
    op.drop_index("ix_gateway_instances_target_gateway_type", table_name="gateway_instances")
    op.drop_index("ix_gateway_instances_deployment_mode", table_name="gateway_instances")
    op.drop_column("gateway_instances", "topology")
    op.drop_column("gateway_instances", "target_gateway_type")
    op.drop_column("gateway_instances", "deployment_mode")
    op.drop_column("gateway_instances", "endpoints")
