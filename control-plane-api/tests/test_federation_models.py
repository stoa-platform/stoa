"""Tests for Federation ORM models — MasterAccount, SubAccount, SubAccountTool (CAB-1452).

Validates column definitions, enums, defaults, indexes, constraints, and relationships
without requiring a running database.
"""

from src.models.federation import (
    MasterAccount,
    MasterAccountStatus,
    SubAccount,
    SubAccountStatus,
    SubAccountTool,
    SubAccountType,
)

# =============================================================================
# Enum Tests
# =============================================================================


class TestMasterAccountStatus:
    def test_values(self):
        assert MasterAccountStatus.ACTIVE == "active"
        assert MasterAccountStatus.SUSPENDED == "suspended"
        assert MasterAccountStatus.DISABLED == "disabled"

    def test_is_str_enum(self):
        assert isinstance(MasterAccountStatus.ACTIVE, str)


class TestSubAccountType:
    def test_values(self):
        assert SubAccountType.DEVELOPER == "developer"
        assert SubAccountType.AGENT == "agent"


class TestSubAccountStatus:
    def test_values(self):
        assert SubAccountStatus.ACTIVE == "active"
        assert SubAccountStatus.SUSPENDED == "suspended"
        assert SubAccountStatus.REVOKED == "revoked"


# =============================================================================
# MasterAccount
# =============================================================================


class TestMasterAccount:
    def test_tablename(self):
        assert MasterAccount.__tablename__ == "master_accounts"

    def test_columns_exist(self):
        cols = {c.name for c in MasterAccount.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "name",
            "display_name",
            "description",
            "status",
            "max_sub_accounts",
            "quota_config",
            "created_at",
            "updated_at",
            "created_by",
        }
        assert expected.issubset(cols)

    def test_primary_key_is_uuid(self):
        assert MasterAccount.__table__.c.id.primary_key

    def test_tenant_id_not_nullable(self):
        assert not MasterAccount.__table__.c.tenant_id.nullable

    def test_name_not_nullable(self):
        assert not MasterAccount.__table__.c.name.nullable

    def test_max_sub_accounts_default(self):
        col = MasterAccount.__table__.c.max_sub_accounts
        assert col.default.arg == 10

    def test_quota_config_nullable(self):
        assert MasterAccount.__table__.c.quota_config.nullable

    def test_indexes_defined(self):
        idx_names = {idx.name for idx in MasterAccount.__table__.indexes}
        assert "ix_master_accounts_tenant_name" in idx_names
        assert "ix_master_accounts_tenant_status" in idx_names

    def test_tenant_name_index_is_unique(self):
        idx = next(i for i in MasterAccount.__table__.indexes if i.name == "ix_master_accounts_tenant_name")
        assert idx.unique

    def test_sub_accounts_relationship(self):
        rels = MasterAccount.__mapper__.relationships
        assert "sub_accounts" in rels
        assert rels["sub_accounts"].cascade.delete_orphan

    def test_repr(self):
        from unittest.mock import MagicMock

        m = MagicMock(spec=MasterAccount)
        m.id = "test-id"
        m.name = "acme-fed"
        m.tenant_id = "acme"
        result = MasterAccount.__repr__(m)
        assert "acme-fed" in result
        assert "acme" in result


# =============================================================================
# SubAccount
# =============================================================================


class TestSubAccount:
    def test_tablename(self):
        assert SubAccount.__tablename__ == "sub_accounts"

    def test_columns_exist(self):
        cols = {c.name for c in SubAccount.__table__.columns}
        expected = {
            "id",
            "master_account_id",
            "tenant_id",
            "name",
            "display_name",
            "account_type",
            "status",
            "api_key_hash",
            "api_key_prefix",
            "kc_client_id",
            "created_at",
            "updated_at",
            "created_by",
        }
        assert expected.issubset(cols)

    def test_master_account_fk(self):
        col = SubAccount.__table__.c.master_account_id
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert "master_accounts.id" in str(fks[0])

    def test_master_account_fk_cascade_delete(self):
        col = SubAccount.__table__.c.master_account_id
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_api_key_hash_nullable(self):
        assert SubAccount.__table__.c.api_key_hash.nullable

    def test_api_key_prefix_nullable(self):
        assert SubAccount.__table__.c.api_key_prefix.nullable

    def test_kc_client_id_nullable(self):
        assert SubAccount.__table__.c.kc_client_id.nullable

    def test_indexes_defined(self):
        idx_names = {idx.name for idx in SubAccount.__table__.indexes}
        assert "ix_sub_accounts_master_name" in idx_names
        assert "ix_sub_accounts_tenant_status" in idx_names
        assert "ix_sub_accounts_key_prefix" in idx_names

    def test_master_name_index_is_unique(self):
        idx = next(i for i in SubAccount.__table__.indexes if i.name == "ix_sub_accounts_master_name")
        assert idx.unique

    def test_master_account_relationship(self):
        rels = SubAccount.__mapper__.relationships
        assert "master_account" in rels

    def test_allowed_tools_relationship(self):
        rels = SubAccount.__mapper__.relationships
        assert "allowed_tools" in rels
        assert rels["allowed_tools"].cascade.delete_orphan

    def test_repr(self):
        from unittest.mock import MagicMock

        s = MagicMock(spec=SubAccount)
        s.id = "sub-id"
        s.name = "agent-alpha"
        s.account_type = SubAccountType.AGENT
        result = SubAccount.__repr__(s)
        assert "agent-alpha" in result
        assert "agent" in result


# =============================================================================
# SubAccountTool
# =============================================================================


class TestSubAccountTool:
    def test_tablename(self):
        assert SubAccountTool.__tablename__ == "sub_account_tools"

    def test_columns_exist(self):
        cols = {c.name for c in SubAccountTool.__table__.columns}
        expected = {"id", "sub_account_id", "tool_name", "created_at"}
        assert expected.issubset(cols)

    def test_sub_account_fk(self):
        col = SubAccountTool.__table__.c.sub_account_id
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert "sub_accounts.id" in str(fks[0])

    def test_sub_account_fk_cascade_delete(self):
        col = SubAccountTool.__table__.c.sub_account_id
        fk = next(iter(col.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_tool_name_not_nullable(self):
        assert not SubAccountTool.__table__.c.tool_name.nullable

    def test_unique_index(self):
        idx_names = {idx.name for idx in SubAccountTool.__table__.indexes}
        assert "ix_sub_account_tools_unique" in idx_names
        idx = next(i for i in SubAccountTool.__table__.indexes if i.name == "ix_sub_account_tools_unique")
        assert idx.unique

    def test_sub_account_relationship(self):
        rels = SubAccountTool.__mapper__.relationships
        assert "sub_account" in rels

    def test_repr(self):
        from unittest.mock import MagicMock

        t = MagicMock(spec=SubAccountTool)
        t.id = "tool-id"
        t.sub_account_id = "sub-id"
        t.tool_name = "list_apis"
        result = SubAccountTool.__repr__(t)
        assert "list_apis" in result
