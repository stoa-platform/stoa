"""Tests for email notification service (CAB-1538)."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.services.email import EmailService


class TestEmailServiceInit:
    """Tests for EmailService configuration from env vars."""

    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            svc = EmailService()
            assert svc.smtp_host == "localhost"
            assert svc.smtp_port == 587
            assert svc.smtp_user == ""
            assert svc.smtp_password == ""
            assert svc.smtp_from == "noreply@gostoa.dev"
            assert svc.smtp_tls is True
            assert svc.enabled is False
            assert svc.portal_url == "https://portal.gostoa.dev"

    def test_custom_env_vars(self):
        env = {
            "SMTP_HOST": "mail.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "user@example.com",
            "SMTP_PASSWORD": "pass123",
            "SMTP_FROM": "alerts@example.com",
            "SMTP_TLS": "false",
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "PORTAL_URL": "https://portal.example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()
            assert svc.smtp_host == "mail.example.com"
            assert svc.smtp_port == 465
            assert svc.smtp_user == "user@example.com"
            assert svc.smtp_password == "pass123"
            assert svc.smtp_from == "alerts@example.com"
            assert svc.smtp_tls is False
            assert svc.enabled is True
            assert svc.portal_url == "https://portal.example.com"


class TestSendEmailDisabled:
    """Tests for send_email when notifications are disabled."""

    @pytest.mark.asyncio
    async def test_disabled_returns_true_without_sending(self):
        with patch.dict("os.environ", {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=True):
            svc = EmailService()
            result = await svc.send_email("user@test.com", "Subject", "<p>Body</p>")
            assert result is True


class TestKeyRotationEmail:
    """Tests for the key rotation email template."""

    @pytest.mark.asyncio
    async def test_rotation_email_disabled_returns_true(self):
        with patch.dict("os.environ", {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=True):
            svc = EmailService()
            result = await svc.send_key_rotation_notification(
                to_email="dev@test.com",
                subscription_id="sub-123",
                api_name="My API",
                application_name="My App",
                new_api_key="stoa_key_abc123",
                old_key_expires_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
                grace_period_hours=24,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_send_email_smtp_failure_returns_false(self):
        env = {"EMAIL_NOTIFICATIONS_ENABLED": "true", "SMTP_HOST": "invalid.host.local"}
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()
            result = await svc.send_email("user@test.com", "Test", "<p>Test</p>")
            assert result is False
