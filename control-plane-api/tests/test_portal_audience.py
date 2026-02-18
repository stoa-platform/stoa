"""Tests for multi-audience content model (CAB-1323).

Covers:
- get_allowed_audiences role mapping
- Portal list endpoint audience filtering
- Portal detail endpoint audience enforcement
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.models.catalog import APICatalog, AudienceEnum
from src.repositories.catalog import get_allowed_audiences


# ============================================================================
# Unit Tests — get_allowed_audiences
# ============================================================================


class TestAudienceMapping:
    """Role → audience ceiling mapping."""

    def test_cpi_admin_sees_all(self):
        result = get_allowed_audiences(["cpi-admin"])
        assert "public" in result
        assert "internal" in result
        assert "partner" in result

    def test_tenant_admin_sees_all(self):
        result = get_allowed_audiences(["tenant-admin"])
        assert "public" in result
        assert "internal" in result
        assert "partner" in result

    def test_devops_sees_public_and_internal(self):
        result = get_allowed_audiences(["devops"])
        assert "public" in result
        assert "internal" in result
        assert "partner" not in result

    def test_viewer_sees_public_only(self):
        result = get_allowed_audiences(["viewer"])
        assert result == ["public"]

    def test_empty_roles_default_to_public(self):
        result = get_allowed_audiences([])
        assert result == ["public"]

    def test_union_of_multiple_roles(self):
        """A user with viewer + devops gets devops ceiling (union)."""
        result = get_allowed_audiences(["viewer", "devops"])
        assert "public" in result
        assert "internal" in result
        assert "partner" not in result

    def test_unknown_role_defaults_to_public(self):
        result = get_allowed_audiences(["unknown-role"])
        assert result == ["public"]


# ============================================================================
# Integration Tests — Portal list endpoint audience filtering
# ============================================================================


def _make_api(audience: str = "public", **kwargs) -> MagicMock:
    """Create a mock APICatalog row."""
    api = MagicMock(spec=APICatalog)
    api.api_id = kwargs.get("api_id", f"api-{uuid.uuid4().hex[:6]}")
    api.api_name = kwargs.get("api_name", "Test API")
    api.version = kwargs.get("version", "1.0.0")
    api.tenant_id = kwargs.get("tenant_id", "test-tenant")
    api.status = kwargs.get("status", "active")
    api.category = kwargs.get("category", None)
    api.tags = kwargs.get("tags", [])
    api.portal_published = kwargs.get("portal_published", True)
    api.audience = audience
    api.api_metadata = kwargs.get("api_metadata", {"description": "A test API"})
    api.openapi_spec = None
    return api


class TestPortalAPIsAudienceFilter:
    """Tests for audience filtering on the list endpoint."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_see_internal_apis(self):
        """Viewer role should only see public APIs."""
        from src.routers.portal import list_portal_apis

        public_api = _make_api("public", api_id="pub-api")
        internal_api = _make_api("internal", api_id="int-api")

        mock_repo = AsyncMock()
        mock_repo.get_portal_apis.return_value = ([public_api], 1)

        user = MagicMock()
        user.roles = ["viewer"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await list_portal_apis(user=user, db=db)

        # Verify repo was called with viewer roles
        call_kwargs = mock_repo.get_portal_apis.call_args.kwargs
        assert call_kwargs["user_roles"] == ["viewer"]

    @pytest.mark.asyncio
    async def test_devops_cannot_see_partner_apis(self):
        """Devops role should not see partner APIs."""
        from src.routers.portal import list_portal_apis

        mock_repo = AsyncMock()
        mock_repo.get_portal_apis.return_value = ([], 0)

        user = MagicMock()
        user.roles = ["devops"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await list_portal_apis(user=user, db=db)

        call_kwargs = mock_repo.get_portal_apis.call_args.kwargs
        assert call_kwargs["user_roles"] == ["devops"]

    @pytest.mark.asyncio
    async def test_cpi_admin_sees_all_audiences(self):
        """cpi-admin should see all audiences."""
        from src.routers.portal import list_portal_apis

        mock_repo = AsyncMock()
        mock_repo.get_portal_apis.return_value = (
            [_make_api("public"), _make_api("internal"), _make_api("partner")],
            3,
        )

        user = MagicMock()
        user.roles = ["cpi-admin"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await list_portal_apis(user=user, db=db)

        assert result.total == 3
        call_kwargs = mock_repo.get_portal_apis.call_args.kwargs
        assert call_kwargs["user_roles"] == ["cpi-admin"]

    @pytest.mark.asyncio
    async def test_audience_param_forwarded_to_repo(self):
        """Explicit audience query param is forwarded."""
        from src.routers.portal import list_portal_apis

        mock_repo = AsyncMock()
        mock_repo.get_portal_apis.return_value = ([], 0)

        user = MagicMock()
        user.roles = ["cpi-admin"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            await list_portal_apis(user=user, db=db, audience="internal")

        call_kwargs = mock_repo.get_portal_apis.call_args.kwargs
        assert call_kwargs["audience_filter"] == "internal"

    @pytest.mark.asyncio
    async def test_response_includes_audience_field(self):
        """API list items include the audience field."""
        from src.routers.portal import list_portal_apis

        mock_repo = AsyncMock()
        mock_repo.get_portal_apis.return_value = ([_make_api("partner")], 1)

        user = MagicMock()
        user.roles = ["cpi-admin"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await list_portal_apis(user=user, db=db)

        assert result.apis[0].audience == "partner"


class TestPortalAPIDetailAudience:
    """Tests for audience enforcement on the detail endpoint."""

    @pytest.mark.asyncio
    async def test_viewer_gets_404_for_internal_api(self):
        """Viewer should get 404 when requesting an internal API."""
        from src.routers.portal import get_portal_api

        internal_api = _make_api("internal", api_id="secret-api")

        mock_repo = AsyncMock()
        mock_repo.find_api_by_name.return_value = internal_api

        user = MagicMock()
        user.roles = ["viewer"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await get_portal_api(api_id="secret-api", user=user, db=db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_cpi_admin_can_access_partner_api(self):
        """cpi-admin should access partner APIs."""
        from src.routers.portal import get_portal_api

        partner_api = _make_api("partner", api_id="partner-api", api_name="Partner API")

        mock_repo = AsyncMock()
        mock_repo.find_api_by_name.return_value = partner_api

        user = MagicMock()
        user.roles = ["cpi-admin"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await get_portal_api(api_id="partner-api", user=user, db=db)

        assert result.audience == "partner"

    @pytest.mark.asyncio
    async def test_devops_gets_404_for_partner_api(self):
        """Devops should get 404 when requesting a partner API."""
        from src.routers.portal import get_portal_api

        partner_api = _make_api("partner", api_id="partner-api")

        mock_repo = AsyncMock()
        mock_repo.find_api_by_name.return_value = partner_api

        user = MagicMock()
        user.roles = ["devops"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            with pytest.raises(HTTPException) as exc_info:
                await get_portal_api(api_id="partner-api", user=user, db=db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_detail_response_includes_audience(self):
        """Detail response includes audience field."""
        from src.routers.portal import get_portal_api

        api = _make_api("internal", api_id="int-api", api_name="Internal API")

        mock_repo = AsyncMock()
        mock_repo.find_api_by_name.return_value = api

        user = MagicMock()
        user.roles = ["tenant-admin"]
        db = AsyncMock()

        with patch("src.routers.portal.CatalogRepository", return_value=mock_repo):
            result = await get_portal_api(api_id="int-api", user=user, db=db)

        assert result.audience == "internal"
