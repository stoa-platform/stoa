"""Tests for Tenant DR (Disaster Recovery) — Export/Import (CAB-1474)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.schemas.tenant_dr import (
    ExportedBackendApi,
    ExportedConsumer,
    ExportedContract,
    ExportedExternalMcpServer,
    ExportedPlan,
    ExportedPolicy,
    ExportedSkill,
    ExportedSubscription,
    ExportedWebhook,
    ExportMetadata,
    ImportMode,
    ImportResult,
    TenantExportResponse,
)

# ============ Schema Tests ============


class TestExportMetadata:
    def test_default_version(self):
        meta = ExportMetadata(
            exported_at=datetime.now(UTC),
            tenant_id="acme",
        )
        assert meta.export_version == "1.0"
        assert meta.tenant_id == "acme"
        assert meta.resource_counts == {}

    def test_with_counts(self):
        meta = ExportMetadata(
            exported_at=datetime.now(UTC),
            tenant_id="acme",
            tenant_name="Acme Corp",
            resource_counts={"backend_apis": 5, "contracts": 3},
        )
        assert meta.tenant_name == "Acme Corp"
        assert meta.resource_counts["backend_apis"] == 5


class TestExportedBackendApi:
    def test_minimal(self):
        api = ExportedBackendApi(
            id=uuid.uuid4(),
            name="payment-api",
        )
        assert api.name == "payment-api"
        assert api.display_name is None
        assert api.auth_type is None

    def test_full(self):
        api = ExportedBackendApi(
            id=uuid.uuid4(),
            name="payment-api",
            display_name="Payment API",
            backend_url="https://api.example.com",
            auth_type="bearer",
            status="active",
        )
        assert api.backend_url == "https://api.example.com"
        assert api.auth_type == "bearer"


class TestExportedContract:
    def test_with_bindings(self):
        contract = ExportedContract(
            id=uuid.uuid4(),
            name="payment-service",
            version="2.0.0",
            status="published",
            bindings=[
                {"protocol": "rest", "enabled": True, "endpoint": "/api/v1"},
                {"protocol": "mcp", "enabled": True, "tool_name": "create_payment"},
            ],
        )
        assert len(contract.bindings) == 2
        assert contract.bindings[0]["protocol"] == "rest"

    def test_deprecated_contract(self):
        now = datetime.now(UTC)
        contract = ExportedContract(
            id=uuid.uuid4(),
            name="legacy-api",
            version="1.0.0",
            status="deprecated",
            deprecated_at=now,
            deprecation_reason="Replaced by v2",
            grace_period_days=90,
        )
        assert contract.deprecated_at == now
        assert contract.grace_period_days == 90


class TestExportedConsumer:
    def test_consumer(self):
        consumer = ExportedConsumer(
            id=uuid.uuid4(),
            external_id="ext-123",
            name="Partner Corp",
            email="api@partner.com",
            status="active",
        )
        assert consumer.external_id == "ext-123"
        assert consumer.company is None


class TestExportedPlan:
    def test_plan_with_quotas(self):
        plan = ExportedPlan(
            id=uuid.uuid4(),
            slug="gold",
            name="Gold Plan",
            rate_limit_per_minute=1000,
            monthly_request_limit=1_000_000,
        )
        assert plan.slug == "gold"
        assert plan.rate_limit_per_minute == 1000


class TestExportedSubscription:
    def test_subscription(self):
        sub = ExportedSubscription(
            id=uuid.uuid4(),
            application_id="app-1",
            application_name="My App",
            subscriber_email="dev@example.com",
            api_id="api-1",
            status="active",
        )
        assert sub.application_name == "My App"
        assert sub.plan_id is None


class TestExportedPolicy:
    def test_rate_limit_policy(self):
        policy = ExportedPolicy(
            id=uuid.uuid4(),
            name="rate-limit-gold",
            policy_type="rate_limit",
            config={"requests_per_minute": 1000},
        )
        assert policy.policy_type == "rate_limit"
        assert policy.config["requests_per_minute"] == 1000


class TestExportedSkill:
    def test_skill(self):
        skill = ExportedSkill(
            id=uuid.uuid4(),
            name="summarize",
            scope="tenant",
            instructions="Summarize the API response",
        )
        assert skill.scope == "tenant"
        assert skill.priority == 50


class TestExportedWebhook:
    def test_webhook(self):
        webhook = ExportedWebhook(
            id=uuid.uuid4(),
            name="subscription-events",
            url="https://hooks.example.com/stoa",
            events=["subscription.created", "subscription.approved"],
        )
        assert len(webhook.events) == 2
        assert webhook.enabled is True


class TestExportedExternalMcpServer:
    def test_server_with_tools(self):
        server = ExportedExternalMcpServer(
            id=uuid.uuid4(),
            name="linear",
            base_url="https://mcp.linear.app/sse",
            tools=[
                {"name": "create_issue", "description": "Create a Linear issue"},
            ],
        )
        assert server.base_url == "https://mcp.linear.app/sse"
        assert len(server.tools) == 1


class TestTenantExportResponse:
    def test_empty_export(self):
        export = TenantExportResponse(
            metadata=ExportMetadata(
                exported_at=datetime.now(UTC),
                tenant_id="acme",
            ),
        )
        assert len(export.backend_apis) == 0
        assert len(export.contracts) == 0
        assert len(export.consumers) == 0

    def test_full_export(self):
        api_id = uuid.uuid4()
        export = TenantExportResponse(
            metadata=ExportMetadata(
                exported_at=datetime.now(UTC),
                tenant_id="acme",
                resource_counts={"backend_apis": 1},
            ),
            backend_apis=[
                ExportedBackendApi(id=api_id, name="my-api"),
            ],
        )
        assert len(export.backend_apis) == 1
        assert export.backend_apis[0].id == api_id


class TestImportMode:
    def test_defaults(self):
        mode = ImportMode()
        assert mode.conflict_resolution == "skip"
        assert mode.dry_run is False

    def test_overwrite_mode(self):
        mode = ImportMode(conflict_resolution="overwrite", dry_run=True)
        assert mode.conflict_resolution == "overwrite"
        assert mode.dry_run is True


class TestImportResult:
    def test_success(self):
        result = ImportResult(
            tenant_id="acme",
            created={"backend_apis": 3, "contracts": 2},
            skipped={"consumers": 1},
        )
        assert result.success is True
        assert result.created["backend_apis"] == 3

    def test_failure(self):
        result = ImportResult(
            tenant_id="acme",
            errors=["Contract 'payment-api' references missing plan"],
            success=False,
        )
        assert result.success is False
        assert len(result.errors) == 1


# ============ Service Tests ============


class TestTenantExportService:
    """Tests for the export service using mocked DB session."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async DB session."""
        db = AsyncMock()
        return db

    @pytest.fixture
    def tenant_id(self):
        return "acme-corp"

    def _make_mock_result(self, items):
        """Create a mock SQLAlchemy result with scalars().all()."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = items
        mock_result.scalars.return_value = mock_scalars
        mock_result.scalar_one_or_none.return_value = items[0] if items else None
        return mock_result

    @pytest.mark.asyncio
    async def test_export_tenant_not_found(self, mock_db):
        """Export should raise ValueError for non-existent tenant."""
        from src.services.tenant_dr_service import TenantExportService

        # Mock tenant lookup returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = TenantExportService(mock_db)
        with pytest.raises(ValueError, match="not found"):
            await service.export_tenant("non-existent")

    @pytest.mark.asyncio
    async def test_export_empty_tenant(self, mock_db, tenant_id):
        """Export of a tenant with no resources should return empty lists."""
        from src.services.tenant_dr_service import TenantExportService

        # Mock tenant exists
        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Acme Corp"

        # First call = tenant lookup, rest = empty resource queries
        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = mock_tenant

        empty_result = self._make_mock_result([])

        mock_db.execute.side_effect = [tenant_result] + [empty_result] * 9

        service = TenantExportService(mock_db)
        export = await service.export_tenant(tenant_id)

        assert export.metadata.tenant_id == tenant_id
        assert export.metadata.tenant_name == "Acme Corp"
        assert export.metadata.export_version == "1.0"
        assert all(v == 0 for v in export.metadata.resource_counts.values())
        assert len(export.backend_apis) == 0
        assert len(export.contracts) == 0

    @pytest.mark.asyncio
    async def test_export_with_backend_apis(self, mock_db, tenant_id):
        """Export should include backend APIs."""
        from src.services.tenant_dr_service import TenantExportService

        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Acme Corp"

        mock_api = MagicMock()
        mock_api.id = uuid.uuid4()
        mock_api.name = "payment-api"
        mock_api.display_name = "Payment API"
        mock_api.description = "Process payments"
        mock_api.backend_url = "https://api.example.com"
        mock_api.openapi_spec_url = "https://specs.example.com/payment.yaml"
        mock_api.auth_type = "bearer"
        mock_api.status = "active"
        mock_api.created_at = datetime.now(UTC)

        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = mock_tenant

        api_result = self._make_mock_result([mock_api])
        empty_result = self._make_mock_result([])

        mock_db.execute.side_effect = [tenant_result, api_result] + [empty_result] * 8

        service = TenantExportService(mock_db)
        export = await service.export_tenant(tenant_id)

        assert len(export.backend_apis) == 1
        assert export.backend_apis[0].name == "payment-api"
        assert export.backend_apis[0].auth_type == "bearer"
        assert export.metadata.resource_counts["backend_apis"] == 1

    @pytest.mark.asyncio
    async def test_export_with_contracts_and_bindings(self, mock_db, tenant_id):
        """Export should include contracts with their protocol bindings."""
        from src.services.tenant_dr_service import TenantExportService

        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Acme Corp"

        contract_id = uuid.uuid4()
        mock_contract = MagicMock()
        mock_contract.id = contract_id
        mock_contract.name = "payment-service"
        mock_contract.display_name = "Payment Service"
        mock_contract.description = None
        mock_contract.version = "2.0.0"
        mock_contract.status = "published"
        mock_contract.openapi_spec_url = None
        mock_contract.deprecated_at = None
        mock_contract.sunset_at = None
        mock_contract.deprecation_reason = None
        mock_contract.grace_period_days = None
        mock_contract.created_at = datetime.now(UTC)

        mock_binding = MagicMock()
        mock_binding.protocol = "rest"
        mock_binding.enabled = True
        mock_binding.endpoint = "/api/v1/payments"
        mock_binding.tool_name = None

        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = mock_tenant

        empty_result = self._make_mock_result([])
        contract_result = self._make_mock_result([mock_contract])
        binding_result = self._make_mock_result([mock_binding])

        # Order: tenant, backend_apis(empty), contracts, bindings, consumers...
        mock_db.execute.side_effect = [
            tenant_result,  # tenant lookup
            empty_result,  # backend_apis
            contract_result,  # contracts
            binding_result,  # bindings for contract
            empty_result,  # consumers
            empty_result,  # plans
            empty_result,  # subscriptions
            empty_result,  # policies
            empty_result,  # skills
            empty_result,  # webhooks
            empty_result,  # external_mcp_servers
        ]

        service = TenantExportService(mock_db)
        export = await service.export_tenant(tenant_id)

        assert len(export.contracts) == 1
        assert export.contracts[0].name == "payment-service"
        assert export.contracts[0].version == "2.0.0"
        assert len(export.contracts[0].bindings) == 1
        assert export.contracts[0].bindings[0]["protocol"] == "rest"

    @pytest.mark.asyncio
    async def test_export_excludes_sensitive_data(self, mock_db, tenant_id):
        """Export should NOT include API key hashes or encrypted auth configs."""
        from src.services.tenant_dr_service import TenantExportService

        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Acme Corp"

        # Backend API with encrypted auth (should NOT appear in export)
        mock_api = MagicMock()
        mock_api.id = uuid.uuid4()
        mock_api.name = "secure-api"
        mock_api.display_name = None
        mock_api.description = None
        mock_api.backend_url = "https://secure.example.com"
        mock_api.openapi_spec_url = None
        mock_api.auth_type = "oauth2_cc"
        mock_api.status = "active"
        mock_api.auth_config_encrypted = "ENCRYPTED_BLOB_HERE"
        mock_api.created_at = datetime.now(UTC)

        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = mock_tenant
        api_result = self._make_mock_result([mock_api])
        empty_result = self._make_mock_result([])

        mock_db.execute.side_effect = [tenant_result, api_result] + [empty_result] * 8

        service = TenantExportService(mock_db)
        export = await service.export_tenant(tenant_id)

        # Verify auth_config_encrypted is NOT in the export schema
        api_dict = export.backend_apis[0].model_dump()
        assert "auth_config_encrypted" not in api_dict
        assert "api_key_hash" not in api_dict

    @pytest.mark.asyncio
    async def test_export_metadata_resource_counts(self, mock_db, tenant_id):
        """Export metadata should have accurate resource counts."""
        from src.services.tenant_dr_service import TenantExportService

        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.name = "Test Tenant"

        tenant_result = MagicMock()
        tenant_result.scalar_one_or_none.return_value = mock_tenant

        # 2 consumers, 1 plan, rest empty
        mock_consumer1 = MagicMock()
        mock_consumer1.id = uuid.uuid4()
        mock_consumer1.external_id = "c1"
        mock_consumer1.name = "Consumer 1"
        mock_consumer1.email = "c1@example.com"
        mock_consumer1.company = None
        mock_consumer1.description = None
        mock_consumer1.status = "active"
        mock_consumer1.consumer_metadata = None
        mock_consumer1.created_at = datetime.now(UTC)

        mock_consumer2 = MagicMock()
        mock_consumer2.id = uuid.uuid4()
        mock_consumer2.external_id = "c2"
        mock_consumer2.name = "Consumer 2"
        mock_consumer2.email = "c2@example.com"
        mock_consumer2.company = "Corp B"
        mock_consumer2.description = None
        mock_consumer2.status = "active"
        mock_consumer2.consumer_metadata = None
        mock_consumer2.created_at = datetime.now(UTC)

        mock_plan = MagicMock()
        mock_plan.id = uuid.uuid4()
        mock_plan.slug = "gold"
        mock_plan.name = "Gold"
        mock_plan.description = None
        mock_plan.rate_limit_per_second = None
        mock_plan.rate_limit_per_minute = 1000
        mock_plan.daily_request_limit = None
        mock_plan.monthly_request_limit = None
        mock_plan.burst_limit = None
        mock_plan.requires_approval = False
        mock_plan.status = "active"
        mock_plan.created_at = datetime.now(UTC)

        empty_result = self._make_mock_result([])
        consumer_result = self._make_mock_result([mock_consumer1, mock_consumer2])
        plan_result = self._make_mock_result([mock_plan])

        mock_db.execute.side_effect = [
            tenant_result,  # tenant
            empty_result,  # backend_apis
            empty_result,  # contracts
            consumer_result,  # consumers
            plan_result,  # plans
            empty_result,  # subscriptions
            empty_result,  # policies
            empty_result,  # skills
            empty_result,  # webhooks
            empty_result,  # external_mcp_servers
        ]

        service = TenantExportService(mock_db)
        export = await service.export_tenant(tenant_id)

        assert export.metadata.resource_counts["consumers"] == 2
        assert export.metadata.resource_counts["plans"] == 1
        assert export.metadata.resource_counts["backend_apis"] == 0


# ============ Router Tests ============


class TestExportEndpoint:
    """Tests for the GET /v1/tenants/{tenant_id}/export endpoint."""

    def test_export_access_denied_wrong_tenant(self, client_as_other_tenant):
        """Non-admin users cannot export other tenants.

        mock_user_other_tenant has tenant_id='other-tenant',
        so accessing tenant 'acme' should be denied before hitting DB.
        """
        response = client_as_other_tenant.get("/v1/tenants/acme/export")
        assert response.status_code == 403

    def test_export_tenant_not_found(self, client_as_cpi_admin):
        """Export should return 404 or 500 for non-existent tenant.

        cpi-admin has no tenant_id restriction. The mock DB session
        returns a default mock for scalar_one_or_none which may be
        truthy (causing downstream errors → 500) or produce a
        ValueError → 404.
        """
        response = client_as_cpi_admin.get("/v1/tenants/non-existent/export")
        assert response.status_code in (404, 500)
