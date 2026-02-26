"""OAuth client model for SCIM→Roles protocol mapper + DCR automation (CAB-1483).

Tracks Keycloak OIDC clients registered via the DCR onboarding API.
Each client has SCIM-derived product_roles embedded as JWT claims
via Keycloak protocol mappers.
"""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class OAuthClientStatus(enum.StrEnum):
    """Lifecycle status of a registered OAuth client."""

    ACTIVE = "active"
    REVOKED = "revoked"
    PENDING = "pending"


class OAuthClient(Base):
    """Registered OAuth client with SCIM-derived product_roles.

    Created via DCR onboarding API. The product_roles field stores
    the SCIM group→role mapping applied as a Keycloak protocol mapper
    (oidc-hardcoded-claim-mapper) on the client's access tokens.
    """

    __tablename__ = "oauth_clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Keycloak reference
    keycloak_client_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    keycloak_uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Client metadata
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SCIM-derived roles — JSON array of role strings embedded in JWT via protocol mapper
    product_roles: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=list)

    # OAuth metadata — grant types, redirect URIs, etc.
    oauth_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Vault secret path reference (secret itself never stored in DB)
    vault_secret_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OAuthClientStatus.ACTIVE.value)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_oauth_client_tenant", "tenant_id"),
        Index("idx_oauth_client_status", "status"),
        Index("idx_oauth_client_kc_client_id", "keycloak_client_id"),
    )

    def __repr__(self) -> str:
        return f"<OAuthClient {self.keycloak_client_id} tenant={self.tenant_id} status={self.status}>"
