"""Repository for credential mapping CRUD operations (CAB-1432)."""

import logging
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.credential_mapping import CredentialMapping
from src.services.encryption_service import decrypt_auth_config, encrypt_auth_config

logger = logging.getLogger(__name__)


class CredentialMappingRepository:
    """Repository for credential mapping database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, mapping: CredentialMapping) -> CredentialMapping:
        """Create a new credential mapping."""
        self.session.add(mapping)
        await self.session.flush()
        await self.session.refresh(mapping)
        return mapping

    async def get_by_id(self, mapping_id: UUID) -> CredentialMapping | None:
        """Get credential mapping by ID."""
        result = await self.session.execute(select(CredentialMapping).where(CredentialMapping.id == mapping_id))
        return result.scalar_one_or_none()

    async def get_by_consumer_and_api(self, consumer_id: UUID, api_id: str) -> CredentialMapping | None:
        """Get mapping by consumer + API (unique pair)."""
        result = await self.session.execute(
            select(CredentialMapping).where(
                and_(
                    CredentialMapping.consumer_id == consumer_id,
                    CredentialMapping.api_id == api_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        consumer_id: UUID | None = None,
        api_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[CredentialMapping], int]:
        """List credential mappings for a tenant with optional filters."""
        query = select(CredentialMapping).where(CredentialMapping.tenant_id == tenant_id)

        if consumer_id:
            query = query.where(CredentialMapping.consumer_id == consumer_id)
        if api_id:
            query = query.where(CredentialMapping.api_id == api_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(CredentialMapping.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        mappings = result.scalars().all()

        return list(mappings), total

    async def update(self, mapping: CredentialMapping) -> CredentialMapping:
        """Update a credential mapping (caller sets fields before calling)."""
        from datetime import datetime

        mapping.updated_at = datetime.utcnow()  # type: ignore[assignment]
        await self.session.flush()
        await self.session.refresh(mapping)
        return mapping

    async def delete(self, mapping: CredentialMapping) -> None:
        """Hard delete a credential mapping."""
        await self.session.delete(mapping)
        await self.session.flush()

    async def list_active_for_sync(self, tenant_id: str) -> list[dict]:
        """List active mappings with decrypted values for gateway sync.

        Returns list of dicts with plaintext credential values.
        Only used by the STOA adapter sync endpoint (admin-only).
        """
        query = (
            select(CredentialMapping)
            .where(
                and_(
                    CredentialMapping.tenant_id == tenant_id,
                    CredentialMapping.is_active.is_(True),
                )
            )
            .order_by(CredentialMapping.created_at.asc())
        )
        result = await self.session.execute(query)
        mappings = result.scalars().all()

        sync_items = []
        for m in mappings:
            try:
                decrypted = decrypt_auth_config(m.encrypted_value)  # type: ignore[arg-type]
                credential_value = decrypted.get("value", "")
            except (ValueError, Exception):
                logger.warning("Failed to decrypt credential mapping %s, skipping", m.id)
                continue

            sync_items.append(
                {
                    "consumer_id": str(m.consumer_id),
                    "api_id": m.api_id,
                    "auth_type": m.auth_type.value if hasattr(m.auth_type, "value") else str(m.auth_type),
                    "header_name": m.header_name,
                    "header_value": credential_value,
                }
            )

        return sync_items

    @staticmethod
    def encrypt_credential(value: str) -> str:
        """Encrypt a credential value for storage."""
        return encrypt_auth_config({"value": value})
