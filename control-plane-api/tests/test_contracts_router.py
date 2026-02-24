"""Tests for Contracts Router — CAB-1452

Covers: /v1/contracts (CRUD, bindings, MCP tools) and /v1/mcp/generated-tools.
Router uses direct SQLAlchemy queries (no repository pattern), so db.execute is mocked.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

CACHE_PATH = "src.routers.contracts.contract_cache"
ADAPTER_PATH = "src.routers.contracts.AdapterRegistry"
GENERATOR_PATH = "src.routers.contracts.UacToolGenerator"


def _mock_contract(tenant_id: str = "acme") -> MagicMock:
    c = MagicMock()
    c.id = uuid4()
    c.tenant_id = tenant_id
    c.name = "payment-service"
    c.display_name = "Payment Service API"
    c.description = "API for processing payments"
    c.version = "1.0.0"
    c.status = "draft"
    c.openapi_spec_url = None
    c.schema_hash = None
    c.created_at = datetime.utcnow()
    c.updated_at = datetime.utcnow()
    c.created_by = "tenant-admin-user-id"
    return c


def _mock_binding(protocol: str = "rest", enabled: bool = False) -> MagicMock:
    b = MagicMock()
    b.protocol = protocol
    b.enabled = enabled
    b.endpoint = None
    b.playground_url = None
    b.tool_name = None
    b.operations = None
    b.proto_file_url = None
    b.topic_name = None
    b.traffic_24h = None
    b.generated_at = None
    b.generation_error = None
    return b


class TestCreateContract:
    """Tests for POST /v1/contracts."""

    def test_create_contract_success(self, app_with_tenant_admin, mock_db_session):
        _now = datetime.utcnow()
        no_conflict_result = MagicMock()
        no_conflict_result.scalar_one_or_none.return_value = None

        # _get_or_create_default_bindings will query and get empty → creates 5 bindings
        bindings_result = MagicMock()
        bindings_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[no_conflict_result, bindings_result])

        # Intercept db.add: when the Contract object is added, stamp its timestamps.
        from src.models.contract import Contract as ContractModel

        def _fake_add(obj: object) -> None:
            if isinstance(obj, ContractModel):
                obj.created_at = _now
                obj.updated_at = _now

        mock_db_session.add = MagicMock(side_effect=_fake_add)
        mock_db_session.flush = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.delete_by_prefix = AsyncMock()

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/contracts", json={"name": "payment-service", "version": "1.0.0"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "payment-service"
        assert data["tenant_id"] == "acme"
        assert data["status"] == "draft"

    def test_create_contract_409_duplicate_name(self, app_with_tenant_admin, mock_db_session):
        conflict_result = MagicMock()
        conflict_result.scalar_one_or_none.return_value = _mock_contract()
        mock_db_session.execute = AsyncMock(return_value=conflict_result)

        mock_cache = AsyncMock()
        mock_cache.delete_by_prefix = AsyncMock()

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/contracts", json={"name": "payment-service"})

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_contract_400_no_tenant(self, app_with_cpi_admin, mock_db_session):
        mock_cache = AsyncMock()
        with patch(CACHE_PATH, mock_cache), TestClient(app_with_cpi_admin) as client:
            resp = client.post("/v1/contracts", json={"name": "payment-service"})
        assert resp.status_code == 400
        assert "tenant" in resp.json()["detail"].lower()


class TestListContracts:
    """Tests for GET /v1/contracts."""

    def test_list_contracts_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract()
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 1

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [contract]

        bindings_result = MagicMock()
        bindings_result.scalars.return_value.all.return_value = [_mock_binding()]

        mock_db_session.execute = AsyncMock(side_effect=[count_result, list_result, bindings_result])

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/contracts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_contracts_uses_cache(self, app_with_tenant_admin, mock_db_session):
        from src.schemas.contract import ContractListResponse

        cached = ContractListResponse(items=[], total=0, page=1, page_size=20)
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=cached)
        mock_cache.set = AsyncMock()

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/contracts")

        assert resp.status_code == 200
        mock_db_session.execute.assert_not_awaited()

    def test_list_contracts_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[count_result, list_result])

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/contracts")

        assert resp.status_code == 200


class TestGetContract:
    """Tests for GET /v1/contracts/{contract_id}."""

    def test_get_contract_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        bindings_result = MagicMock()
        bindings_result.scalars.return_value.all.return_value = [_mock_binding()]

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, bindings_result])

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{contract.id}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "payment-service"

    def test_get_contract_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{uuid4()}")

        assert resp.status_code == 404

    def test_get_contract_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="other-tenant")
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{contract.id}")

        assert resp.status_code == 403


class TestUpdateContract:
    """Tests for PATCH /v1/contracts/{contract_id}."""

    def test_update_contract_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        bindings_result = MagicMock()
        bindings_result.scalars.return_value.all.return_value = [_mock_binding()]

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, bindings_result])
        mock_db_session.flush = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.delete_by_prefix = AsyncMock()

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(f"/v1/contracts/{contract.id}", json={"version": "2.0.0"})

        assert resp.status_code == 200

    def test_update_contract_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(f"/v1/contracts/{uuid4()}", json={"version": "2.0.0"})

        assert resp.status_code == 404

    def test_update_contract_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="other-tenant")
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.patch(f"/v1/contracts/{contract.id}", json={"version": "2.0.0"})

        assert resp.status_code == 403


class TestDeleteContract:
    """Tests for DELETE /v1/contracts/{contract_id}."""

    def test_delete_contract_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)
        mock_db_session.delete = AsyncMock()

        mock_cache = AsyncMock()
        mock_cache.delete_by_prefix = AsyncMock()

        with patch(CACHE_PATH, mock_cache), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{contract.id}")

        assert resp.status_code == 204
        mock_db_session.delete.assert_awaited_once()

    def test_delete_contract_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_contract_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="other-tenant")
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{contract.id}")

        assert resp.status_code == 403


class TestListBindings:
    """Tests for GET /v1/contracts/{contract_id}/bindings."""

    def test_list_bindings_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        bindings_result = MagicMock()
        bindings_result.scalars.return_value.all.return_value = [
            _mock_binding("rest", True),
            _mock_binding("mcp", False),
        ]

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, bindings_result])

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{contract.id}/bindings")

        assert resp.status_code == 200
        assert resp.json()["contract_name"] == "payment-service"

    def test_list_bindings_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{uuid4()}/bindings")

        assert resp.status_code == 404


class TestEnableBinding:
    """Tests for POST /v1/contracts/{contract_id}/bindings."""

    def test_enable_binding_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = None

        gw_result = MagicMock()
        gw_result.scalars.return_value.all.return_value = []

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, binding_result, gw_result])
        mock_db_session.flush = AsyncMock()

        with patch(ADAPTER_PATH, MagicMock()), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{contract.id}/bindings", json={"protocol": "rest"})

        assert resp.status_code == 200
        assert resp.json()["protocol"] == "rest"
        assert resp.json()["status"] == "active"

    def test_enable_binding_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{uuid4()}/bindings", json={"protocol": "rest"})

        assert resp.status_code == 404

    def test_enable_binding_409_already_enabled(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        binding = _mock_binding("rest", enabled=True)

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = binding

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, binding_result])

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{contract.id}/bindings", json={"protocol": "rest"})

        assert resp.status_code == 409


class TestDisableBinding:
    """Tests for DELETE /v1/contracts/{contract_id}/bindings/{protocol}."""

    def test_disable_binding_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        binding = _mock_binding("rest", enabled=True)

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = binding

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, binding_result])
        mock_db_session.flush = AsyncMock()

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{contract.id}/bindings/rest")

        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_disable_binding_404_binding_not_found(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = None

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, binding_result])

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{contract.id}/bindings/rest")

        assert resp.status_code == 404

    def test_disable_binding_409_already_disabled(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        binding = _mock_binding("rest", enabled=False)

        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = contract

        binding_result = MagicMock()
        binding_result.scalar_one_or_none.return_value = binding

        mock_db_session.execute = AsyncMock(side_effect=[contract_result, binding_result])

        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/contracts/{contract.id}/bindings/rest")

        assert resp.status_code == 409


class TestGenerateMcpTools:
    """Tests for POST /v1/contracts/{contract_id}/mcp-tools/generate."""

    def test_generate_mcp_tools_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        contract_result = MagicMock()
        contract_result.scalars.return_value.first.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        mock_generator = MagicMock()
        mock_generator.generate_tools = AsyncMock(return_value=[])

        with patch(GENERATOR_PATH, return_value=mock_generator), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{contract.id}/mcp-tools/generate")

        assert resp.status_code == 200
        assert resp.json()["generated"] == 0

    def test_generate_mcp_tools_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{uuid4()}/mcp-tools/generate")

        assert resp.status_code == 404

    def test_generate_mcp_tools_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="other-tenant")
        contract_result = MagicMock()
        contract_result.scalars.return_value.first.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/contracts/{contract.id}/mcp-tools/generate")

        assert resp.status_code == 403


class TestListMcpTools:
    """Tests for GET /v1/contracts/{contract_id}/mcp-tools."""

    def test_list_mcp_tools_success(self, app_with_tenant_admin, mock_db_session):
        contract = _mock_contract(tenant_id="acme")
        contract_result = MagicMock()
        contract_result.scalars.return_value.first.return_value = contract
        mock_db_session.execute = AsyncMock(return_value=contract_result)

        mock_generator = MagicMock()
        mock_generator.get_tools_for_contract = AsyncMock(return_value=[])

        with patch(GENERATOR_PATH, return_value=mock_generator), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{contract.id}/mcp-tools")

        assert resp.status_code == 200
        assert resp.json()["contract_name"] == "payment-service"

    def test_list_mcp_tools_404(self, app_with_tenant_admin, mock_db_session):
        not_found = MagicMock()
        not_found.scalars.return_value.first.return_value = None
        mock_db_session.execute = AsyncMock(return_value=not_found)

        with TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/contracts/{uuid4()}/mcp-tools")

        assert resp.status_code == 404


class TestGetTenantTools:
    """Tests for GET /v1/mcp/generated-tools (discovery router)."""

    def test_get_tenant_tools_success(self, app_with_tenant_admin, mock_db_session):
        mock_generator = MagicMock()
        mock_generator.get_tools_for_tenant = AsyncMock(return_value=[])

        with patch(GENERATOR_PATH, return_value=mock_generator), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/mcp/generated-tools?tenant_id=acme")

        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "acme"
        assert resp.json()["total"] == 0

    def test_get_tenant_tools_403_cross_tenant(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/mcp/generated-tools?tenant_id=other-tenant")

        assert resp.status_code == 403

    def test_get_tenant_tools_cpi_admin_any_tenant(self, app_with_cpi_admin, mock_db_session):
        mock_generator = MagicMock()
        mock_generator.get_tools_for_tenant = AsyncMock(return_value=[])

        with patch(GENERATOR_PATH, return_value=mock_generator), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/mcp/generated-tools?tenant_id=any-tenant")

        assert resp.status_code == 200
