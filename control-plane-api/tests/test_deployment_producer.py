"""Tests for deployment lifecycle event producer (CAB-1410)."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.events.deployment_producer import (
    emit_deployment_completed,
    emit_deployment_failed,
    emit_deployment_rolledback,
    emit_deployment_started,
)
from src.services.kafka_service import Topics

PUBLISH_PATH = "src.events.deployment_producer.kafka_service.publish"


def _mock_deployment(**overrides):
    m = MagicMock()
    m.id = uuid4()
    m.tenant_id = "acme"
    m.api_id = "petstore"
    m.api_name = "Petstore API"
    m.environment = "production"
    m.version = "1.2.0"
    m.status = "pending"
    m.deployed_by = "admin"
    m.gateway_id = "stoa-k8s"
    m.rollback_of = None
    m.rollback_version = None
    m.error_message = None
    m.spec_hash = "abc123"
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


class TestEmitDeploymentStarted:
    @pytest.mark.asyncio
    async def test_publishes_to_deployment_events(self):
        dep = _mock_deployment()
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "event-id-1"
            result = await emit_deployment_started(dep)
        mock_pub.assert_called_once()
        call_kwargs = mock_pub.call_args.kwargs
        assert call_kwargs["topic"] == Topics.DEPLOYMENT_EVENTS
        assert call_kwargs["event_type"] == "deployment.started"
        assert call_kwargs["tenant_id"] == "acme"
        assert result == "event-id-1"

    @pytest.mark.asyncio
    async def test_payload_contains_required_fields(self):
        dep = _mock_deployment()
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "x"
            await emit_deployment_started(dep)
        payload = mock_pub.call_args.kwargs["payload"]
        assert payload["deployment_id"] == str(dep.id)
        assert payload["api_id"] == "petstore"
        assert payload["environment"] == "production"

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_kafka_error(self):
        dep = _mock_deployment()
        with patch(PUBLISH_PATH, new_callable=AsyncMock, side_effect=Exception("Kafka down")):
            result = await emit_deployment_started(dep)
        assert result == ""


class TestEmitDeploymentCompleted:
    @pytest.mark.asyncio
    async def test_event_type(self):
        dep = _mock_deployment(spec_hash="deadbeef")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev-2"
            await emit_deployment_completed(dep)
        assert mock_pub.call_args.kwargs["event_type"] == "deployment.completed"

    @pytest.mark.asyncio
    async def test_payload_includes_spec_hash(self):
        dep = _mock_deployment(spec_hash="cafebabe")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev"
            await emit_deployment_completed(dep)
        payload = mock_pub.call_args.kwargs["payload"]
        assert payload["spec_hash"] == "cafebabe"

    @pytest.mark.asyncio
    async def test_graceful_on_error(self):
        dep = _mock_deployment()
        with patch(PUBLISH_PATH, new_callable=AsyncMock, side_effect=RuntimeError("conn refused")):
            result = await emit_deployment_completed(dep)
        assert result == ""


class TestEmitDeploymentFailed:
    @pytest.mark.asyncio
    async def test_event_type(self):
        dep = _mock_deployment(error_message="timeout")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev-3"
            await emit_deployment_failed(dep)
        assert mock_pub.call_args.kwargs["event_type"] == "deployment.failed"

    @pytest.mark.asyncio
    async def test_payload_includes_error(self):
        dep = _mock_deployment(error_message="gateway unreachable")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev"
            await emit_deployment_failed(dep)
        payload = mock_pub.call_args.kwargs["payload"]
        assert payload["error_message"] == "gateway unreachable"


class TestEmitDeploymentRolledback:
    @pytest.mark.asyncio
    async def test_event_type(self):
        dep = _mock_deployment(rollback_version="1.1.0")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev-4"
            await emit_deployment_rolledback(dep)
        assert mock_pub.call_args.kwargs["event_type"] == "deployment.rolledback"

    @pytest.mark.asyncio
    async def test_payload_includes_rollback_version(self):
        dep = _mock_deployment(rollback_version="0.9.0")
        with patch(PUBLISH_PATH, new_callable=AsyncMock) as mock_pub:
            mock_pub.return_value = "ev"
            await emit_deployment_rolledback(dep)
        payload = mock_pub.call_args.kwargs["payload"]
        assert payload["rollback_version"] == "0.9.0"
