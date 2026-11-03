import json
import logging
import traceback
from collections.abc import Iterator
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import hvac
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection

from src.services.credential_resolver import create_adapter_with_credentials, resolve_gateway_auth_config
from src.services.vault_client import VaultClient

MARKER = "cab-2282-synthetic-sensitive-value"
VAULT_PATH = "gateways/cab-2282"


class VaultTransport:
    def __init__(self) -> None:
        self.failure: tuple[str, str] | None = None
        self.paths: list[str] = []

    def connect(self, connection: HTTPSConnection) -> None:
        connection.sock = MagicMock()
        connection.is_verified = True
        connection.sock.sendall.side_effect = lambda data: self.paths.append(data.split()[1].decode())
        connection.sock.makefile.side_effect = self.respond

    def respond(self, *args: Any) -> BytesIO:
        path = self.paths[-1]
        stage = {"/v1/auth/token/lookup-self": "auth", "/v1/sys/health": "health"}.get(path, "read")
        status = 200
        data = {"data": {"data": {"api_key": MARKER}}} if stage == "read" else {"sealed": False}
        if self.failure and stage == self.failure[0]:
            if self.failure[1] == "timeout":
                raise TimeoutError(MARKER)
            status = 503 if self.failure[1] == "error" else 404
            data = {"errors": [MARKER]}
        body = json.dumps(data).encode()
        return BytesIO(
            f"HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nConnection: close\r\n"
            f"Content-Length: {len(body)}\r\n\r\n".encode() + body
        )


@pytest.fixture
def vault_boundary(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> Iterator[VaultTransport]:
    transport = VaultTransport()
    monkeypatch.setattr(HTTPSConnection, "connect", lambda conn: transport.connect(conn))
    session = requests.Session()
    session.trust_env = False
    session.mount("https://", HTTPAdapter(max_retries=1))
    real_client = hvac.Client
    monkeypatch.setattr(hvac, "Client", lambda **kwargs: real_client(session=session, **kwargs))
    vault = VaultClient("https://vault.example.invalid", vault_token=MARKER)
    monkeypatch.setattr("src.services.credential_resolver.get_vault_client", lambda: vault)
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="urllib3")
    yield transport
    assert all(value not in repr([r.__dict__ for r in caplog.get_records("call")]) for value in (MARKER, VAULT_PATH))
    transport.failure = None
    session.get("https://vault.example.invalid/transport-probe")
    assert "/transport-probe" in caplog.text  # Real HTTP logging remains enabled outside Vault requests.


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
    with patch("src.services.credential_resolver.AdapterRegistry.create") as create:
        adapter = await create_adapter_with_credentials("kong", "https://gateway.example.invalid", auth)
    assert adapter is create.return_value
    assert create.call_args.kwargs["config"]["auth_config"] == {"api_key": MARKER, "type": "api_key"}
    vault_boundary.failure = ("read", "timeout")
    with pytest.raises(ValueError, match="operation refused"):
        await resolve_gateway_auth_config(auth)
    assert vault_boundary.paths.count(f"/v1/secret/data/{VAULT_PATH}") == 3  # Fresh read plus one retry.
