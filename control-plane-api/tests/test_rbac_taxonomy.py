"""Tests for RBAC Taxonomy v2 — CAB-1634.

Covers:
- normalize_roles() alias resolution
- Persona role permission inheritance
- Core role regression (no changes)
- ROLE_METADATA completeness
- GET /v1/roles endpoint
- GET /v1/me role_display_names field
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.auth.rbac import (
    ROLE_ALIASES,
    ROLE_METADATA,
    ROLE_PERMISSIONS,
    get_user_permissions,
    normalize_roles,
)


# ---------------------------------------------------------------------------
# normalize_roles()
# ---------------------------------------------------------------------------


class TestNormalizeRoles:
    def test_core_role_passes_through(self):
        assert normalize_roles(["cpi-admin"]) == ["cpi-admin"]

    def test_alias_adds_core_role(self):
        result = normalize_roles(["stoa.admin"])
        assert "stoa.admin" in result
        assert "cpi-admin" in result

    def test_all_aliases_resolve(self):
        for alias, core in ROLE_ALIASES.items():
            result = normalize_roles([alias])
            assert core in result, f"{alias} should resolve to {core}"
            assert alias in result, f"{alias} should be kept in result"

    def test_idempotent(self):
        first = normalize_roles(["stoa.developer"])
        second = normalize_roles(first)
        assert first == second

    def test_mixed_roles(self):
        result = normalize_roles(["stoa.developer", "stoa.security"])
        assert "devops" in result  # alias resolved
        assert "stoa.security" in result  # additive kept
        assert "stoa.developer" in result  # original kept

    def test_unknown_roles_pass_through(self):
        result = normalize_roles(["unknown-role", "viewer"])
        assert "unknown-role" in result
        assert "viewer" in result

    def test_empty_list(self):
        assert normalize_roles([]) == []

    def test_duplicate_handling(self):
        result = normalize_roles(["cpi-admin", "stoa.admin"])
        assert result.count("cpi-admin") == 1  # no duplicates

    def test_result_is_sorted(self):
        result = normalize_roles(["stoa.consumer", "stoa.admin"])
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# Persona role permission inheritance
# ---------------------------------------------------------------------------


class TestPersonaPermissions:
    def test_stoa_admin_gets_cpi_admin_perms(self):
        roles = normalize_roles(["stoa.admin"])
        perms = get_user_permissions(roles)
        cpi_perms = set(ROLE_PERMISSIONS["cpi-admin"])
        assert cpi_perms.issubset(set(perms))

    def test_stoa_product_owner_gets_tenant_admin_perms(self):
        roles = normalize_roles(["stoa.product_owner"])
        perms = get_user_permissions(roles)
        ta_perms = set(ROLE_PERMISSIONS["tenant-admin"])
        assert ta_perms.issubset(set(perms))

    def test_stoa_developer_gets_devops_perms(self):
        roles = normalize_roles(["stoa.developer"])
        perms = get_user_permissions(roles)
        devops_perms = set(ROLE_PERMISSIONS["devops"])
        assert devops_perms.issubset(set(perms))

    def test_stoa_consumer_gets_viewer_perms(self):
        roles = normalize_roles(["stoa.consumer"])
        perms = get_user_permissions(roles)
        viewer_perms = set(ROLE_PERMISSIONS["viewer"])
        assert viewer_perms.issubset(set(perms))

    def test_stoa_security_standalone(self):
        perms = get_user_permissions(["stoa.security"])
        assert "audit:read" in perms
        assert "apis:read" in perms
        assert "apis:create" not in perms  # read-only

    def test_stoa_agent_minimal(self):
        perms = get_user_permissions(["stoa.agent"])
        assert "apis:read" in perms
        assert "apps:read" in perms
        assert len(perms) == 2  # exactly 2 permissions

    def test_combined_additive_union(self):
        """stoa.developer + stoa.security = union of both permission sets."""
        roles = normalize_roles(["stoa.developer", "stoa.security"])
        perms = set(get_user_permissions(roles))
        devops_perms = set(ROLE_PERMISSIONS["devops"])
        security_perms = set(ROLE_PERMISSIONS["stoa.security"])
        assert devops_perms.issubset(perms)
        assert security_perms.issubset(perms)


# ---------------------------------------------------------------------------
# Core role regression
# ---------------------------------------------------------------------------


class TestCoreRolesRegression:
    def test_cpi_admin_has_18_perms(self):
        assert len(ROLE_PERMISSIONS["cpi-admin"]) == 18

    def test_tenant_admin_has_correct_perms(self):
        perms = ROLE_PERMISSIONS["tenant-admin"]
        assert "tenants:read" in perms
        assert "tenants:create" not in perms

    def test_devops_cannot_delete(self):
        perms = ROLE_PERMISSIONS["devops"]
        assert "apis:delete" not in perms
        assert "apps:delete" not in perms

    def test_viewer_read_only(self):
        perms = ROLE_PERMISSIONS["viewer"]
        assert all("read" in p or "workflows:read" in p for p in perms)


# ---------------------------------------------------------------------------
# ROLE_METADATA
# ---------------------------------------------------------------------------


class TestRoleMetadata:
    def test_all_roles_have_metadata(self):
        all_roles = set(ROLE_PERMISSIONS.keys()) | set(ROLE_ALIASES.keys())
        for role in all_roles:
            assert role in ROLE_METADATA, f"{role} missing from ROLE_METADATA"

    def test_metadata_fields(self):
        for name, meta in ROLE_METADATA.items():
            assert "display_name" in meta, f"{name} missing display_name"
            assert "description" in meta, f"{name} missing description"
            assert "scope" in meta, f"{name} missing scope"
            assert "category" in meta, f"{name} missing category"
            assert meta["scope"] in ("platform", "tenant")
            assert meta["category"] in ("core", "persona", "additive")

    def test_persona_roles_have_inherits_from(self):
        for name, meta in ROLE_METADATA.items():
            if meta["category"] == "persona":
                assert "inherits_from" in meta, f"{name} persona missing inherits_from"
                assert meta["inherits_from"] in ROLE_PERMISSIONS

    def test_alias_roles_match_metadata_inherits(self):
        for alias, core in ROLE_ALIASES.items():
            meta = ROLE_METADATA[alias]
            assert meta.get("inherits_from") == core


# ---------------------------------------------------------------------------
# GET /v1/roles endpoint
# ---------------------------------------------------------------------------


class TestRolesEndpoint:
    @pytest.fixture
    def mock_user(self):
        from src.auth.dependencies import User
        return User(
            id="test-user",
            email="test@example.com",
            username="testuser",
            roles=["viewer"],
        )

    @pytest.mark.asyncio
    async def test_list_roles_returns_all(self, mock_user):
        from src.routers.roles import list_roles

        response = await list_roles(_user=mock_user)
        assert len(response.roles) == len(ROLE_METADATA)
        role_names = {r.name for r in response.roles}
        for name in ROLE_METADATA:
            assert name in role_names

    @pytest.mark.asyncio
    async def test_list_roles_aliases(self, mock_user):
        from src.routers.roles import list_roles

        response = await list_roles(_user=mock_user)
        assert response.aliases == ROLE_ALIASES

    @pytest.mark.asyncio
    async def test_persona_role_inherits_perms(self, mock_user):
        from src.routers.roles import list_roles

        response = await list_roles(_user=mock_user)
        stoa_admin = next(r for r in response.roles if r.name == "stoa.admin")
        assert stoa_admin.inherits_from == "cpi-admin"
        assert stoa_admin.permissions == sorted(ROLE_PERMISSIONS["cpi-admin"])

    @pytest.mark.asyncio
    async def test_additive_role_own_perms(self, mock_user):
        from src.routers.roles import list_roles

        response = await list_roles(_user=mock_user)
        agent = next(r for r in response.roles if r.name == "stoa.agent")
        assert agent.inherits_from is None
        assert set(agent.permissions) == {"apis:read", "apps:read"}


# ---------------------------------------------------------------------------
# GET /v1/me — role_display_names field
# ---------------------------------------------------------------------------


class TestMeEndpointDisplayNames:
    @pytest.mark.asyncio
    async def test_display_names_for_core_role(self):
        """Verify /v1/me includes role_display_names."""
        from src.routers.users import UserPermissionsResponse

        # Verify the field exists on the model
        assert "role_display_names" in UserPermissionsResponse.model_fields

    @pytest.mark.asyncio
    async def test_display_names_mapping(self):
        """Verify display name lookup from ROLE_METADATA."""
        from src.auth.rbac import ROLE_METADATA

        meta = ROLE_METADATA.get("cpi-admin")
        assert meta is not None
        assert meta["display_name"] == "Platform Admin"

        meta = ROLE_METADATA.get("tenant-admin")
        assert meta["display_name"] == "Workspace Admin"

        meta = ROLE_METADATA.get("stoa.security")
        assert meta["display_name"] == "Security Auditor"
