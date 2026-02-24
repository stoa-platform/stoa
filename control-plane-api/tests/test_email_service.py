"""Unit tests for EmailService — email.py (CAB-1437 Phase 2)

Tests send_email (enabled/disabled), SMTP interactions, and key rotation notification.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.email import EmailService


@pytest.fixture()
def service_disabled():
    """EmailService with notifications disabled (default)."""
    with patch.dict("os.environ", {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=False):
        return EmailService()


@pytest.fixture()
def service_enabled():
    """EmailService with notifications enabled and SMTP config."""
    env = {
        "EMAIL_NOTIFICATIONS_ENABLED": "true",
        "SMTP_HOST": "smtp.test.local",
        "SMTP_PORT": "587",
        "SMTP_USER": "user@test.local",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "noreply@test.local",
        "SMTP_TLS": "true",
        "PORTAL_URL": "https://portal.test.local",
    }
    with patch.dict("os.environ", env, clear=False):
        return EmailService()


# ── Disabled mode ──


class TestDisabledMode:
    async def test_send_email_returns_true_when_disabled(self, service_disabled):
        result = await service_disabled.send_email("user@test.com", "Test", "<p>Hi</p>")
        assert result is True

    async def test_no_smtp_connection_when_disabled(self, service_disabled):
        with patch("smtplib.SMTP") as mock_smtp:
            await service_disabled.send_email("user@test.com", "Test", "<p>Hi</p>")
            mock_smtp.assert_not_called()


# ── Enabled mode ──


class TestEnabledMode:
    async def test_send_email_success(self, service_enabled):
        mock_server = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_server):
            mock_server.__enter__ = MagicMock(return_value=mock_server)
            mock_server.__exit__ = MagicMock(return_value=False)
            result = await service_enabled.send_email("user@test.com", "Hello", "<p>Hi</p>")

        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@test.local", "secret")
        mock_server.sendmail.assert_called_once()

    async def test_send_email_with_text_body(self, service_enabled):
        mock_server = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_server):
            mock_server.__enter__ = MagicMock(return_value=mock_server)
            mock_server.__exit__ = MagicMock(return_value=False)
            result = await service_enabled.send_email(
                "user@test.com", "Hello", "<p>Hi</p>", text_body="Hi"
            )
        assert result is True

    async def test_send_email_smtp_failure(self, service_enabled):
        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("no server")):
            result = await service_enabled.send_email("user@test.com", "Hello", "<p>Hi</p>")
        assert result is False

    async def test_no_tls_when_disabled(self):
        env = {
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "SMTP_TLS": "false",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
        }
        with patch.dict("os.environ", env, clear=False):
            svc = EmailService()

        mock_server = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_server):
            mock_server.__enter__ = MagicMock(return_value=mock_server)
            mock_server.__exit__ = MagicMock(return_value=False)
            await svc.send_email("user@test.com", "Hello", "<p>Hi</p>")

        mock_server.starttls.assert_not_called()
        mock_server.login.assert_not_called()


# ── Key rotation notification ──


class TestKeyRotationNotification:
    async def test_sends_rotation_email(self, service_enabled):
        mock_server = MagicMock()
        with patch("smtplib.SMTP", return_value=mock_server):
            mock_server.__enter__ = MagicMock(return_value=mock_server)
            mock_server.__exit__ = MagicMock(return_value=False)
            result = await service_enabled.send_key_rotation_notification(
                to_email="dev@test.com",
                subscription_id="sub-123",
                api_name="Pet Store",
                application_name="My App",
                new_api_key="stoa_sk_new_key_here",
                old_key_expires_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
                grace_period_hours=24,
            )

        assert result is True
        call_args = mock_server.sendmail.call_args
        msg_body = call_args[0][2]
        assert "Pet Store" in msg_body
        assert "stoa_sk_new_key_here" in msg_body
        assert "24 hours" in msg_body

    async def test_rotation_subject_contains_api_name(self, service_disabled):
        with patch.object(service_disabled, "send_email", return_value=True) as mock_send:
            await service_disabled.send_key_rotation_notification(
                to_email="dev@test.com",
                subscription_id="sub-123",
                api_name="Payment API",
                application_name="App",
                new_api_key="key",
                old_key_expires_at=datetime(2026, 3, 1, tzinfo=UTC),
                grace_period_hours=12,
            )
        subject = mock_send.call_args[0][1]
        assert "Payment API" in subject
