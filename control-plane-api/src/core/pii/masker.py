"""PIIMasker — Service principal. Target: < 5ms pour 10KB."""
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Any
from functools import lru_cache

from .patterns import PIIPatterns, PIIType
from .config import PIIMaskingConfig, MaskingLevel, FieldMaskingMode

logger = logging.getLogger(__name__)


@dataclass
class MaskingContext:
    tenant_id: str | None = None
    user_id: str | None = None
    user_roles: set[str] = field(default_factory=set)
    request_id: str | None = None
    source: str = "unknown"

    def is_exempt(self, config: PIIMaskingConfig) -> bool:
        if config.level == MaskingLevel.STRICT:
            return False
        return bool(self.user_roles & config.exempt_roles)


@dataclass
class MaskingResult:
    original_length: int
    masked_length: int
    pii_found: dict[PIIType, int]

    @property
    def total_pii_count(self) -> int:
        return sum(self.pii_found.values())


class PIIMasker:
    def __init__(self, config: PIIMaskingConfig | None = None):
        self.config = config or PIIMaskingConfig.default_production()
        self._patterns = PIIPatterns.get_enabled(self.config.disabled_types)

    def mask(self, text: str, context: MaskingContext | None = None) -> str:
        if not self.config.enabled:
            return text
        ctx = context or MaskingContext()
        if ctx.is_exempt(self.config):
            return text

        if len(text) > self.config.max_text_length:
            text = text[:self.config.max_text_length]

        pii_found: dict[PIIType, int] = {}
        for pattern in self._patterns:
            matches = list(pattern.pattern.finditer(text))
            if matches:
                pii_found[pattern.pii_type] = len(matches)
                mask_func = self._get_mask_func(pattern)
                text = pattern.pattern.sub(lambda m: mask_func(m.group(0)), text)

        if self.config.audit_enabled and pii_found:
            logger.info("PII masked", extra={
                "tenant": ctx.tenant_id,
                "pii": {t.value: c for t, c in pii_found.items()},
            })

        return text

    def mask_dict(self, data: dict[str, Any], context: MaskingContext | None = None, recursive: bool = True) -> dict[str, Any]:
        if not self.config.enabled:
            return data
        return self._mask_recursive(data, context, recursive)

    def _mask_recursive(self, data: Any, ctx: MaskingContext | None, rec: bool) -> Any:
        if isinstance(data, str):
            return self.mask(data, ctx)
        elif isinstance(data, dict):
            return {k: self._mask_recursive(v, ctx, rec) if rec else v for k, v in data.items()}
        elif isinstance(data, list):
            return [self._mask_recursive(i, ctx, rec) if rec else i for i in data]
        return data

    def _get_mask_func(self, pattern):
        override = self.config.field_overrides.get(pattern.pii_type)
        if override == FieldMaskingMode.FULL:
            return PIIPatterns.mask_full
        elif override == FieldMaskingMode.HASH:
            return lambda v: f"[HASH:{hashlib.sha256(v.encode()).hexdigest()[:8]}]"
        elif override == FieldMaskingMode.NONE:
            return lambda v: v
        return pattern.mask_func

    def detect_only(self, text: str) -> dict[PIIType, list[str]]:
        """Retourne valeurs en clair - debug only."""
        return {p.pii_type: p.pattern.findall(text) for p in self._patterns if p.pattern.findall(text)}

    @classmethod
    @lru_cache(maxsize=128)
    def for_tenant(cls, tenant_id: str) -> "PIIMasker":
        # TODO: Load from UAC
        return cls()


_default_masker: PIIMasker | None = None


def get_masker() -> PIIMasker:
    global _default_masker
    if _default_masker is None:
        _default_masker = PIIMasker()
    return _default_masker


def mask_pii(text: str, context: MaskingContext | None = None) -> str:
    return get_masker().mask(text, context)
