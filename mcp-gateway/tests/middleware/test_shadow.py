# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Shadow Traffic Middleware."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from src.middleware.shadow import ShadowMiddleware


@pytest.fixture
def app_with_shadow():
    """Create test app with shadow middleware."""
    app = FastAPI()

    app.add_middleware(
        ShadowMiddleware,
        rust_gateway_url="http://rust-gateway:8080",
        enabled=True,
        timeout=5.0,
    )

    @app.post("/mcp/v1/tools")
    async def mcp_tools():
        return {"tools": [{"name": "test_tool"}]}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.fixture
def client(app_with_shadow):
    """Create test client."""
    return TestClient(app_with_shadow)


class TestShadowMiddleware:
    """Tests for ShadowMiddleware class."""

    def test_non_mcp_requests_not_shadowed(self, client):
        """Non-MCP requests should pass through without shadowing."""
        with patch("src.middleware.shadow.httpx.AsyncClient") as mock_client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}
            # Shadow client should not be called for non-MCP paths
            mock_client.return_value.request.assert_not_called()

    def test_mcp_request_returns_python_response(self, client):
        """MCP requests should return Python gateway response."""
        with patch.object(
            ShadowMiddleware, "_shadow_request", new_callable=AsyncMock
        ) as mock_shadow:
            response = client.post("/mcp/v1/tools")
            assert response.status_code == 200
            assert "tools" in response.json()

    def test_shadow_middleware_disabled(self):
        """Middleware should pass through when disabled."""
        app = FastAPI()
        app.add_middleware(
            ShadowMiddleware,
            rust_gateway_url="http://rust-gateway:8080",
            enabled=False,
        )

        @app.post("/mcp/v1/tools")
        async def mcp_tools():
            return {"tools": []}

        client = TestClient(app)
        response = client.post("/mcp/v1/tools")
        assert response.status_code == 200


class TestResponseComparison:
    """Tests for response comparison logic."""

    def test_compare_bodies_matching_json(self):
        """Matching JSON bodies should return True."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"name": "test", "value": 42}'
        rust_body = b'{"name": "test", "value": 42}'

        assert middleware._compare_bodies(python_body, rust_body) is True

    def test_compare_bodies_matching_json_different_order(self):
        """JSON with different key order should still match."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"name": "test", "value": 42}'
        rust_body = b'{"value": 42, "name": "test"}'

        assert middleware._compare_bodies(python_body, rust_body) is True

    def test_compare_bodies_mismatching_json(self):
        """Mismatching JSON bodies should return False."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"name": "test", "value": 42}'
        rust_body = b'{"name": "test", "value": 99}'

        assert middleware._compare_bodies(python_body, rust_body) is False

    def test_compare_bodies_with_dynamic_fields_stripped(self):
        """Dynamic fields (timestamp, request_id) should be ignored."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"name": "test", "timestamp": "2024-01-01", "request_id": "abc"}'
        rust_body = b'{"name": "test", "timestamp": "2024-01-02", "request_id": "xyz"}'

        assert middleware._compare_bodies(python_body, rust_body) is True

    def test_compare_bodies_nested_dynamic_fields(self):
        """Nested dynamic fields should also be stripped."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"data": {"name": "test", "trace_id": "abc", "duration_ms": 100}}'
        rust_body = b'{"data": {"name": "test", "trace_id": "xyz", "duration_ms": 200}}'

        assert middleware._compare_bodies(python_body, rust_body) is True

    def test_compare_bodies_null_rust_response(self):
        """Null Rust response should return False."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b'{"name": "test"}'
        rust_body = None

        assert middleware._compare_bodies(python_body, rust_body) is False

    def test_compare_bodies_non_json_matching(self):
        """Non-JSON matching bodies should return True."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b"plain text response"
        rust_body = b"plain text response"

        assert middleware._compare_bodies(python_body, rust_body) is True

    def test_compare_bodies_non_json_mismatching(self):
        """Non-JSON mismatching bodies should return False."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        python_body = b"plain text response"
        rust_body = b"different text response"

        assert middleware._compare_bodies(python_body, rust_body) is False


class TestJsonNormalization:
    """Tests for JSON normalization logic."""

    def test_normalize_json_removes_timestamp(self):
        """Should remove timestamp field."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {"name": "test", "timestamp": "2024-01-01T00:00:00Z"}
        middleware._normalize_json(obj)

        assert "timestamp" not in obj
        assert obj["name"] == "test"

    def test_normalize_json_removes_request_id(self):
        """Should remove request_id field."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {"name": "test", "request_id": "abc-123"}
        middleware._normalize_json(obj)

        assert "request_id" not in obj

    def test_normalize_json_removes_trace_id(self):
        """Should remove trace_id field."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {"name": "test", "trace_id": "trace-abc"}
        middleware._normalize_json(obj)

        assert "trace_id" not in obj

    def test_normalize_json_removes_duration_ms(self):
        """Should remove duration_ms field."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {"name": "test", "duration_ms": 150}
        middleware._normalize_json(obj)

        assert "duration_ms" not in obj

    def test_normalize_json_handles_nested_objects(self):
        """Should handle nested objects."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {
            "data": {
                "name": "test",
                "timestamp": "2024-01-01",
                "nested": {"trace_id": "abc"},
            }
        }
        middleware._normalize_json(obj)

        assert "timestamp" not in obj["data"]
        assert "trace_id" not in obj["data"]["nested"]
        assert obj["data"]["name"] == "test"

    def test_normalize_json_handles_arrays(self):
        """Should handle arrays."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://test",
        )

        obj = {
            "items": [
                {"name": "item1", "timestamp": "t1"},
                {"name": "item2", "timestamp": "t2"},
            ]
        }
        middleware._normalize_json(obj)

        assert "timestamp" not in obj["items"][0]
        assert "timestamp" not in obj["items"][1]
        assert obj["items"][0]["name"] == "item1"


class TestShadowRequest:
    """Tests for shadow request logic."""

    @pytest.mark.asyncio
    async def test_shadow_request_success(self):
        """Should send shadow request and compare responses."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://rust-gateway:8080",
        )

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/mcp/v1/tools"
        mock_request.url.query = ""
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "application/json"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"tools": []}'

        with patch.object(
            middleware, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch.object(
                middleware, "_compare_responses", new_callable=AsyncMock
            ) as mock_compare:
                await middleware._shadow_request(
                    request=mock_request,
                    body=b'{"name": "test"}',
                    python_response_status=200,
                    python_response_body=b'{"tools": []}',
                    python_latency=0.1,
                )

                mock_client.request.assert_called_once()
                mock_compare.assert_called_once()

    @pytest.mark.asyncio
    async def test_shadow_request_timeout_handling(self):
        """Should handle timeout gracefully."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://rust-gateway:8080",
        )

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/mcp/v1/tools"
        mock_request.url.query = ""
        mock_request.method = "POST"
        mock_request.headers = {}

        with patch.object(
            middleware, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("timeout")
            mock_get_client.return_value = mock_client

            with patch.object(
                middleware, "_compare_responses", new_callable=AsyncMock
            ) as mock_compare:
                await middleware._shadow_request(
                    request=mock_request,
                    body=b"{}",
                    python_response_status=200,
                    python_response_body=b"{}",
                    python_latency=0.1,
                )

                # Should still call compare with error
                mock_compare.assert_called_once()
                call_kwargs = mock_compare.call_args[1]
                assert call_kwargs["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_shadow_request_adds_headers(self):
        """Should add X-Shadow-Mode and X-Shadow-Request-Id headers."""
        middleware = ShadowMiddleware(
            app=MagicMock(),
            rust_gateway_url="http://rust-gateway:8080",
        )

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/mcp/v1/tools"
        mock_request.url.query = "foo=bar"
        mock_request.method = "POST"

        # Use MagicMock for headers to allow method assignment
        mock_headers = MagicMock()
        mock_headers.get = lambda k, d=None: (
            "original-req-id" if k == "x-request-id" else d
        )
        mock_headers.items = lambda: [("x-request-id", "original-req-id")]
        mock_request.headers = mock_headers

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"{}"

        with patch.object(
            middleware, "_get_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch.object(middleware, "_compare_responses", new_callable=AsyncMock):
                await middleware._shadow_request(
                    request=mock_request,
                    body=b"{}",
                    python_response_status=200,
                    python_response_body=b"{}",
                    python_latency=0.1,
                )

                call_kwargs = mock_client.request.call_args[1]
                assert call_kwargs["headers"]["X-Shadow-Mode"] == "true"
                assert call_kwargs["headers"]["X-Shadow-Request-Id"] == "original-req-id"
                assert "?foo=bar" in call_kwargs["url"]
