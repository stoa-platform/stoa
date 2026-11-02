"""API key model. Only the SHA-256 hash is persisted."""

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.models.base import Base, TimestampMixin, UUIDMixin


class ApiKey(Base, UUIDMixin, TimestampMixin):
    """Credential used to call list and admin endpoints.

    `key_hash` is the SHA-256 hex digest of the secret. The plaintext is
    returned once by the create endpoint and is not stored.
    """

    __tablename__ = "api_keys"

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("uq_api_keys_key_hash", "key_hash", unique=True),
        Index("idx_api_keys_tenant", "tenant_id"),
    )
