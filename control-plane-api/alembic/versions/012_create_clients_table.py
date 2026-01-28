"""Create clients table for mTLS API Client Certificate Provisioning.

Revision ID: 012
Revises: 011
Create Date: 2026-01-28

CAB-865: mTLS API Client Certificate Provisioning

Creates table for API clients with optional mTLS certificates:
- clients: API clients with auth_type (oauth2, mtls, mtls_oauth2)
- Certificate metadata stored (NO private key)
- Soft delete support via deleted_at
- Partial unique index on tenant_id + name for active clients
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create auth_type enum
    auth_type_enum = postgresql.ENUM(
        'oauth2', 'mtls', 'mtls_oauth2',
        name='auth_type_enum',
        create_type=False
    )
    auth_type_enum.create(op.get_bind(), checkfirst=True)

    # Create client_status enum
    client_status_enum = postgresql.ENUM(
        'active', 'suspended', 'revoked',
        name='client_status_enum',
        create_type=False
    )
    client_status_enum.create(op.get_bind(), checkfirst=True)

    # Create clients table
    op.create_table(
        'clients',
        # Primary key
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text('gen_random_uuid()'),
            comment='Unique client identifier'
        ),

        # Tenant isolation
        sa.Column(
            'tenant_id',
            sa.String(64),
            nullable=False,
            comment='Tenant ID - always from JWT, never from body'
        ),

        # Client identity
        sa.Column(
            'name',
            sa.String(100),
            nullable=False,
            comment='Client name - unique per tenant'
        ),
        sa.Column(
            'description',
            sa.String(500),
            nullable=True,
            comment='Optional description'
        ),

        # Authentication
        sa.Column(
            'auth_type',
            auth_type_enum,
            nullable=False,
            server_default='oauth2',
            comment='Authentication method'
        ),

        # Status
        sa.Column(
            'status',
            client_status_enum,
            nullable=False,
            server_default='active',
            comment='Client lifecycle status'
        ),

        # Certificate metadata (NO private key)
        sa.Column(
            'certificate_fingerprint_sha256',
            sa.String(128),
            nullable=True,
            comment='SHA256 fingerprint for identification'
        ),
        sa.Column(
            'certificate_serial',
            sa.String(128),
            nullable=True,
            comment='Certificate serial number (hex)'
        ),
        sa.Column(
            'certificate_subject',
            sa.String(256),
            nullable=True,
            comment='Certificate subject DN'
        ),
        sa.Column(
            'certificate_issuer',
            sa.String(256),
            nullable=True,
            comment='Certificate issuer DN'
        ),
        sa.Column(
            'certificate_valid_from',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Certificate not_before'
        ),
        sa.Column(
            'certificate_valid_until',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Certificate not_after'
        ),
        sa.Column(
            'certificate_revoked_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When certificate was revoked'
        ),
        sa.Column(
            'certificate_revoked_by',
            sa.String(255),
            nullable=True,
            comment='Who revoked the certificate'
        ),
        sa.Column(
            'certificate_revocation_reason',
            sa.String(500),
            nullable=True,
            comment='Why certificate was revoked'
        ),

        # Vault reference
        sa.Column(
            'vault_pki_serial',
            sa.String(128),
            nullable=True,
            comment='Vault PKI serial for revocation API'
        ),

        # Audit trail
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='Creation timestamp'
        ),
        sa.Column(
            'created_by',
            sa.String(255),
            nullable=False,
            comment='User who created the client'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Last update timestamp'
        ),
        sa.Column(
            'updated_by',
            sa.String(255),
            nullable=True,
            comment='User who last updated'
        ),

        # Soft delete
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Soft delete timestamp - null means active'
        ),
        sa.Column(
            'deleted_by',
            sa.String(255),
            nullable=True,
            comment='User who deleted'
        ),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        comment='API Clients with optional mTLS certificates (CAB-865)'
    )

    # Indexes
    op.create_index('ix_clients_tenant_id', 'clients', ['tenant_id'])
    op.create_index('ix_clients_status', 'clients', ['status'])
    op.create_index('ix_clients_deleted_at', 'clients', ['deleted_at'])

    # Unique index on certificate fingerprint
    op.create_index(
        'ix_clients_certificate_fingerprint_sha256',
        'clients',
        ['certificate_fingerprint_sha256'],
        unique=True,
        postgresql_where=sa.text('certificate_fingerprint_sha256 IS NOT NULL')
    )

    # Unique index on certificate serial
    op.create_index(
        'ix_clients_certificate_serial',
        'clients',
        ['certificate_serial'],
        unique=True,
        postgresql_where=sa.text('certificate_serial IS NOT NULL')
    )

    # Index for certificate expiration monitoring
    op.create_index(
        'ix_clients_cert_expiry',
        'clients',
        ['certificate_valid_until'],
        postgresql_where=sa.text('certificate_valid_until IS NOT NULL')
    )

    # Partial unique index: unique name per tenant for active (non-deleted) clients
    op.create_index(
        'ix_clients_tenant_name_active',
        'clients',
        ['tenant_id', 'name'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL')
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_clients_tenant_name_active', 'clients')
    op.drop_index('ix_clients_cert_expiry', 'clients')
    op.drop_index('ix_clients_certificate_serial', 'clients')
    op.drop_index('ix_clients_certificate_fingerprint_sha256', 'clients')
    op.drop_index('ix_clients_deleted_at', 'clients')
    op.drop_index('ix_clients_status', 'clients')
    op.drop_index('ix_clients_tenant_id', 'clients')

    # Drop table
    op.drop_table('clients')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS client_status_enum')
    op.execute('DROP TYPE IF EXISTS auth_type_enum')
