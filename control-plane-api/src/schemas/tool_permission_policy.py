"""Validated payload for a signed tool-permission policy (CAB-2222 S1)."""

from datetime import UTC, datetime, timedelta
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config import settings

MAX_POLICY_ENTRIES = 5000
MAX_POLICY_BYTES = 1024 * 1024
MAX_POLICY_VALIDITY_SECONDS = 3600


class ToolPermissionPolicyEntry(BaseModel):
    """An explicit decision for one server/tool pair."""

    model_config = ConfigDict(extra="forbid")

    mcp_server: str = Field(min_length=1, strict=True)
    tool: str = Field(min_length=1, strict=True)
    allowed: bool = Field(strict=True)

    @field_validator("mcp_server", "tool")
    @classmethod
    def require_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy entry identities must not be blank")
        return value


class ToolPermissionPolicy(BaseModel):
    """Complete policy payload; signing and publication are separate concerns."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, strict=True)
    version: int = Field(ge=1, strict=True)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    permissions: list[ToolPermissionPolicyEntry] = Field(max_length=MAX_POLICY_ENTRIES)

    @field_validator("tenant_id")
    @classmethod
    def require_tenant_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Policy tenant identity must not be blank")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        validity = (self.expires_at.astimezone(UTC) - self.issued_at.astimezone(UTC)).total_seconds()
        if not 0 < validity <= MAX_POLICY_VALIDITY_SECONDS:
            raise ValueError("Policy validity must be positive and at most 3600 seconds")
        identities = {(entry.mcp_server, entry.tool) for entry in self.permissions}
        if len(identities) != len(self.permissions):
            raise ValueError("Duplicate policy entries are not allowed")
        if len(self.model_dump_json().encode("utf-8")) > MAX_POLICY_BYTES:
            raise ValueError("Serialized policy must not exceed 1 MiB")
        return self

    @classmethod
    def issue(
        cls,
        *,
        tenant_id: str,
        version: int,
        permissions: list[ToolPermissionPolicyEntry],
        issued_at: datetime,
    ) -> Self:
        """Build a payload using the configured CP validity duration."""
        return cls(
            tenant_id=tenant_id,
            version=version,
            permissions=permissions,
            issued_at=issued_at,
            expires_at=issued_at.astimezone(UTC) + timedelta(seconds=settings.TOOL_PERMISSION_POLICY_TTL_SECONDS),
        )
