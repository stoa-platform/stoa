"""
Tests for Contracts Router - CAB-839

Target: 80%+ coverage on src/routers/contracts.py
Tests: 9 test cases covering CRUD, bindings, and authorization
"""

import pytest
from datetime import datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# Mock ProtocolType enum to match the actual model
class ProtocolType(str, Enum):
    """Mock ProtocolType for testing - mirrors src.models.contract.ProtocolType"""
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    MCP = "mcp"
    KAFKA = "kafka"


class TestContractsRouter:
    """Test suite for Contracts Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_contract(self, data: dict) -> MagicMock:
        """Create a mock Contract object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    def _create_mock_binding(
        self,
        contract_id,
        protocol: ProtocolType,
        enabled: bool = False
    ) -> MagicMock:
        """Create a mock ProtocolBinding object."""
        mock = MagicMock()
        mock.id = uuid4()
        mock.contract_id = contract_id
        mock.protocol = protocol
        mock.enabled = enabled
        mock.endpoint = f"https://api.example.com/{protocol.value}" if enabled else None
        mock.playground_url = None
        mock.tool_name = None
        mock.operations = None
        mock.proto_file_url = None
        mock.topic_name = None
        mock.generated_at = datetime.utcnow() if enabled else None
        mock.generation_error = None
        return mock

    def _create_default_bindings(self, contract_id) -> list:
        """Create all 5 default protocol bindings (disabled)."""
        return [
            self._create_mock_binding(contract_id, protocol)
            for protocol in ProtocolType
        ]

    # ============== Create Contract Tests ==============

    def test_create_contract_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test successful contract creation with default bindings."""

        # Mock db.execute for duplicate check (returns None)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        # Mock db.execute for bindings query (returns empty list initially)
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: duplicate check
                return mock_result
            else:
                # Subsequent calls: bindings query
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        # Track added items to set timestamps on flush
        added_items = []

        def track_add(item):
            added_items.append(item)

        async def mock_flush():
            # Set timestamps on Contract instances (simulating DB behavior)
            now = datetime.utcnow()
            for item in added_items:
                if hasattr(item, 'created_at') and item.created_at is None:
                    item.created_at = now
                if hasattr(item, 'updated_at') and item.updated_at is None:
                    item.updated_at = now

        mock_db_session.add = MagicMock(side_effect=track_add)
        mock_db_session.flush = AsyncMock(side_effect=mock_flush)

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/contracts",
                json={
                    "name": "payment-service",
                    "display_name": "Payment Service API",
                    "description": "API for processing payments",
                    "version": "1.0.0",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "payment-service"
        assert data["status"] == "draft"
        assert "bindings" in data
        # All 5 protocols should be present
        assert len(data["bindings"]) == 5

    def test_create_contract_409_duplicate(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test creating duplicate contract returns 409."""
        mock_existing = self._create_mock_contract(sample_contract_data)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/contracts",
                json={
                    "name": "payment-service",
                    "display_name": "Payment Service API",
                },
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_contract_400_no_tenant(
        self, app_with_no_tenant_user, mock_db_session
    ):
        """Test user without tenant cannot create contract."""
        with TestClient(app_with_no_tenant_user) as client:
            response = client.post(
                "/v1/contracts",
                json={
                    "name": "orphan-contract",
                    "display_name": "Should Fail",
                },
            )

        assert response.status_code == 400
        assert "must belong to a tenant" in response.json()["detail"]

    # ============== List Contracts Tests ==============

    def test_list_contracts_pagination(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test listing contracts with pagination."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock select query
        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [mock_contract]

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_count_result
            elif call_count[0] == 2:
                return mock_select_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/contracts?page=1&page_size=20")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 20

    # ============== Get Contract Tests ==============

    def test_get_contract_with_bindings(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test getting contract with all bindings."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_bindings = self._create_default_bindings(sample_contract_data["id"])

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = mock_bindings

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/contracts/{sample_contract_data['id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "payment-service"
        assert len(data["bindings"]) == 5

    def test_get_contract_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session, sample_contract_data
    ):
        """Test user from different tenant cannot access contract."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        # Contract belongs to 'acme', user is from 'other-tenant'

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_other_tenant) as client:
            response = client.get(f"/v1/contracts/{sample_contract_data['id']}")

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # ============== Enable Binding Tests ==============

    def test_enable_binding_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test enabling a protocol binding (e.g., GraphQL)."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_binding = self._create_mock_binding(
            sample_contract_data["id"],
            ProtocolType.GRAPHQL,
            enabled=False
        )

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = mock_binding

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                f"/v1/contracts/{sample_contract_data['id']}/bindings",
                json={"protocol": "graphql"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "graphql"
        assert data["status"] == "active"
        assert "endpoint" in data

    def test_enable_binding_409_already_enabled(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test enabling already-enabled binding returns 409."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_binding = self._create_mock_binding(
            sample_contract_data["id"],
            ProtocolType.REST,
            enabled=True  # Already enabled
        )

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = mock_binding

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                f"/v1/contracts/{sample_contract_data['id']}/bindings",
                json={"protocol": "rest"},
            )

        assert response.status_code == 409
        assert "already enabled" in response.json()["detail"]

    # ============== Disable Binding Tests ==============

    def test_disable_binding_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test disabling an enabled protocol binding."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_binding = self._create_mock_binding(
            sample_contract_data["id"],
            ProtocolType.REST,
            enabled=True  # Currently enabled
        )

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = mock_binding

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(
                f"/v1/contracts/{sample_contract_data['id']}/bindings/rest"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "rest"
        assert data["status"] == "disabled"

    # ============== Phase 2: Update Contract Tests ==============

    def test_update_contract_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test updating contract with partial fields."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_bindings = self._create_default_bindings(sample_contract_data["id"])

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = mock_bindings

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.patch(
                f"/v1/contracts/{sample_contract_data['id']}",
                json={"display_name": "Updated Payment API", "description": "Updated description"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "bindings" in data

    def test_update_contract_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test updating non-existent contract returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.patch(
                f"/v1/contracts/{uuid4()}",
                json={"display_name": "Updated Name"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_update_contract_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session, sample_contract_data
    ):
        """Test updating contract from other tenant returns 403."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_other_tenant) as client:
            response = client.patch(
                f"/v1/contracts/{sample_contract_data['id']}",
                json={"display_name": "Hacked Name"},
            )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # ============== Phase 2: Delete Contract Tests ==============

    def test_delete_contract_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test deleting contract successfully."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/contracts/{sample_contract_data['id']}")

        assert response.status_code == 204

    def test_delete_contract_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test deleting non-existent contract returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/contracts/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_delete_contract_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session, sample_contract_data
    ):
        """Test deleting contract from other tenant returns 403."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_contract
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_other_tenant) as client:
            response = client.delete(f"/v1/contracts/{sample_contract_data['id']}")

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # ============== Phase 2: Binding Error Tests ==============

    def test_get_contract_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test getting non-existent contract returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/contracts/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_disable_binding_404_not_found(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test disabling non-existent binding returns 404."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        # Mock contract query success
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query returns None (not found)
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = None

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(
                f"/v1/contracts/{sample_contract_data['id']}/bindings/grpc"
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    # ============== Phase 3: CPI-Admin Access (Line 41) ==============

    def test_list_contracts_cpi_admin(
        self, app_with_cpi_admin, mock_db_session, sample_contract_data
    ):
        """Test CPI admin can list all contracts across tenants."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        # Mock count query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock select query
        mock_select_result = MagicMock()
        mock_select_result.scalars.return_value.all.return_value = [mock_contract]

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_count_result
            elif call_count[0] == 2:
                return mock_select_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_cpi_admin) as client:
            response = client.get("/v1/contracts?page=1&page_size=20")

        # CPI admin should see contracts from all tenants
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    # ============== Phase 3: Update All Fields (Lines 333-342) ==============

    def test_update_contract_all_fields(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test PATCH /{id} updates all supported fields."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_bindings = self._create_default_bindings(sample_contract_data["id"])

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = mock_bindings

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.patch(
                f"/v1/contracts/{sample_contract_data['id']}",
                json={
                    "display_name": "Updated Display Name",
                    "description": "Updated description",
                    "version": "2.0.0",
                    "status": "published",
                    "openapi_spec_url": "https://example.com/spec.yaml",
                },
            )

        assert response.status_code == 200
        # Verify all fields were processed (mock contract object would be updated)

    # ============== Phase 3: List Bindings Success (Lines 410-430) ==============

    def test_list_bindings_success(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test GET /{id}/bindings returns all protocol bindings."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_bindings = self._create_default_bindings(sample_contract_data["id"])
        # Enable one binding to test traffic_24h calculation
        mock_bindings[0].enabled = True

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock bindings query
        mock_bindings_result = MagicMock()
        mock_bindings_result.scalars.return_value.all.return_value = mock_bindings

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_bindings_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/contracts/{sample_contract_data['id']}/bindings")

        assert response.status_code == 200
        data = response.json()
        assert "bindings" in data
        assert data["contract_id"] == str(sample_contract_data["id"])
        assert len(data["bindings"]) == 5

    # ============== Phase 3: Enable Binding Creates New Binding (Lines 465-472) ==============

    def test_enable_binding_creates_new(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test enabling creates new binding if not exists."""
        mock_contract = self._create_mock_contract(sample_contract_data)

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query returns None (binding doesn't exist yet)
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = None

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                f"/v1/contracts/{sample_contract_data['id']}/bindings",
                json={"protocol": "mcp"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["protocol"] == "mcp"
        assert data["status"] == "active"
        # Verify db.add was called (new binding created)
        assert mock_db_session.add.called

    # ============== Phase 3: Disable Binding Already Disabled (Line 548-550) ==============

    def test_disable_binding_409_already_disabled(
        self, app_with_tenant_admin, mock_db_session, sample_contract_data
    ):
        """Test DELETE /{id}/bindings/{protocol} on disabled binding → 409."""
        mock_contract = self._create_mock_contract(sample_contract_data)
        mock_binding = self._create_mock_binding(
            sample_contract_data["id"],
            ProtocolType.KAFKA,
            enabled=False  # Already disabled
        )

        # Mock contract query
        mock_contract_result = MagicMock()
        mock_contract_result.scalar_one_or_none.return_value = mock_contract

        # Mock binding query
        mock_binding_result = MagicMock()
        mock_binding_result.scalar_one_or_none.return_value = mock_binding

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_contract_result
            else:
                return mock_binding_result

        mock_db_session.execute = AsyncMock(side_effect=mock_execute)

        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(
                f"/v1/contracts/{sample_contract_data['id']}/bindings/kafka"
            )

        assert response.status_code == 409
        assert "already disabled" in response.json()["detail"]
