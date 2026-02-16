"""Tests for logging_config (CAB-1291)"""
import logging
from unittest.mock import MagicMock, patch

import pytest

from src.logging_config import (
    ComponentLevelFilter,
    SensitiveDataMasker,
    add_app_context,
    bind_request_context,
    clear_context,
    generate_request_id,
    get_logger,
    unbind_context,
)


# ── SensitiveDataMasker ──


class TestSensitiveDataMasker:
    def _make_masker(self, patterns=None):
        return SensitiveDataMasker(patterns or ["password", "secret", "token"])

    def test_masks_matching_keys(self):
        masker = self._make_masker()
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_MASKING_ENABLED = True
            result = masker(MagicMock(), "info", {
                "username": "alice", "password": "s3cret", "api_token": "abc123"
            })
        assert result["username"] == "alice"
        assert result["password"] == "[REDACTED]"
        assert result["api_token"] == "[REDACTED]"

    def test_masks_nested_dicts(self):
        masker = self._make_masker()
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_MASKING_ENABLED = True
            result = masker(MagicMock(), "info", {
                "data": {"secret_key": "val", "name": "test"}
            })
        assert result["data"]["secret_key"] == "[REDACTED]"
        assert result["data"]["name"] == "test"

    def test_masks_in_list_of_dicts(self):
        masker = self._make_masker()
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_MASKING_ENABLED = True
            result = masker(MagicMock(), "info", {
                "items": [{"password": "x"}, {"name": "y"}]
            })
        assert result["items"][0]["password"] == "[REDACTED]"
        assert result["items"][1]["name"] == "y"

    def test_disabled_masking_passes_through(self):
        masker = self._make_masker()
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_MASKING_ENABLED = False
            original = {"password": "visible"}
            result = masker(MagicMock(), "info", original)
        assert result["password"] == "visible"

    def test_custom_mask_value(self):
        masker = SensitiveDataMasker(["secret"], mask_value="***")
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_MASKING_ENABLED = True
            result = masker(MagicMock(), "info", {"secret": "val"})
        assert result["secret"] == "***"


# ── ComponentLevelFilter ──


class TestComponentLevelFilter:
    def test_exact_match(self):
        f = ComponentLevelFilter({"src.routers": "WARNING"}, default_level="INFO")
        record = MagicMock()
        record.name = "src.routers"
        record.levelno = logging.INFO
        assert f.filter(record) is False  # INFO < WARNING

        record.levelno = logging.WARNING
        assert f.filter(record) is True

    def test_child_logger_match(self):
        f = ComponentLevelFilter({"src.routers": "ERROR"}, default_level="DEBUG")
        record = MagicMock()
        record.name = "src.routers.api"
        record.levelno = logging.WARNING
        assert f.filter(record) is False  # WARNING < ERROR

    def test_default_level(self):
        f = ComponentLevelFilter({}, default_level="WARNING")
        record = MagicMock()
        record.name = "unknown.module"
        record.levelno = logging.INFO
        assert f.filter(record) is False

        record.levelno = logging.WARNING
        assert f.filter(record) is True

    def test_prefix_match(self):
        f = ComponentLevelFilter({"src.services": "DEBUG"}, default_level="WARNING")
        record = MagicMock()
        record.name = "src.services.keycloak"
        record.levelno = logging.DEBUG
        assert f.filter(record) is True


# ── add_app_context ──


class TestAddAppContext:
    def test_adds_component(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_TENANT_ID = False
            mock_settings.LOG_CONTEXT_USER_ID = False
            event_dict = {}
            result = add_app_context(MagicMock(), "info", event_dict)
            assert result["component"] == "control-plane-api"

    def test_preserves_existing_component(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_TENANT_ID = False
            mock_settings.LOG_CONTEXT_USER_ID = False
            event_dict = {"component": "custom"}
            result = add_app_context(MagicMock(), "info", event_dict)
            assert result["component"] == "custom"

    def test_adds_environment_when_context_enabled(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_TENANT_ID = True
            mock_settings.LOG_CONTEXT_USER_ID = False
            mock_settings.ENVIRONMENT = "production"
            mock_settings.VERSION = "1.0.0"
            event_dict = {}
            result = add_app_context(MagicMock(), "info", event_dict)
            assert result["environment"] == "production"
            assert result["version"] == "1.0.0"


# ── Helpers ──


class TestGenerateRequestId:
    def test_returns_uuid_string(self):
        rid = generate_request_id()
        assert isinstance(rid, str)
        assert len(rid) == 36  # UUID format with dashes

    def test_unique(self):
        ids = {generate_request_id() for _ in range(10)}
        assert len(ids) == 10


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test")
        assert logger is not None


class TestBindRequestContext:
    def test_with_request_id(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_REQUEST_ID = True
            mock_settings.LOG_CONTEXT_TENANT_ID = False
            mock_settings.LOG_CONTEXT_USER_ID = False
            mock_settings.LOG_CONTEXT_TRACE_ID = False
            with patch("src.logging_config.bind_context") as mock_bind:
                rid = bind_request_context(request_id="req-1")
                assert rid == "req-1"
                mock_bind.assert_called_once_with(request_id="req-1")

    def test_generates_request_id(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_REQUEST_ID = True
            mock_settings.LOG_CONTEXT_TENANT_ID = False
            mock_settings.LOG_CONTEXT_USER_ID = False
            mock_settings.LOG_CONTEXT_TRACE_ID = False
            with patch("src.logging_config.bind_context"):
                rid = bind_request_context()
                assert len(rid) == 36  # UUID

    def test_with_all_context(self):
        with patch("src.logging_config.settings") as mock_settings:
            mock_settings.LOG_CONTEXT_REQUEST_ID = True
            mock_settings.LOG_CONTEXT_TENANT_ID = True
            mock_settings.LOG_CONTEXT_USER_ID = True
            mock_settings.LOG_CONTEXT_TRACE_ID = True
            with patch("src.logging_config.bind_context") as mock_bind:
                bind_request_context(
                    request_id="r", tenant_id="t", user_id="u",
                    trace_id="tr", span_id="sp",
                )
                call_kwargs = mock_bind.call_args[1]
                assert call_kwargs["request_id"] == "r"
                assert call_kwargs["tenant_id"] == "t"
                assert call_kwargs["user_id"] == "u"
                assert call_kwargs["trace_id"] == "tr"
                assert call_kwargs["span_id"] == "sp"


class TestClearAndUnbind:
    def test_clear_context(self):
        with patch("src.logging_config.structlog.contextvars.clear_contextvars") as mock_clear:
            clear_context()
            mock_clear.assert_called_once()

    def test_unbind_context(self):
        with patch("src.logging_config.structlog.contextvars.unbind_contextvars") as mock_unbind:
            unbind_context("a", "b")
            mock_unbind.assert_called_once_with("a", "b")
