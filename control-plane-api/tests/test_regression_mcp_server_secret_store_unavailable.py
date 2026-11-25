"""MCP server writes are refused (503) when the secret store cannot save credentials.

Creating or updating an external or tenant MCP server with credentials used to
succeed when the store failed: the server was saved without them and only a
log line said so. The request now fails with 503 and nothing is written. The
same applies when the store is disabled (VAULT_ENABLED=false) and credentials
are supplied: they could not be kept, so the write is refused.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.routers import external_mcp_servers, tenant_mcp_servers
from src.services.vault_client import VaultSealedException, VaultUnavailableError
from tests.test_external_mcp_servers_router import _mock_server as external_server
from tests.test_tenant_mcp_servers_router import _mock_server as tenant_server

EXT_REPO = "src.routers.external_mcp_servers.ExternalMCPServerRepository"
EXT_VAULT = "src.routers.external_mcp_servers.get_vault_client"
TEN_REPO = "src.routers.tenant_mcp_servers.ExternalMCPServerRepository"
TEN_VAULT = "src.routers.tenant_mcp_servers.get_vault_client"
EXT_BASE = "/v1/admin/external-mcp-servers"
TEN_BASE = "/v1/tenants/acme/mcp-servers"

FAILURES = [
    pytest.param(VaultUnavailableError("Secret store is unavailable"), id="unavailable"),
    pytest.param(VaultSealedException(), id="sealed"),
    pytest.param(TimeoutError("read timed out"), id="timeout"),
]

EXT_CREATE = {
    "name": "secure-mcp",
    "display_name": "Secure MCP",
    "base_url": "https://mcp.example.test/sse",
    "auth_type": "bearer_token",
    "credentials": {"bearer_token": "placeholder"},
}
TEN_CREATE = {
    "display_name": "My Tool",
    "base_url": "https://mcp.example.test/sse",
    "transport": "sse",
    "auth_type": "bearer_token",
    "credentials": {"bearer_token": "placeholder"},
    "tool_prefix": "tool",
}


def _failing_vault(error: Exception) -> MagicMock:
    vault = MagicMock()
    vault.store_credential = AsyncMock(side_effect=error)
    return vault


def _assert_refused(response, repo, db, write: str) -> None:
    assert response.status_code == 503
    assert response.json()["detail"] == external_mcp_servers.SECRET_STORE_UNAVAILABLE_DETAIL
    assert "placeholder" not in response.text
    getattr(repo, write).assert_not_awaited()
    db.commit.assert_not_awaited()


def test_both_routers_share_the_message():
    assert external_mcp_servers.SECRET_STORE_UNAVAILABLE_DETAIL == tenant_mcp_servers.SECRET_STORE_UNAVAILABLE_DETAIL


@pytest.mark.parametrize("error", FAILURES)
def test_external_create_refused(app_with_cpi_admin, mock_db_session, error):
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=_failing_vault(error)):
        repo = repo_cls.return_value
        repo.get_by_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=external_server())
        with TestClient(app_with_cpi_admin) as client:
            response = client.post(EXT_BASE, json=EXT_CREATE)
    _assert_refused(response, repo, mock_db_session, "create")


@pytest.mark.parametrize("error", FAILURES)
def test_external_update_refused(app_with_cpi_admin, mock_db_session, error):
    server_id = uuid4()
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=_failing_vault(error)):
        repo = repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=external_server(id=server_id))
        repo.update = AsyncMock()
        with TestClient(app_with_cpi_admin) as client:
            response = client.put(f"{EXT_BASE}/{server_id}", json={"credentials": {"bearer_token": "placeholder"}})
    _assert_refused(response, repo, mock_db_session, "update")
    mock_db_session.rollback.assert_awaited()


@pytest.mark.parametrize("error", FAILURES)
def test_tenant_create_refused(app_with_tenant_admin, mock_db_session, error):
    with patch(TEN_REPO) as repo_cls, patch(TEN_VAULT, return_value=_failing_vault(error)):
        repo = repo_cls.return_value
        repo.get_by_tenant_and_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=tenant_server())
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(TEN_BASE, json=TEN_CREATE)
    _assert_refused(response, repo, mock_db_session, "create")


@pytest.mark.parametrize("error", FAILURES)
def test_tenant_update_refused(app_with_tenant_admin, mock_db_session, error):
    server = tenant_server()
    with patch(TEN_REPO) as repo_cls, patch(TEN_VAULT, return_value=_failing_vault(error)):
        repo = repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=server)
        repo.update = AsyncMock()
        with TestClient(app_with_tenant_admin) as client:
            response = client.put(f"{TEN_BASE}/{server.id}", json={"credentials": {"bearer_token": "placeholder"}})
    _assert_refused(response, repo, mock_db_session, "update")
    mock_db_session.rollback.assert_awaited()


def test_create_without_credentials_does_not_touch_the_store(app_with_cpi_admin, mock_db_session):
    vault = _failing_vault(VaultUnavailableError("down"))
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=vault):
        repo = repo_cls.return_value
        repo.get_by_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=external_server())
        body = {k: v for k, v in EXT_CREATE.items() if k != "credentials"} | {"auth_type": "none"}
        with TestClient(app_with_cpi_admin) as client:
            response = client.post(EXT_BASE, json=body)
    assert response.status_code == 201
    vault.store_credential.assert_not_awaited()


def _disabled_vault() -> MagicMock:
    vault = MagicMock()
    vault.enabled = False
    vault.store_credential = AsyncMock(return_value=None)
    return vault


def test_external_create_refused_when_store_disabled(app_with_cpi_admin, mock_db_session):
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=_disabled_vault()):
        repo = repo_cls.return_value
        repo.get_by_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=external_server())
        with TestClient(app_with_cpi_admin) as client:
            response = client.post(EXT_BASE, json=EXT_CREATE)
    _assert_refused(response, repo, mock_db_session, "create")


def test_external_update_refused_when_store_disabled(app_with_cpi_admin, mock_db_session):
    server_id = uuid4()
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=_disabled_vault()):
        repo = repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=external_server(id=server_id))
        repo.update = AsyncMock()
        with TestClient(app_with_cpi_admin) as client:
            response = client.put(f"{EXT_BASE}/{server_id}", json={"credentials": {"bearer_token": "placeholder"}})
    _assert_refused(response, repo, mock_db_session, "update")
    mock_db_session.rollback.assert_awaited()


def test_tenant_create_refused_when_store_disabled(app_with_tenant_admin, mock_db_session):
    with patch(TEN_REPO) as repo_cls, patch(TEN_VAULT, return_value=_disabled_vault()):
        repo = repo_cls.return_value
        repo.get_by_tenant_and_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=tenant_server())
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(TEN_BASE, json=TEN_CREATE)
    _assert_refused(response, repo, mock_db_session, "create")


def test_tenant_update_refused_when_store_disabled(app_with_tenant_admin, mock_db_session):
    server = tenant_server()
    with patch(TEN_REPO) as repo_cls, patch(TEN_VAULT, return_value=_disabled_vault()):
        repo = repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=server)
        repo.update = AsyncMock()
        with TestClient(app_with_tenant_admin) as client:
            response = client.put(f"{TEN_BASE}/{server.id}", json={"credentials": {"bearer_token": "placeholder"}})
    _assert_refused(response, repo, mock_db_session, "update")
    mock_db_session.rollback.assert_awaited()


def test_create_without_credentials_allowed_when_store_disabled(app_with_cpi_admin, mock_db_session):
    vault = _disabled_vault()
    with patch(EXT_REPO) as repo_cls, patch(EXT_VAULT, return_value=vault):
        repo = repo_cls.return_value
        repo.get_by_name = AsyncMock(return_value=None)
        repo.create = AsyncMock(return_value=external_server())
        body = {k: v for k, v in EXT_CREATE.items() if k != "credentials"} | {"auth_type": "none"}
        with TestClient(app_with_cpi_admin) as client:
            response = client.post(EXT_BASE, json=body)
    assert response.status_code == 201
    vault.store_credential.assert_not_awaited()
