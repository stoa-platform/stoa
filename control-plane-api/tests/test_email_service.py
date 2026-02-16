"""Tests for EmailService (CAB-1291)"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.services.email import EmailService


class TestEmailServiceInit:
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            svc = EmailService()
        assert svc.smtp_host == "localhost"
        assert svc.smtp_port == 587
        assert svc.smtp_from == "noreply@gostoa.dev"
        assert svc.smtp_tls is True
        assert svc.enabled is False

    def test_custom_env(self):
        env = {
            "SMTP_HOST": "mail.example.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": "false",
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "PORTAL_URL": "https://portal.test",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()
        assert svc.smtp_host == "mail.example.com"
        assert svc.smtp_port == 465
        assert svc.smtp_user == "user"
        assert svc.smtp_tls is False
        assert svc.enabled is True
        assert svc.portal_url == "https://portal.test"


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_disabled_returns_true(self):
        with patch.dict("os.environ", {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=True):
            svc = EmailService()
        result = await svc.send_email("test@example.com", "Subject", "<p>Body</p>")
        assert result is True

    @pytest.mark.asyncio
    async def test_enabled_sends_email(self):
        env = {
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "SMTP_HOST": "localhost",
            "SMTP_PORT": "587",
            "SMTP_TLS": "true",
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("src.services.email.smtplib.SMTP", return_value=mock_smtp):
            result = await svc.send_email("to@example.com", "Test", "<p>HTML</p>", "Text")

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "pass")
        mock_smtp.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_enabled_no_tls_no_auth(self):
        env = {
            "EMAIL_NOTIFICATIONS_ENABLED": "true",
            "SMTP_TLS": "false",
            "SMTP_USER": "",
            "SMTP_PASSWORD": "",
        }
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("src.services.email.smtplib.SMTP", return_value=mock_smtp):
            result = await svc.send_email("to@example.com", "Test", "<p>HTML</p>")

        assert result is True
        mock_smtp.starttls.assert_not_called()
        mock_smtp.login.assert_not_called()

    @pytest.mark.asyncio
    async def test_smtp_error_returns_false(self):
        env = {"EMAIL_NOTIFICATIONS_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()

        with patch("src.services.email.smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
            result = await svc.send_email("to@example.com", "Test", "<p>HTML</p>")

        assert result is False

    @pytest.mark.asyncio
    async def test_html_only_no_text(self):
        env = {"EMAIL_NOTIFICATIONS_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("src.services.email.smtplib.SMTP", return_value=mock_smtp):
            result = await svc.send_email("to@example.com", "Test", "<p>HTML only</p>")

        assert result is True
        # sendmail called with the message
        args = mock_smtp.sendmail.call_args[0]
        msg_str = args[2]
        assert "HTML only" in msg_str


class TestSendKeyRotationNotification:
    @pytest.mark.asyncio
    async def test_disabled_returns_true(self):
        with patch.dict("os.environ", {"EMAIL_NOTIFICATIONS_ENABLED": "false"}, clear=True):
            svc = EmailService()

        result = await svc.send_key_rotation_notification(
            to_email="dev@example.com",
            subscription_id="sub-123",
            api_name="Weather API",
            application_name="MyApp",
            new_api_key="sk_new_key_value",
            old_key_expires_at=datetime(2026, 3, 1, 12, 0, 0),
            grace_period_hours=24,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_builds_correct_subject(self):
        env = {"EMAIL_NOTIFICATIONS_ENABLED": "true"}
        with patch.dict("os.environ", env, clear=True):
            svc = EmailService()

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("src.services.email.smtplib.SMTP", return_value=mock_smtp):
            result = await svc.send_key_rotation_notification(
                to_email="dev@example.com",
                subscription_id="sub-456",
                api_name="Payment API",
                application_name="FinApp",
                new_api_key="sk_rotated_abc",
                old_key_expires_at=datetime(2026, 3, 1, 12, 0, 0),
                grace_period_hours=48,
            )

        assert result is True
        msg_str = mock_smtp.sendmail.call_args[0][2]
        assert "[STOA] API Key Rotated - Payment API" in msg_str
        assert "sk_rotated_abc" in msg_str
        assert "48 hours" in msg_str
        assert "sub-456" in msg_str
