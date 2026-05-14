"""Vault transit wrapping for audit pseudonymization keys.

Implements ADR-069 §4.2 and the operator decision recorded in
docs/decisions/2026-05-13-cab-2225-2229-operator-approvals.md §CAB-2226.

The encrypt path is mandatory before PR #2781 may exit DRAFT. Raw storage of
`pseudonymization_key` is not an accepted final state.
"""

import base64
import os

import hvac
from hvac.exceptions import VaultError

from src.config import settings


class VaultPseudoWrapError(RuntimeError):
    """Raised when Vault transit wrapping for audit pseudonymization fails."""


def _authenticated_vault_client() -> hvac.Client:
    """Create an authenticated Vault client using kubeauth first, token auth for dev."""
    if not settings.VAULT_ENABLED:
        raise VaultPseudoWrapError("Vault is disabled; refusing to store raw pseudonymization key")

    client = hvac.Client(url=settings.VAULT_ADDR)

    jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if settings.VAULT_KUBERNETES_ROLE and os.path.exists(jwt_path):
        try:
            with open(jwt_path) as f:
                jwt_token = f.read()
            client.auth.kubernetes.login(role=settings.VAULT_KUBERNETES_ROLE, jwt=jwt_token)
        except Exception as exc:
            raise VaultPseudoWrapError("Vault Kubernetes authentication failed") from exc

    if not client.is_authenticated() and settings.VAULT_TOKEN:
        client.token = settings.VAULT_TOKEN

    if not client.is_authenticated():
        raise VaultPseudoWrapError("Vault authentication failed")

    return client


async def wrap_pseudonymization_key(raw_key: bytes) -> bytes:
    """Envelope-encrypt the raw key via Vault transit engine.

    Returns ciphertext bytes (Vault format: `vault:v1:<base64>`), ready for
    storage in `pseudonymized_audit_erasures.pseudonymization_key`.

    The plaintext `raw_key` never leaves this function unencrypted. Vault
    unavailability MUST raise — we never persist raw bytes (operator policy
    2026-05-13).
    """
    try:
        client = _authenticated_vault_client()
        plaintext = base64.b64encode(raw_key).decode("ascii")
        response = client.secrets.transit.encrypt_data(
            name=settings.AUDIT_PSEUDO_VAULT_KEY_NAME,
            plaintext=plaintext,
        )
        ciphertext = response["data"]["ciphertext"]
        if not isinstance(ciphertext, str):
            raise TypeError("Vault transit ciphertext must be a string")
        return ciphertext.encode("utf-8")
    except VaultPseudoWrapError:
        raise
    except (KeyError, TypeError, VaultError) as exc:
        raise VaultPseudoWrapError("Vault transit encryption failed") from exc
    except Exception as exc:
        raise VaultPseudoWrapError("Unexpected Vault transit encryption failure") from exc


async def unwrap_pseudonymization_key(ciphertext: bytes) -> bytes:
    """Decrypt via Vault transit engine.

    Dual-control gate is enforced at the Vault POLICY layer (two-operator
    unwrap policy on the transit key), not in this function. Callers of unwrap
    MUST be the re-identification workflow only, and MUST emit audit events per
    ADR-068 (separate future ticket).
    """
    try:
        client = _authenticated_vault_client()
        response = client.secrets.transit.decrypt_data(
            name=settings.AUDIT_PSEUDO_VAULT_KEY_NAME,
            ciphertext=ciphertext.decode("utf-8"),
        )
        plaintext = response["data"]["plaintext"]
        if not isinstance(plaintext, str):
            raise TypeError("Vault transit plaintext must be a string")
        return base64.b64decode(plaintext)
    except VaultPseudoWrapError:
        raise
    except (KeyError, TypeError, ValueError, VaultError) as exc:
        raise VaultPseudoWrapError("Vault transit decryption failed") from exc
    except Exception as exc:
        raise VaultPseudoWrapError("Unexpected Vault transit decryption failure") from exc
