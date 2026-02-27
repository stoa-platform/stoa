"""Tests for TenantExportService + TenantImportService — CAB-1559

Covers:
- Export: tenant not found, empty export, full export with all resource types
- Import: skip/overwrite/fail conflict modes, dry-run, subscriptions skipped, tenant not found
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.tenant_dr import (
    ExportedBackendApi,
    ExportedConsumer,
    ExportedContract,
    ExportedExternalMcpServer,
    ExportedPlan,
    ExportedPolicy,
    ExportedSkill,
    ExportedWebhook,
    ImportMode,
    TenantExportResponse,
    TenantImportRequest,
)
from src.services.tenant_dr_service import TenantExportService, TenantImportService

TENANT_ID = "acme"


def _mock_scalar_result(items):
    """Create a mock execute result that returns scalars().all() → items."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    return mock_result


def _mock_scalar_one_or_none(item):
    """Create a mock execute result for scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = item
    return mock_result


def _mock_scalar_one(item):
    """Create a mock execute result for scalar_one()."""
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = item
    return mock_result


def _make_tenant(tenant_id=TENANT_ID, name="ACME Corp"):
    mock = MagicMock()
    mock.id = tenant_id
    mock.name = name
    return mock


def _make_backend_api(name="test-api"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.display_name = f"{name} Display"
    mock.description = "Test API"
    mock.backend_url = "https://api.example.com"
    mock.openapi_spec_url = None
    mock.auth_type = "none"
    mock.status = "active"
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_plan(slug="free"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.slug = slug
    mock.name = f"{slug} plan"
    mock.description = "Test plan"
    mock.rate_limit_per_second = 10
    mock.rate_limit_per_minute = 100
    mock.daily_request_limit = 1000
    mock.monthly_request_limit = 30000
    mock.burst_limit = 20
    mock.requires_approval = False
    mock.status = "active"
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_consumer(ext_id="user-1"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.external_id = ext_id
    mock.name = "Test User"
    mock.email = "test@example.com"
    mock.company = "ACME"
    mock.description = None
    mock.status = "active"
    mock.consumer_metadata = {}
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_policy(name="rate-limit"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.description = "Test policy"
    mock.policy_type = "rate_limit"
    mock.config = {"requests_per_minute": 60}
    mock.enabled = True
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_skill(name="search"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.description = "Test skill"
    mock.scope = "tenant"
    mock.priority = 50
    mock.instructions = "Search docs"
    mock.tool_ref = None
    mock.user_ref = None
    mock.enabled = True
    mock.tenant_id = TENANT_ID
    return mock


def _make_webhook(name="deploy-hook"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.url = "https://hooks.example.com/deploy"
    mock.events = ["api.deployed"]
    mock.enabled = True
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_mcp_server(name="linear-mcp"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.base_url = "https://mcp.linear.app"
    mock.description = "Linear MCP"
    mock.enabled = True
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_mcp_tool(name="create_issue"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.description = "Create issue"
    mock.input_schema = {"type": "object"}
    return mock


def _make_contract(name="weather-uac"):
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.name = name
    mock.display_name = "Weather UAC"
    mock.description = "Weather contract"
    mock.version = "1.0"
    mock.status = "published"
    mock.openapi_spec_url = None
    mock.deprecated_at = None
    mock.sunset_at = None
    mock.deprecation_reason = None
    mock.grace_period_days = None
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


def _make_binding():
    mock = MagicMock()
    mock.protocol = "rest"
    mock.enabled = True
    mock.endpoint = "/v1/weather"
    mock.tool_name = "get_weather"
    return mock


def _make_subscription():
    mock = MagicMock()
    mock.id = uuid.uuid4()
    mock.application_id = "app-1"
    mock.application_name = "Test App"
    mock.subscriber_email = "dev@example.com"
    mock.api_id = "api-1"
    mock.api_name = "Test API"
    mock.plan_id = uuid.uuid4()
    mock.status = "active"
    mock.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    mock.tenant_id = TENANT_ID
    return mock


# ============ Export Tests ============


class TestExportTenantNotFound:
    @pytest.mark.asyncio
    async def test_export_raises_if_tenant_missing(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(None))
        svc = TenantExportService(db)

        with pytest.raises(ValueError, match="not found"):
            await svc.export_tenant("nonexistent")


class TestExportEmpty:
    @pytest.mark.asyncio
    async def test_export_empty_tenant(self):
        tenant = _make_tenant()
        db = AsyncMock()
        # First call: tenant lookup. All subsequent: empty resource lists.
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_result([]),  # backend_apis
                _mock_scalar_result([]),  # contracts
                _mock_scalar_result([]),  # consumers
                _mock_scalar_result([]),  # plans
                _mock_scalar_result([]),  # subscriptions
                _mock_scalar_result([]),  # policies
                _mock_scalar_result([]),  # skills
                _mock_scalar_result([]),  # webhooks
                _mock_scalar_result([]),  # mcp_servers
            ]
        )
        svc = TenantExportService(db)
        result = await svc.export_tenant(TENANT_ID)

        assert result.metadata.tenant_id == TENANT_ID
        assert result.metadata.tenant_name == "ACME Corp"
        assert all(v == 0 for v in result.metadata.resource_counts.values())
        assert result.backend_apis == []
        assert result.consumers == []


class TestExportFull:
    @pytest.mark.asyncio
    async def test_export_with_all_resources(self):
        tenant = _make_tenant()
        api = _make_backend_api()
        contract = _make_contract()
        binding = _make_binding()
        consumer = _make_consumer()
        plan = _make_plan()
        sub = _make_subscription()
        policy = _make_policy()
        skill = _make_skill()
        webhook = _make_webhook()
        server = _make_mcp_server()
        tool = _make_mcp_tool()

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_result([api]),  # backend_apis
                _mock_scalar_result([contract]),  # contracts
                _mock_scalar_result([binding]),  # contract bindings
                _mock_scalar_result([consumer]),  # consumers
                _mock_scalar_result([plan]),  # plans
                _mock_scalar_result([sub]),  # subscriptions
                _mock_scalar_result([policy]),  # policies
                _mock_scalar_result([skill]),  # skills
                _mock_scalar_result([webhook]),  # webhooks
                _mock_scalar_result([server]),  # mcp_servers
                _mock_scalar_result([tool]),  # mcp_server tools
            ]
        )
        svc = TenantExportService(db)
        result = await svc.export_tenant(TENANT_ID)

        assert result.metadata.resource_counts["backend_apis"] == 1
        assert result.metadata.resource_counts["contracts"] == 1
        assert result.metadata.resource_counts["consumers"] == 1
        assert result.metadata.resource_counts["plans"] == 1
        assert result.metadata.resource_counts["policies"] == 1
        assert result.metadata.resource_counts["skills"] == 1
        assert result.metadata.resource_counts["webhooks"] == 1
        assert result.metadata.resource_counts["external_mcp_servers"] == 1
        assert len(result.backend_apis) == 1
        assert result.backend_apis[0].name == "test-api"
        assert len(result.contracts) == 1
        assert len(result.contracts[0].bindings) == 1

    @pytest.mark.asyncio
    async def test_export_metadata_timestamp(self):
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                *[_mock_scalar_result([]) for _ in range(9)],
            ]
        )
        svc = TenantExportService(db)
        result = await svc.export_tenant(TENANT_ID)

        assert result.metadata.export_version == "1.0"
        assert result.metadata.exported_at is not None


# ============ Import Tests ============


def _empty_archive():
    """Create a minimal empty export archive for import testing."""
    return TenantExportResponse(
        metadata={
            "exported_at": datetime.now(UTC),
            "tenant_id": TENANT_ID,
            "tenant_name": "ACME Corp",
            "resource_counts": {},
        },
    )


def _archive_with_api(name="new-api"):
    archive = _empty_archive()
    archive.backend_apis = [
        ExportedBackendApi(
            id=uuid.uuid4(),
            name=name,
            display_name="New API",
            backend_url="https://new.example.com",
        )
    ]
    return archive


def _archive_with_plan(slug="premium"):
    archive = _empty_archive()
    archive.plans = [
        ExportedPlan(
            id=uuid.uuid4(),
            slug=slug,
            name="Premium Plan",
        )
    ]
    return archive


class TestImportTenantNotFound:
    @pytest.mark.asyncio
    async def test_import_raises_if_tenant_missing(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(None))
        svc = TenantImportService(db)

        request = TenantImportRequest(archive=_empty_archive())
        with pytest.raises(ValueError, match="not found"):
            await svc.import_tenant("nonexistent", request)


class TestImportDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self):
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),  # tenant lookup
                _mock_scalar_one_or_none(None),  # api not found → create
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_api()
        request = TenantImportRequest(
            archive=archive,
            mode=ImportMode(dry_run=True),
        )
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.dry_run is True
        assert result.created.get("backend_apis", 0) == 1
        db.add.assert_not_called()
        db.flush.assert_not_called()


class TestImportSkipMode:
    @pytest.mark.asyncio
    async def test_skip_existing_api(self):
        tenant = _make_tenant()
        existing_api = _make_backend_api("existing-api")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(existing_api),  # api already exists
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_api("existing-api")
        request = TenantImportRequest(
            archive=archive,
            mode=ImportMode(conflict_resolution="skip"),
        )
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.skipped.get("backend_apis") == 1
        assert result.created.get("backend_apis", 0) == 0
        assert result.success is True


class TestImportFailMode:
    @pytest.mark.asyncio
    async def test_fail_on_conflict(self):
        tenant = _make_tenant()
        existing_api = _make_backend_api("conflict-api")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(existing_api),  # conflict!
            ]
        )
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_api("conflict-api")
        request = TenantImportRequest(
            archive=archive,
            mode=ImportMode(conflict_resolution="fail"),
        )
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.success is False
        assert any("already exists" in e for e in result.errors)


class TestImportCreateNew:
    @pytest.mark.asyncio
    async def test_create_new_api(self):
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(None),  # api not found → create
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_api()
        request = TenantImportRequest(archive=archive)
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.created.get("backend_apis") == 1
        assert result.success is True
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_new_plan(self):
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(None),  # plan not found → create
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_plan()
        request = TenantImportRequest(archive=archive)
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.created.get("plans") == 1
        assert result.success is True


class TestImportSubscriptionsSkipped:
    @pytest.mark.asyncio
    async def test_subscriptions_skipped_for_security(self):
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_scalar_one_or_none(tenant))
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _empty_archive()
        archive.subscriptions = [
            ExportedBackendApi(  # just needs to be truthy list
                id=uuid.uuid4(), name="sub"
            )
        ]
        request = TenantImportRequest(archive=archive)
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.skipped.get("subscriptions") == 1
        assert result.success is True


class TestImportOverwriteMode:
    @pytest.mark.asyncio
    async def test_overwrite_existing_api(self):
        tenant = _make_tenant()
        existing = _make_backend_api("overwrite-api")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(existing),  # exists → overwrite
                _mock_scalar_one(existing),  # _overwrite_backend_api fetch
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _archive_with_api("overwrite-api")
        request = TenantImportRequest(
            archive=archive,
            mode=ImportMode(conflict_resolution="overwrite"),
        )
        result = await svc.import_tenant(TENANT_ID, request)

        # Overwrite counts as "skipped" in the current implementation
        assert result.skipped.get("backend_apis") == 1
        assert result.success is True


class TestImportMultipleResources:
    @pytest.mark.asyncio
    async def test_import_mixed_resources(self):
        """Import archive with both APIs and plans — both get created."""
        tenant = _make_tenant()
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(tenant),
                _mock_scalar_one_or_none(None),  # api not found
                _mock_scalar_one_or_none(None),  # plan not found
            ]
        )
        db.add = MagicMock()
        db.flush = AsyncMock()
        svc = TenantImportService(db)

        archive = _empty_archive()
        archive.backend_apis = [
            ExportedBackendApi(id=uuid.uuid4(), name="api-1", backend_url="https://a.com")
        ]
        archive.plans = [
            ExportedPlan(id=uuid.uuid4(), slug="basic", name="Basic")
        ]
        request = TenantImportRequest(archive=archive)
        result = await svc.import_tenant(TENANT_ID, request)

        assert result.created.get("backend_apis") == 1
        assert result.created.get("plans") == 1
        assert result.success is True
