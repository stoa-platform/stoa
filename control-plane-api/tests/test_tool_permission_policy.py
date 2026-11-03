"""Bounds for the tool-permission policy payload (CAB-2222 S1)."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.config import Settings, settings
from src.schemas.tool_permission_policy import ToolPermissionPolicy, ToolPermissionPolicyEntry

ISSUED_AT = datetime(2026, 11, 3, tzinfo=UTC)


def entry(index: int = 0, **changes: object) -> dict:
    return {"mcp_server": "server-a", "tool": f"tool-{index}", "allowed": True, **changes}


def payload(**changes: object) -> dict:
    return {
        "tenant_id": "tenant-a",
        "version": 1,
        "issued_at": ISSUED_AT,
        "expires_at": ISSUED_AT + timedelta(seconds=900),
        "permissions": [entry()],
        **changes,
    }


def test_entry_count_boundary() -> None:
    entries = [entry(i) for i in range(5000)]
    policy = ToolPermissionPolicy.model_validate(payload(permissions=entries))
    assert len(policy.permissions) == 5000
    assert len(ToolPermissionPolicy.model_validate_json(policy.model_dump_json()).permissions) == 5000
    with pytest.raises(ValidationError):
        ToolPermissionPolicy.model_validate(payload(permissions=[*entries, entry(5000)]))


def test_serialized_size_boundary() -> None:
    data = payload()
    size = len(ToolPermissionPolicy.model_validate(data).model_dump_json().encode("utf-8"))
    data["tenant_id"] += "x" * (1024 * 1024 - size)
    policy = ToolPermissionPolicy.model_validate(data)
    assert len(policy.model_dump_json().encode("utf-8")) == 1024 * 1024
    data["tenant_id"] += "x"
    with pytest.raises(ValidationError, match="1 MiB"):
        ToolPermissionPolicy.model_validate(data)


def test_serialized_size_counts_utf8_bytes() -> None:
    with pytest.raises(ValidationError, match="1 MiB"):
        ToolPermissionPolicy.model_validate(payload(permissions=[entry(tool="é" * (600 * 1024))]))


@pytest.mark.parametrize("allowed", [True, False])
def test_duplicate_identity_rejected(allowed: bool) -> None:
    with pytest.raises(ValidationError, match="Duplicate"):
        ToolPermissionPolicy.model_validate(payload(permissions=[entry(), entry(allowed=allowed)]))


def test_same_tool_on_different_servers_accepted() -> None:
    policy = ToolPermissionPolicy.model_validate(payload(permissions=[entry(), entry(mcp_server="server-b")]))
    assert len(policy.permissions) == 2


@pytest.mark.parametrize("field", ["tool", "mcp_server", "allowed"])
def test_missing_entry_field_rejected(field: str) -> None:
    incomplete = entry()
    del incomplete[field]
    with pytest.raises(ValidationError):
        ToolPermissionPolicy.model_validate(payload(permissions=[incomplete]))


@pytest.mark.parametrize("field", ["tool", "mcp_server"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_invalid_entry_identity_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ToolPermissionPolicy.model_validate(payload(permissions=[entry(**{field: value})]))


@pytest.mark.parametrize("tenant_id", [None, "", "   ", "\t\n", "\u00a0\u2003"])
@pytest.mark.parametrize("as_json", [False, True], ids=["model", "json"])
def test_regression_invalid_tenant_identity_rejected(tenant_id: str | None, as_json: bool) -> None:
    data = payload(tenant_id=tenant_id)
    with pytest.raises(ValidationError, match="tenant_id"):
        if as_json:
            ToolPermissionPolicy.model_validate_json(json.dumps(data, default=str))
        else:
            ToolPermissionPolicy.model_validate(data)


@pytest.mark.parametrize("as_json", [False, True], ids=["model", "json"])
def test_missing_tenant_identity_rejected(as_json: bool) -> None:
    data = payload()
    del data["tenant_id"]
    with pytest.raises(ValidationError, match="tenant_id"):
        if as_json:
            ToolPermissionPolicy.model_validate_json(json.dumps(data, default=str))
        else:
            ToolPermissionPolicy.model_validate(data)


@pytest.mark.parametrize("seconds", [0, -1, 3601])
def test_invalid_validity_window_rejected(seconds: int) -> None:
    with pytest.raises(ValidationError, match="validity"):
        ToolPermissionPolicy.model_validate(payload(expires_at=ISSUED_AT + timedelta(seconds=seconds)))


@pytest.mark.parametrize("seconds", [1, 900, 3600])
def test_validity_window_accepted(seconds: int) -> None:
    policy = ToolPermissionPolicy.model_validate(payload(expires_at=ISSUED_AT + timedelta(seconds=seconds)))
    assert (policy.expires_at - policy.issued_at).total_seconds() == seconds


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
@pytest.mark.parametrize("value", ["invalid", ISSUED_AT.replace(tzinfo=None)])
def test_invalid_timestamp_rejected(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ToolPermissionPolicy.model_validate(payload(**{field: value}))


@pytest.mark.parametrize("seconds", [0, -1, 901, 3600, 3601])
def test_invalid_configured_duration_rejected(seconds: int) -> None:
    with pytest.raises(ValidationError):
        Settings(TOOL_PERMISSION_POLICY_TTL_SECONDS=seconds)


def test_default_duration_and_configurable_issuance(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings.model_fields["TOOL_PERMISSION_POLICY_TTL_SECONDS"].default == 900
    for seconds in (900, 300, 1):
        monkeypatch.setattr(settings, "TOOL_PERMISSION_POLICY_TTL_SECONDS", seconds)
        policy = ToolPermissionPolicy.issue(
            tenant_id="tenant-a", version=1, permissions=[ToolPermissionPolicyEntry(**entry())], issued_at=ISSUED_AT
        )
        assert (policy.expires_at - policy.issued_at).total_seconds() == seconds


def test_validity_uses_elapsed_seconds_across_clock_change(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 11, 1, 1, 55, tzinfo=ZoneInfo("America/New_York"))
    with pytest.raises(ValidationError, match="validity"):
        ToolPermissionPolicy.model_validate(payload(issued_at=start, expires_at=start + timedelta(seconds=900)))
    monkeypatch.setattr(settings, "TOOL_PERMISSION_POLICY_TTL_SECONDS", 900)
    policy = ToolPermissionPolicy.issue(tenant_id="tenant-a", version=1, permissions=[], issued_at=start)
    assert (policy.expires_at.astimezone(UTC) - start.astimezone(UTC)).total_seconds() == 900
