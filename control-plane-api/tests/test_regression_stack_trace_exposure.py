"""Regression tests for stack trace exposure fix (PR #1930).

Ensures that internal exception messages are never leaked to HTTP clients
in the gateway OIDC configuration and MCP GitOps sync status endpoints.

Security: CWE-209 (Generation of Error Message Containing Sensitive Information)
"""

from unittest.mock import AsyncMock, MagicMock, patch


GATEWAY_SERVICE_PATH = "src.routers.gateway.gateway_service"
MCP_SYNC_SERVICE_PATH = "src.routers.mcp_gitops.MCPSyncService"


class TestRegressionStackTraceExposureGatewayOIDC:
    """PR #1930: configure_api_oidc must not leak exception details."""

    def test_regression_configure_oidc_error_hides_exception_message(
        self, client_as_cpi_admin
    ):
        """When configure_api_oidc raises, the response detail must be a static
        string and must NOT contain the raw exception message."""
        secret_error = "Connection refused to internal-db.corp:5432 password=hunter2"

        with patch(GATEWAY_SERVICE_PATH) as mock_gw:
            mock_gw.configure_api_oidc = AsyncMock(
                side_effect=Exception(secret_error)
            )
            resp = client_as_cpi_admin.post(
                "/v1/gateway/configure-oidc",
                json={
                    "tenant_id": "acme",
                    "api_name": "test-api",
                    "api_version": "1.0",
                    "api_id": "api-123",
                    "client_id": "client-123",
                    "audience": "https://api.example.com",
                    "auth_server_alias": "local",
                },
            )

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert detail == "Gateway OIDC configuration error"
        assert secret_error not in detail
        assert "hunter2" not in detail
        assert "Connection refused" not in detail

    def test_regression_configure_oidc_error_does_not_contain_str_repr(
        self, client_as_cpi_admin
    ):
        """The error detail must not use f-string interpolation of the exception."""
        with patch(GATEWAY_SERVICE_PATH) as mock_gw:
            mock_gw.configure_api_oidc = AsyncMock(
                side_effect=RuntimeError("KeyError: 'KEYCLOAK_SECRET'")
            )
            resp = client_as_cpi_admin.post(
                "/v1/gateway/configure-oidc",
                json={
                    "tenant_id": "acme",
                    "api_name": "test-api",
                    "api_version": "1.0",
                    "api_id": "api-123",
                    "client_id": "client-123",
                    "audience": "https://api.example.com",
                    "auth_server_alias": "local",
                },
            )

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "KEYCLOAK_SECRET" not in detail
        assert "KeyError" not in detail


class TestRegressionStackTraceExposureSyncStatus:
    """PR #1930: get_sync_status must not leak exception details."""

    def test_regression_sync_status_error_hides_exception_message(
        self, client_as_cpi_admin
    ):
        """When get_sync_status raises, the response detail must be the static
        string, not the raw exception message."""
        secret_error = "psycopg2.OperationalError: FATAL password auth failed for user 'stoa_admin'"

        with patch(MCP_SYNC_SERVICE_PATH) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_sync_status = AsyncMock(
                side_effect=Exception(secret_error)
            )
            mock_cls.return_value = mock_instance

            resp = client_as_cpi_admin.get("/v1/mcp/gitops/status")

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert detail == "Failed to get sync status"
        assert secret_error not in detail
        assert "stoa_admin" not in detail
        assert "password" not in detail

    def test_regression_sync_status_error_does_not_contain_traceback(
        self, client_as_cpi_admin
    ):
        """The error detail must not contain any part of an internal traceback."""
        with patch(MCP_SYNC_SERVICE_PATH) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_sync_status = AsyncMock(
                side_effect=ConnectionError(
                    "Traceback (most recent call last): File '/app/src/db.py'"
                )
            )
            mock_cls.return_value = mock_instance

            resp = client_as_cpi_admin.get("/v1/mcp/gitops/status")

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "Traceback" not in detail
        assert "/app/src/db.py" not in detail
