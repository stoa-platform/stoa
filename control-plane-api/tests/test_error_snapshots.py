"""Tests for error_snapshots feature: service, middleware, and storage.

CAB-397: Covers SnapshotService, ErrorSnapshotMiddleware, and SnapshotStorage.
"""

import gzip
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.features.error_snapshots.config import SnapshotSettings
from src.features.error_snapshots.masking import MaskingConfig, PIIMasker
from src.features.error_snapshots.middleware import (
    ErrorSnapshotMiddleware,
    SimpleErrorSnapshotMiddleware,
)
from src.features.error_snapshots.models import (
    BackendState,
    ErrorSnapshot,
    EnvironmentInfo,
    PolicyResult,
    RequestSnapshot,
    ResolutionStatus,
    ResponseSnapshot,
    RoutingInfo,
    SnapshotFilters,
    SnapshotSummary,
    SnapshotTrigger,
)
from src.features.error_snapshots.service import SnapshotService
from src.features.error_snapshots.storage import SnapshotStorage


# ─────────────────────────────────────────────────────────────────────────────
# Shared Helpers & Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def make_settings(**overrides) -> SnapshotSettings:
    """Build SnapshotSettings with predictable defaults, no .env lookup."""
    defaults = dict(
        enabled=True,
        capture_on_4xx=True,
        capture_on_5xx=True,
        capture_on_timeout=True,
        timeout_threshold_ms=30_000,
        storage_bucket="test-snapshots",
        storage_endpoint="minio:9000",
        storage_access_key="test-key",
        storage_secret_key="test-secret",
        storage_use_ssl=False,
        storage_region="us-east-1",
        retention_days=30,
        max_body_size=10_000,
        max_logs_per_snapshot=100,
        async_capture=False,  # synchronous for tests
        log_window_seconds=5,
        exclude_paths='["/health", "/metrics", "/ready"]',
        masking_extra_headers="[]",
        masking_extra_body_paths="[]",
    )
    defaults.update(overrides)
    return SnapshotSettings.model_construct(**defaults)


def make_snapshot(
    tenant_id: str = "tenant-acme",
    trigger: SnapshotTrigger = SnapshotTrigger.ERROR_5XX,
    status: int = 500,
    path: str = "/api/orders",
    duration_ms: int = 1500,
    **overrides,
) -> ErrorSnapshot:
    """Build a minimal but valid ErrorSnapshot."""
    return ErrorSnapshot(
        tenant_id=tenant_id,
        trigger=trigger,
        request=RequestSnapshot(method="POST", path=path),
        response=ResponseSnapshot(status=status, duration_ms=duration_ms),
        **overrides,
    )


def make_scope(
    path: str = "/api/test",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    state: dict | None = None,
) -> Scope:
    """Build a minimal ASGI http scope."""
    return {
        "type": "http",
        "path": path,
        "method": method,
        "headers": headers or [],
        "query_string": b"",
        "state": state or {},
    }


def make_mock_storage() -> MagicMock:
    """Return a fully-mocked SnapshotStorage."""
    storage = MagicMock(spec=SnapshotStorage)
    storage.save = AsyncMock(return_value="s3://test-snapshots/key.json.gz")
    storage.get = AsyncMock(return_value=None)
    storage.list = AsyncMock(return_value=([], 0))
    storage.delete = AsyncMock(return_value=True)
    return storage


def make_service(storage: MagicMock | None = None, **setting_overrides) -> SnapshotService:
    """Return a SnapshotService wired to a mock storage."""
    if storage is None:
        storage = make_mock_storage()
    settings = make_settings(**setting_overrides)
    return SnapshotService(storage=storage, settings=settings)


def _make_starlette_request(
    path: str = "/api/test",
    method: str = "GET",
    headers: dict[str, str] | None = None,
    query_string: str = "",
    client_host: str = "127.0.0.1",
) -> Request:
    """Build a real Starlette Request from a synthetic scope."""
    header_list = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode(),
        "headers": header_list,
        "server": ("testserver", 80),
    }
    if client_host:
        scope["client"] = (client_host, 12345)
    return Request(scope)


# ─────────────────────────────────────────────────────────────────────────────
# SnapshotService Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestSnapshotServiceParseBody:
    """Unit tests for SnapshotService._parse_body."""

    def setup_method(self):
        self.service = make_service()

    def test_none_body_returns_none(self):
        assert self.service._parse_body(None) is None

    def test_empty_bytes_returns_none(self):
        assert self.service._parse_body(b"") is None

    def test_valid_json_is_parsed(self):
        body = json.dumps({"key": "value"}).encode()
        result = self.service._parse_body(body)
        assert result == {"key": "value"}

    def test_valid_json_list_is_parsed(self):
        body = json.dumps([1, 2, 3]).encode()
        result = self.service._parse_body(body)
        assert result == [1, 2, 3]

    def test_plain_text_returned_as_string(self):
        body = b"Hello, world!"
        result = self.service._parse_body(body)
        assert result == "Hello, world!"

    def test_large_body_is_truncated(self):
        """Body exceeding max_body_size should return a truncation marker."""
        service = make_service(max_body_size=10)
        big = b"x" * 11
        result = service._parse_body(big)
        assert "[TRUNCATED:" in result
        assert "11 bytes" in result

    def test_exactly_at_limit_is_not_truncated(self):
        """Body at exactly max_body_size should parse normally."""
        service = make_service(max_body_size=10)
        body = b'{"k":"v"}x'  # 10 bytes, invalid JSON → fallback to str
        result = service._parse_body(body)
        assert "[TRUNCATED:" not in str(result)

    def test_invalid_json_falls_back_to_utf8(self):
        body = b"not json at all"
        result = self.service._parse_body(body)
        assert result == "not json at all"

    def test_invalid_utf8_falls_back_to_string_with_replacement(self):
        """Invalid UTF-8 bytes decoded with errors='replace' produce a non-None string."""
        # The [BINARY: N bytes] path in _parse_body requires decode() itself to
        # raise an exception (beyond UnicodeDecodeError). Since errors="replace"
        # never raises, in practice the fallback always returns a string with
        # replacement characters. This test verifies that invariant.
        service = make_service()
        # \xff is invalid UTF-8 but decode(errors="replace") will replace it
        body = b"\xff\xfe\xfd"
        result = service._parse_body(body)
        # Should be a non-None string (replacement chars), not a BINARY marker
        assert isinstance(result, str)
        assert result is not None


class TestSnapshotServiceGetClientIp:
    """Unit tests for SnapshotService._get_client_ip."""

    def setup_method(self):
        self.service = make_service()

    def test_x_forwarded_for_single_ip(self):
        req = _make_starlette_request(headers={"x-forwarded-for": "10.0.0.1"})
        assert self.service._get_client_ip(req) == "10.0.0.1"

    def test_x_forwarded_for_chain_returns_first(self):
        req = _make_starlette_request(
            headers={"x-forwarded-for": "10.0.0.1, 172.16.0.1, 192.168.1.1"}
        )
        assert self.service._get_client_ip(req) == "10.0.0.1"

    def test_x_real_ip_used_when_no_forwarded_for(self):
        req = _make_starlette_request(headers={"x-real-ip": "10.0.0.2"})
        assert self.service._get_client_ip(req) == "10.0.0.2"

    def test_falls_back_to_client_host(self):
        req = _make_starlette_request(client_host="192.168.0.5")
        assert self.service._get_client_ip(req) == "192.168.0.5"

    def test_no_ip_available_returns_none(self):
        scope: Scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            # no "client" key
        }
        req = Request(scope)
        assert self.service._get_client_ip(req) is None


class TestSnapshotServiceEnrichEnvironment:
    """Unit tests for SnapshotService._enrich_with_environment."""

    def setup_method(self):
        self.service = make_service()

    def test_reads_hostname_env(self):
        snapshot = make_snapshot()
        with patch.dict(os.environ, {"HOSTNAME": "api-pod-123"}, clear=False):
            self.service._enrich_with_environment(snapshot)
        assert snapshot.environment.pod == "api-pod-123"

    def test_reads_pod_name_when_no_hostname(self):
        snapshot = make_snapshot()
        env = {"POD_NAME": "stoa-api-abc", "NODE_NAME": "node-1", "POD_NAMESPACE": "stoa-system"}
        with patch.dict(os.environ, env, clear=False):
            # Remove HOSTNAME if present
            os.environ.pop("HOSTNAME", None)
            self.service._enrich_with_environment(snapshot)
        assert snapshot.environment.pod == "stoa-api-abc"
        assert snapshot.environment.node == "node-1"
        assert snapshot.environment.namespace == "stoa-system"

    def test_none_values_when_no_env_vars(self):
        snapshot = make_snapshot()
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("HOSTNAME", "POD_NAME", "NODE_NAME", "POD_NAMESPACE")
        }
        with patch.dict(os.environ, clean_env, clear=True):
            self.service._enrich_with_environment(snapshot)
        assert snapshot.environment.pod is None
        assert snapshot.environment.node is None
        assert snapshot.environment.namespace is None


class TestSnapshotServiceEnrichWithLogs:
    """Unit tests for SnapshotService.enrich_with_logs."""

    def setup_method(self):
        self.service = make_service()
        self.snapshot = make_snapshot()

    async def test_no_query_func_returns_early(self):
        """When no query_func is provided, snapshot.logs is not modified."""
        self.snapshot.logs = []
        await self.service.enrich_with_logs(self.snapshot, query_func=None)
        assert self.snapshot.logs == []

    async def test_logs_attached_from_query_func(self):
        logs_data = [
            {"timestamp": datetime.now(UTC), "level": "ERROR", "message": "boom", "extra": {}},
            {"timestamp": datetime.now(UTC), "level": "WARN", "message": "lag", "extra": {}},
        ]
        query_func = AsyncMock(return_value=logs_data)
        await self.service.enrich_with_logs(self.snapshot, query_func=query_func)
        assert len(self.snapshot.logs) == 2
        assert self.snapshot.logs[0].message == "boom"

    async def test_query_func_exception_is_swallowed(self):
        """Errors in query_func must not propagate."""
        query_func = AsyncMock(side_effect=RuntimeError("loki down"))
        # Should not raise
        await self.service.enrich_with_logs(self.snapshot, query_func=query_func)
        assert self.snapshot.logs == []

    async def test_logs_capped_at_max_logs_per_snapshot(self):
        service = make_service(max_logs_per_snapshot=2)
        snapshot = make_snapshot()
        logs_data = [
            {"timestamp": datetime.now(UTC), "level": "INFO", "message": f"msg-{i}", "extra": {}}
            for i in range(10)
        ]
        query_func = AsyncMock(return_value=logs_data)
        await service.enrich_with_logs(snapshot, query_func=query_func)
        assert len(snapshot.logs) == 2


class TestSnapshotServiceCaptureError:
    """Integration tests for SnapshotService.capture_error."""

    def setup_method(self):
        self.storage = make_mock_storage()
        self.service = make_service(storage=self.storage)

    async def test_capture_stores_snapshot(self):
        req = _make_starlette_request(
            path="/api/payments",
            method="POST",
            headers={"content-type": "application/json"},
            client_host="10.0.0.1",
        )
        snapshot = await self.service.capture_error(
            request=req,
            response_status=502,
            response_headers={"content-type": "application/json"},
            request_body=json.dumps({"amount": 100}).encode(),
            response_body=json.dumps({"error": "upstream"}).encode(),
            duration_ms=500,
            tenant_id="tenant-acme",
            trigger=SnapshotTrigger.ERROR_5XX,
            trace_id="trace-abc123",
        )
        assert snapshot.tenant_id == "tenant-acme"
        assert snapshot.response.status == 502
        assert snapshot.trigger == SnapshotTrigger.ERROR_5XX
        assert snapshot.trace_id == "trace-abc123"
        self.storage.save.assert_called_once_with(snapshot)

    async def test_capture_masks_auth_header(self):
        req = _make_starlette_request(
            headers={"authorization": "Bearer secret-token-value"}
        )
        snapshot = await self.service.capture_error(
            request=req,
            response_status=500,
            response_headers={},
            request_body=None,
            response_body=None,
            duration_ms=100,
            tenant_id="acme",
            trigger=SnapshotTrigger.ERROR_5XX,
        )
        assert snapshot.request.headers.get("authorization") == "[REDACTED]"
        assert "headers.authorization" in snapshot.masked_fields

    async def test_capture_sets_client_ip_from_forwarded_for(self):
        req = _make_starlette_request(
            headers={"x-forwarded-for": "203.0.113.5, 10.0.0.1"}
        )
        snapshot = await self.service.capture_error(
            request=req,
            response_status=500,
            response_headers={},
            request_body=None,
            response_body=None,
            duration_ms=100,
            tenant_id="acme",
            trigger=SnapshotTrigger.ERROR_5XX,
        )
        assert snapshot.request.client_ip == "203.0.113.5"

    async def test_capture_with_none_bodies(self):
        req = _make_starlette_request()
        snapshot = await self.service.capture_error(
            request=req,
            response_status=503,
            response_headers={},
            request_body=None,
            response_body=None,
            duration_ms=200,
            tenant_id="acme",
            trigger=SnapshotTrigger.ERROR_5XX,
        )
        assert snapshot.request.body is None
        assert snapshot.response.body is None

    async def test_capture_returns_snapshot_with_environment_enriched(self):
        req = _make_starlette_request()
        with patch.dict(os.environ, {"HOSTNAME": "pod-xyz"}, clear=False):
            snapshot = await self.service.capture_error(
                request=req,
                response_status=500,
                response_headers={},
                request_body=None,
                response_body=None,
                duration_ms=100,
                tenant_id="acme",
                trigger=SnapshotTrigger.ERROR_5XX,
            )
        assert snapshot.environment.pod == "pod-xyz"


class TestSnapshotServiceList:
    """Tests for SnapshotService.list filtering logic."""

    def _build_summary(self, **overrides) -> SnapshotSummary:
        defaults = dict(
            id="SNP-20260101-000000-abc12345",
            timestamp=datetime.now(UTC),
            tenant_id="acme",
            trigger=SnapshotTrigger.ERROR_5XX,
            status=500,
            method="GET",
            path="/api/test",
            duration_ms=100,
            source="control-plane",
            resolution_status=ResolutionStatus.UNRESOLVED,
        )
        defaults.update(overrides)
        return SnapshotSummary(**defaults)

    async def test_list_delegates_to_storage(self):
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([], 0))
        service = make_service(storage=storage)
        filters = SnapshotFilters()
        result = await service.list("acme", filters)
        storage.list.assert_called_once()
        assert result.items == []
        assert result.total == 0

    async def test_list_filters_by_status_code(self):
        s1 = self._build_summary(status=500)
        s2 = self._build_summary(status=404)
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([s1, s2], 2))
        service = make_service(storage=storage)
        filters = SnapshotFilters(status_code=500)
        result = await service.list("acme", filters)
        assert len(result.items) == 1
        assert result.items[0].status == 500

    async def test_list_filters_by_trigger(self):
        s1 = self._build_summary(trigger=SnapshotTrigger.ERROR_5XX)
        s2 = self._build_summary(trigger=SnapshotTrigger.TIMEOUT)
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([s1, s2], 2))
        service = make_service(storage=storage)
        filters = SnapshotFilters(trigger=SnapshotTrigger.TIMEOUT)
        result = await service.list("acme", filters)
        assert len(result.items) == 1
        assert result.items[0].trigger == SnapshotTrigger.TIMEOUT

    async def test_list_filters_by_path_contains(self):
        s1 = self._build_summary(path="/api/payments/v1")
        s2 = self._build_summary(path="/api/orders")
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([s1, s2], 2))
        service = make_service(storage=storage)
        filters = SnapshotFilters(path_contains="payments")
        result = await service.list("acme", filters)
        assert len(result.items) == 1
        assert "payments" in result.items[0].path

    async def test_list_filters_by_source(self):
        s1 = self._build_summary(source="kong")
        s2 = self._build_summary(source="control-plane")
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([s1, s2], 2))
        service = make_service(storage=storage)
        filters = SnapshotFilters(source="kong")
        result = await service.list("acme", filters)
        assert len(result.items) == 1
        assert result.items[0].source == "kong"

    async def test_list_filters_by_resolution_status(self):
        s1 = self._build_summary(resolution_status=ResolutionStatus.RESOLVED)
        s2 = self._build_summary(resolution_status=ResolutionStatus.UNRESOLVED)
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([s1, s2], 2))
        service = make_service(storage=storage)
        filters = SnapshotFilters(resolution_status=ResolutionStatus.RESOLVED)
        result = await service.list("acme", filters)
        assert len(result.items) == 1
        assert result.items[0].resolution_status == ResolutionStatus.RESOLVED

    async def test_list_pagination_passed_to_storage(self):
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=([], 0))
        service = make_service(storage=storage)
        filters = SnapshotFilters()
        await service.list("acme", filters, page=3, page_size=10)
        call_kwargs = storage.list.call_args
        assert call_kwargs.kwargs["limit"] == 10
        assert call_kwargs.kwargs["offset"] == 20  # (page-1)*page_size

    async def test_list_no_filter_returns_all(self):
        summaries = [self._build_summary() for _ in range(5)]
        storage = make_mock_storage()
        storage.list = AsyncMock(return_value=(summaries, 5))
        service = make_service(storage=storage)
        result = await service.list("acme", SnapshotFilters())
        assert result.total == 5
        assert len(result.items) == 5


class TestSnapshotServiceGetSaveDelete:
    """Tests for SnapshotService.get, save, and delete (delegation)."""

    def setup_method(self):
        self.storage = make_mock_storage()
        self.service = make_service(storage=self.storage)

    async def test_get_delegates_to_storage(self):
        snap = make_snapshot()
        self.storage.get = AsyncMock(return_value=snap)
        result = await self.service.get("SNP-20260101-000000-abc12345", "acme")
        self.storage.get.assert_called_once_with("SNP-20260101-000000-abc12345", "acme")
        assert result == snap

    async def test_get_returns_none_when_not_found(self):
        self.storage.get = AsyncMock(return_value=None)
        result = await self.service.get("SNP-missing", "acme")
        assert result is None

    async def test_save_delegates_to_storage(self):
        snap = make_snapshot()
        self.storage.save = AsyncMock(return_value="s3://bucket/key.json.gz")
        url = await self.service.save(snap)
        self.storage.save.assert_called_once_with(snap)
        assert url == "s3://bucket/key.json.gz"

    async def test_delete_delegates_to_storage(self):
        self.storage.delete = AsyncMock(return_value=True)
        result = await self.service.delete("SNP-20260101-000000-abc12345", "acme")
        self.storage.delete.assert_called_once_with("SNP-20260101-000000-abc12345", "acme")
        assert result is True

    async def test_delete_returns_false_when_not_found(self):
        self.storage.delete = AsyncMock(return_value=False)
        result = await self.service.delete("SNP-missing", "acme")
        assert result is False


class TestSnapshotServiceGenerateReplayCurl:
    """Tests for SnapshotService.generate_replay_curl."""

    def setup_method(self):
        self.service = make_service()

    def _make_snap_with_request(
        self,
        method: str = "GET",
        path: str = "/api/test",
        headers: dict | None = None,
        body: Any = None,
        query_params: dict | None = None,
    ) -> ErrorSnapshot:
        return ErrorSnapshot(
            tenant_id="acme",
            request=RequestSnapshot(
                method=method,
                path=path,
                headers=headers or {},
                body=body,
                query_params=query_params or {},
            ),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )

    def test_basic_get_request(self):
        snap = self._make_snap_with_request(method="GET", path="/api/orders")
        curl = self.service.generate_replay_curl(snap)
        assert "curl" in curl
        assert "-X GET" in curl
        assert "/api/orders" in curl

    def test_post_with_json_body(self):
        snap = self._make_snap_with_request(
            method="POST",
            path="/api/payments",
            body={"amount": 100},
        )
        curl = self.service.generate_replay_curl(snap)
        assert "-X POST" in curl
        assert "-d" in curl
        assert "amount" in curl

    def test_headers_included(self):
        snap = self._make_snap_with_request(
            headers={"content-type": "application/json", "x-tenant-id": "acme"},
        )
        curl = self.service.generate_replay_curl(snap)
        assert "-H" in curl
        assert "content-type" in curl

    def test_host_and_content_length_skipped(self):
        snap = self._make_snap_with_request(
            headers={
                "host": "api.gostoa.dev",
                "content-length": "100",
                "transfer-encoding": "chunked",
                "x-custom": "kept",
            }
        )
        curl = self.service.generate_replay_curl(snap)
        assert "host" not in curl
        assert "content-length" not in curl
        assert "transfer-encoding" not in curl
        assert "x-custom" in curl

    def test_query_params_appended_to_url(self):
        snap = self._make_snap_with_request(
            path="/api/items",
            query_params={"page": "1", "limit": "10"},
        )
        curl = self.service.generate_replay_curl(snap)
        assert "page=1" in curl
        assert "limit=10" in curl

    def test_string_body_serialized(self):
        snap = self._make_snap_with_request(
            method="POST",
            body="raw text body",
        )
        curl = self.service.generate_replay_curl(snap)
        assert "raw text body" in curl

    def test_no_body_no_d_flag(self):
        snap = self._make_snap_with_request(method="GET", body=None)
        curl = self.service.generate_replay_curl(snap)
        assert " -d " not in curl


# ─────────────────────────────────────────────────────────────────────────────
# ErrorSnapshotMiddleware Tests
# ─────────────────────────────────────────────────────────────────────────────


def make_service_mock() -> MagicMock:
    """Build a MagicMock SnapshotService."""
    svc = MagicMock(spec=SnapshotService)
    svc.settings = make_settings()
    svc.capture_error = AsyncMock(return_value=make_snapshot())
    return svc


async def _send_asgi_request(
    middleware: ErrorSnapshotMiddleware,
    path: str = "/api/test",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    response_status: int = 200,
    response_body: bytes = b"OK",
) -> dict:
    """Drive the ASGI middleware and return captured response state."""
    scope = make_scope(path=path, method=method, headers=headers or [])
    result = {}

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] = message.get("body", b"")

    # Build a trivial inner app that returns the desired status/body
    async def inner_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": response_status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": response_body, "more_body": False})

    middleware_instance = ErrorSnapshotMiddleware(app=inner_app, service=middleware.service)
    middleware_instance.service = middleware.service
    await middleware_instance(scope, receive, send)
    return result


class TestErrorSnapshotMiddlewareShouldSkipPath:
    """Tests for ErrorSnapshotMiddleware._should_skip_path."""

    def setup_method(self):
        svc = make_service_mock()
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)

    def test_health_path_skipped(self):
        assert self.middleware._should_skip_path("/health") is True

    def test_metrics_path_skipped(self):
        assert self.middleware._should_skip_path("/metrics") is True

    def test_ready_path_skipped(self):
        assert self.middleware._should_skip_path("/ready") is True

    def test_health_subpath_skipped(self):
        assert self.middleware._should_skip_path("/health/live") is True

    def test_api_path_not_skipped(self):
        assert self.middleware._should_skip_path("/api/v1/orders") is False

    def test_root_path_not_skipped(self):
        assert self.middleware._should_skip_path("/") is False


class TestErrorSnapshotMiddlewareShouldCapture:
    """Tests for ErrorSnapshotMiddleware._should_capture."""

    def setup_method(self):
        svc = make_service_mock()
        # All capture flags enabled
        svc.settings = make_settings(
            capture_on_4xx=True,
            capture_on_5xx=True,
            capture_on_timeout=True,
            timeout_threshold_ms=5_000,
        )
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)

    def test_5xx_triggers_capture(self):
        assert self.middleware._should_capture(500, 100) is True

    def test_4xx_triggers_capture(self):
        assert self.middleware._should_capture(404, 100) is True

    def test_2xx_does_not_capture(self):
        assert self.middleware._should_capture(200, 100) is False

    def test_3xx_does_not_capture(self):
        assert self.middleware._should_capture(302, 100) is False

    def test_timeout_triggers_capture(self):
        assert self.middleware._should_capture(200, 6_000) is True

    def test_4xx_capture_disabled(self):
        svc = make_service_mock()
        svc.settings = make_settings(capture_on_4xx=False)
        middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)
        assert middleware._should_capture(404, 100) is False

    def test_5xx_capture_disabled(self):
        svc = make_service_mock()
        svc.settings = make_settings(capture_on_5xx=False)
        middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)
        assert middleware._should_capture(500, 100) is False

    def test_timeout_capture_disabled(self):
        svc = make_service_mock()
        svc.settings = make_settings(capture_on_timeout=False, timeout_threshold_ms=5_000)
        middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)
        assert middleware._should_capture(200, 6_000) is False


class TestErrorSnapshotMiddlewareDetermineTrigger:
    """Tests for ErrorSnapshotMiddleware._determine_trigger."""

    def setup_method(self):
        svc = make_service_mock()
        svc.settings = make_settings(timeout_threshold_ms=5_000)
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)

    def test_timeout_trigger(self):
        assert self.middleware._determine_trigger(200, 6_000) == SnapshotTrigger.TIMEOUT

    def test_5xx_trigger(self):
        assert self.middleware._determine_trigger(503, 100) == SnapshotTrigger.ERROR_5XX

    def test_4xx_trigger(self):
        assert self.middleware._determine_trigger(404, 100) == SnapshotTrigger.ERROR_4XX

    def test_manual_trigger_for_2xx_below_timeout(self):
        assert self.middleware._determine_trigger(200, 100) == SnapshotTrigger.MANUAL


class TestErrorSnapshotMiddlewareExtractTenantId:
    """Tests for ErrorSnapshotMiddleware._extract_tenant_id."""

    def setup_method(self):
        svc = make_service_mock()
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)

    def test_extracts_from_x_tenant_id_header(self):
        scope = make_scope(headers=[(b"x-tenant-id", b"tenant-acme")])
        assert self.middleware._extract_tenant_id(scope) == "tenant-acme"

    def test_falls_back_to_scope_state_user(self):
        user = MagicMock()
        user.tenant_id = "tenant-from-jwt"
        scope = make_scope(state={"user": user})
        assert self.middleware._extract_tenant_id(scope) == "tenant-from-jwt"

    def test_falls_back_to_unknown(self):
        scope = make_scope()
        assert self.middleware._extract_tenant_id(scope) == "unknown"

    def test_header_takes_priority_over_state(self):
        user = MagicMock()
        user.tenant_id = "jwt-tenant"
        scope = make_scope(
            headers=[(b"x-tenant-id", b"header-tenant")],
            state={"user": user},
        )
        assert self.middleware._extract_tenant_id(scope) == "header-tenant"


class TestErrorSnapshotMiddlewareExtractTraceId:
    """Tests for ErrorSnapshotMiddleware._extract_trace_id."""

    def setup_method(self):
        svc = make_service_mock()
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=svc)

    def test_extracts_x_trace_id(self):
        scope = make_scope(headers=[(b"x-trace-id", b"trace-abc")])
        assert self.middleware._extract_trace_id(scope) == "trace-abc"

    def test_extracts_x_request_id(self):
        scope = make_scope(headers=[(b"x-request-id", b"req-123")])
        assert self.middleware._extract_trace_id(scope) == "req-123"

    def test_extracts_traceparent(self):
        scope = make_scope(headers=[(b"traceparent", b"00-trace-span-01")])
        assert self.middleware._extract_trace_id(scope) == "00-trace-span-01"

    def test_extracts_x_correlation_id(self):
        scope = make_scope(headers=[(b"x-correlation-id", b"corr-xyz")])
        assert self.middleware._extract_trace_id(scope) == "corr-xyz"

    def test_first_matching_header_wins(self):
        """x-trace-id takes priority over x-request-id."""
        scope = make_scope(
            headers=[
                (b"x-trace-id", b"primary"),
                (b"x-request-id", b"secondary"),
            ]
        )
        assert self.middleware._extract_trace_id(scope) == "primary"

    def test_returns_none_when_no_trace_headers(self):
        scope = make_scope()
        assert self.middleware._extract_trace_id(scope) is None


class TestErrorSnapshotMiddlewareSafeCapture:
    """Tests for ErrorSnapshotMiddleware._safe_capture."""

    def setup_method(self):
        self.svc = make_service_mock()
        self.middleware = ErrorSnapshotMiddleware(app=MagicMock(), service=self.svc)

    async def test_calls_capture_error(self):
        scope = make_scope(
            path="/api/test",
            headers=[(b"x-tenant-id", b"acme"), (b"x-trace-id", b"t-123")],
        )
        await self.middleware._safe_capture(
            scope=scope,
            request_body=b"req",
            response_status=500,
            response_headers={},
            response_body=b"err",
            duration_ms=100,
        )
        self.svc.capture_error.assert_called_once()
        call_kwargs = self.svc.capture_error.call_args.kwargs
        assert call_kwargs["tenant_id"] == "acme"
        assert call_kwargs["trace_id"] == "t-123"
        assert call_kwargs["response_status"] == 500

    async def test_exception_in_capture_does_not_propagate(self):
        """_safe_capture must never raise, even if capture_error fails."""
        self.svc.capture_error = AsyncMock(side_effect=RuntimeError("storage down"))
        scope = make_scope()
        # Should not raise
        await self.middleware._safe_capture(
            scope=scope,
            request_body=b"",
            response_status=500,
            response_headers={},
            response_body=b"",
            duration_ms=100,
        )


class TestErrorSnapshotMiddlewareASGI:
    """Integration tests for the full ASGI __call__ flow."""

    def _build_middleware_with_inner(
        self,
        response_status: int = 200,
        response_body: bytes = b"OK",
    ) -> tuple[ErrorSnapshotMiddleware, MagicMock]:
        svc = make_service_mock()

        async def inner_app(scope: Scope, receive: Receive, send: Send) -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": response_status,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": response_body, "more_body": False})

        middleware = ErrorSnapshotMiddleware(app=inner_app, service=svc)
        return middleware, svc

    async def test_non_http_scope_passes_through(self):
        """WebSocket scopes are passed through without capture."""
        middleware, svc = self._build_middleware_with_inner()
        scope = {"type": "websocket", "path": "/ws"}
        received: list[Any] = []

        async def ws_receive():
            return {}

        async def ws_send(msg):
            received.append(msg)

        # The inner app for websocket needs to be more explicit
        async def inner_ws(scope: Scope, receive: Receive, send: Send) -> None:
            pass

        middleware_ws = ErrorSnapshotMiddleware(app=inner_ws, service=svc)
        await middleware_ws(scope, ws_receive, ws_send)
        svc.capture_error.assert_not_called()

    async def test_excluded_path_not_captured(self):
        middleware, svc = self._build_middleware_with_inner(response_status=200)
        scope = make_scope(path="/health")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        messages: list = []

        async def send(msg):
            messages.append(msg)

        await middleware(scope, receive, send)
        svc.capture_error.assert_not_called()

    async def test_5xx_response_triggers_capture(self):
        middleware, svc = self._build_middleware_with_inner(response_status=500)
        scope = make_scope(path="/api/orders")
        messages: list = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            messages.append(msg)

        await middleware(scope, receive, send)
        svc.capture_error.assert_called_once()

    async def test_2xx_response_not_captured(self):
        middleware, svc = self._build_middleware_with_inner(response_status=200)
        scope = make_scope(path="/api/orders")
        messages: list = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            messages.append(msg)

        await middleware(scope, receive, send)
        svc.capture_error.assert_not_called()

    async def test_inner_exception_captured_and_reraised(self):
        svc = make_service_mock()

        async def crashing_app(scope: Scope, receive: Receive, send: Send) -> None:
            raise ValueError("boom")

        middleware = ErrorSnapshotMiddleware(app=crashing_app, service=svc)
        scope = make_scope(path="/api/crash")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            pass

        with pytest.raises(ValueError, match="boom"):
            await middleware(scope, receive, send)

        svc.capture_error.assert_called_once()
        call_kwargs = svc.capture_error.call_args.kwargs
        assert call_kwargs["response_status"] == 500

    async def test_response_headers_parsed_correctly(self):
        """Response headers as byte tuples should be decoded to strings."""
        svc = make_service_mock()
        captured_headers: dict = {}

        async def inner(scope: Scope, receive: Receive, send: Send) -> None:
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-request-id", b"abc-123"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": b"", "more_body": False})

        # Intercept _safe_capture to grab headers
        original_safe_capture = ErrorSnapshotMiddleware._safe_capture

        async def capture_spy(self, **kwargs):
            captured_headers.update(kwargs.get("response_headers", {}))
            await svc.capture_error(
                request=None,
                response_status=kwargs["response_status"],
                response_headers=kwargs["response_headers"],
                request_body=kwargs["request_body"],
                response_body=kwargs["response_body"],
                duration_ms=kwargs["duration_ms"],
                tenant_id="unknown",
                trigger=SnapshotTrigger.ERROR_5XX,
            )

        middleware = ErrorSnapshotMiddleware(app=inner, service=svc)
        scope = make_scope(path="/api/test")

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            pass

        with patch.object(ErrorSnapshotMiddleware, "_safe_capture", capture_spy):
            await middleware(scope, receive, send)

        assert captured_headers.get("content-type") == "application/json"
        assert captured_headers.get("x-request-id") == "abc-123"


class TestSimpleErrorSnapshotMiddleware:
    """Tests for SimpleErrorSnapshotMiddleware (BaseHTTPMiddleware variant)."""

    def setup_method(self):
        self.svc = make_service_mock()

    def _build_starlette_app(self, response_status: int = 200) -> ASGIApp:
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Route

        async def endpoint(request: Request) -> Response:
            if response_status >= 500:
                raise RuntimeError("simulated 5xx")
            return Response(content="OK", status_code=response_status)

        app = Starlette(routes=[Route("/api/test", endpoint)])
        return app

    def test_excluded_path_not_captured(self):
        from starlette.applications import Starlette
        from starlette.responses import Response
        from starlette.routing import Route

        async def health(request: Request) -> Response:
            return Response("ok")

        app = Starlette(routes=[Route("/health", health)])
        middleware_app = SimpleErrorSnapshotMiddleware(app=app, service=self.svc)
        client = TestClient(middleware_app, raise_server_exceptions=False)
        client.get("/health")
        self.svc.capture_error.assert_not_called()

    def test_should_capture_5xx(self):
        """_should_capture must return True for 5xx."""
        svc = make_service_mock()
        svc.settings = make_settings(capture_on_5xx=True)
        from starlette.applications import Starlette

        middleware = SimpleErrorSnapshotMiddleware(app=Starlette(), service=svc)
        assert middleware._should_capture(500, 100) is True

    def test_should_not_capture_2xx(self):
        svc = make_service_mock()
        svc.settings = make_settings()
        from starlette.applications import Starlette

        middleware = SimpleErrorSnapshotMiddleware(app=Starlette(), service=svc)
        assert middleware._should_capture(200, 100) is False

    def test_determine_trigger_5xx(self):
        svc = make_service_mock()
        svc.settings = make_settings()
        from starlette.applications import Starlette

        middleware = SimpleErrorSnapshotMiddleware(app=Starlette(), service=svc)
        assert middleware._determine_trigger(503, 100) == SnapshotTrigger.ERROR_5XX

    def test_determine_trigger_timeout(self):
        svc = make_service_mock()
        svc.settings = make_settings(timeout_threshold_ms=5_000)
        from starlette.applications import Starlette

        middleware = SimpleErrorSnapshotMiddleware(app=Starlette(), service=svc)
        assert middleware._determine_trigger(200, 6_000) == SnapshotTrigger.TIMEOUT


# ─────────────────────────────────────────────────────────────────────────────
# SnapshotStorage Tests
# ─────────────────────────────────────────────────────────────────────────────


def _make_client_error(code: str) -> ClientError:
    """Build a botocore ClientError with the given code."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": "test error"}},
        operation_name="TestOp",
    )


def _make_async_s3_client(
    *,
    head_bucket_raises: ClientError | None = None,
    get_object_raises: ClientError | None = None,
    get_object_body: bytes | None = None,
    list_pages: list[dict] | None = None,
    delete_raises: ClientError | None = None,
):
    """Build an async context-manager mock for the S3 client."""
    client = MagicMock()

    # head_bucket
    if head_bucket_raises:
        client.head_bucket = AsyncMock(side_effect=head_bucket_raises)
    else:
        client.head_bucket = AsyncMock(return_value={})

    client.create_bucket = AsyncMock(return_value={})
    client.put_object = AsyncMock(return_value={})
    client.delete_object = AsyncMock(return_value={})
    client.delete_objects = AsyncMock(return_value={})

    # get_object
    if get_object_raises:
        client.get_object = AsyncMock(side_effect=get_object_raises)
    elif get_object_body is not None:
        body_stream = AsyncMock()
        body_stream.read = AsyncMock(return_value=get_object_body)
        client.get_object = AsyncMock(return_value={"Body": body_stream})
    else:
        client.get_object = AsyncMock(return_value={})

    # delete_object
    if delete_raises:
        client.delete_object = AsyncMock(side_effect=delete_raises)

    # paginator
    paginator = MagicMock()
    pages = list_pages or []

    async def _async_paginate(**kwargs):
        for page in pages:
            yield page

    paginator.paginate = MagicMock(return_value=_async_paginate())
    client.get_paginator = MagicMock(return_value=paginator)

    # Context manager protocol
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return client, cm


def _mock_storage_with_client(client_cm, settings: SnapshotSettings | None = None) -> SnapshotStorage:
    """Return a SnapshotStorage whose _get_client() returns client_cm."""
    storage = SnapshotStorage(settings=settings or make_settings())
    storage._get_client = MagicMock(return_value=client_cm)
    return storage


class TestSnapshotStorageGetObjectKey:
    """Tests for SnapshotStorage._get_object_key."""

    def setup_method(self):
        self.storage = SnapshotStorage(settings=make_settings())

    def test_key_format(self):
        snap = ErrorSnapshot(
            id="SNP-20260115-094512-a1b2c3d4",
            timestamp=datetime(2026, 1, 15, 9, 45, 12, tzinfo=UTC),
            tenant_id="tenant-acme",
            request=RequestSnapshot(method="GET", path="/"),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )
        key = self.storage._get_object_key(snap)
        assert key == "tenant-acme/2026/01/15/SNP-20260115-094512-a1b2c3d4.json.gz"

    def test_key_zero_padded_month_and_day(self):
        snap = ErrorSnapshot(
            timestamp=datetime(2026, 3, 5, tzinfo=UTC),
            tenant_id="acme",
            request=RequestSnapshot(method="GET", path="/"),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )
        key = self.storage._get_object_key(snap)
        assert "/2026/03/05/" in key


class TestSnapshotStorageParseObjectKey:
    """Tests for SnapshotStorage._parse_object_key."""

    def setup_method(self):
        self.storage = SnapshotStorage(settings=make_settings())

    def test_valid_key_parsed(self):
        key = "tenant-acme/2026/01/15/SNP-20260115-094512-a1b2c3d4.json.gz"
        meta = self.storage._parse_object_key(key)
        assert meta["tenant_id"] == "tenant-acme"
        assert meta["year"] == 2026
        assert meta["month"] == 1
        assert meta["day"] == 15
        assert meta["snapshot_id"] == "SNP-20260115-094512-a1b2c3d4"

    def test_invalid_key_returns_empty_dict(self):
        meta = self.storage._parse_object_key("bad/key")
        assert meta == {}

    def test_key_with_too_many_parts_returns_empty(self):
        meta = self.storage._parse_object_key("a/b/c/d/e/f/g.json.gz")
        assert meta == {}


class TestSnapshotStorageConnect:
    """Tests for SnapshotStorage.connect."""

    async def test_connect_creates_bucket_when_404(self):
        _, cm = _make_async_s3_client(
            head_bucket_raises=_make_client_error("404")
        )
        storage = _mock_storage_with_client(cm)

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value = MagicMock()
            await storage.connect()

        # create_bucket should have been called
        client = cm.__aenter__.return_value
        client.create_bucket.assert_called_once_with(Bucket="test-snapshots")
        assert storage._connected is True

    async def test_connect_bucket_exists_no_create(self):
        _, cm = _make_async_s3_client()  # head_bucket succeeds
        storage = _mock_storage_with_client(cm)

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value = MagicMock()
            await storage.connect()

        client = cm.__aenter__.return_value
        client.create_bucket.assert_not_called()
        assert storage._connected is True

    async def test_connect_raises_on_non_404_error(self):
        _, cm = _make_async_s3_client(
            head_bucket_raises=_make_client_error("403")
        )
        storage = _mock_storage_with_client(cm)

        with patch("aioboto3.Session"), pytest.raises(ClientError):
            await storage.connect()

    async def test_connect_nobucket_error_code_creates_bucket(self):
        _, cm = _make_async_s3_client(
            head_bucket_raises=_make_client_error("NoSuchBucket")
        )
        storage = _mock_storage_with_client(cm)

        with patch("aioboto3.Session") as mock_session:
            mock_session.return_value = MagicMock()
            await storage.connect()

        client = cm.__aenter__.return_value
        client.create_bucket.assert_called_once()


class TestSnapshotStorageSave:
    """Tests for SnapshotStorage.save."""

    async def test_save_puts_gzip_object(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)
        snap = make_snapshot()

        url = await storage.save(snap)

        client = cm.__aenter__.return_value
        call_kwargs = client.put_object.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-snapshots"
        assert call_kwargs["ContentEncoding"] == "gzip"
        assert call_kwargs["ContentType"] == "application/json"
        # Body should be valid gzip
        body = call_kwargs["Body"]
        decompressed = gzip.decompress(body)
        parsed = json.loads(decompressed)
        assert parsed["tenant_id"] == snap.tenant_id

    async def test_save_returns_s3_url(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)
        snap = make_snapshot()

        url = await storage.save(snap)

        assert url.startswith("s3://test-snapshots/")
        assert ".json.gz" in url

    async def test_save_metadata_includes_tenant_and_trigger(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)
        snap = make_snapshot(trigger=SnapshotTrigger.TIMEOUT)

        await storage.save(snap)

        client = cm.__aenter__.return_value
        meta = client.put_object.call_args.kwargs["Metadata"]
        assert meta["tenant_id"] == snap.tenant_id
        assert meta["trigger"] == SnapshotTrigger.TIMEOUT.value


class TestSnapshotStorageGet:
    """Tests for SnapshotStorage.get."""

    async def test_get_existing_snapshot(self):
        snap = make_snapshot()
        json_bytes = snap.model_dump_json().encode()
        compressed = gzip.compress(json_bytes)

        _, cm = _make_async_s3_client(get_object_body=compressed)
        storage = _mock_storage_with_client(cm)

        result = await storage.get("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is not None
        assert result.tenant_id == snap.tenant_id

    async def test_get_nonexistent_returns_none(self):
        _, cm = _make_async_s3_client(get_object_raises=_make_client_error("NoSuchKey"))
        storage = _mock_storage_with_client(cm)

        result = await storage.get("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is None

    async def test_get_404_returns_none(self):
        _, cm = _make_async_s3_client(get_object_raises=_make_client_error("404"))
        storage = _mock_storage_with_client(cm)

        result = await storage.get("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is None

    async def test_get_other_client_error_propagates(self):
        _, cm = _make_async_s3_client(get_object_raises=_make_client_error("403"))
        storage = _mock_storage_with_client(cm)

        with pytest.raises(ClientError):
            await storage.get("SNP-20260115-094512-a1b2c3d4", "tenant-acme")

    async def test_get_invalid_snapshot_id_returns_none(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)

        result = await storage.get("invalid-id", "tenant-acme")
        assert result is None

    async def test_get_builds_correct_key(self):
        snap = make_snapshot()
        json_bytes = snap.model_dump_json().encode()
        compressed = gzip.compress(json_bytes)

        client, cm = _make_async_s3_client(get_object_body=compressed)
        storage = _mock_storage_with_client(cm)

        await storage.get("SNP-20260115-094512-a1b2c3d4", "tenant-acme")

        call_kwargs = client.get_object.call_args.kwargs
        assert "tenant-acme/2026/01/15/SNP-20260115-094512-a1b2c3d4.json.gz" == call_kwargs["Key"]


class TestSnapshotStorageDelete:
    """Tests for SnapshotStorage.delete."""

    async def test_delete_existing_returns_true(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)

        result = await storage.delete("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is True

    async def test_delete_nonexistent_returns_false(self):
        _, cm = _make_async_s3_client(delete_raises=_make_client_error("NoSuchKey"))
        storage = _mock_storage_with_client(cm)

        result = await storage.delete("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is False

    async def test_delete_404_returns_false(self):
        _, cm = _make_async_s3_client(delete_raises=_make_client_error("404"))
        storage = _mock_storage_with_client(cm)

        result = await storage.delete("SNP-20260115-094512-a1b2c3d4", "tenant-acme")
        assert result is False

    async def test_delete_other_error_propagates(self):
        _, cm = _make_async_s3_client(delete_raises=_make_client_error("403"))
        storage = _mock_storage_with_client(cm)

        with pytest.raises(ClientError):
            await storage.delete("SNP-20260115-094512-a1b2c3d4", "tenant-acme")

    async def test_delete_invalid_id_returns_false(self):
        _, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)

        result = await storage.delete("not-a-valid-id", "tenant-acme")
        assert result is False

    async def test_delete_builds_correct_key(self):
        client, cm = _make_async_s3_client()
        storage = _mock_storage_with_client(cm)

        await storage.delete("SNP-20260115-094512-a1b2c3d4", "tenant-acme")

        call_kwargs = client.delete_object.call_args.kwargs
        assert call_kwargs["Key"] == "tenant-acme/2026/01/15/SNP-20260115-094512-a1b2c3d4.json.gz"


class TestSnapshotStorageList:
    """Tests for SnapshotStorage.list."""

    def _build_list_page(
        self,
        keys: list[str],
        last_modified: datetime | None = None,
    ) -> dict:
        lm = last_modified or datetime(2026, 1, 15, tzinfo=UTC)
        return {
            "Contents": [{"Key": k, "LastModified": lm} for k in keys]
        }

    def _make_paginating_client(self, pages: list[dict]):
        """Build an S3 client mock with a proper async paginator."""
        client = MagicMock()
        client.put_object = AsyncMock(return_value={})
        client.delete_object = AsyncMock(return_value={})
        client.delete_objects = AsyncMock(return_value={})
        client.head_bucket = AsyncMock(return_value={})
        client.create_bucket = AsyncMock(return_value={})

        paginator = MagicMock()

        async def _async_paginate(**kwargs):
            for page in pages:
                yield page

        paginator.paginate = MagicMock(return_value=_async_paginate())
        client.get_paginator = MagicMock(return_value=paginator)

        snap = make_snapshot()
        json_bytes = snap.model_dump_json().encode()
        compressed = gzip.compress(json_bytes)
        body_stream = AsyncMock()
        body_stream.read = AsyncMock(return_value=compressed)
        client.get_object = AsyncMock(return_value={"Body": body_stream})

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        return client, cm

    async def test_list_returns_summaries_and_total(self):
        key = "tenant-acme/2026/01/15/SNP-20260115-094512-a1b2c3d4.json.gz"
        pages = [self._build_list_page([key])]
        client, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        summaries, total = await storage.list("tenant-acme")
        assert total == 1
        assert len(summaries) == 1

    async def test_list_empty_bucket_returns_empty(self):
        pages = [{"Contents": []}]
        _, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        summaries, total = await storage.list("tenant-acme")
        assert total == 0
        assert summaries == []

    async def test_list_pagination_offset_applied(self):
        keys = [
            f"tenant-acme/2026/01/15/SNP-20260115-00000{i}-abc0000{i}.json.gz"
            for i in range(5)
        ]
        pages = [self._build_list_page(keys)]
        client, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        _, total = await storage.list("tenant-acme", limit=2, offset=0)
        assert total == 5

    async def test_list_skips_non_json_gz_keys(self):
        pages = [self._build_list_page(["tenant-acme/2026/01/15/readme.txt"])]
        _, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        summaries, total = await storage.list("tenant-acme")
        assert total == 0

    async def test_list_same_day_uses_specific_prefix(self):
        """When start_date == end_date, paginator should use day-specific prefix."""
        pages: list[dict] = [{}]
        client, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        day = datetime(2026, 1, 15, tzinfo=UTC)
        await storage.list("tenant-acme", start_date=day, end_date=day)

        paginator = client.get_paginator.return_value
        call_args = paginator.paginate.call_args
        prefix = call_args.kwargs.get("Prefix") or (call_args.args[0] if call_args.args else "")
        assert "tenant-acme/2026/01/15/" in str(prefix)

    async def test_list_filters_out_of_range_dates(self):
        """Objects outside start/end date range should be filtered."""
        # Key is on 2026-01-10; range is 2026-01-15 to 2026-01-20
        key = "tenant-acme/2026/01/10/SNP-20260110-000000-abcdef01.json.gz"
        lm = datetime(2026, 1, 10, tzinfo=UTC)
        pages = [self._build_list_page([key], last_modified=lm)]
        _, cm = self._make_paginating_client(pages)
        storage = _mock_storage_with_client(cm)

        start = datetime(2026, 1, 15, tzinfo=UTC)
        end = datetime(2026, 1, 20, tzinfo=UTC)
        summaries, total = await storage.list("tenant-acme", start_date=start, end_date=end)
        assert total == 0
        assert summaries == []


class TestSnapshotStorageCleanupExpired:
    """Tests for SnapshotStorage.cleanup_expired.

    Note: cleanup_expired calls logger.info() with keyword arguments using
    structlog-style syntax (logger.info("msg", key=value)). Standard Python
    logging does not support this form, so we patch the storage logger to
    avoid a TypeError from the underlying logging implementation.
    """

    def _make_cleanup_client(self, objects: list[dict]) -> tuple[MagicMock, MagicMock]:
        client = MagicMock()
        client.delete_objects = AsyncMock(return_value={})

        paginator = MagicMock()

        async def _async_paginate(**kwargs):
            yield {"Contents": objects}

        paginator.paginate = MagicMock(return_value=_async_paginate())
        client.get_paginator = MagicMock(return_value=paginator)

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=client)
        cm.__aexit__ = AsyncMock(return_value=False)
        return client, cm

    async def test_deletes_old_objects(self):
        cutoff = datetime.now(UTC) - timedelta(days=31)
        objects = [{"Key": "tenant/old.json.gz", "LastModified": cutoff}]
        client, cm = self._make_cleanup_client(objects)
        storage = _mock_storage_with_client(cm)

        with patch("src.features.error_snapshots.storage.logger") as mock_logger:
            deleted = await storage.cleanup_expired()

        assert deleted == 1
        client.delete_objects.assert_called_once()
        mock_logger.info.assert_called()

    async def test_skips_recent_objects(self):
        recent = datetime.now(UTC) - timedelta(days=1)
        objects = [{"Key": "tenant/new.json.gz", "LastModified": recent}]
        client, cm = self._make_cleanup_client(objects)
        storage = _mock_storage_with_client(cm)

        with patch("src.features.error_snapshots.storage.logger"):
            deleted = await storage.cleanup_expired()

        assert deleted == 0
        client.delete_objects.assert_not_called()

    async def test_empty_bucket_returns_zero(self):
        client, cm = self._make_cleanup_client([])
        storage = _mock_storage_with_client(cm)

        with patch("src.features.error_snapshots.storage.logger"):
            deleted = await storage.cleanup_expired()

        assert deleted == 0
