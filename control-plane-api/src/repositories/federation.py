"""Repository for federation master/sub-account CRUD (CAB-1313/CAB-1361/CAB-1370)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.federation import (
    MasterAccount,
    MasterAccountStatus,
    SubAccount,
    SubAccountStatus,
    SubAccountTool,
)


class MasterAccountRepository:
    """Repository for master account database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, master: MasterAccount) -> MasterAccount:
        self.session.add(master)
        await self.session.flush()
        await self.session.refresh(master)
        return master

    async def get_by_id(self, account_id: UUID) -> MasterAccount | None:
        result = await self.session.execute(select(MasterAccount).where(MasterAccount.id == account_id))
        return result.scalar_one_or_none()

    async def get_by_tenant_and_name(self, tenant_id: str, name: str) -> MasterAccount | None:
        result = await self.session.execute(
            select(MasterAccount).where(and_(MasterAccount.tenant_id == tenant_id, MasterAccount.name == name))
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        status: MasterAccountStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MasterAccount], int]:
        query = select(MasterAccount).where(MasterAccount.tenant_id == tenant_id)

        if status:
            query = query.where(MasterAccount.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(MasterAccount.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()
        return list(items), total

    async def update(self, master: MasterAccount) -> MasterAccount:
        await self.session.flush()
        await self.session.refresh(master)
        return master

    async def delete(self, master: MasterAccount) -> None:
        await self.session.delete(master)
        await self.session.flush()

    async def count_sub_accounts(self, master_id: UUID) -> int:
        result = await self.session.execute(select(func.count()).where(SubAccount.master_account_id == master_id))
        return result.scalar_one()


class SubAccountRepository:
    """Repository for sub-account database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, sub: SubAccount) -> SubAccount:
        self.session.add(sub)
        await self.session.flush()
        await self.session.refresh(sub)
        return sub

    async def get_by_id(self, sub_id: UUID) -> SubAccount | None:
        result = await self.session.execute(select(SubAccount).where(SubAccount.id == sub_id))
        return result.scalar_one_or_none()

    async def get_by_master_and_name(self, master_id: UUID, name: str) -> SubAccount | None:
        result = await self.session.execute(
            select(SubAccount).where(and_(SubAccount.master_account_id == master_id, SubAccount.name == name))
        )
        return result.scalar_one_or_none()

    async def list_by_master(
        self,
        master_id: UUID,
        status: SubAccountStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SubAccount], int]:
        query = select(SubAccount).where(SubAccount.master_account_id == master_id)

        if status:
            query = query.where(SubAccount.status == status)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(SubAccount.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        items = result.scalars().all()
        return list(items), total

    async def get_by_key_prefix(self, prefix: str) -> SubAccount | None:
        result = await self.session.execute(select(SubAccount).where(SubAccount.api_key_prefix == prefix))
        return result.scalar_one_or_none()

    async def update(self, sub: SubAccount) -> SubAccount:
        await self.session.flush()
        await self.session.refresh(sub)
        return sub

    # ============== CAB-1370: Bulk Revoke + Tool Allow-List ==============

    async def bulk_revoke(self, master_id: UUID) -> tuple[int, int]:
        """Revoke all active/suspended sub-accounts under a master."""
        already_q = select(func.count()).where(
            and_(
                SubAccount.master_account_id == master_id,
                SubAccount.status == SubAccountStatus.REVOKED,
            )
        )
        already_result = await self.session.execute(already_q)
        already_revoked = already_result.scalar_one()

        stmt = (
            update(SubAccount)
            .where(
                and_(
                    SubAccount.master_account_id == master_id,
                    SubAccount.status.in_([SubAccountStatus.ACTIVE, SubAccountStatus.SUSPENDED]),
                )
            )
            .values(
                status=SubAccountStatus.REVOKED,
                api_key_hash=None,
                updated_at=datetime.utcnow(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount, already_revoked

    async def set_tool_allow_list(self, sub_id: UUID, tool_names: list[str]) -> list[str]:
        """Replace the tool allow-list for a sub-account."""
        await self.session.execute(delete(SubAccountTool).where(SubAccountTool.sub_account_id == sub_id))
        unique_tools = sorted(set(tool_names))
        for tool_name in unique_tools:
            self.session.add(SubAccountTool(sub_account_id=sub_id, tool_name=tool_name))
        await self.session.flush()
        return unique_tools

    async def get_tool_allow_list(self, sub_id: UUID) -> list[str]:
        """Get sorted tool names for a sub-account."""
        result = await self.session.execute(
            select(SubAccountTool.tool_name)
            .where(SubAccountTool.sub_account_id == sub_id)
            .order_by(SubAccountTool.tool_name)
        )
        return list(result.scalars().all())
