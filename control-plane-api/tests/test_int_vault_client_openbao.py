"""Live Vault API compatibility tests for VaultClient (CAB-1795, ADR-075).

STOA reaches its secrets backend through the Vault HTTP API and ships OpenBao
as the reference backend. These tests run the control plane's hvac client
against a real server: OpenBao in CI (job ``openbao-compat`` in
.github/workflows/control-plane-api-ci.yml). Nothing here is OpenBao-specific,
so a HashiCorp Vault dev server works too.

Covered: token auth, the seal check, KV v2 write/read/delete on the paths the
code uses (external-mcp-servers/, mcp-connector-templates/, gateway
vault_path reads) and the transit wrap of audit pseudonymization keys.

The module is skipped unless VAULT_IT_ADDR is set, so the unit-test job is
unaffected. It reads its own variables rather than VAULT_ADDR, so an exported
address of a real server never turns these writes on. Use a throwaway dev
server only: the tests write and delete random secrets and mount transit/ when
it is missing.

    VAULT_IT_ADDR=http://localhost:18200 VAULT_IT_TOKEN=<dev root token> \\
        pytest tests/test_int_vault_client_openbao.py -v
"""

import logging
import os
import secrets
import uuid

import hvac
import pytest
import requests
from hvac.exceptions import InvalidPath, VaultError

from src.config import settings
from src.services.audit_pseudo_vault import unwrap_pseudonymization_key, wrap_pseudonymization_key
from src.services.connector_oauth import ConnectorOAuthService
from src.services.credential_resolver import resolve_gateway_auth_config
from src.services.vault_client import VaultClient, VaultUnavailableError

VAULT_IT_ADDR = os.environ.get("VAULT_IT_ADDR", "")
MOUNT = "secret"  # settings.VAULT_MOUNT_POINT default

pytestmark = pytest.mark.skipif(
    not VAULT_IT_ADDR, reason="VAULT_IT_ADDR not set: no OpenBao/Vault server for the live VaultClient tests"
)


@pytest.fixture
def token() -> str:
    value = os.environ.get("VAULT_IT_TOKEN", "")
    if not value:
        pytest.fail("VAULT_IT_ADDR is set but VAULT_IT_TOKEN is empty")
    return value


@pytest.fixture
def vault(token: str) -> VaultClient:
    """The client under test, built as get_vault_client() builds it for token auth."""
    return VaultClient(vault_addr=VAULT_IT_ADDR, vault_token=token, mount_point=MOUNT)


@pytest.fixture
def admin(token: str) -> hvac.Client:
    """Plain hvac client for setup, checks and cleanup outside the code under test."""
    return hvac.Client(url=VAULT_IT_ADDR, token=token)


@pytest.fixture
def name() -> str:
    return f"cab-1795-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def written(admin: hvac.Client):
    """KV paths a test writes; every version and the metadata are removed afterwards."""
    paths: list[str] = []
    yield paths
    for path in paths:
        admin.secrets.kv.v2.delete_metadata_and_all_versions(path=path, mount_point=MOUNT)


def test_token_auth_and_seal_check(vault: VaultClient) -> None:
    assert vault._get_client().is_authenticated()
    vault._ensure_unsealed()  # raises when the server is sealed or unreachable
    assert vault.health_check() is True
    assert vault.is_available is True


async def test_invalid_token_fails_closed(name: str) -> None:
    vault = VaultClient(vault_addr=VAULT_IT_ADDR, vault_token=f"invalid-{name}", mount_point=MOUNT)
    with pytest.raises(VaultError, match="Failed to authenticate"):
        vault._get_client()
    assert vault.health_check() is False
    with pytest.raises(VaultUnavailableError):
        await vault.store_credential(name, {"api_key": "never-written"})


async def test_external_mcp_server_credentials_write_read_delete(
    vault: VaultClient, admin: hvac.Client, written: list[str], name: str
) -> None:
    path = f"external-mcp-servers/{name}"
    written.append(path)
    credentials = {"client_id": "it-client", "client_secret": "it-secret-v1", "auth_type": "oauth2_client_credentials"}

    assert await vault.store_credential(name, credentials) == f"{MOUNT}/data/{path}"
    assert await vault.retrieve_credential(name) == credentials

    # An update writes a new KV v2 version; the client reads the latest one.
    await vault.store_credential(name, {**credentials, "client_secret": "it-secret-v2"})
    assert await vault.retrieve_credential(name) == {**credentials, "client_secret": "it-secret-v2"}
    assert admin.secrets.kv.v2.read_secret_metadata(path=path, mount_point=MOUNT)["data"]["current_version"] == 2

    assert await vault.delete_credential(name) is True
    assert await vault.retrieve_credential(name) is None
    with pytest.raises(InvalidPath):  # every version and the metadata are gone
        admin.secrets.kv.v2.read_secret_metadata(path=path, mount_point=MOUNT)


async def test_gateway_vault_path_resolution(
    vault: VaultClient, admin: hvac.Client, written: list[str], name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = f"gateways/{name}"
    written.append(path)
    admin.secrets.kv.v2.create_or_update_secret(path=path, secret={"api_key": "it-gateway-key"}, mount_point=MOUNT)

    assert await vault.read_secret(path) == {"api_key": "it-gateway-key"}
    assert await vault.read_secret(f"{path}-missing") is None

    monkeypatch.setattr("src.services.credential_resolver.get_vault_client", lambda: vault)
    resolved = await resolve_gateway_auth_config({"type": "api_key", "vault_path": path})
    assert resolved == {"type": "api_key", "api_key": "it-gateway-key"}


def test_connector_template_credentials(
    vault: VaultClient, written: list[str], name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The write mirrors routers/mcp_connectors.py; the read is services/connector_oauth.py.
    path = f"mcp-connector-templates/{name}"
    written.append(path)
    provider = {"client_id": "it-app", "client_secret": "it-app-secret"}
    vault._ensure_unsealed()
    vault._get_client().secrets.kv.v2.create_or_update_secret(path=path, secret=provider, mount_point=vault.mount_point)

    monkeypatch.setattr("src.services.connector_oauth.get_vault_client", lambda: vault)
    assert ConnectorOAuthService._get_vault_provider_credentials(name) == provider


async def test_audit_pseudonymization_key_transit_roundtrip(
    admin: hvac.Client, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "transit/" not in admin.sys.list_mounted_secrets_engines()["data"]:
        admin.sys.enable_secrets_engine(backend_type="transit", path="transit")
    admin.secrets.transit.create_key(name=settings.AUDIT_PSEUDO_VAULT_KEY_NAME)  # no-op when it exists
    monkeypatch.setattr(settings, "VAULT_ENABLED", True)
    monkeypatch.setattr(settings, "VAULT_ADDR", VAULT_IT_ADDR)
    monkeypatch.setattr(settings, "VAULT_TOKEN", token)

    raw_key = secrets.token_bytes(32)
    wrapped = await wrap_pseudonymization_key(raw_key)
    assert wrapped.startswith(b"vault:v1:")
    assert await unwrap_pseudonymization_key(wrapped) == raw_key


async def test_transport_logs_carry_no_path_or_value(
    vault: VaultClient, written: list[str], name: str, caplog: pytest.LogCaptureFixture
) -> None:
    """CAB-2282 on a real transport: no urllib3 record carries the secret path or value."""
    written.append(f"external-mcp-servers/{name}")
    caplog.set_level(logging.DEBUG, logger="urllib3")

    await vault.store_credential(name, {"api_key": "it-transport-marker"})
    assert await vault.retrieve_credential(name) == {"api_key": "it-transport-marker"}

    transport = repr([record.__dict__ for record in caplog.records if record.name.startswith("urllib3")])
    assert name not in transport
    assert "it-transport-marker" not in transport
    requests.get(f"{VAULT_IT_ADDR}/v1/sys/health", timeout=5)  # positive control: transport logging is on
    assert "/v1/sys/health" in caplog.text
