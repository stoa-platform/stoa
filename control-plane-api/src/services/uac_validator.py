"""
UAC Validator — JSON Schema-based validation for UAC contracts.

Validates UAC contract documents against the formal v1.0 JSON Schema
and applies additional semantic rules (classification↔policy consistency,
endpoint uniqueness, naming conventions).
"""

import json
import logging
from pathlib import Path

from jsonschema import Draft202012Validator

from src.schemas.uac import CLASSIFICATION_POLICIES, UacClassification

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "uac_contract_v1_schema.json"
_SCHEMA: dict | None = None


def _load_schema() -> dict:
    """Load and cache the UAC v1.0 JSON Schema."""
    global _SCHEMA
    if _SCHEMA is None:
        with open(_SCHEMA_PATH) as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


class UacValidationResult:
    """Result of UAC contract validation."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __repr__(self) -> str:
        return f"UacValidationResult(valid={self.valid}, errors={len(self.errors)}, warnings={len(self.warnings)})"


def validate_uac_contract(document: dict) -> UacValidationResult:
    """Validate a UAC contract document against the v1.0 specification.

    Performs two-pass validation:
      1. JSON Schema structural validation (types, required fields, patterns)
      2. Semantic validation (classification↔policy, endpoint uniqueness, naming)

    Args:
        document: UAC contract as a Python dict.

    Returns:
        UacValidationResult with errors and warnings.
    """
    result = UacValidationResult()

    # Pass 1: JSON Schema validation
    schema = _load_schema()
    validator = Draft202012Validator(schema)

    for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        result.add_error(f"schema: {path}: {error.message}")

    # Pass 2: Semantic validation (only if schema is valid enough)
    if not result.errors:
        _validate_semantics(document, result)

    return result


def validate_uac_contract_strict(document: dict) -> list[str]:
    """Strict validation — returns a flat list of error strings.

    Convenience wrapper for use in services and routers.
    """
    result = validate_uac_contract(document)
    return result.errors


def _validate_semantics(document: dict, result: UacValidationResult) -> None:
    """Semantic validation beyond JSON Schema structural checks."""
    _check_classification_policy_consistency(document, result)
    _check_endpoint_uniqueness(document, result)
    _check_naming_conventions(document, result)
    _check_published_readiness(document, result)


def _check_classification_policy_consistency(document: dict, result: UacValidationResult) -> None:
    """Verify required_policies matches the classification level."""
    classification_str = document.get("classification", "H")
    try:
        classification = UacClassification(classification_str)
    except ValueError:
        return  # Already caught by schema validation

    expected = set(CLASSIFICATION_POLICIES.get(classification, []))
    actual = set(document.get("required_policies", []))

    missing = expected - actual
    if missing:
        result.add_warning(
            f"classification '{classification_str}' requires policies {sorted(missing)} "
            f"but they are not in required_policies"
        )

    extra = actual - expected
    if extra:
        # Extra policies are fine — it's stricter than required
        pass


def _check_endpoint_uniqueness(document: dict, result: UacValidationResult) -> None:
    """Check for duplicate path+methods combinations."""
    seen: dict[str, set[str]] = {}
    for i, ep in enumerate(document.get("endpoints", [])):
        path = ep.get("path", "")
        methods = ep.get("methods", [])
        if path in seen:
            overlap = seen[path] & set(methods)
            if overlap:
                result.add_error(f"endpoints[{i}]: duplicate method(s) {sorted(overlap)} " f"for path '{path}'")
            seen[path].update(methods)
        else:
            seen[path] = set(methods)


def _check_naming_conventions(document: dict, result: UacValidationResult) -> None:
    """Check operation_id naming conventions."""
    for i, ep in enumerate(document.get("endpoints", [])):
        op_id = ep.get("operation_id")
        if op_id and not op_id.replace("_", "").replace("-", "").isalnum():
            result.add_warning(
                f"endpoints[{i}].operation_id '{op_id}' contains " f"non-alphanumeric characters beyond _ and -"
            )


def _check_published_readiness(document: dict, result: UacValidationResult) -> None:
    """Additional checks for published contracts."""
    if document.get("status") != "published":
        return

    # Published contracts should have a version
    version = document.get("version", "")
    if version == "0.0.0":
        result.add_warning("published contract has placeholder version 0.0.0")

    # Published contracts should have a description
    if not document.get("description"):
        result.add_warning("published contract has no description")

    # Published contracts should have a display_name
    if not document.get("display_name"):
        result.add_warning("published contract has no display_name")
