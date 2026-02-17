"""Tests for federation models, schemas, repos, key generation, and RBAC (CAB-1313/CAB-1361)."""

import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.auth.dependencies import User
from src.models.federation import (
    MasterAccount,
    MasterAccountStatus,
    SubAccount,
    SubAccountStatus,
    SubAccountTool,
    SubAccountType,
)

# ============== Fixtures ==============

TENANT_ID = "test-tenant"
USER_ADMIN = User(id="admin-1", email="admin@test.com", username="admin", roles=["cpi-admin"], tenant_id=TENANT_ID)
USER_TENANT_ADMIN = User(id="ta-1", email="ta@test.com", username="tadmin", roles=["tenant-admin"], tenant_id=TENANT_ID)
USER_VIEWER = User(id="viewer-1", email="v@test.com", username="viewer", roles=["viewer"], tenant_id=TENANT_ID)
USER_OTHER_TENANT = User(
    id="other-1", email="o@test.com", username="other", roles=["tenant-admin"], tenant_id="other-tenant"
)
USER_DEVOPS = User(id="devops-1", email="d@test.com", username="devops", roles=["devops"], tenant_id=TENANT_ID)


def _make_master(
    name: str = "acme-federation",
    tenant_id: str = TENANT_ID,
    status: MasterAccountStatus = MasterAccountStatus.ACTIVE,
    max_sub_accounts: int = 10,
) -> MasterAccount:
    return MasterAccount(
        id=uuid4(),
        tenant_id=tenant_id,
        name=name,
        display_name=f"{name} display",
        description=f"Test {name}",
        status=status,
        max_sub_accounts=max_sub_accounts,
        quota_config=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test",
    )


def _make_sub(
    name: str = "agent-alpha",
    master_id=None,
    tenant_id: str = TENANT_ID,
    account_type: SubAccountType = SubAccountType.AGENT,
    status: SubAccountStatus = SubAccountStatus.ACTIVE,
) -> SubAccount:
    return SubAccount(
        id=uuid4(),
        master_account_id=master_id or uuid4(),
        tenant_id=tenant_id,
        name=name,
        display_name=f"{name} display",
        account_type=account_type,
        status=status,
        api_key_hash=hashlib.sha256(b"test-key").hexdigest(),
        api_key_prefix="stoa_fed_ab12",
        kc_client_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        created_by="test",
    )


# ============== Unit Tests: Models ==============


class TestFederationModels:
    def test_master_account_repr(self):
        master = _make_master()
        assert "MasterAccount" in repr(master)
        assert "acme-federation" in repr(master)

    def test_sub_account_repr(self):
        sub = _make_sub()
        assert "SubAccount" in repr(sub)
        assert "agent-alpha" in repr(sub)

    def test_sub_account_tool_repr(self):
        tool = SubAccountTool(
            id=uuid4(),
            sub_account_id=uuid4(),
            tool_name="weather-tool",
            created_at=datetime.utcnow(),
        )
        assert "SubAccountTool" in repr(tool)
        assert "weather-tool" in repr(tool)

    def test_master_status_enum_values(self):
        assert MasterAccountStatus.ACTIVE == "active"
        assert MasterAccountStatus.SUSPENDED == "suspended"
        assert MasterAccountStatus.DISABLED == "disabled"

    def test_sub_account_type_enum_values(self):
        assert SubAccountType.DEVELOPER == "developer"
        assert SubAccountType.AGENT == "agent"

    def test_sub_account_status_enum_values(self):
        assert SubAccountStatus.ACTIVE == "active"
        assert SubAccountStatus.SUSPENDED == "suspended"
        assert SubAccountStatus.REVOKED == "revoked"


# ============== Unit Tests: Schemas ==============


class TestFederationSchemas:
    def test_master_create_validation(self):
        from src.schemas.federation import MasterAccountCreate

        schema = MasterAccountCreate(
            name="test-fed",
            display_name="Test Federation",
            max_sub_accounts=50,
        )
        assert schema.name == "test-fed"
        assert schema.max_sub_accounts == 50

    def test_master_create_min_fields(self):
        from src.schemas.federation import MasterAccountCreate

        schema = MasterAccountCreate(name="minimal")
        assert schema.max_sub_accounts == 10
        assert schema.quota_config is None

    def test_master_create_name_min_length(self):
        from src.schemas.federation import MasterAccountCreate

        with pytest.raises(ValidationError):
            MasterAccountCreate(name="")

    def test_sub_create_validation(self):
        from src.schemas.federation import SubAccountCreate

        schema = SubAccountCreate(name="agent-beta", account_type="agent")
        assert schema.name == "agent-beta"
        assert schema.account_type == "agent"

    def test_sub_create_default_type(self):
        from src.schemas.federation import SubAccountCreate

        schema = SubAccountCreate(name="dev-user")
        assert schema.account_type == "developer"

    def test_sub_response_no_hash_exposure(self):
        from src.schemas.federation import SubAccountResponse

        sub = _make_sub()
        response = SubAccountResponse.model_validate(sub)
        dumped = response.model_dump()
        assert "api_key_hash" not in dumped
        assert "api_key_prefix" in dumped

    def test_master_response_from_attributes(self):
        from src.schemas.federation import MasterAccountResponse

        master = _make_master()
        response = MasterAccountResponse(
            id=master.id,
            tenant_id=master.tenant_id,
            name=master.name,
            display_name=master.display_name,
            description=master.description,
            status=master.status,
            max_sub_accounts=master.max_sub_accounts,
            quota_config=master.quota_config,
            sub_account_count=5,
            created_at=master.created_at,
            updated_at=master.updated_at,
            created_by=master.created_by,
        )
        assert response.sub_account_count == 5

    def test_master_update_partial(self):
        from src.schemas.federation import MasterAccountUpdate

        schema = MasterAccountUpdate(display_name="New Name")
        dumped = schema.model_dump(exclude_unset=True)
        assert "display_name" in dumped
        assert "status" not in dumped


# ============== Unit Tests: Key Generation ==============


class TestKeyGeneration:
    def test_generate_federation_key_format(self):
        from src.services.federation_service import _generate_federation_key

        plaintext, key_hash, prefix = _generate_federation_key()
        assert plaintext.startswith("stoa_fed_")
        assert prefix.startswith("stoa_fed_")
        assert len(key_hash) == 64  # SHA-256 hex
        assert hashlib.sha256(plaintext.encode()).hexdigest() == key_hash

    def test_generate_federation_key_uniqueness(self):
        from src.services.federation_service import _generate_federation_key

        keys = {_generate_federation_key()[0] for _ in range(10)}
        assert len(keys) == 10

    def test_generate_federation_key_prefix_structure(self):
        from src.services.federation_service import _generate_federation_key

        plaintext, _, prefix = _generate_federation_key()
        # prefix = stoa_fed_XXXX, plaintext = prefix_<64hex>
        assert plaintext.startswith(prefix + "_")
        assert len(prefix) == len("stoa_fed_") + 4  # 4 hex chars


# ============== Unit Tests: Repository (mocked session) ==============


class TestFederationRepository:
    @pytest.mark.asyncio
    async def test_master_create(self):
        from src.repositories.federation import MasterAccountRepository

        session = AsyncMock()
        repo = MasterAccountRepository(session)
        master = _make_master()

        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        result = await repo.create(master)
        session.add.assert_called_once_with(master)
        session.flush.assert_awaited_once()
        assert result is master

    @pytest.mark.asyncio
    async def test_master_delete(self):
        from src.repositories.federation import MasterAccountRepository

        session = AsyncMock()
        repo = MasterAccountRepository(session)
        master = _make_master()

        session.flush = AsyncMock()

        await repo.delete(master)
        session.delete.assert_awaited_once_with(master)

    @pytest.mark.asyncio
    async def test_sub_create(self):
        from src.repositories.federation import SubAccountRepository

        session = AsyncMock()
        repo = SubAccountRepository(session)
        sub = _make_sub()

        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        result = await repo.create(sub)
        session.add.assert_called_once_with(sub)
        assert result is sub

    @pytest.mark.asyncio
    async def test_master_get_by_id(self):
        from src.repositories.federation import MasterAccountRepository

        session = AsyncMock()
        repo = MasterAccountRepository(session)
        master = _make_master()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = master
        session.execute.return_value = mock_result

        result = await repo.get_by_id(master.id)
        assert result is master

    @pytest.mark.asyncio
    async def test_sub_get_by_master_and_name(self):
        from src.repositories.federation import SubAccountRepository

        session = AsyncMock()
        repo = SubAccountRepository(session)
        sub = _make_sub()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        session.execute.return_value = mock_result

        result = await repo.get_by_master_and_name(sub.master_account_id, sub.name)
        assert result is sub


# ============== Unit Tests: RBAC ==============


class TestFederationRBAC:
    def test_admin_has_access(self):
        from src.routers.federation import _has_tenant_access

        assert _has_tenant_access(USER_ADMIN, "any-tenant") is True

    def test_tenant_admin_own_tenant(self):
        from src.routers.federation import _has_tenant_access

        assert _has_tenant_access(USER_TENANT_ADMIN, TENANT_ID) is True

    def test_other_tenant_denied(self):
        from src.routers.federation import _has_tenant_access

        assert _has_tenant_access(USER_OTHER_TENANT, TENANT_ID) is False

    def test_viewer_write_denied(self):
        from fastapi import HTTPException

        from src.routers.federation import _require_write_access

        with pytest.raises(HTTPException) as exc_info:
            _require_write_access(USER_VIEWER, TENANT_ID)
        assert exc_info.value.status_code == 403

    def test_admin_only_non_admin_denied(self):
        from fastapi import HTTPException

        from src.routers.federation import _require_admin_only

        with pytest.raises(HTTPException) as exc_info:
            _require_admin_only(USER_TENANT_ADMIN)
        assert exc_info.value.status_code == 403

    def test_admin_only_admin_allowed(self):
        from src.routers.federation import _require_admin_only

        # Should not raise
        _require_admin_only(USER_ADMIN)

    def test_devops_write_denied(self):
        from fastapi import HTTPException

        from src.routers.federation import _require_write_access

        with pytest.raises(HTTPException) as exc_info:
            _require_write_access(USER_DEVOPS, TENANT_ID)
        assert exc_info.value.status_code == 403


# ============== Unit Tests: Service (key generation + revoke logic) ==============


class TestFederationService:
    @pytest.mark.asyncio
    async def test_revoke_clears_key(self):
        from src.services.federation_service import FederationService

        session = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()

        svc = FederationService(session)
        sub = _make_sub()
        assert sub.api_key_hash is not None

        result = await svc.revoke_sub_account(sub)
        assert result.status == SubAccountStatus.REVOKED
        assert result.api_key_hash is None

    @pytest.mark.asyncio
    async def test_create_sub_quota_exceeded(self):
        from src.services.federation_service import FederationService

        session = AsyncMock()
        svc = FederationService(session)

        master = _make_master(max_sub_accounts=1)

        # Mock repo methods
        svc.sub_repo.get_by_master_and_name = AsyncMock(return_value=None)
        svc.master_repo.count_sub_accounts = AsyncMock(return_value=1)

        with pytest.raises(ValueError, match="sub-account limit"):
            await svc.create_sub_account(
                master=master,
                name="excess-sub",
                display_name=None,
                account_type="developer",
                created_by="test",
            )

    @pytest.mark.asyncio
    async def test_create_sub_duplicate_name(self):
        from src.services.federation_service import FederationService

        session = AsyncMock()
        svc = FederationService(session)

        master = _make_master()
        existing_sub = _make_sub(master_id=master.id)

        svc.sub_repo.get_by_master_and_name = AsyncMock(return_value=existing_sub)

        with pytest.raises(ValueError, match="already exists"):
            await svc.create_sub_account(
                master=master,
                name=existing_sub.name,
                display_name=None,
                account_type="developer",
                created_by="test",
            )
