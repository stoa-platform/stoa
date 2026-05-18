import asyncio
import uuid
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from jose import jwt
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth.dependencies import User, get_current_user
from src.config import settings
from src.database import get_db
from src.services.approval_token_service import ApprovalTokenService
from src.services.approval_token_signer import ApprovalTokenSigner
from src.utils.canonical_json import canonical_hash


def test_canonical_hash_vector() -> None:
    assert (
        canonical_hash({"id": "A", "nested": {"b": 2, "a": 1}})
        == "d19f077a1f0fd7c47cc9563295b1afd5eb3655e6dada92dd9ae9cbaace5c01b7"
    )
    assert canonical_hash(None) == canonical_hash({})


@pytest.fixture
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@pytest.fixture
def signer(private_key_pem: str) -> ApprovalTokenSigner:
    return ApprovalTokenSigner(signing_key=private_key_pem, ttl_seconds=300)


async def _issue(
    db: AsyncSession,
    signer: ApprovalTokenSigner,
    *,
    arguments: dict[str, Any] | None = None,
):
    return await ApprovalTokenService(db, signer).issue(
        tenant_id="acme",
        tool_name="acme:payments:delete-payment",
        tool_call_id=uuid.uuid4(),
        arguments=arguments or {"id": "A"},
        policy_version="policy-v1",
        contract_version="contract-v1",
        requester_actor_id="requester-1",
        approver_actor_id="approver-1",
    )


@pytest.mark.integration
async def test_regression_cab_2227_issue_rejects_self_approval(integration_db: AsyncSession, signer) -> None:
    with pytest.raises(ValueError, match="approver_actor_id must differ"):
        await ApprovalTokenService(integration_db, signer).issue(
            tenant_id="acme",
            tool_name="acme:payments:delete-payment",
            tool_call_id=uuid.uuid4(),
            arguments={"id": "A"},
            policy_version="policy-v1",
            contract_version="contract-v1",
            requester_actor_id="same-actor",
            approver_actor_id="same-actor",
        )


@pytest.mark.integration
async def test_regression_cab_2227_consume_is_single_use(integration_db: AsyncSession, signer) -> None:
    issued = await _issue(integration_db, signer)
    first = await ApprovalTokenService(integration_db).consume(
        jti=issued.jti,
        tenant_id="acme",
        tool_name="acme:payments:delete-payment",
        arguments_hash=canonical_hash({"id": "A"}),
    )
    second = await ApprovalTokenService(integration_db).consume(
        jti=issued.jti,
        tenant_id="acme",
        tool_name="acme:payments:delete-payment",
        arguments_hash=canonical_hash({"id": "A"}),
    )
    assert first.consumed is True
    assert second == type(second)(consumed=False, reason="replay")


@pytest.mark.integration
async def test_regression_cab_2227_consume_rejects_arguments_mismatch(integration_db: AsyncSession, signer) -> None:
    issued = await _issue(integration_db, signer, arguments={"id": "A"})
    result = await ApprovalTokenService(integration_db).consume(
        jti=issued.jti,
        tenant_id="acme",
        tool_name="acme:payments:delete-payment",
        arguments_hash=canonical_hash({"id": "B"}),
    )
    assert result.consumed is False
    assert result.reason == "arguments_mismatch"


@pytest.mark.integration
async def test_regression_cab_2227_consume_rejects_expired(integration_db: AsyncSession, private_key_pem: str) -> None:
    expired_signer = ApprovalTokenSigner(signing_key=private_key_pem, ttl_seconds=-1)
    issued = await _issue(integration_db, expired_signer)
    result = await ApprovalTokenService(integration_db).consume(
        jti=issued.jti,
        tenant_id="acme",
        tool_name="acme:payments:delete-payment",
        arguments_hash=canonical_hash({"id": "A"}),
    )
    assert result.consumed is False
    assert result.reason == "expired"


@pytest.mark.integration
async def test_regression_cab_2227_issued_token_has_all_adr_067_claims(integration_db: AsyncSession, signer) -> None:
    issued = await _issue(integration_db, signer)
    claims = jwt.decode(
        issued.approval_token,
        signer.public_key_pem(),
        algorithms=["RS256"],
        audience="stoa-gateway",
        issuer="control-plane-api",
    )
    assert set(claims) >= {
        "iss",
        "aud",
        "jti",
        "tool_call_id",
        "tenant_id",
        "tool_name",
        "arguments_hash",
        "policy_version",
        "contract_version",
        "requester_actor_id",
        "approver_actor_id",
        "iat",
        "nbf",
        "exp",
    }


@pytest.mark.integration
async def test_regression_cab_2227_consume_requires_gateway_key(app, integration_db: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "gw-test")

    async def override_db():
        yield integration_db

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {
            "jti": str(uuid.uuid4()),
            "tenant_id": "acme",
            "tool_name": "acme:payments:delete-payment",
            "arguments_hash": canonical_hash({"id": "A"}),
        }
        assert (await client.post("/v1/internal/approval-tokens/consume", json=body)).status_code == 401
        assert (
            await client.post(
                "/v1/internal/approval-tokens/consume",
                json=body,
                headers={"X-Gateway-Key": "wrong"},
            )
        ).status_code == 401


@pytest.mark.integration
async def test_regression_cab_2227_issue_endpoint_rejects_self_approval(
    app, integration_db: AsyncSession, private_key_pem: str, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "approval_token_signing_key", SecretStr(private_key_pem))
    user = User(
        id="tenant-admin-user-id",
        email="admin@acme.com",
        username="tenant-admin",
        roles=["tenant-admin"],
        tenant_id="acme",
    )

    async def override_user():
        return user

    async def override_db():
        yield integration_db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/tenants/acme/tool-approvals",
            json={
                "requester_actor_id": user.id,
                "tool_name": "acme:payments:delete-payment",
                "tool_call_id": str(uuid.uuid4()),
                "arguments": {"id": "A"},
                "policy_version": "policy-v1",
                "contract_version": "contract-v1",
            },
        )
    assert response.status_code == 422


@pytest.mark.integration
async def test_regression_cab_2227_consume_atomic_under_race(integration_db: AsyncSession, signer) -> None:
    bind = integration_db.bind
    if bind is None:
        pytest.skip("integration_db has no bind for concurrent sessions")
    factory = async_sessionmaker(bind, class_=AsyncSession, expire_on_commit=False)
    async with factory() as setup_session:
        issued = await _issue(setup_session, signer)
        await setup_session.commit()

    async def consume_once():
        async with factory() as session:
            result = await ApprovalTokenService(session).consume(
                jti=issued.jti,
                tenant_id="acme",
                tool_name="acme:payments:delete-payment",
                arguments_hash=canonical_hash({"id": "A"}),
            )
            await session.commit()
            return result

    results = await asyncio.gather(consume_once(), consume_once())
    assert sorted(result.consumed for result in results) == [False, True]
