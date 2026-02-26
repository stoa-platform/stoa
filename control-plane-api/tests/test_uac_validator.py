"""Tests for UAC v1.0 JSON Schema validation and semantic checks."""

import json
from pathlib import Path

import pytest

from src.services.uac_validator import (
    UacValidationResult,
    validate_uac_contract,
    validate_uac_contract_strict,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "uac"
SCHEMA_PATH = Path(__file__).parent.parent / "src" / "schemas" / "uac_contract_v1_schema.json"


def _load_example(name: str) -> dict:
    """Load an example UAC document."""
    with open(EXAMPLES_DIR / name) as f:
        return json.load(f)


def _minimal_contract(**overrides: object) -> dict:
    """Create a minimal valid UAC contract."""
    base = {
        "name": "test-api",
        "version": "1.0.0",
        "tenant_id": "test-tenant",
        "classification": "H",
        "endpoints": [
            {
                "path": "/health",
                "methods": ["GET"],
                "backend_url": "https://backend.example.com/health",
            }
        ],
        "required_policies": ["rate-limit", "auth-jwt"],
        "status": "draft",
    }
    base.update(overrides)
    return base


# =============================================================================
# Schema file validity
# =============================================================================


class TestSchemaFile:
    """Verify the JSON Schema file itself is well-formed."""

    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.exists(), f"Schema file not found: {SCHEMA_PATH}"

    def test_schema_file_is_valid_json(self) -> None:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "UAC Contract v1.0" in schema["title"]

    def test_schema_has_required_defs(self) -> None:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        defs = schema.get("$defs", {})
        assert "Classification" in defs
        assert "Status" in defs
        assert "Endpoint" in defs
        assert "LlmConfig" in defs


# =============================================================================
# Example documents validation (Phase 1 acceptance: 5+ examples validate)
# =============================================================================


class TestExampleDocuments:
    """All example UAC documents must validate without errors."""

    @pytest.mark.parametrize(
        "filename",
        [
            "01-rest-api.json",
            "02-graphql-api.json",
            "03-grpc-service.json",
            "04-websocket-api.json",
            "05-mcp-tool.json",
            "06-llm-contract.json",
        ],
    )
    def test_example_validates(self, filename: str) -> None:
        doc = _load_example(filename)
        result = validate_uac_contract(doc)
        assert result.valid, f"{filename}: {result.errors}"

    def test_all_examples_load(self) -> None:
        """Verify examples directory has at least 5 files."""
        examples = list(EXAMPLES_DIR.glob("*.json"))
        assert len(examples) >= 5, f"Expected >=5 examples, found {len(examples)}"


# =============================================================================
# Structural validation (JSON Schema pass)
# =============================================================================


class TestStructuralValidation:
    """JSON Schema structural validation."""

    def test_valid_minimal_contract(self) -> None:
        result = validate_uac_contract(_minimal_contract())
        assert result.valid, result.errors

    def test_missing_name(self) -> None:
        doc = _minimal_contract()
        del doc["name"]
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("name" in e for e in result.errors)

    def test_missing_version(self) -> None:
        doc = _minimal_contract()
        del doc["version"]
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("version" in e for e in result.errors)

    def test_missing_tenant_id(self) -> None:
        doc = _minimal_contract()
        del doc["tenant_id"]
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("tenant_id" in e for e in result.errors)

    def test_invalid_name_pattern(self) -> None:
        result = validate_uac_contract(_minimal_contract(name="INVALID_NAME"))
        assert not result.valid
        assert any("name" in e and "does not match" in e for e in result.errors)

    def test_invalid_version_format(self) -> None:
        result = validate_uac_contract(_minimal_contract(version="v1"))
        assert not result.valid
        assert any("version" in e for e in result.errors)

    def test_invalid_classification(self) -> None:
        result = validate_uac_contract(_minimal_contract(classification="EXTREME"))
        assert not result.valid
        assert any("classification" in e for e in result.errors)

    def test_invalid_status(self) -> None:
        result = validate_uac_contract(_minimal_contract(status="active"))
        assert not result.valid
        assert any("status" in e for e in result.errors)

    def test_endpoint_missing_path(self) -> None:
        doc = _minimal_contract(endpoints=[{"methods": ["GET"], "backend_url": "https://x.com"}])
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("path" in e for e in result.errors)

    def test_endpoint_empty_methods(self) -> None:
        doc = _minimal_contract(endpoints=[{"path": "/test", "methods": [], "backend_url": "https://x.com"}])
        result = validate_uac_contract(doc)
        assert not result.valid

    def test_endpoint_invalid_method(self) -> None:
        doc = _minimal_contract(endpoints=[{"path": "/test", "methods": ["FOOBAR"], "backend_url": "https://x.com"}])
        result = validate_uac_contract(doc)
        assert not result.valid

    def test_additional_properties_rejected(self) -> None:
        doc = _minimal_contract(unknown_field="surprise")
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("additional" in e.lower() for e in result.errors)

    def test_published_requires_endpoints_or_llm(self) -> None:
        doc = _minimal_contract(status="published", endpoints=[])
        result = validate_uac_contract(doc)
        assert not result.valid

    def test_draft_allows_empty_endpoints(self) -> None:
        doc = _minimal_contract(status="draft", endpoints=[])
        result = validate_uac_contract(doc)
        assert result.valid

    def test_published_with_llm_config_no_endpoints(self) -> None:
        doc = _minimal_contract(
            status="published",
            endpoints=[],
            llm_config={
                "capabilities": [
                    {
                        "capability": "chat",
                        "providers": [
                            {
                                "name": "anthropic",
                                "model": "claude-sonnet-4-5-20250929",
                                "backend_url": "https://api.anthropic.com/v1",
                                "priority": 1,
                            }
                        ],
                    }
                ],
            },
        )
        result = validate_uac_contract(doc)
        assert result.valid, result.errors


# =============================================================================
# Semantic validation
# =============================================================================


class TestSemanticValidation:
    """Semantic validation beyond JSON Schema."""

    def test_classification_policy_mismatch_warning(self) -> None:
        doc = _minimal_contract(
            classification="VVH",
            required_policies=["rate-limit"],  # Missing many
        )
        result = validate_uac_contract(doc)
        assert result.valid  # Warnings don't fail validation
        assert len(result.warnings) > 0
        assert any("classification" in w for w in result.warnings)

    def test_classification_policy_match_no_warning(self) -> None:
        doc = _minimal_contract(
            classification="H",
            required_policies=["rate-limit", "auth-jwt"],
        )
        result = validate_uac_contract(doc)
        assert result.valid
        assert len(result.warnings) == 0

    def test_extra_policies_no_warning(self) -> None:
        """Extra policies (stricter than classification) are fine."""
        doc = _minimal_contract(
            classification="H",
            required_policies=["rate-limit", "auth-jwt", "mtls"],  # Extra
        )
        result = validate_uac_contract(doc)
        assert result.valid
        assert not any("extra" in w.lower() for w in result.warnings)

    def test_duplicate_endpoint_methods(self) -> None:
        doc = _minimal_contract(
            endpoints=[
                {
                    "path": "/users",
                    "methods": ["GET"],
                    "backend_url": "https://x.com/a",
                },
                {
                    "path": "/users",
                    "methods": ["GET", "POST"],
                    "backend_url": "https://x.com/b",
                },
            ]
        )
        result = validate_uac_contract(doc)
        assert not result.valid
        assert any("duplicate" in e.lower() for e in result.errors)

    def test_non_overlapping_methods_same_path(self) -> None:
        """Different methods on the same path should be fine."""
        doc = _minimal_contract(
            endpoints=[
                {
                    "path": "/users",
                    "methods": ["GET"],
                    "backend_url": "https://x.com/a",
                },
                {
                    "path": "/users",
                    "methods": ["POST"],
                    "backend_url": "https://x.com/b",
                },
            ]
        )
        result = validate_uac_contract(doc)
        assert result.valid

    def test_published_without_description_warning(self) -> None:
        doc = _minimal_contract(status="published")
        result = validate_uac_contract(doc)
        assert result.valid  # Warning only
        assert any("description" in w for w in result.warnings)

    def test_published_without_display_name_warning(self) -> None:
        doc = _minimal_contract(status="published")
        result = validate_uac_contract(doc)
        assert any("display_name" in w for w in result.warnings)


# =============================================================================
# Strict wrapper
# =============================================================================


class TestStrictWrapper:
    """Test the flat error list wrapper."""

    def test_strict_returns_empty_for_valid(self) -> None:
        errors = validate_uac_contract_strict(_minimal_contract())
        assert errors == []

    def test_strict_returns_errors(self) -> None:
        doc = _minimal_contract()
        del doc["name"]
        errors = validate_uac_contract_strict(doc)
        assert len(errors) > 0
        assert any("name" in e for e in errors)


# =============================================================================
# Result object
# =============================================================================


class TestValidationResult:
    def test_result_repr(self) -> None:
        r = UacValidationResult()
        assert "valid=True" in repr(r)

    def test_result_with_errors(self) -> None:
        r = UacValidationResult()
        r.add_error("test error")
        assert not r.valid
        assert "valid=False" in repr(r)

    def test_result_with_warnings_still_valid(self) -> None:
        r = UacValidationResult()
        r.add_warning("test warning")
        assert r.valid
        assert r.warnings == ["test warning"]
