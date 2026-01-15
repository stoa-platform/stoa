"""Create contracts and protocol bindings tables

Revision ID: 007_contracts_bindings
Revises: 006_mcp_snapshots
Create Date: 2026-01-15

UAC Protocol Switcher: Universal API Contracts with multi-protocol bindings.
Allows defining an API once and exposing via REST, GraphQL, gRPC, MCP, Kafka.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '007_contracts_bindings'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ProtocolType enum
    op.execute("CREATE TYPE protocoltype AS ENUM ('rest', 'graphql', 'grpc', 'mcp', 'kafka')")

    # Create contracts table
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', sa.String(255), nullable=False, index=True),

        # Contract identification
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('version', sa.String(50), nullable=False, default='1.0.0'),

        # Contract status
        sa.Column('status', sa.String(50), nullable=False, default='draft'),

        # OpenAPI/Schema reference
        sa.Column('openapi_spec_url', sa.String(512), nullable=True),
        sa.Column('schema_hash', sa.String(64), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.String(255), nullable=True),
    )

    # Create composite indexes for contracts
    op.create_index('ix_contracts_tenant_name', 'contracts', ['tenant_id', 'name'], unique=True)
    op.create_index('ix_contracts_tenant_status', 'contracts', ['tenant_id', 'status'])

    # Create protocol_bindings table
    op.create_table(
        'protocol_bindings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'contract_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('contracts.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'protocol',
            postgresql.ENUM('rest', 'graphql', 'grpc', 'mcp', 'kafka', name='protocoltype', create_type=False),
            nullable=False,
        ),
        sa.Column('enabled', sa.Boolean, nullable=False, default=False),

        # Protocol-specific endpoint info
        sa.Column('endpoint', sa.String(512), nullable=True),
        sa.Column('playground_url', sa.String(512), nullable=True),

        # MCP-specific fields
        sa.Column('tool_name', sa.String(255), nullable=True),

        # GraphQL-specific fields
        sa.Column('operations', sa.Text, nullable=True),

        # gRPC-specific fields
        sa.Column('proto_file_url', sa.String(512), nullable=True),

        # Kafka-specific fields
        sa.Column('topic_name', sa.String(255), nullable=True),

        # Generation metadata
        sa.Column('generated_at', sa.DateTime, nullable=True),
        sa.Column('generation_error', sa.Text, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # Create composite unique index for bindings (one binding per protocol per contract)
    op.create_index(
        'ix_bindings_contract_protocol',
        'protocol_bindings',
        ['contract_id', 'protocol'],
        unique=True,
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table('protocol_bindings')
    op.drop_table('contracts')

    # Drop enum
    op.execute('DROP TYPE protocoltype')
