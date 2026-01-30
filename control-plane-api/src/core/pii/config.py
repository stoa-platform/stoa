"""Configuration PII Masking par tenant."""
from enum import Enum
from pydantic import BaseModel, Field
from .patterns import PIIType


class MaskingLevel(str, Enum):
    STRICT = "strict"
    MODERATE = "moderate"
    MINIMAL = "minimal"
    DISABLED = "disabled"


class FieldMaskingMode(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    HASH = "hash"
    NONE = "none"


class PIIMaskingConfig(BaseModel):
    enabled: bool = True
    level: MaskingLevel = MaskingLevel.MODERATE
    field_overrides: dict[PIIType, FieldMaskingMode] = Field(default_factory=dict)
    disabled_types: set[PIIType] = Field(default_factory=set)
    exempt_roles: set[str] = Field(default_factory=lambda: {"platform_admin", "security_officer"})
    audit_enabled: bool = True
    max_text_length: int = 100_000

    @classmethod
    def strict(cls) -> "PIIMaskingConfig":
        return cls(level=MaskingLevel.STRICT, exempt_roles=set())

    @classmethod
    def development(cls) -> "PIIMaskingConfig":
        return cls(enabled=False, level=MaskingLevel.DISABLED)

    @classmethod
    def default_production(cls) -> "PIIMaskingConfig":
        return cls(exempt_roles={"platform_admin"})
