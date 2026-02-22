"""Tests for deployment notification service (CAB-1413)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.notifications import templates
from src.notifications.deployment_notifier import notify_deployment_event


# ---------------------------------------------------------------------------
# templates.py unit tests
# ---------------------------------------------------------------------------

PAYLOAD_BASE = {
    "deployment_id": "deploy-abc123",
    "tenant_id": "acme",
    "api_id": "api-1",
    "api_name": "customer-api",
    "environment": "production",
    "version": "2.1.0",
    "deployed_by": "alice",
    "gateway_id": "gw-1",
    "rollback_of": None,
}


class TestTemplates:
    def test_deploy_started(self):
        msg = templates.format_message("deployment.started", PAYLOAD_BASE)
        assert ":rocket:" in msg
        assert "customer-api" in msg
        assert "v2.1.0" in msg
        assert "production" in msg.lower()
        assert "alice" in msg

    def test_rollback_started(self):
        payload = {**PAYLOAD_BASE, "rollback_of": "prev-deploy-xyz"}
        msg = templates.format_message("deployment.started", payload)
        assert ":arrows_counterclockwise:" in msg
        assert "customer-api" in msg
        assert "alice" in msg

    def test_deploy_completed(self):
        msg = templates.format_message("deployment.completed", PAYLOAD_BASE)
        assert ":white_check_mark:" in msg
        assert "customer-api" in msg
        assert "v2.1.0" in msg

    def test_deploy_failed(self):
        payload = {**PAYLOAD_BASE, "error_message": "timeout connecting to upstream"}
        msg = templates.format_message("deployment.failed", payload)
        assert ":x:" in msg
        assert "customer-api" in msg
        assert "timeout connecting to upstream" in msg
        assert "stoa logs customer-api" in msg

    def test_deploy_failed_no_api_name(self):
        payload = {**PAYLOAD_BASE, "api_name": None, "error_message": "oops"}
        msg = templates.format_message("deployment.failed", payload)
        assert "stoa deploy list" in msg  # fallback hint

    def test_deploy_rolledback(self):
        payload = {**PAYLOAD_BASE, "rollback_version": "1.5.0"}
        msg = templates.format_message("deployment.rolledback", payload)
        assert ":white_check_mark:" in msg
        assert "v1.5.0" in msg

    def test_unknown_event_type_returns_none(self):
        msg = templates.format_message("some.other.event", PAYLOAD_BASE)
        assert msg is None

    def test_tenant_env_included(self):
        msg = templates.format_message("deployment.completed", PAYLOAD_BASE)
        assert "acme" in msg
        assert "PRODUCTION" in msg


# ---------------------------------------------------------------------------
# deployment_notifier.py — integration with Slack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestNotifyDeploymentEvent:
    async def test_webhook_called_when_configured(self):
        with patch("src.notifications.deployment_notifier.settings") as mock_settings:
            mock_settings.SLACK_BOT_TOKEN = ""
            mock_settings.SLACK_CHANNEL_ID = ""
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                mock_client.post.return_value = MagicMock(raise_for_status=MagicMock())

                await notify_deployment_event("deployment.completed", PAYLOAD_BASE)

                mock_client.post.assert_called_once()
                call_kwargs = mock_client.post.call_args
                assert "https://hooks.slack.com/test" in call_kwargs[0]

    async def test_bot_api_called_when_configured(self):
        with patch("src.notifications.deployment_notifier.settings") as mock_settings:
            mock_settings.SLACK_BOT_TOKEN = "xoxb-test-token"
            mock_settings.SLACK_CHANNEL_ID = "C12345"
            mock_settings.SLACK_WEBHOOK_URL = ""

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                mock_client.post.return_value = AsyncMock()
                mock_client.post.return_value.json.return_value = {"ok": True}

                await notify_deployment_event("deployment.started", PAYLOAD_BASE)

                mock_client.post.assert_called_once()
                call_kwargs = mock_client.post.call_args
                assert "chat.postMessage" in call_kwargs[0][0]

    async def test_no_op_when_unconfigured(self):
        with patch("src.notifications.deployment_notifier.settings") as mock_settings:
            mock_settings.SLACK_BOT_TOKEN = ""
            mock_settings.SLACK_CHANNEL_ID = ""
            mock_settings.SLACK_WEBHOOK_URL = ""

            with patch("httpx.AsyncClient") as mock_client_cls:
                await notify_deployment_event("deployment.completed", PAYLOAD_BASE)
                mock_client_cls.assert_not_called()

    async def test_unknown_event_type_is_no_op(self):
        with patch("httpx.AsyncClient") as mock_client_cls:
            await notify_deployment_event("not.a.real.event", PAYLOAD_BASE)
            mock_client_cls.assert_not_called()

    async def test_slack_error_does_not_raise(self):
        with patch("src.notifications.deployment_notifier.settings") as mock_settings:
            mock_settings.SLACK_BOT_TOKEN = ""
            mock_settings.SLACK_CHANNEL_ID = ""
            mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.com/test"

            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                mock_client.post.side_effect = Exception("network error")

                # Must not raise — errors are logged as warnings
                await notify_deployment_event("deployment.completed", PAYLOAD_BASE)
