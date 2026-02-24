"""Tests for Skills router — CRUD + cascade resolution (CAB-1314)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from src.models.skill import SkillScope

# ── Helpers ──

TENANT_ID = "acme"
SVC_PATH = "src.routers.skills.SkillRepository"


def _make_skill_orm(
    skill_id: UUID | None = None,
    tenant_id: str = TENANT_ID,
    name: str = "python-style",
    scope: str = SkillScope.TENANT,
    priority: int = 50,
    enabled: bool = True,
    instructions: str = "Use type hints.",
    tool_ref: str | None = None,
    user_ref: str | None = None,
) -> MagicMock:
    """Return a mock ORM Skill object that Pydantic can validate via from_attributes."""
    m = MagicMock()
    m.id = skill_id or uuid4()
    m.tenant_id = tenant_id
    m.name = name
    m.description = None
    m.scope = scope
    m.priority = priority
    m.enabled = enabled
    m.instructions = instructions
    m.tool_ref = tool_ref
    m.user_ref = user_ref
    return m


# ── Create ──


class TestCreateSkill:
    def test_create_returns_201(self, client_as_tenant_admin):
        """POST /v1/tenants/{tenant_id}/skills returns 201 and the created skill."""
        skill_id = uuid4()
        mock_skill = _make_skill_orm(skill_id=skill_id)

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.create = AsyncMock(return_value=mock_skill)

            response = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/skills",
                json={"name": "python-style", "instructions": "Use type hints."},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "python-style"
        assert data["tenant_id"] == TENANT_ID

    def test_create_with_tool_scope(self, client_as_tenant_admin):
        """Creating a tool-scoped skill passes tool_ref to repository."""
        mock_skill = _make_skill_orm(scope=SkillScope.TOOL, tool_ref="my-tool")

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.create = AsyncMock(return_value=mock_skill)

            response = client_as_tenant_admin.post(
                f"/v1/tenants/{TENANT_ID}/skills",
                json={"name": "tool-skill", "scope": "tool", "tool_ref": "my-tool"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["scope"] == "tool"

    def test_create_missing_name_returns_422(self, client_as_tenant_admin):
        """POST without required name field returns 422."""
        response = client_as_tenant_admin.post(
            f"/v1/tenants/{TENANT_ID}/skills",
            json={"instructions": "No name provided"},
        )
        assert response.status_code == 422


# ── List ──


class TestListSkills:
    def test_list_returns_200(self, client_as_tenant_admin):
        """GET /v1/tenants/{tenant_id}/skills returns paginated list."""
        skill = _make_skill_orm()

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_by_tenant = AsyncMock(return_value=[skill])
            mock_repo.count_by_tenant = AsyncMock(return_value=1)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_list_empty_returns_200(self, client_as_tenant_admin):
        """Empty skill list returns 200 with empty items."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_by_tenant = AsyncMock(return_value=[])
            mock_repo.count_by_tenant = AsyncMock(return_value=0)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_with_pagination(self, client_as_tenant_admin):
        """limit and offset query params are forwarded to repository."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_by_tenant = AsyncMock(return_value=[])
            mock_repo.count_by_tenant = AsyncMock(return_value=0)

            client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills?limit=10&offset=5")

            call_kwargs = mock_repo.list_by_tenant.call_args
            assert call_kwargs.kwargs["limit"] == 10
            assert call_kwargs.kwargs["offset"] == 5

    def test_list_with_scope_filter(self, client_as_tenant_admin):
        """scope query param is forwarded to repository."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_by_tenant = AsyncMock(return_value=[])
            mock_repo.count_by_tenant = AsyncMock(return_value=0)

            client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills?scope=global")

            call_kwargs = mock_repo.list_by_tenant.call_args
            assert call_kwargs.kwargs["scope"] == SkillScope.GLOBAL


# ── Get ──


class TestGetSkill:
    def test_get_existing_skill_returns_200(self, client_as_tenant_admin):
        """GET /{skill_id} returns the skill when it exists."""
        skill_id = uuid4()
        mock_skill = _make_skill_orm(skill_id=skill_id)

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=mock_skill)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/{skill_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(skill_id)

    def test_get_nonexistent_skill_returns_404(self, client_as_tenant_admin):
        """GET /{skill_id} returns 404 when skill does not exist."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=None)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/{uuid4()}")

        assert response.status_code == 404

    def test_get_skill_wrong_tenant_returns_404(self, client_as_tenant_admin):
        """GET /{skill_id} returns 404 when skill belongs to different tenant."""
        skill_id = uuid4()
        mock_skill = _make_skill_orm(skill_id=skill_id, tenant_id="other-tenant")

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=mock_skill)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/{skill_id}")

        assert response.status_code == 404


# ── Update ──


class TestUpdateSkill:
    def test_update_existing_skill_returns_200(self, client_as_tenant_admin):
        """PATCH /{skill_id} updates and returns the skill."""
        skill_id = uuid4()
        original = _make_skill_orm(skill_id=skill_id)
        updated = _make_skill_orm(skill_id=skill_id, priority=80)

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=original)
            mock_repo.update = AsyncMock(return_value=updated)

            response = client_as_tenant_admin.patch(
                f"/v1/tenants/{TENANT_ID}/skills/{skill_id}",
                json={"priority": 80},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["priority"] == 80

    def test_update_nonexistent_skill_returns_404(self, client_as_tenant_admin):
        """PATCH /{skill_id} returns 404 when skill does not exist."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=None)

            response = client_as_tenant_admin.patch(
                f"/v1/tenants/{TENANT_ID}/skills/{uuid4()}",
                json={"priority": 80},
            )

        assert response.status_code == 404


# ── Delete ──


class TestDeleteSkill:
    def test_delete_existing_skill_returns_204(self, client_as_tenant_admin):
        """DELETE /{skill_id} returns 204 on successful deletion."""
        skill_id = uuid4()
        mock_skill = _make_skill_orm(skill_id=skill_id)

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=mock_skill)
            mock_repo.delete = AsyncMock(return_value=None)

            response = client_as_tenant_admin.delete(f"/v1/tenants/{TENANT_ID}/skills/{skill_id}")

        assert response.status_code == 204

    def test_delete_nonexistent_skill_returns_404(self, client_as_tenant_admin):
        """DELETE /{skill_id} returns 404 when skill does not exist."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.get = AsyncMock(return_value=None)

            response = client_as_tenant_admin.delete(f"/v1/tenants/{TENANT_ID}/skills/{uuid4()}")

        assert response.status_code == 404


# ── Resolve ──


class TestResolveSkills:
    def test_resolve_returns_list(self, client_as_tenant_admin):
        """GET /resolve returns the CSS-cascaded skill list."""
        resolved_data = [
            {
                "name": "python-style",
                "scope": SkillScope.TENANT,
                "priority": 50,
                "instructions": "Use type hints.",
                "specificity": 1,
            }
        ]

        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_resolved = AsyncMock(return_value=resolved_data)

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/resolve")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "python-style"

    def test_resolve_empty_returns_empty_list(self, client_as_tenant_admin):
        """GET /resolve returns [] when no skills are configured."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_resolved = AsyncMock(return_value=[])

            response = client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/resolve")

        assert response.status_code == 200
        assert response.json() == []

    def test_resolve_with_tool_ref_filter(self, client_as_tenant_admin):
        """GET /resolve?tool_ref=my-tool forwards the filter to the repository."""
        with patch(SVC_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo
            mock_repo.list_resolved = AsyncMock(return_value=[])

            client_as_tenant_admin.get(f"/v1/tenants/{TENANT_ID}/skills/resolve?tool_ref=my-tool")

            call_kwargs = mock_repo.list_resolved.call_args.kwargs
            assert call_kwargs.get("tool_ref") == "my-tool"
