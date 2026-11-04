"""Compact policy issuance, using only ephemeral signing keys in tests."""

import base64
import json
import logging
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.config import Settings, settings
from src.services.policy_artifact_signer import _b64url, sign_policy_artifact

KID = "cp-policy-202611-1"


def decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


@pytest.fixture
def signing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ed25519.Ed25519PrivateKey:
    key = ed25519.Ed25519PrivateKey.generate()
    path = tmp_path / "ephemeral-key"
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KEY_FILE", str(path))
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KID", KID)
    return key


def test_rfc8037_appendix_a_public_vector() -> None:
    # https://www.rfc-editor.org/rfc/rfc8037.html#appendix-A.4
    # A.4/A.5 wire bytes and public key only; the published private seed is never loaded.
    signing_input = _b64url(b'{"alg":"EdDSA"}') + b"." + _b64url(b"Example of Ed25519 signing")
    assert signing_input == b"eyJhbGciOiJFZERTQSJ9.RXhhbXBsZSBvZiBFZDI1NTE5IHNpZ25pbmc"
    signature = decode("hgyY0il_MGCjP0JzlnLWG1PPOt7-09PGcvMg3AIbQR6dWbhijcNR4ki4iylGjg5BhVsPt9g7sVvpAr_MuM0KAg")
    public = ed25519.Ed25519PublicKey.from_public_bytes(decode("11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"))
    public.verify(signature, signing_input)
    with pytest.raises(InvalidSignature):
        public.verify(signature, signing_input + b"!")


def test_issuance_signs_exact_bytes(signing_key: ed25519.Ed25519PrivateKey, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    payload = {"tenant_id": "tenant-é", "alg": "none", "issued_at": 1, "expires_at": 901}
    artifact = sign_policy_artifact(payload)
    header, body, signature = artifact.split(".")
    assert json.loads(decode(header)) == {"alg": "EdDSA", "typ": "stoa-tool-policy+jws", "kid": KID}
    assert json.loads(decode(body)) == payload
    assert "=" not in artifact
    signing_key.public_key().verify(decode(signature), f"{header}.{body}".encode("ascii"))
    pem = Path(settings.STOA_POLICY_SIGNING_KEY_FILE).read_text()
    assert all(line not in caplog.text for line in pem.splitlines())


@pytest.mark.parametrize("alg", ["none", "HS256", "RS256", "ES256"])
def test_alternate_algorithm_is_not_an_option(signing_key: ed25519.Ed25519PrivateKey, alg: str) -> None:
    with pytest.raises(TypeError):
        sign_policy_artifact({}, alg=alg)


@pytest.mark.parametrize("kid", ["", "cp-policy-202613-1", "cp-policy-202611-0", "other", "cp-policy-202611-1\n"])
def test_invalid_kid_refuses_issuance(
    signing_key: ed25519.Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch, kid: str
) -> None:
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KID", kid)
    with pytest.raises(HTTPException) as error:
        sign_policy_artifact({})
    assert error.value.status_code == 503
    assert error.value.detail == {"code": "policy_signing_unavailable"}


@pytest.mark.parametrize("mode", ["unset", "missing", "directory", "malformed", "public_only", "encrypted"])
def test_unavailable_key_returns_path_free_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, mode: str
) -> None:
    caplog.set_level(logging.DEBUG)
    path = tmp_path / "private-mount-location"
    content = b"-----BEGIN PRIVATE KEY-----\ninvalid PEM material\n-----END PRIVATE KEY-----\n"
    if mode == "directory":
        path.mkdir()
    elif mode in ("malformed", "public_only", "encrypted"):
        if mode != "malformed":
            key = ed25519.Ed25519PrivateKey.generate()
            if mode == "public_only":
                content = key.public_key().public_bytes(
                    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
                )
            else:
                content = key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.BestAvailableEncryption(b"test-only"),
                )
        path.write_bytes(content)
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KEY_FILE", "" if mode == "unset" else str(path))
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KID", KID)
    app = FastAPI()

    @app.get("/test-issuance")
    def issue() -> dict[str, str]:
        return {"artifact": sign_policy_artifact({})}

    with TestClient(app) as client:
        response = client.get("/test-issuance")
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "policy_signing_unavailable"}}
    assert str(path) not in response.text + caplog.text
    assert all(line not in response.text + caplog.text for line in content.decode().splitlines())


@pytest.mark.parametrize("kid", [KID, "cp-policy-202611-10"])
def test_compact_artifact_size_boundary(
    signing_key: ed25519.Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch, kid: str
) -> None:
    monkeypatch.setattr(settings, "STOA_POLICY_SIGNING_KID", kid)
    payload = {"value": ""}
    header, _, signature = sign_policy_artifact(payload).split(".")
    max_payload_bytes = (1024 * 1024 - len(header) - len(signature) - 2) * 3 // 4
    payload["value"] = "x" * (max_payload_bytes - len(json.dumps(payload, separators=(",", ":"))))
    artifact = sign_policy_artifact(payload)
    size = len(artifact.encode("ascii"))
    assert 1024 * 1024 - 1 <= size <= 1024 * 1024
    payload["value"] += "x"
    assert len(json.dumps(payload).encode()) < 1024 * 1024
    with pytest.raises(HTTPException) as error:
        sign_policy_artifact(payload)
    assert error.value.status_code == 413
    assert error.value.detail == {"code": "policy_artifact_too_large"}


@pytest.mark.parametrize("seconds", [901, 3600, 3601])
def test_startup_rejects_ttl_above_deployed_cap(seconds: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOOL_PERMISSION_POLICY_TTL_SECONDS", str(seconds))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("seconds", [1, 900])
def test_startup_accepts_ttl_within_cap(seconds: int) -> None:
    assert seconds == Settings(TOOL_PERMISSION_POLICY_TTL_SECONDS=seconds).TOOL_PERMISSION_POLICY_TTL_SECONDS
