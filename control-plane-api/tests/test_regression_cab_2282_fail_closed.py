import json
import traceback
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import requests
from urllib3.connection import HTTPSConnection

from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.subscription import ProvisioningStatus
from src.services.credential_resolver import create_adapter_with_credentials, resolve_gateway_auth_config
from src.services.provisioning_service import provision_on_approval
from src.services.vault_client import VaultClient

MARKER = "cab-2282-synthetic-sensitive-value"
VAULT_PATH = "gateways/cab-2282"


@pytest.fixture
def vault_boundary(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    boundary = SimpleNamespace(failure=None, paths=[])  # Fake socket under urllib3: real transport logs, no network.

    def respond(*_: object) -> BytesIO:
        path = boundary.paths[-1].split("?")[0]
        stage = {"/v1/auth/token/lookup-self": "auth", "/v1/sys/health": "health", "/probe": "probe"}.get(path, "read")
        status, data = 200, {"data": {"data": {"api_key": MARKER}}} if stage == "read" else {"sealed": False}
        if boundary.failure and stage == boundary.failure[0]:
            if boundary.failure[1] == "timeout":
                raise TimeoutError(MARKER)
            status, data = 503 if boundary.failure[1] == "error" else 404, {"errors": [MARKER]}
        body = json.dumps(data).encode()
        return BytesIO(f"HTTP/1.0 {status}\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)

    def connect(connection: HTTPSConnection) -> None:
        connection.sock, connection.is_verified = MagicMock(), True
        connection.sock.sendall.side_effect = lambda data: boundary.paths.append(data.split()[1].decode())
        connection.sock.makefile.side_effect = respond

    monkeypatch.setattr(HTTPSConnection, "connect", connect)
    vault = VaultClient("https://vault.example.invalid", vault_token=MARKER)
    monkeypatch.setattr("src.services.credential_resolver.get_vault_client", lambda: vault)
    caplog.set_level("DEBUG", logger="urllib3")  # The supported transport DEBUG override from logging_config.
    yield boundary
    # Whatever the Vault outcome (success, 503, 404, timeout), no transport record may carry the value or reference.
    assert all(v not in repr([r.__dict__ for r in caplog.get_records("call")]) for v in (MARKER, VAULT_PATH))
    requests.get("https://vault.example.invalid/probe", timeout=1)  # Positive control: logging stays active elsewhere.
    assert "/probe" in caplog.text


@pytest.mark.parametrize("stage", ["auth", "health", "read"])
@pytest.mark.parametrize("failure", ["error", "timeout", "missing"])
async def test_regression_cab_2282_outage_refuses_adapter(vault_boundary, stage: str, failure: str) -> None:
    vault_boundary.failure = (stage, failure)
    auth = {"vault_path": VAULT_PATH, "api_key": MARKER, "type": "api_key"}
    with patch("src.services.credential_resolver.AdapterRegistry.create") as create:
        with pytest.raises(ValueError, match="operation refused") as error:
            await create_adapter_with_credentials("kong", "https://gateway.example.invalid", auth)
        create.assert_not_called()
    assert all(value not in "".join(traceback.format_exception(error.value)) for value in (MARKER, VAULT_PATH))
    assert vault_boundary.paths and (stage == "read" or not any("/secret/data/" in p for p in vault_boundary.paths))


async def test_regression_cab_2282_available_then_outage_never_uses_cache(vault_boundary) -> None:
    auth = {"vault_path": VAULT_PATH, "api_key": "old-direct-value", "type": "api_key"}
    assert await resolve_gateway_auth_config(auth) == {"api_key": MARKER, "type": "api_key"}
    vault_boundary.failure = ("read", "timeout")
    with pytest.raises(ValueError, match="operation refused"):
        await resolve_gateway_auth_config(auth)
    assert vault_boundary.paths.count(f"/v1/secret/data/{VAULT_PATH}") == 2


@pytest.mark.parametrize("direct", [{}, {"api_key": MARKER}], ids=["reference-only", "hybrid"])
async def test_regression_cab_2282_provisioning_failed(vault_boundary, direct: dict[str, str]) -> None:
    db = AsyncMock()
    sub = SimpleNamespace(id=uuid4(), api_id="test-api", tenant_id="test-tenant", provisioned_at=object())
    gateway = GatewayInstance(
        id=uuid4(),
        name="test-gateway",
        gateway_type=GatewayType.KONG,
        source="manual",
        base_url="https://gateway.example.invalid",
        auth_config={"vault_path": VAULT_PATH, **direct},
    )
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.side_effect = [SimpleNamespace(gateway_instance_id=gateway.id), gateway]
    statuses = []
    db.commit.side_effect = lambda: statuses.append(sub.provisioning_status)
    vault_boundary.failure = ("read", "timeout")
    with patch("src.services.credential_resolver.AdapterRegistry.create") as create:
        await provision_on_approval(db, sub, None, "test-correlation")
        create.assert_not_called()
    assert statuses == [ProvisioningStatus.PROVISIONING, ProvisioningStatus.FAILED]
    assert sub.provisioning_error == "Required read failed; no fallback credentials allowed; operation refused."
    assert sub.provisioned_at is None
