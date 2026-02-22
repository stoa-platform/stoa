"""Tests for events router (CAB-1388)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse

from src.routers.events import (
    DeploymentResult,
    event_generator,
    receive_deployment_result,
    stream_global_events,
    stream_events,
)


# ── event_generator ──


class TestEventGenerator:
    async def test_disconnects_immediately_yields_nothing(self):
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)
        user = MagicMock()

        events = []
        async for event in event_generator(mock_request, "acme", user):
            events.append(event)

        assert events == []

    async def test_yields_heartbeat_before_disconnect(self):
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, True])
        user = MagicMock()

        events = []
        with patch("src.routers.events.asyncio.sleep", new_callable=AsyncMock):
            async for event in event_generator(mock_request, "acme", user):
                events.append(event)

        assert len(events) == 1
        assert events[0]["event"] == "heartbeat"

    async def test_heartbeat_includes_connected_status(self):
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=[False, True])
        user = MagicMock()

        events = []
        with patch("src.routers.events.asyncio.sleep", new_callable=AsyncMock):
            async for event in event_generator(mock_request, "acme", user):
                events.append(event)

        import json

        data = json.loads(events[0]["data"])
        assert data["status"] == "connected"

    async def test_handles_cancelled_error_silently(self):
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(side_effect=asyncio.CancelledError)
        user = MagicMock()

        events = []
        async for event in event_generator(mock_request, "acme", user):
            events.append(event)

        assert events == []

    async def test_passes_event_types_through(self):
        mock_request = AsyncMock()
        mock_request.is_disconnected = AsyncMock(return_value=True)
        user = MagicMock()

        events = []
        async for event in event_generator(mock_request, "acme", user, ["api-created"]):
            events.append(event)

        assert events == []


# ── stream_global_events ──


class TestStreamGlobalEvents:
    async def test_non_admin_raises_403(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["tenant-admin"]

        with pytest.raises(HTTPException) as exc_info:
            await stream_global_events(mock_request, None, user)
        assert exc_info.value.status_code == 403

    async def test_cpi_admin_returns_event_source_response(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["cpi-admin"]

        result = await stream_global_events(mock_request, None, user)
        assert isinstance(result, EventSourceResponse)

    async def test_with_event_types_filter(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["cpi-admin"]

        result = await stream_global_events(mock_request, "deploy-success,deploy-failed", user)
        assert isinstance(result, EventSourceResponse)


# ── stream_events ──


class TestStreamEvents:
    async def test_returns_event_source_response_for_matching_tenant(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["cpi-admin"]
        user.tenant_id = "acme"

        result = await stream_events(mock_request, tenant_id="acme", event_types=None, user=user)
        assert isinstance(result, EventSourceResponse)

    async def test_with_event_types_filter(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["cpi-admin"]
        user.tenant_id = "acme"

        result = await stream_events(
            mock_request, tenant_id="acme", event_types="api-created,api-deleted", user=user
        )
        assert isinstance(result, EventSourceResponse)

    async def test_non_matching_tenant_raises_403(self):
        mock_request = MagicMock()
        user = MagicMock()
        user.roles = ["tenant-admin"]
        user.tenant_id = "other"

        with pytest.raises(HTTPException) as exc_info:
            await stream_events(mock_request, tenant_id="acme", event_types=None, user=user)
        assert exc_info.value.status_code == 403


# ── receive_deployment_result ──


class TestReceiveDeploymentResult:
    async def test_returns_received_status(self):
        result = DeploymentResult(api_name="test-api", tenant_id="acme", status="success")
        from src.services.kafka_service import kafka_service

        with patch.object(kafka_service, "_producer", None):
            response = await receive_deployment_result(result)

        assert response["status"] == "received"
        assert response["api_name"] == "test-api"
        assert response["deployment_status"] == "success"

    async def test_publishes_to_kafka_when_producer_set(self):
        result = DeploymentResult(api_name="myapi", tenant_id="acme", status="success")
        from src.services.kafka_service import kafka_service

        mock_producer = MagicMock()
        with patch.object(kafka_service, "_producer", mock_producer):
            with patch.object(kafka_service, "publish", new=AsyncMock()):
                response = await receive_deployment_result(result)

        assert response["status"] == "received"

    async def test_handles_kafka_publish_failure_gracefully(self):
        result = DeploymentResult(api_name="myapi", tenant_id="acme", status="failed")
        from src.services.kafka_service import kafka_service

        mock_producer = MagicMock()
        with patch.object(kafka_service, "_producer", mock_producer):
            with patch.object(kafka_service, "publish", new=AsyncMock(side_effect=Exception("Kafka down"))):
                response = await receive_deployment_result(result)

        assert response["status"] == "received"
        assert response["deployment_status"] == "failed"

    async def test_all_fields_in_response(self):
        result = DeploymentResult(
            api_name="api-v2",
            api_version="2.0",
            api_id="abc-123",
            tenant_id="org-x",
            status="rollback",
            action="deploy",
            message="rolled back",
        )
        from src.services.kafka_service import kafka_service

        with patch.object(kafka_service, "_producer", None):
            response = await receive_deployment_result(result)

        assert response["api_name"] == "api-v2"
        assert response["deployment_status"] == "rollback"
