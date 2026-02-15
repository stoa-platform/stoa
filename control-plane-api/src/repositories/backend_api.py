"""Repository for backend API and scoped API key CRUD (CAB-1188/CAB-1249)."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.backend_api import BackendApi, BackendApiStatus
from src.models.saas_api_key import SaasApiKey, SaasApiKeyStatus


class BackendApiRepository:
    """Repository for backend API database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, backend_api: BackendApi) -> BackendApi:
        self.session.add(backend_api)
        await self.session.flush()
        await self.session.refresh(backend_api)
        return backend_api

    async def get_by_id(self, api_id: UUID) -> BackendApi | None:
        result = await self.session.execute(select(BackendApi).where(BackendApi.id == api_id))
        return result.scalar_one_or_none()

    async def get_by_tenant_and_name(self, tenant_id: str, name: str) -> BackendApi | None:
        result = await self.session.execute(
            select(BackendApi).where(and_(BackendApi.tenant_id == tenant_id, BackendApi.name == name))
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: BackendApiStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[BackendApi], int]:
        query = select(BackendApi).where(BackendApi.tenant_id == tenant_id)

        if status:
            query = query.where(BackendApi.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(BackendApi.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()
        return list(items), total

    async def update(self, backend_api: BackendApi) -> BackendApi:
        await self.session.flush()
        await self.session.refresh(backend_api)
        return backend_api

    async def delete(self, backend_api: BackendApi) -> None:
        await self.session.delete(backend_api)
        await self.session.flush()

    async def delete_all_by_tenant(self, tenant_id: str) -> int:
        """Delete all backend APIs for a tenant (GDPR purge)."""
        query = select(BackendApi).where(BackendApi.tenant_id == tenant_id)
        result = await self.session.execute(query)
        items = result.scalars().all()
        count = len(items)
        for item in items:
            await self.session.delete(item)
        if count:
            await self.session.flush()
        return count


class SaasApiKeyRepository:
    """Repository for scoped API key database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, api_key: SaasApiKey) -> SaasApiKey:
        self.session.add(api_key)
        await self.session.flush()
        await self.session.refresh(api_key)
        return api_key

    async def get_by_id(self, key_id: UUID) -> SaasApiKey | None:
        result = await self.session.execute(select(SaasApiKey).where(SaasApiKey.id == key_id))
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> SaasApiKey | None:
        result = await self.session.execute(select(SaasApiKey).where(SaasApiKey.key_hash == key_hash))
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: SaasApiKeyStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SaasApiKey], int]:
        query = select(SaasApiKey).where(SaasApiKey.tenant_id == tenant_id)

        if status:
            query = query.where(SaasApiKey.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(SaasApiKey.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()
        return list(items), total

    async def update(self, api_key: SaasApiKey) -> SaasApiKey:
        await self.session.flush()
        await self.session.refresh(api_key)
        return api_key

    async def delete_all_by_tenant(self, tenant_id: str) -> int:
        """Delete all API keys for a tenant (GDPR purge)."""
        query = select(SaasApiKey).where(SaasApiKey.tenant_id == tenant_id)
        result = await self.session.execute(query)
        items = result.scalars().all()
        count = len(items)
        for item in items:
            await self.session.delete(item)
        if count:
            await self.session.flush()
        return count
