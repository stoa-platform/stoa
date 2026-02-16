"""Tests for UAC Transformer — OpenAPI to UAC Contract conversion."""

import pytest

from src.schemas.uac import UacClassification, UacContractStatus
from src.services.uac_transformer import (
    _compute_spec_hash,
    _extract_endpoints,
    _title_to_name,
    is_blocked_url,
    transform_openapi_to_uac,
)


# ============ Fixtures ============


PETSTORE_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Petstore API",
        "version": "2.1.0",
        "description": "A sample pet store API",
    },
    "servers": [{"url": "https://petstore.example.com/v1"}],
    "paths": {
        "/pets": {
            "get": {
                "operationId": "listPets",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "array", "items": {"type": "object"}}
                            }
                        }
                    }
                },
            },
            "post": {
                "operationId": "createPet",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
                        }
                    }
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            },
        },
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"type": "object"}}}}
                },
            },
            "delete": {
                "operationId": "deletePet",
                "responses": {"204": {}},
            },
        },
    },
}

MINIMAL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "My API", "version": "1.0.0"},
    "paths": {
        "/health": {
            "get": {"responses": {"200": {}}},
        }
    },
}


# ============ SSRF Blocklist ============


class TestSsrfBlocklist:
    def test_blocks_localhost(self) -> None:
        assert is_blocked_url("http://localhost:8080/api") is True

    def test_blocks_loopback(self) -> None:
        assert is_blocked_url("http://127.0.0.1:3000") is True

    def test_blocks_private_10(self) -> None:
        assert is_blocked_url("http://10.0.0.1/internal") is True

    def test_blocks_private_192(self) -> None:
        assert is_blocked_url("http://192.168.1.1/api") is True

    def test_blocks_private_172(self) -> None:
        assert is_blocked_url("http://172.16.0.1/api") is True

    def test_blocks_link_local(self) -> None:
        assert is_blocked_url("http://169.254.169.254/latest") is True

    def test_blocks_zero_addr(self) -> None:
        assert is_blocked_url("http://0.0.0.0:8080") is True  # noqa: S104

    def test_allows_public_ip(self) -> None:
        assert is_blocked_url("http://51.83.45.13:8080/health") is False

    def test_allows_public_hostname(self) -> None:
        assert is_blocked_url("https://petstore.example.com/v1") is False

    def test_blocks_empty_url(self) -> None:
        assert is_blocked_url("") is True

    def test_blocks_no_host(self) -> None:
        assert is_blocked_url("file:///etc/passwd") is True


# ============ Title to Name ============


class TestTitleToName:
    def test_simple_title(self) -> None:
        assert _title_to_name("Payment Service API") == "payment-service-api"

    def test_special_chars(self) -> None:
        assert _title_to_name("My API (v2)") == "my-api-v2"

    def test_empty_title(self) -> None:
        assert _title_to_name("") == "unnamed-api"

    def test_single_char(self) -> None:
        assert _title_to_name("X") == "x-api"

    def test_already_kebab(self) -> None:
        assert _title_to_name("petstore-api") == "petstore-api"


# ============ Endpoint Extraction ============


class TestExtractEndpoints:
    def test_extracts_all_paths(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        assert len(endpoints) == 2

    def test_extracts_methods(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        pets_ep = next(e for e in endpoints if e.path == "/pets")
        assert "GET" in pets_ep.methods
        assert "POST" in pets_ep.methods

    def test_extracts_operation_id(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        pets_ep = next(e for e in endpoints if e.path == "/pets")
        assert pets_ep.operation_id == "listPets"

    def test_builds_backend_url(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        pets_ep = next(e for e in endpoints if e.path == "/pets")
        assert pets_ep.backend_url == "https://backend.example.com/pets"

    def test_extracts_request_schema(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        pets_ep = next(e for e in endpoints if e.path == "/pets")
        assert pets_ep.input_schema is not None
        assert pets_ep.input_schema["type"] == "object"

    def test_extracts_response_schema(self) -> None:
        endpoints = _extract_endpoints(PETSTORE_SPEC, "https://backend.example.com")
        pets_ep = next(e for e in endpoints if e.path == "/pets")
        assert pets_ep.output_schema is not None

    def test_handles_empty_paths(self) -> None:
        spec = {"paths": {}}
        endpoints = _extract_endpoints(spec, "")
        assert endpoints == []


# ============ Spec Hash ============


class TestSpecHash:
    def test_deterministic(self) -> None:
        h1 = _compute_spec_hash(MINIMAL_SPEC)
        h2 = _compute_spec_hash(MINIMAL_SPEC)
        assert h1 == h2

    def test_different_specs_different_hash(self) -> None:
        h1 = _compute_spec_hash(MINIMAL_SPEC)
        h2 = _compute_spec_hash(PETSTORE_SPEC)
        assert h1 != h2

    def test_hash_length(self) -> None:
        h = _compute_spec_hash(MINIMAL_SPEC)
        assert len(h) == 16


# ============ Full Transform ============


class TestTransformOpenapiToUac:
    def test_basic_transform(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC, tenant_id="acme"
        )
        assert contract.name == "petstore-api"
        assert contract.version == "2.1.0"
        assert contract.tenant_id == "acme"
        assert contract.display_name == "Petstore API"
        assert contract.description == "A sample pet store API"
        assert contract.classification == UacClassification.H
        assert contract.status == UacContractStatus.DRAFT
        assert len(contract.endpoints) == 2

    def test_auto_populates_policies(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC, tenant_id="acme", classification=UacClassification.VH
        )
        assert "rate-limit" in contract.required_policies
        assert "mtls" in contract.required_policies

    def test_uses_server_as_backend(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC, tenant_id="acme"
        )
        pets_ep = next(e for e in contract.endpoints if e.path == "/pets")
        assert pets_ep.backend_url == "https://petstore.example.com/v1/pets"

    def test_overrides_backend_url(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC,
            tenant_id="acme",
            backend_base_url="https://internal.acme.com",
        )
        pets_ep = next(e for e in contract.endpoints if e.path == "/pets")
        assert pets_ep.backend_url == "https://internal.acme.com/pets"

    def test_records_source_url(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC,
            tenant_id="acme",
            source_spec_url="https://example.com/petstore.json",
        )
        assert contract.source_spec_url == "https://example.com/petstore.json"

    def test_computes_spec_hash(self) -> None:
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        assert contract.spec_hash is not None
        assert len(contract.spec_hash) == 16

    def test_missing_title_raises(self) -> None:
        spec = {"openapi": "3.0.0", "info": {}, "paths": {}}
        with pytest.raises(ValueError, match="missing info.title"):
            transform_openapi_to_uac(spec, tenant_id="acme")

    def test_no_servers_empty_backend(self) -> None:
        contract = transform_openapi_to_uac(
            MINIMAL_SPEC, tenant_id="acme"
        )
        ep = contract.endpoints[0]
        assert ep.backend_url == "/health"

    def test_validate_for_publish(self) -> None:
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        errors = contract.validate_for_publish()
        assert errors == []

    def test_vvh_classification(self) -> None:
        contract = transform_openapi_to_uac(
            PETSTORE_SPEC,
            tenant_id="acme",
            classification=UacClassification.VVH,
        )
        assert "data-encryption" in contract.required_policies
        assert "geo-restriction" in contract.required_policies
