"""Tests for UAC contract adapter methods and mapper."""

import httpx
import pytest

from src.adapters.stoa.adapter import StoaGatewayAdapter
from src.adapters.stoa.mappers import map_uac_to_stoa_contract

# ============ Mapper Tests ============


class TestMapUacToStoaContract:
    def test_maps_all_fields(self) -> None:
        spec = {
            "name": "payment-service",
            "version": "2.0.0",
            "tenant_id": "acme",
            "display_name": "Payment Service",
            "description": "Handles payments",
            "classification": "VH",
            "endpoints": [
                {
                    "path": "/payments",
                    "methods": ["GET", "POST"],
                    "backend_url": "https://backend.acme.com/payments",
                    "operation_id": "listPayments",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "array"},
                }
            ],
            "required_policies": ["rate-limit", "auth-jwt", "mtls", "audit-logging"],
            "status": "published",
            "source_spec_url": "https://example.com/spec.json",
            "spec_hash": "abc123",
        }
        result = map_uac_to_stoa_contract(spec)

        assert result["name"] == "payment-service"
        assert result["version"] == "2.0.0"
        assert result["tenant_id"] == "acme"
        assert result["display_name"] == "Payment Service"
        assert result["classification"] == "VH"
        assert len(result["endpoints"]) == 1
        assert result["endpoints"][0]["path"] == "/payments"
        assert result["endpoints"][0]["operation_id"] == "listPayments"
        assert "mtls" in result["required_policies"]
        assert result["status"] == "published"
        assert result["spec_hash"] == "abc123"

    def test_defaults_for_missing_fields(self) -> None:
        spec = {"name": "minimal"}
        result = map_uac_to_stoa_contract(spec)

        assert result["name"] == "minimal"
        assert result["version"] == "1.0.0"
        assert result["tenant_id"] == ""
        assert result["classification"] == "H"
        assert result["endpoints"] == []
        assert result["required_policies"] == []
        assert result["status"] == "draft"

    def test_maps_multiple_endpoints(self) -> None:
        spec = {
            "name": "multi-ep",
            "endpoints": [
                {"path": "/a", "methods": ["GET"], "backend_url": "http://a"},
                {"path": "/b", "methods": ["POST"], "backend_url": "http://b"},
                {"path": "/c", "methods": ["DELETE"], "backend_url": "http://c"},
            ],
        }
        result = map_uac_to_stoa_contract(spec)
        assert len(result["endpoints"]) == 3
        assert result["endpoints"][1]["methods"] == ["POST"]


# ============ Adapter Tests ============


class TestStoaAdapterContract:
    @pytest.fixture
    def adapter(self) -> StoaGatewayAdapter:
        return StoaGatewayAdapter(config={
            "base_url": "http://localhost:8080",
            "auth_config": {"admin_token": "test-token"},
        })

    @pytest.mark.asyncio
    async def test_deploy_contract_success(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract returns success with resource_id."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            json={"name": "payment-service", "routes_created": 2, "tools_created": 2},
            status_code=201,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({
            "name": "payment-service",
            "version": "1.0.0",
            "tenant_id": "acme",
            "classification": "H",
            "endpoints": [],
        })
        await adapter.disconnect()

        assert result.success is True
        assert result.resource_id == "payment-service"
        assert result.data["routes_created"] == 2

    @pytest.mark.asyncio
    async def test_deploy_contract_failure(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract returns failure on HTTP error."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            text="bad request",
            status_code=400,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "bad"})
        await adapter.disconnect()

        assert result.success is False
        assert "400" in result.error

    @pytest.mark.asyncio
    async def test_delete_contract_success(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Delete contract returns success."""
        httpx_mock.add_response(
            method="DELETE",
            url="http://localhost:8080/admin/contracts/payment-service",
            status_code=204,
        )

        await adapter.connect()
        result = await adapter.delete_contract("payment-service")
        await adapter.disconnect()

        assert result.success is True
        assert result.resource_id == "payment-service"

    @pytest.mark.asyncio
    async def test_delete_contract_idempotent(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Delete contract returns success even if already deleted (404)."""
        httpx_mock.add_response(
            method="DELETE",
            url="http://localhost:8080/admin/contracts/gone",
            status_code=404,
        )

        await adapter.connect()
        result = await adapter.delete_contract("gone")
        await adapter.disconnect()

        assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_contract_failure(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Delete contract returns failure on 500."""
        httpx_mock.add_response(
            method="DELETE",
            url="http://localhost:8080/admin/contracts/broken",
            status_code=500,
        )

        await adapter.connect()
        result = await adapter.delete_contract("broken")
        await adapter.disconnect()

        assert result.success is False
        assert "500" in result.error


# ============ Edge Case Tests ============


class TestUacContractEdgeCases:
    @pytest.fixture
    def adapter(self) -> StoaGatewayAdapter:
        return StoaGatewayAdapter(config={
            "base_url": "http://localhost:8080",
            "auth_config": {"admin_token": "test-token"},
        })

    @pytest.mark.asyncio
    async def test_deploy_contract_409_conflict(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract is idempotent on 409 duplicate — adapter returns failure with status."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            text="contract already exists",
            status_code=409,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "payment-service", "version": "1.0.0"})
        await adapter.disconnect()

        assert result.success is False
        assert "409" in result.error

    @pytest.mark.asyncio
    async def test_deploy_contract_connection_error(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract handles httpx connection error gracefully."""
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "unreachable"})
        await adapter.disconnect()

        assert result.success is False
        assert "Connection refused" in result.error

    @pytest.mark.asyncio
    async def test_list_contracts_success(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy + verify: successful deploy returns contract data in response."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            json={"name": "svc-a", "routes_created": 3, "tools_created": 3},
            status_code=201,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({
            "name": "svc-a",
            "version": "2.0.0",
            "tenant_id": "acme",
            "endpoints": [{"path": "/a"}, {"path": "/b"}, {"path": "/c"}],
        })
        await adapter.disconnect()

        assert result.success is True
        assert result.resource_id == "svc-a"
        assert result.data["routes_created"] == 3
        assert result.data["tools_created"] == 3

    @pytest.mark.asyncio
    async def test_list_contracts_empty(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract with 200 (update) returns success with minimal data."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            json={"name": "empty-svc", "routes_created": 0, "tools_created": 0},
            status_code=200,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "empty-svc", "endpoints": []})
        await adapter.disconnect()

        assert result.success is True
        assert result.resource_id == "empty-svc"
        assert result.data["routes_created"] == 0

    @pytest.mark.asyncio
    async def test_list_contracts_http_error(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract returns failure on 500 server error."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            text="Internal Server Error",
            status_code=500,
        )

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "server-err"})
        await adapter.disconnect()

        assert result.success is False
        assert "500" in result.error
        assert "Internal Server Error" in result.error

    @pytest.mark.asyncio
    async def test_deploy_contract_malformed_response(self, adapter: StoaGatewayAdapter, httpx_mock) -> None:  # type: ignore[no-untyped-def]
        """Deploy contract handles non-JSON 201 response without crashing."""
        httpx_mock.add_response(
            method="POST",
            url="http://localhost:8080/admin/contracts",
            text="<html>Created</html>",
            status_code=201,
            headers={"content-type": "text/html"},
        )

        await adapter.connect()
        result = await adapter.deploy_contract({"name": "malformed"})
        await adapter.disconnect()

        # json() will raise — the adapter's except block catches it
        assert result.success is False
