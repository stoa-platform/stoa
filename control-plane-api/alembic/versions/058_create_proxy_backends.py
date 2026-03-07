"""create proxy_backends table

Revision ID: 058
Revises: 057
Create Date: 2026-03-06

CAB-1725: Backend registry model for STOA Gateway API proxy (dogfooding).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "058_create_proxy_backends"
down_revision: str | None = "057_seed_gateway_instances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    proxy_backend_auth_type_enum = sa.Enum(
        "api_key",
        "bearer",
        "basic",
        "oauth2_cc",
        name="proxy_backend_auth_type_enum",
    )

    proxy_backend_status_enum = sa.Enum(
        "active",
        "disabled",
        name="proxy_backend_status_enum",
    )

    op.create_table(
        "proxy_backends",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("base_url", sa.String(2048), nullable=False),
        sa.Column("health_endpoint", sa.String(512), nullable=True),
        sa.Column(
            "auth_type",
            proxy_backend_auth_type_enum,
            nullable=False,
            server_default="api_key",
        ),
        sa.Column("credential_ref", sa.String(255), nullable=True),
        sa.Column("rate_limit_rpm", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "circuit_breaker_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "fallback_direct",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("timeout_secs", sa.Integer, nullable=False, server_default="30"),
        sa.Column(
            "status",
            proxy_backend_status_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_proxy_backends_status", "proxy_backends", ["status"])
    op.create_index("ix_proxy_backends_active", "proxy_backends", ["is_active"])

    # Seed the 8 initial backends (STOA dogfooding targets)
    op.execute(
        sa.text("""
        INSERT INTO proxy_backends (name, display_name, base_url, health_endpoint, auth_type, credential_ref, rate_limit_rpm)
        VALUES
            ('n8n', 'n8n Workflow Automation', 'https://n8n.gostoa.dev', '/healthz', 'api_key', 'api-proxy:n8n', 60),
            ('linear', 'Linear Project Management', 'https://api.linear.app', '/', 'bearer', 'api-proxy:linear', 120),
            ('github', 'GitHub API', 'https://api.github.com', '/', 'bearer', 'api-proxy:github', 300),
            ('slack-bot', 'Slack Bot API', 'https://slack.com/api', '/api.test', 'bearer', 'api-proxy:slack-bot', 120),
            ('slack-webhook', 'Slack Incoming Webhook', 'https://hooks.slack.com', NULL, 'bearer', 'api-proxy:slack-webhook', 30),
            ('infisical', 'Infisical Secrets Manager', 'https://vault.gostoa.dev', '/api/status', 'bearer', 'api-proxy:infisical', 60),
            ('cloudflare', 'Cloudflare API', 'https://api.cloudflare.com/client/v4', NULL, 'bearer', 'api-proxy:cloudflare', 120),
            ('pushgateway', 'Prometheus Pushgateway', 'https://pushgateway.gostoa.dev', NULL, 'basic', 'api-proxy:pushgateway', 60)
        ON CONFLICT (name) DO NOTHING
        """)
    )


def downgrade() -> None:
    op.drop_index("ix_proxy_backends_active", table_name="proxy_backends")
    op.drop_index("ix_proxy_backends_status", table_name="proxy_backends")
    op.drop_table("proxy_backends")

    # Drop enums
    sa.Enum(name="proxy_backend_auth_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="proxy_backend_status_enum").drop(op.get_bind(), checkfirst=True)
