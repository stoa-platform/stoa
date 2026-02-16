"""Tests for UAC v1 Pydantic schema models."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas.uac import (
    CLASSIFICATION_POLICIES,
    UacClassification,
    UacContractSpec,
    UacContractStatus,
    UacEndpointSpec,
)

# =============================================================================
# Fixtures
# =============================================================================


def _sample_endpoint() -> dict:
    return {
        "path": "/payments/{id}",
        "methods": ["GET", "POST"],
        "backend_url": "https://backend.acme.com/v1/payments",
        "operation_id": "get_payment",
    }


def _sample_contract() -> dict:
    return {
        "name": "payment-service",
        "version": "1.0.0",
        "tenant_id": "acme",
        "display_name": "Payment Service",
        "description": "Process payments",
        "classification": "H",
        "endpoints": [_sample_endpoint()],
        "status": "draft",
    }


# =============================================================================
# Endpoint Tests
# =============================================================================


class TestUacEndpointSpec:
    def test_valid_endpoint(self):
        ep = UacEndpointSpec(**_sample_endpoint())
        assert ep.path == "/payments/{id}"
        assert ep.methods == ["GET", "POST"]
        assert ep.backend_url == "https://backend.acme.com/v1/payments"
        assert ep.operation_id == "get_payment"

    def test_optional_fields_none(self):
        ep = UacEndpointSpec(
            path="/health",
            methods=["GET"],
            backend_url="https://api.example.com/health",
        )
        assert ep.operation_id is None
        assert ep.input_schema is None
        assert ep.output_schema is None


# =============================================================================
# Contract Tests
# =============================================================================


class TestUacContractSpec:
    def test_valid_contract(self):
        spec = UacContractSpec(**_sample_contract())
        assert spec.name == "payment-service"
        assert spec.tenant_id == "acme"
        assert spec.classification == UacClassification.H
        assert spec.status == UacContractStatus.DRAFT

    def test_defaults(self):
        spec = UacContractSpec(name="test-api", tenant_id="t1")
        assert spec.version == "1.0.0"
        assert spec.classification == UacClassification.H
        assert spec.status == UacContractStatus.DRAFT
        assert spec.endpoints == []
        assert spec.required_policies == []

    def test_refresh_policies_h(self):
        spec = UacContractSpec(name="test-api", tenant_id="t1")
        spec.refresh_policies()
        assert "rate-limit" in spec.required_policies
        assert "auth-jwt" in spec.required_policies
        assert len(spec.required_policies) == 2

    def test_refresh_policies_vvh(self):
        spec = UacContractSpec(
            name="critical-api",
            tenant_id="t1",
            classification=UacClassification.VVH,
        )
        spec.refresh_policies()
        assert "rate-limit" in spec.required_policies
        assert "auth-jwt" in spec.required_policies
        assert "mtls" in spec.required_policies
        assert "audit-logging" in spec.required_policies
        assert "data-encryption" in spec.required_policies
        assert "geo-restriction" in spec.required_policies
        assert len(spec.required_policies) == 6

    def test_validate_for_publish_no_endpoints(self):
        spec = UacContractSpec(name="test-api", tenant_id="t1")
        errors = spec.validate_for_publish()
        assert any("at least one endpoint" in e for e in errors)

    def test_validate_for_publish_valid(self):
        spec = UacContractSpec(**_sample_contract())
        errors = spec.validate_for_publish()
        assert errors == []

    def test_name_validation_kebab(self):
        with pytest.raises(ValidationError):
            UacContractSpec(name="Invalid Name!", tenant_id="t1")

    def test_version_validation_semver(self):
        with pytest.raises(ValidationError):
            UacContractSpec(name="test-api", tenant_id="t1", version="not-semver")

    def test_serde_roundtrip(self):
        data = _sample_contract()
        spec = UacContractSpec(**data)
        json_str = spec.model_dump_json()
        roundtrip = UacContractSpec.model_validate_json(json_str)
        assert roundtrip.name == spec.name
        assert roundtrip.tenant_id == spec.tenant_id
        assert roundtrip.classification == spec.classification
        assert len(roundtrip.endpoints) == len(spec.endpoints)


# =============================================================================
# Cross-Language Parity (JSON Schema)
# =============================================================================


class TestJsonSchemaParity:
    """Verify Python models match the JSON Schema source of truth."""

    @pytest.fixture
    def json_schema(self) -> dict:
        schema_path = (
            Path(__file__).parent.parent.parent
            / "stoa-gateway"
            / "uac-contract-v1.schema.json"
        )
        if not schema_path.exists():
            pytest.skip("JSON Schema file not found (cross-repo test)")
        return json.loads(schema_path.read_text())

    def test_classification_enum_parity(self, json_schema: dict):
        json_values = set(json_schema["$defs"]["Classification"]["enum"])
        python_values = {c.value for c in UacClassification}
        assert json_values == python_values

    def test_status_enum_parity(self, json_schema: dict):
        json_values = set(json_schema["$defs"]["ContractStatus"]["enum"])
        python_values = {s.value for s in UacContractStatus}
        assert json_values == python_values

    def test_required_fields_parity(self, json_schema: dict):
        json_required = set(json_schema["required"])
        expected = {"name", "version", "tenant_id", "classification", "endpoints", "status"}
        assert json_required == expected


# =============================================================================
# Classification Policies
# =============================================================================


class TestClassificationPolicies:
    def test_h_policies(self):
        policies = CLASSIFICATION_POLICIES[UacClassification.H]
        assert set(policies) == {"rate-limit", "auth-jwt"}

    def test_vh_policies_superset_of_h(self):
        h = set(CLASSIFICATION_POLICIES[UacClassification.H])
        vh = set(CLASSIFICATION_POLICIES[UacClassification.VH])
        assert h.issubset(vh)

    def test_vvh_policies_superset_of_vh(self):
        vh = set(CLASSIFICATION_POLICIES[UacClassification.VH])
        vvh = set(CLASSIFICATION_POLICIES[UacClassification.VVH])
        assert vh.issubset(vvh)
