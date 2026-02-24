"""Tests for UAC → MCP Tool Generator (CAB-605)."""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contract import Contract, McpGeneratedTool
from src.schemas.uac import UacContractSpec, UacEndpointSpec
from src.services.uac_tool_generator import UacToolGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_contract(**overrides) -> Contract:
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "name": "customer-api",
        "display_name": "Customer API",
        "description": "Manage customers",
        "version": "1.0.0",
        "status": "published",
        "openapi_spec_url": "https://specs.acme.com/customers.json",
        "schema_hash": "abc123",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    c = Contract()
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


def _make_uac_spec(**overrides) -> UacContractSpec:
    defaults = {
        "name": "customer-api",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": "Customer API",
        "description": "Manage customers",
        "endpoints": [
            UacEndpointSpec(
                path="/customers",
                methods=["GET"],
                backend_url="https://backend.acme.com/v1/customers",
                operation_id="list_customers",
            ),
            UacEndpointSpec(
                path="/customers/{id}",
                methods=["GET"],
                backend_url="https://backend.acme.com/v1/customers/{id}",
                operation_id="get_customer",
            ),
            UacEndpointSpec(
                path="/customers",
                methods=["POST"],
                backend_url="https://backend.acme.com/v1/customers",
                operation_id="create_customer",
                input_schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                    "required": ["name", "email"],
                },
            ),
        ],
        "spec_hash": "abc123",
    }
    defaults.update(overrides)
    return UacContractSpec(**defaults)


# ---------------------------------------------------------------------------
# Tool naming tests
# ---------------------------------------------------------------------------


class TestToolNaming:
    def test_tool_name_with_operation_id(self):
        ep = UacEndpointSpec(
            path="/customers",
            methods=["GET"],
            backend_url="https://b.com/customers",
            operation_id="searchCustomers",
        )
        name = UacToolGenerator._build_tool_name("acme", "customer-api", ep)
        assert name == "acme:customer-api:searchcustomers"

    def test_tool_name_without_operation_id(self):
        ep = UacEndpointSpec(
            path="/payments/{id}",
            methods=["POST"],
            backend_url="https://b.com/payments/{id}",
        )
        name = UacToolGenerator._build_tool_name("acme", "payment-api", ep)
        assert name == "acme:payment-api:post_payments_id"

    def test_tool_name_special_chars_sanitized(self):
        ep = UacEndpointSpec(
            path="/api/v1/data",
            methods=["GET"],
            backend_url="https://b.com/data",
            operation_id="get-data.v1",
        )
        name = UacToolGenerator._build_tool_name("tenant-a", "data-svc", ep)
        assert name == "tenant-a:data-svc:get_data_v1"

    def test_tool_name_nested_path_no_op_id(self):
        ep = UacEndpointSpec(
            path="/orgs/{org_id}/users/{user_id}",
            methods=["DELETE"],
            backend_url="https://b.com/orgs",
        )
        name = UacToolGenerator._build_tool_name("acme", "iam-api", ep)
        assert name == "acme:iam-api:delete_orgs_org_id_users_user_id"


# ---------------------------------------------------------------------------
# Description tests
# ---------------------------------------------------------------------------


class TestDescription:
    def test_single_method(self):
        ep = UacEndpointSpec(path="/items", methods=["GET"], backend_url="https://b.com/items")
        desc = UacToolGenerator._build_description(ep, "Item Service")
        assert desc == "GET /items — Item Service"

    def test_multiple_methods(self):
        ep = UacEndpointSpec(
            path="/items",
            methods=["GET", "POST"],
            backend_url="https://b.com/items",
        )
        desc = UacToolGenerator._build_description(ep, "Item Service")
        assert desc == "GET, POST /items — Item Service"


# ---------------------------------------------------------------------------
# Input schema tests
# ---------------------------------------------------------------------------


class TestInputSchema:
    def test_explicit_input_schema_passthrough(self):
        ep = UacEndpointSpec(
            path="/customers",
            methods=["POST"],
            backend_url="https://b.com",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        )
        schema = UacToolGenerator._build_input_schema(ep)
        assert schema == ep.input_schema

    def test_path_params_extracted(self):
        ep = UacEndpointSpec(
            path="/customers/{id}/orders/{order_id}",
            methods=["GET"],
            backend_url="https://b.com",
        )
        schema = UacToolGenerator._build_input_schema(ep)
        assert schema["type"] == "object"
        assert "id" in schema["properties"]
        assert "order_id" in schema["properties"]
        assert schema["required"] == ["id", "order_id"]

    def test_no_params_returns_none(self):
        ep = UacEndpointSpec(path="/health", methods=["GET"], backend_url="https://b.com")
        assert UacToolGenerator._build_input_schema(ep) is None


# ---------------------------------------------------------------------------
# generate_tools tests (with mocked DB)
# ---------------------------------------------------------------------------


class TestGenerateTools:
    @pytest.mark.asyncio
    async def test_generate_creates_tools_per_endpoint(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock())
        db.flush = AsyncMock()
        db.add = MagicMock()

        contract = _make_contract()
        spec = _make_uac_spec()

        generator = UacToolGenerator(db)
        tools = await generator.generate_tools(contract, spec)

        assert len(tools) == 3
        assert db.add.call_count == 3

        names = [t.tool_name for t in tools]
        assert "acme:customer-api:list_customers" in names
        assert "acme:customer-api:get_customer" in names
        assert "acme:customer-api:create_customer" in names

    @pytest.mark.asyncio
    async def test_generate_stores_input_schema(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock())
        db.flush = AsyncMock()
        db.add = MagicMock()

        contract = _make_contract()
        spec = _make_uac_spec()

        generator = UacToolGenerator(db)
        tools = await generator.generate_tools(contract, spec)

        # create_customer has explicit input_schema
        create_tool = next(t for t in tools if "create_customer" in t.tool_name)
        schema = json.loads(create_tool.input_schema)
        assert schema["type"] == "object"
        assert "name" in schema["properties"]

        # get_customer has path params → auto-generated schema
        get_tool = next(t for t in tools if "get_customer" in t.tool_name)
        schema = json.loads(get_tool.input_schema)
        assert "id" in schema["properties"]

    @pytest.mark.asyncio
    async def test_generate_with_no_endpoints_creates_nothing(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock())
        db.flush = AsyncMock()
        db.add = MagicMock()

        contract = _make_contract()
        spec = _make_uac_spec(endpoints=[])

        generator = UacToolGenerator(db)
        tools = await generator.generate_tools(contract, spec)

        assert len(tools) == 0
        assert db.add.call_count == 0

    @pytest.mark.asyncio
    async def test_generate_sets_version_and_spec_hash(self):
        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=MagicMock())
        db.flush = AsyncMock()
        db.add = MagicMock()

        contract = _make_contract()
        spec = _make_uac_spec()

        generator = UacToolGenerator(db)
        tools = await generator.generate_tools(contract, spec)

        for tool in tools:
            assert tool.version == "1.0.0"
            assert tool.spec_hash == "abc123"
            assert tool.enabled is True


# ---------------------------------------------------------------------------
# invalidate_tools tests
# ---------------------------------------------------------------------------


class TestInvalidateTools:
    @pytest.mark.asyncio
    async def test_invalidate_disables_all_tools(self):
        # The DB query filters for enabled=True, so only enabled tools are returned
        tool1 = MagicMock(spec=McpGeneratedTool, enabled=True)
        tool2 = MagicMock(spec=McpGeneratedTool, enabled=True)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tool1, tool2]

        db = AsyncMock(spec=AsyncSession)
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        generator = UacToolGenerator(db)
        count = await generator.invalidate_tools(uuid.uuid4())

        assert count == 2
        assert tool1.enabled is False
        assert tool2.enabled is False
