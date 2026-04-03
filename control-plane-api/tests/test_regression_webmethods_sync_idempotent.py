"""Regression test: webMethods sync_api upsert + list_apis normalization (CAB-1938).

Two bugs caused an infinite sync loop:

Bug A — list_apis returned nested objects {"api": {"apiName": ..., "id": ...}}.
  Drift detection called api.get("id") on the parent → None → false "API missing"
  drift → DRIFTED → re-sync → 500 (duplicate POST).

Bug B — sync_api returned the existing API without updating the spec. Even if the
  match worked, actual_state was stale → spec_hash mismatch → drift → re-sync.

Fix: list_apis normalizes to flat format. sync_api deletes then reimports so the
latest spec is always applied.
"""

from unittest.mock import AsyncMock

from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter


def _make_adapter() -> WebMethodsGatewayAdapter:
    adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
    adapter._config = {"base_url": "http://test:5555"}
    adapter._svc = AsyncMock()
    return adapter


# ── list_apis normalization ──────────────────────────────────────────


class TestListApisNormalization:
    async def test_list_apis_normalizes_nested_format(self) -> None:
        """list_apis must unwrap {"api": {...}} to flat objects."""
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(
            return_value=[
                {
                    "api": {"id": "wm-1", "apiName": "api-alpha", "apiVersion": "1.0"},
                    "responseStatus": "SUCCESS",
                },
                {
                    "api": {"id": "wm-2", "apiName": "api-beta", "apiVersion": "2.0"},
                    "responseStatus": "SUCCESS",
                },
            ]
        )

        result = await adapter.list_apis()

        assert len(result) == 2
        assert result[0]["id"] == "wm-1"
        assert result[0]["apiName"] == "api-alpha"
        assert result[1]["id"] == "wm-2"
        # No nested "api" key — flat objects
        assert "api" not in result[0]

    async def test_list_apis_handles_already_flat_format(self) -> None:
        """list_apis must also handle flat objects (no nesting)."""
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(return_value=[{"id": "flat-1", "apiName": "api-flat", "apiVersion": "1.0"}])

        result = await adapter.list_apis()

        assert len(result) == 1
        assert result[0]["id"] == "flat-1"
        assert result[0]["apiName"] == "api-flat"

    async def test_list_apis_empty(self) -> None:
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(return_value=[])

        result = await adapter.list_apis()

        assert result == []


# ── sync_api upsert (delete + reimport) ──────────────────────────────


class TestSyncApiUpsert:
    async def test_sync_api_deletes_existing_before_reimport(self) -> None:
        """sync_api must delete the existing API then reimport with latest spec."""
        adapter = _make_adapter()
        # list_apis is now normalized — returns flat objects
        adapter._svc.list_apis = AsyncMock(
            return_value=[{"api": {"id": "wm-old", "apiName": "api-beta", "apiVersion": "1.0.0"}}]
        )
        adapter._svc.delete_api = AsyncMock()
        adapter._svc.import_api = AsyncMock(return_value={"apiResponse": {"api": {"id": "wm-new"}}})

        result = await adapter.sync_api(
            api_spec={
                "api_name": "api-beta",
                "version": "1.0.0",
                "openapi_spec": {"openapi": "3.0.0"},
            },
            tenant_id="free-aech",
        )

        assert result.success is True
        assert result.resource_id == "wm-new"
        adapter._svc.delete_api.assert_awaited_once_with("wm-old", auth_token=None)
        adapter._svc.import_api.assert_awaited_once()

    async def test_sync_api_creates_when_no_match(self) -> None:
        """sync_api must only import (no delete) when no existing API matches."""
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(return_value=[])
        adapter._svc.delete_api = AsyncMock()
        adapter._svc.import_api = AsyncMock(return_value={"apiResponse": {"api": {"id": "new-1"}}})

        result = await adapter.sync_api(
            api_spec={"apiName": "api-beta", "apiVersion": "1.0.0"},
            tenant_id="free-aech",
        )

        assert result.success is True
        assert result.resource_id == "new-1"
        adapter._svc.delete_api.assert_not_awaited()
        adapter._svc.import_api.assert_awaited_once()

    async def test_sync_api_creates_when_different_version(self) -> None:
        """sync_api must not delete APIs with a different version."""
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(
            return_value=[{"api": {"id": "wm-old", "apiName": "api-beta", "apiVersion": "0.9.0"}}]
        )
        adapter._svc.delete_api = AsyncMock()
        adapter._svc.import_api = AsyncMock(return_value={"apiResponse": {"api": {"id": "wm-new"}}})

        result = await adapter.sync_api(
            api_spec={"apiName": "api-beta", "apiVersion": "1.0.0"},
            tenant_id="free-aech",
        )

        assert result.success is True
        adapter._svc.delete_api.assert_not_awaited()
        adapter._svc.import_api.assert_awaited_once()

    async def test_sync_api_reimport_updates_resource_id(self) -> None:
        """After delete+reimport, resource_id must be the NEW gateway ID."""
        adapter = _make_adapter()
        adapter._svc.list_apis = AsyncMock(
            return_value=[{"api": {"id": "old-id", "apiName": "svc", "apiVersion": "1.0"}}]
        )
        adapter._svc.delete_api = AsyncMock()
        adapter._svc.import_api = AsyncMock(return_value={"apiResponse": {"api": {"id": "brand-new-id"}}})

        result = await adapter.sync_api(
            api_spec={"apiName": "svc", "apiVersion": "1.0"},
            tenant_id="t",
        )

        assert result.resource_id == "brand-new-id"
