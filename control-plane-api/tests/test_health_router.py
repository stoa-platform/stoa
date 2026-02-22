"""Tests for health router check functions (CAB-1388)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.routers.health import (
    _check_gateway_connected,
    _check_gitlab_connected,
    _check_kafka_connected,
    _check_keycloak_connected,
    readiness,
)

# ── Helper check functions ──


class TestCheckKafkaConnected:
    def test_returns_false_when_producer_is_none(self):
        with patch("src.routers.health.kafka_service") as mock_svc:
            mock_svc._producer = None
            assert _check_kafka_connected() is False

    def test_returns_true_when_producer_is_set(self):
        with patch("src.routers.health.kafka_service") as mock_svc:
            mock_svc._producer = MagicMock()
            assert _check_kafka_connected() is True


class TestCheckGitlabConnected:
    def test_returns_false_when_gl_is_none(self):
        with patch("src.routers.health.git_service") as mock_svc:
            mock_svc._gl = None
            assert _check_gitlab_connected() is False

    def test_returns_true_when_gl_is_set(self):
        with patch("src.routers.health.git_service") as mock_svc:
            mock_svc._gl = MagicMock()
            assert _check_gitlab_connected() is True


class TestCheckKeycloakConnected:
    def test_returns_false_when_admin_is_none(self):
        with patch("src.routers.health.keycloak_service") as mock_svc:
            mock_svc._admin = None
            assert _check_keycloak_connected() is False

    def test_returns_true_when_admin_is_set(self):
        with patch("src.routers.health.keycloak_service") as mock_svc:
            mock_svc._admin = MagicMock()
            assert _check_keycloak_connected() is True


class TestCheckGatewayConnected:
    def test_returns_true_when_oidc_proxy_mode(self):
        with patch("src.config.settings") as mock_cfg:
            mock_cfg.GATEWAY_USE_OIDC_PROXY = True
            assert _check_gateway_connected() is True

    def test_returns_true_when_client_is_set(self):
        with patch("src.config.settings") as mock_cfg:
            mock_cfg.GATEWAY_USE_OIDC_PROXY = False
            with patch("src.routers.health.gateway_service") as mock_gw:
                mock_gw._client = MagicMock()
                assert _check_gateway_connected() is True

    def test_returns_false_when_client_is_none(self):
        with patch("src.config.settings") as mock_cfg:
            mock_cfg.GATEWAY_USE_OIDC_PROXY = False
            with patch("src.routers.health.gateway_service") as mock_gw:
                mock_gw._client = None
                assert _check_gateway_connected() is False


# ── readiness exception paths ──


def _mock_settings(kafka_enabled=True, version="1.0.0"):
    m = MagicMock()
    m.KAFKA_ENABLED = kafka_enabled
    m.VERSION = version
    return m


class TestReadinessExceptions:
    async def test_kafka_exception_returns_503(self):
        with (
            patch("src.routers.health.settings", _mock_settings()),
            patch("src.routers.health._check_kafka_connected", side_effect=Exception("k-down")),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            await readiness()

        assert exc_info.value.status_code == 503
        assert "kafka" in exc_info.value.detail["checks"]

    async def test_keycloak_exception_returns_503(self):
        with (
            patch("src.routers.health.settings", _mock_settings(kafka_enabled=False)),
            patch("src.routers.health._check_keycloak_connected", side_effect=Exception("kc-down")),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", return_value=True),
            pytest.raises(HTTPException) as exc_info,
        ):
            await readiness()

        assert exc_info.value.status_code == 503
        assert "keycloak" in exc_info.value.detail["checks"]

    async def test_gitlab_exception_is_non_critical(self):
        with (
            patch("src.routers.health.settings", _mock_settings(kafka_enabled=False)),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", side_effect=Exception("gl-down")),
            patch("src.routers.health._check_gateway_connected", return_value=True),
        ):
            result = await readiness()

        assert result.status == "healthy"
        assert "error" in result.checks["gitlab"]

    async def test_gateway_exception_is_non_critical(self):
        with (
            patch("src.routers.health.settings", _mock_settings(kafka_enabled=False)),
            patch("src.routers.health._check_keycloak_connected", return_value=True),
            patch("src.routers.health._check_gitlab_connected", return_value=True),
            patch("src.routers.health._check_gateway_connected", side_effect=Exception("gw-down")),
        ):
            result = await readiness()

        assert result.status == "healthy"
        assert "error" in result.checks["gateway"]
