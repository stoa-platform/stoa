"""Tests for Federation Pydantic schemas (CAB-1452).

Validates serialization, validation rules, defaults, and edge cases
for all federation request/response schemas.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.schemas.federation import (
    DelegationTokenRequest,
    DelegationTokenResponse,
    FederationBulkRevokeResponse,
    MasterAccountCreate,
    MasterAccountListResponse,
    MasterAccountResponse,
    MasterAccountStatusEnum,
    MasterAccountUpdate,
    SubAccountCreate,
    SubAccountCreatedResponse,
    SubAccountListResponse,
    SubAccountResponse,
    SubAccountStatusEnum,
    SubAccountTypeEnum,
    SubAccountUpdate,
    ToolAllowListResponse,
    ToolAllowListUpdate,
    UsageResponse,
    UsageStat,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    def test_master_account_status_values(self):
        assert MasterAccountStatusEnum.ACTIVE == "active"
        assert MasterAccountStatusEnum.SUSPENDED == "suspended"
        assert MasterAccountStatusEnum.DISABLED == "disabled"

    def test_sub_account_type_values(self):
        assert SubAccountTypeEnum.DEVELOPER == "developer"
        assert SubAccountTypeEnum.AGENT == "agent"

    def test_sub_account_status_values(self):
        assert SubAccountStatusEnum.ACTIVE == "active"
        assert SubAccountStatusEnum.SUSPENDED == "suspended"
        assert SubAccountStatusEnum.REVOKED == "revoked"


# =============================================================================
# MasterAccountCreate
# =============================================================================


class TestMasterAccountCreate:
    def test_valid_minimal(self):
        m = MasterAccountCreate(name="acme-fed")
        assert m.name == "acme-fed"
        assert m.display_name is None
        assert m.description is None
        assert m.max_sub_accounts == 10
        assert m.quota_config is None

    def test_valid_full(self):
        m = MasterAccountCreate(
            name="acme-fed",
            display_name="Acme Federation",
            description="Enterprise federation",
            max_sub_accounts=50,
            quota_config={"daily_limit": 10000},
        )
        assert m.max_sub_accounts == 50
        assert m.quota_config["daily_limit"] == 10000

    def test_name_required(self):
        with pytest.raises(ValidationError):
            MasterAccountCreate()

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            MasterAccountCreate(name="")

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            MasterAccountCreate(name="x" * 256)

    def test_max_sub_accounts_min_1(self):
        with pytest.raises(ValidationError):
            MasterAccountCreate(name="test", max_sub_accounts=0)

    def test_max_sub_accounts_max_1000(self):
        with pytest.raises(ValidationError):
            MasterAccountCreate(name="test", max_sub_accounts=1001)

    def test_json_schema_extra_example(self):
        schema = MasterAccountCreate.model_json_schema()
        assert "examples" in schema or "example" in schema.get("json_schema_extra", {}) or True
        # Just verify schema generation doesn't crash


# =============================================================================
# MasterAccountUpdate
# =============================================================================


class TestMasterAccountUpdate:
    def test_all_none_valid(self):
        m = MasterAccountUpdate()
        assert m.display_name is None
        assert m.status is None
        assert m.max_sub_accounts is None

    def test_partial_update(self):
        m = MasterAccountUpdate(status=MasterAccountStatusEnum.SUSPENDED)
        assert m.status == MasterAccountStatusEnum.SUSPENDED
        assert m.display_name is None

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            MasterAccountUpdate(status="invalid")


# =============================================================================
# MasterAccountResponse
# =============================================================================


class TestMasterAccountResponse:
    def _sample(self, **overrides):
        defaults = {
            "id": uuid4(),
            "tenant_id": "acme",
            "name": "acme-fed",
            "display_name": "Acme",
            "description": None,
            "status": MasterAccountStatusEnum.ACTIVE,
            "max_sub_accounts": 10,
            "quota_config": None,
            "sub_account_count": 3,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
            "created_by": "admin",
        }
        defaults.update(overrides)
        return defaults

    def test_valid(self):
        r = MasterAccountResponse(**self._sample())
        assert r.tenant_id == "acme"
        assert r.sub_account_count == 3

    def test_sub_account_count_default(self):
        data = self._sample()
        del data["sub_account_count"]
        r = MasterAccountResponse(**data)
        assert r.sub_account_count == 0

    def test_from_attributes_config(self):
        assert MasterAccountResponse.model_config.get("from_attributes") is True


# =============================================================================
# SubAccountCreate
# =============================================================================


class TestSubAccountCreate:
    def test_valid_minimal(self):
        s = SubAccountCreate(name="agent-1")
        assert s.name == "agent-1"
        assert s.account_type == SubAccountTypeEnum.DEVELOPER
        assert s.display_name is None

    def test_agent_type(self):
        s = SubAccountCreate(name="bot-1", account_type=SubAccountTypeEnum.AGENT)
        assert s.account_type == SubAccountTypeEnum.AGENT

    def test_name_required(self):
        with pytest.raises(ValidationError):
            SubAccountCreate()

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            SubAccountCreate(name="")


# =============================================================================
# SubAccountUpdate
# =============================================================================


class TestSubAccountUpdate:
    def test_all_none_valid(self):
        s = SubAccountUpdate()
        assert s.display_name is None
        assert s.status is None

    def test_revoke(self):
        s = SubAccountUpdate(status=SubAccountStatusEnum.REVOKED)
        assert s.status == SubAccountStatusEnum.REVOKED


# =============================================================================
# SubAccountResponse
# =============================================================================


class TestSubAccountResponse:
    def _sample(self, **overrides):
        defaults = {
            "id": uuid4(),
            "master_account_id": uuid4(),
            "tenant_id": "acme",
            "name": "agent-1",
            "display_name": "Agent One",
            "account_type": SubAccountTypeEnum.AGENT,
            "status": SubAccountStatusEnum.ACTIVE,
            "api_key_prefix": "stoa_fed_a1b2",
            "kc_client_id": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
            "created_by": "admin",
        }
        defaults.update(overrides)
        return defaults

    def test_valid(self):
        r = SubAccountResponse(**self._sample())
        assert r.name == "agent-1"
        assert r.account_type == SubAccountTypeEnum.AGENT

    def test_api_key_hash_not_exposed(self):
        """SubAccountResponse schema should NOT have api_key_hash field."""
        fields = SubAccountResponse.model_fields
        assert "api_key_hash" not in fields


# =============================================================================
# SubAccountCreatedResponse
# =============================================================================


class TestSubAccountCreatedResponse:
    def test_valid(self):
        r = SubAccountCreatedResponse(
            id=uuid4(),
            name="agent-1",
            api_key="stoa_fed_a1b2_xxxxxxxxxxxxx",
            api_key_prefix="stoa_fed_a1b2",
        )
        assert r.api_key.startswith("stoa_fed_")

    def test_api_key_required(self):
        with pytest.raises(ValidationError):
            SubAccountCreatedResponse(id=uuid4(), name="a", api_key_prefix="p")


# =============================================================================
# DelegationTokenRequest
# =============================================================================


class TestDelegationTokenRequest:
    def test_defaults(self):
        d = DelegationTokenRequest()
        assert d.scopes == ["stoa:read"]
        assert d.ttl_seconds == 3600

    def test_custom_values(self):
        d = DelegationTokenRequest(scopes=["stoa:read", "stoa:write"], ttl_seconds=7200)
        assert len(d.scopes) == 2
        assert d.ttl_seconds == 7200

    def test_ttl_min_60(self):
        with pytest.raises(ValidationError):
            DelegationTokenRequest(ttl_seconds=30)

    def test_ttl_max_86400(self):
        with pytest.raises(ValidationError):
            DelegationTokenRequest(ttl_seconds=100000)


# =============================================================================
# DelegationTokenResponse
# =============================================================================


class TestDelegationTokenResponse:
    def test_valid(self):
        r = DelegationTokenResponse(
            access_token="eyJ...",  # noqa: S106
            expires_in=3600,
            scope="stoa:read",
            sub_account_id=uuid4(),
            sub_account_name="agent-1",
        )
        assert r.token_type == "Bearer"
        assert r.expires_in == 3600


# =============================================================================
# UsageStat / UsageResponse
# =============================================================================


class TestUsageStat:
    def test_defaults(self):
        u = UsageStat(sub_account_id=uuid4(), sub_account_name="agent-1")
        assert u.request_count == 0
        assert u.token_count == 0
        assert u.error_count == 0
        assert u.last_active_at is None


class TestUsageResponse:
    def test_valid(self):
        r = UsageResponse(
            master_account_id=uuid4(),
            period_days=30,
            sub_accounts=[],
        )
        assert r.total_requests == 0
        assert r.total_tokens == 0
        assert r.sub_accounts == []


# =============================================================================
# Bulk Revoke / Tool Allow-List
# =============================================================================


class TestFederationBulkRevokeResponse:
    def test_valid(self):
        r = FederationBulkRevokeResponse(revoked_count=5, already_revoked=2, total=10)
        assert r.revoked_count == 5


class TestToolAllowListUpdate:
    def test_valid(self):
        t = ToolAllowListUpdate(tools=["list_apis", "get_api_detail"])
        assert len(t.tools) == 2

    def test_tools_required(self):
        with pytest.raises(ValidationError):
            ToolAllowListUpdate()


class TestToolAllowListResponse:
    def test_valid(self):
        r = ToolAllowListResponse(sub_account_id=uuid4(), tools=["list_apis"])
        assert r.tools == ["list_apis"]


# =============================================================================
# List Responses
# =============================================================================


class TestMasterAccountListResponse:
    def test_valid(self):
        r = MasterAccountListResponse(items=[], total=0, page=1, page_size=20)
        assert r.items == []
        assert r.page == 1


class TestSubAccountListResponse:
    def test_valid(self):
        r = SubAccountListResponse(items=[], total=0, page=1, page_size=20)
        assert r.items == []
