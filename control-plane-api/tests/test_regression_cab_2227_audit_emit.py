import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from src.config import settings
from src.database import get_db
from src.main import app
from src.models.audit_event import AuditEvent

PATH = "/v1/internal/audit/emit"
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _payload(tenant_id: str | None = None) -> dict[str, object]:
    return {
        "source": "stoa-gateway",
        "event_type": "TOOL_CALL_DECISION",
        "decision": "deny",
        "reason": "approval_required",
        "tenant_id": tenant_id or str(uuid4()),
        "actor_id": str(uuid4()),
        "session_id": "sess-1",
        "resource_type": "mcp_tool",
        "resource_id": "customer_get_customer",
        "tool_call_id": str(uuid4()),
        "approval_id": None,
        "policy_version": "v2026-05-18",
        "correlation_id": str(uuid4()),
        "occurred_at": datetime(2026, 5, 18, 10, 0, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "details": {"side_effects": "read"},
    }


def _body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _headers(body: bytes, key: str = "idem-1", timestamp: int | None = None, bad: bool = False) -> dict[str, str]:
    ts = int(time.time()) if timestamp is None else timestamp
    signing_string = f"{ts}\nPOST\n{PATH}\n{hashlib.sha256(body).hexdigest()}"
    secret = settings.INTERNAL_AUDIT_HMAC_SECRET.get_secret_value().encode()
    signature = hmac.new(secret, signing_string.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"HMAC-SHA256 {'0' * 64 if bad else signature}",
        "X-Timestamp": str(ts),
        "Idempotency-Key": key,
        "Content-Type": "application/json",
    }


async def _post(client: AsyncClient, payload: dict[str, object], **header_kwargs: object):
    body = _body(payload)
    return await client.post(PATH, content=body, headers=_headers(body, **header_kwargs))


@pytest.fixture
async def audit_emit_client(integration_db):
    async def override_db():
        yield integration_db

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)


async def test_regression_cab_2227_audit_emit_records_deny_event(audit_emit_client, integration_db) -> None:
    payload = _payload()

    response = await _post(audit_emit_client, payload)

    assert response.status_code == 202
    event = await integration_db.scalar(select(AuditEvent).where(AuditEvent.tenant_id == payload["tenant_id"]))
    assert event is not None
    assert event.action == "tool_call_decision"
    assert event.outcome == "failure"
    assert event.actor_type == "service"


async def test_regression_cab_2227_audit_emit_rejects_bad_hmac(audit_emit_client) -> None:
    response = await _post(audit_emit_client, _payload(), bad=True)

    assert response.status_code == 401


async def test_regression_cab_2227_audit_emit_rejects_stale_timestamp(audit_emit_client) -> None:
    response = await _post(audit_emit_client, _payload(), timestamp=int(time.time()) - 301)

    assert response.status_code == 401


async def test_regression_cab_2227_audit_emit_is_idempotent(audit_emit_client, integration_db) -> None:
    tenant_id = str(uuid4())
    payload = _payload(tenant_id)

    first = await _post(audit_emit_client, payload, key="repeat-key")
    second = await _post(audit_emit_client, payload, key="repeat-key")

    assert first.status_code == 202
    assert second.status_code == 202
    count = await integration_db.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.tenant_id == tenant_id)
    )
    assert count == 1


async def test_regression_cab_2227_audit_emit_validates_payload(audit_emit_client) -> None:
    payload = _payload()
    del payload["reason"]

    response = await _post(audit_emit_client, payload)

    assert response.status_code == 422
