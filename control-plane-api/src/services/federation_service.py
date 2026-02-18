"""Federation service — orchestrates repos, KC helper, key generation (CAB-1313/CAB-1361/CAB-1370)."""

import hashlib
import logging
import secrets
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.federation import MasterAccount, MasterAccountStatus, SubAccount, SubAccountStatus
from ..repositories.federation import MasterAccountRepository, SubAccountRepository
from ..services.keycloak_service import keycloak_service

logger = logging.getLogger(__name__)


def _generate_federation_key() -> tuple[str, str, str]:
    """Generate a federation API key.

    Returns:
        (plaintext_key, sha256_hash, key_prefix)
    """
    random_part = secrets.token_hex(32)
    prefix_hex = secrets.token_hex(2)
    prefix = f"stoa_fed_{prefix_hex}"
    plaintext = f"{prefix}_{random_part}"
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    return plaintext, key_hash, prefix


class FederationService:
    """Business logic for federation master/sub-account lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.master_repo = MasterAccountRepository(db)
        self.sub_repo = SubAccountRepository(db)

    async def create_master_account(
        self,
        tenant_id: str,
        name: str,
        display_name: str | None,
        description: str | None,
        max_sub_accounts: int,
        quota_config: dict | None,
        created_by: str | None,
    ) -> MasterAccount:
        existing = await self.master_repo.get_by_tenant_and_name(tenant_id, name)
        if existing:
            raise ValueError(f"Master account '{name}' already exists in this tenant")

        master = MasterAccount(
            tenant_id=tenant_id,
            name=name,
            display_name=display_name,
            description=description,
            max_sub_accounts=max_sub_accounts,
            quota_config=quota_config,
            created_by=created_by,
        )
        master = await self.master_repo.create(master)
        logger.info("Master account created: %s/%s", tenant_id, name)
        return master

    async def get_master_account(self, account_id: UUID) -> MasterAccount | None:
        return await self.master_repo.get_by_id(account_id)

    async def list_master_accounts(
        self,
        tenant_id: str,
        status: MasterAccountStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MasterAccount], int]:
        return await self.master_repo.list_by_tenant(tenant_id, status=status, page=page, page_size=page_size)

    async def update_master_account(self, master: MasterAccount, updates: dict) -> MasterAccount:
        for field, value in updates.items():
            setattr(master, field, value)
        master.updated_at = datetime.utcnow()
        return await self.master_repo.update(master)

    async def delete_master_account(self, master: MasterAccount) -> None:
        await self.master_repo.delete(master)
        logger.info("Master account deleted: %s/%s", master.tenant_id, master.name)

    async def count_sub_accounts(self, master_id: UUID) -> int:
        return await self.master_repo.count_sub_accounts(master_id)

    async def create_sub_account(
        self,
        master: MasterAccount,
        name: str,
        display_name: str | None,
        account_type: str,
        created_by: str | None,
    ) -> tuple[SubAccount, str]:
        """Create a sub-account with API key and optional KC client.

        Returns:
            (sub_account, plaintext_key)
        """
        existing = await self.sub_repo.get_by_master_and_name(master.id, name)
        if existing:
            raise ValueError(f"Sub-account '{name}' already exists in this master account")

        current_count = await self.master_repo.count_sub_accounts(master.id)
        if current_count >= master.max_sub_accounts:
            raise ValueError(f"Master account has reached its sub-account limit ({master.max_sub_accounts})")

        plaintext, key_hash, prefix = _generate_federation_key()

        sub = SubAccount(
            master_account_id=master.id,
            tenant_id=master.tenant_id,
            name=name,
            display_name=display_name,
            account_type=account_type,
            api_key_hash=key_hash,
            api_key_prefix=prefix,
            created_by=created_by,
        )

        # Best-effort KC Token Exchange client setup
        kc_client_id = await keycloak_service.setup_federation_client(
            sub_account_id=str(sub.id),
            master_account_id=str(master.id),
            tenant_id=master.tenant_id,
        )
        if kc_client_id:
            sub.kc_client_id = kc_client_id

        sub = await self.sub_repo.create(sub)
        logger.info("Sub-account created: %s/%s (type=%s)", master.name, name, account_type)
        return sub, plaintext

    async def get_sub_account(self, sub_id: UUID) -> SubAccount | None:
        return await self.sub_repo.get_by_id(sub_id)

    async def list_sub_accounts(
        self,
        master_id: UUID,
        status: SubAccountStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SubAccount], int]:
        return await self.sub_repo.list_by_master(master_id, status=status, page=page, page_size=page_size)

    async def update_sub_account(self, sub: SubAccount, updates: dict) -> SubAccount:
        for field, value in updates.items():
            setattr(sub, field, value)
        sub.updated_at = datetime.utcnow()
        return await self.sub_repo.update(sub)

    async def revoke_sub_account(self, sub: SubAccount) -> SubAccount:
        sub.status = SubAccountStatus.REVOKED
        sub.api_key_hash = None
        sub.updated_at = datetime.utcnow()
        sub = await self.sub_repo.update(sub)
        logger.info("Sub-account revoked: %s", sub.name)
        return sub

    # ============== CAB-1370: Delegation Token + Usage + Bulk Ops ==============

    async def delegate_token(self, sub: SubAccount, scopes: list[str], ttl_seconds: int) -> dict:
        """Exchange a sub-account's KC client credentials for a delegation token."""
        if sub.status != SubAccountStatus.ACTIVE:
            raise ValueError(f"Sub-account '{sub.name}' is not active (status={sub.status})")
        if not sub.kc_client_id:
            raise ValueError(f"Sub-account '{sub.name}' has no Keycloak client configured")

        token_data = await keycloak_service.exchange_federation_token(
            client_id=sub.kc_client_id, scopes=scopes, ttl_seconds=ttl_seconds
        )
        if not token_data:
            raise ValueError(f"Token exchange failed for sub-account '{sub.name}'")

        logger.info("Delegation token issued for sub-account %s", sub.name)
        return token_data

    async def get_usage_aggregation(self, master_id: UUID, period_days: int) -> list[dict]:
        """Return usage statistics per sub-account (stub -- Phase 1 returns zeroes)."""
        items, _ = await self.sub_repo.list_by_master(master_id, page=1, page_size=1000)
        return [
            {
                "sub_account_id": sub.id,
                "sub_account_name": sub.name,
                "request_count": 0,
                "token_count": 0,
                "error_count": 0,
                "last_active_at": None,
            }
            for sub in items
        ]

    async def bulk_revoke(self, master_id: UUID) -> tuple[int, int, int]:
        """Revoke all active/suspended sub-accounts under a master."""
        total = await self.master_repo.count_sub_accounts(master_id)
        newly_revoked, already_revoked = await self.sub_repo.bulk_revoke(master_id)
        logger.info(
            "Bulk revoke for master %s: %d revoked, %d already revoked",
            master_id,
            newly_revoked,
            already_revoked,
        )
        return newly_revoked, already_revoked, total

    async def set_tool_allow_list(self, sub_id: UUID, tool_names: list[str]) -> list[str]:
        """Replace the tool allow-list for a sub-account."""
        tools = await self.sub_repo.set_tool_allow_list(sub_id, tool_names)
        logger.info("Tool allow-list updated for sub %s: %d tools", sub_id, len(tools))
        return tools

    async def get_tool_allow_list(self, sub_id: UUID) -> list[str]:
        """Get the tool allow-list for a sub-account."""
        return await self.sub_repo.get_tool_allow_list(sub_id)
