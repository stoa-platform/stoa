import json
import traceback
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import hvac
import pytest
import requests
from requests.adapters import BaseAdapter

from src.models.gateway_instance import GatewayInstance, GatewayType
from src.models.subscription import ProvisioningStatus
from src.services.credential_resolver import create_adapter_with_credentials, resolve_gateway_auth_config
from src.services.provisioning_service import provision_on_approval
from src.services.vault_client import VaultClient

MARKER = "cab-2282-synthetic-sensitive-value"
VAULT_PATH = "gateways/cab-2282"


class VaultTransport(BaseAdapter):
    def __init__(self) -> None:
        self.failure: tuple[str, str] | None = None
        self.paths: list[str] = []

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:
        path = request.path_url
        self.paths.append(path)
        stage = {"/v1/auth/token/lookup-self": "auth", "/v1/sys/health": "health"}.get(path, "read")
        response = requests.Response()
        response.status_code = 200
        data = {"data": {"data": {"api_key": MARKER}}} if stage == "read" else {"sealed": False}
        if self.failure and stage == self.failure[0]:
            if self.failure[1] == "timeout":
                raise requests.Timeout(MARKER)
            response.status_code = 503 if self.failure[1] == "error" else 404
            data = {"errors": [MARKER]}
        response._content = json.dumps(data).encode()
        return response

    def close(self) -> None:
        pass


@pytest.fixture
def vault_boundary(monkeypatch: pytest.MonkeyPatch) -> VaultTransport:
    transport = VaultTransport()
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", transport)
    real_client = hvac.Client
    monkeypatch.setattr(hvac, "Client", lambda **kwargs: real_client(session=session, **kwargs))
    vault = VaultClient("https://vault.example.invalid", vault_token=MARKER)
    monkeypatch.setattr("src.services.credential_resolver.get_vault_client", lambda: vault)
    return transport


@pytest.mark.parametrize("stage", ["auth", "health", "read"])
@pytest.mark.parametrize("failure", ["error", "timeout", "missing"])
async def test_regression_cab_2282_outage_refuses_adapter(
    vault_boundary: VaultTransport, stage: str, failure: str
) -> None:
    vault_boundary.failure = (stage, failure)
    auth = {"vault_path": VAULT_PATH, "api_key": MARKER, "type": "api_key"}
    with patch("src.services.credential_resolver.AdapterRegistry.create") as create:
        with pytest.raises(ValueError, match="operation refused") as error:
            await create_adapter_with_credentials("kong", "https://gateway.example.invalid", auth)
        create.assert_not_called()
    assert all(value not in "".join(traceback.format_exception(error.value)) for value in (MARKER, VAULT_PATH))
    assert vault_boundary.paths
    if stage in {"auth", "health"}:
        assert not any("/secret/data/" in path for path in vault_boundary.paths)


async def test_regression_cab_2282_available_then_outage_never_uses_cache(vault_boundary: VaultTransport) -> None:
    auth = {"vault_path": VAULT_PATH, "api_key": "old-direct-value", "type": "api_key"}
    assert await resolve_gateway_auth_config(auth) == {"api_key": MARKER, "type": "api_key"}
    vault_boundary.failure = ("read", "timeout")
    with pytest.raises(ValueError, match="operation refused"):
        await resolve_gateway_auth_config(auth)
    assert vault_boundary.paths.count(f"/v1/secret/data/{VAULT_PATH}") == 2


@pytest.mark.parametrize("direct", [{}, {"api_key": MARKER}], ids=["reference-only", "hybrid"])
async def test_regression_cab_2282_provisioning_failed(vault_boundary: VaultTransport, direct: dict[str, str]) -> None:
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
