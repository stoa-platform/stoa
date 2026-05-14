# CAB-2226 audit pseudonymization Vault wrapping tests.
# Verifies Vault transit envelope behavior for ADR-069 §4.2.
#
# regression for CAB-2226
from __future__ import annotations

import base64
import os
import secrets
from unittest.mock import MagicMock, patch

import hvac
import pytest

from src.config import settings
from src.services.audit_pseudo_vault import (
    VaultPseudoWrapError,
    unwrap_pseudonymization_key,
    wrap_pseudonymization_key,
)


def _vault_client() -> MagicMock:
    client = MagicMock()
    client.is_authenticated.return_value = True
    client.secrets.transit.encrypt_data.return_value = {"data": {"ciphertext": "vault:v1:abc"}}
    client.secrets.transit.decrypt_data.return_value = {
        "data": {"plaintext": base64.b64encode(b"raw-key").decode("ascii")}
    }
    return client


@pytest.mark.asyncio
async def test_wrap_calls_vault_transit_encrypt_with_correct_key_name() -> None:
    client = _vault_client()
    raw_key = b"raw-key"

    with patch("src.services.audit_pseudo_vault.hvac.Client", return_value=client):
        await wrap_pseudonymization_key(raw_key)

    client.secrets.transit.encrypt_data.assert_called_once_with(
        name="audit-pseudo",
        plaintext=base64.b64encode(raw_key).decode("ascii"),
    )


@pytest.mark.asyncio
async def test_wrap_returns_vault_ciphertext_bytes() -> None:
    client = _vault_client()

    with patch("src.services.audit_pseudo_vault.hvac.Client", return_value=client):
        wrapped = await wrap_pseudonymization_key(b"raw-key")

    assert wrapped == b"vault:v1:abc"


@pytest.mark.asyncio
async def test_wrap_raises_on_vault_unavailable() -> None:
    client = _vault_client()
    client.secrets.transit.encrypt_data.side_effect = hvac.exceptions.VaultError("vault down")
    raw_key = b"raw-key"

    with (
        patch("src.services.audit_pseudo_vault.hvac.Client", return_value=client),
        pytest.raises(VaultPseudoWrapError),
    ):
        await wrap_pseudonymization_key(raw_key)

    client.secrets.transit.encrypt_data.assert_called_once()


@pytest.mark.asyncio
async def test_unwrap_calls_vault_transit_decrypt() -> None:
    client = _vault_client()

    with patch("src.services.audit_pseudo_vault.hvac.Client", return_value=client):
        plaintext = await unwrap_pseudonymization_key(b"vault:v1:abc")

    client.secrets.transit.decrypt_data.assert_called_once_with(
        name="audit-pseudo",
        ciphertext="vault:v1:abc",
    )
    assert plaintext == b"raw-key"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wrap_unwrap_roundtrip_against_real_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    if not (os.environ.get("VAULT_ADDR") and os.environ.get("VAULT_TOKEN")):
        pytest.skip("VAULT_ADDR and VAULT_TOKEN required for Vault transit integration test")

    monkeypatch.setattr(settings, "VAULT_ADDR", os.environ["VAULT_ADDR"])
    monkeypatch.setattr(settings, "VAULT_TOKEN", os.environ["VAULT_TOKEN"])
    monkeypatch.setattr(
        settings,
        "AUDIT_PSEUDO_VAULT_KEY_NAME",
        os.environ.get("AUDIT_PSEUDO_VAULT_KEY_NAME", "audit-pseudo"),
    )

    raw_key = secrets.token_bytes(32)
    wrapped = await wrap_pseudonymization_key(raw_key)
    assert wrapped.startswith(b"vault:v1:")
    assert await unwrap_pseudonymization_key(wrapped) == raw_key
