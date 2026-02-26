"""Tests for UAC Transformer — OpenAPI ↔ UAC bidirectional conversion."""

import pytest

from src.schemas.uac import UacClassification, UacContractSpec, UacContractStatus, UacEndpointSpec
from src.services.uac_transformer import (
    _compute_spec_hash,
    _extract_base_url,
    _extract_endpoints,
    _title_to_name,
    is_blocked_url,
    transform_openapi_to_uac,
    transform_uac_to_openapi,
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
                    "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}
                },
            },
            "post": {
                "operationId": "createPet",
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"type": "object", "properties": {"name": {"type": "string"}}}}
                    }
                },
                "responses": {"201": {"content": {"application/json": {"schema": {"type": "object"}}}}},
            },
        },
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
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
        assert is_blocked_url("http://0.0.0.0:8080") is True

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
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        assert contract.name == "petstore-api"
        assert contract.version == "2.1.0"
        assert contract.tenant_id == "acme"
        assert contract.display_name == "Petstore API"
        assert contract.description == "A sample pet store API"
        assert contract.classification == UacClassification.H
        assert contract.status == UacContractStatus.DRAFT
        assert len(contract.endpoints) == 2

    def test_auto_populates_policies(self) -> None:
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme", classification=UacClassification.VH)
        assert "rate-limit" in contract.required_policies
        assert "mtls" in contract.required_policies

    def test_uses_server_as_backend(self) -> None:
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
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
        with pytest.raises(ValueError, match=r"missing info\.title"):
            transform_openapi_to_uac(spec, tenant_id="acme")

    def test_no_servers_empty_backend(self) -> None:
        contract = transform_openapi_to_uac(MINIMAL_SPEC, tenant_id="acme")
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


# ============ Base URL Extraction ============


class TestExtractBaseUrl:
    def test_strips_path_suffix(self) -> None:
        assert _extract_base_url("https://api.example.com/v1/pets", "/pets") == "https://api.example.com/v1"

    def test_nested_path(self) -> None:
        assert _extract_base_url("https://api.example.com/v1/users/{id}", "/users/{id}") == "https://api.example.com/v1"

    def test_no_path_match(self) -> None:
        assert _extract_base_url("https://api.example.com/v1/other", "/pets") == "https://api.example.com/v1/other"

    def test_empty_backend(self) -> None:
        assert _extract_base_url("", "/pets") == ""

    def test_path_only(self) -> None:
        assert _extract_base_url("/health", "/health") == ""

    def test_root_path(self) -> None:
        assert _extract_base_url("https://api.example.com/", "/") == "https://api.example.com"


# ============ UAC → OpenAPI Transform ============


class TestTransformUacToOpenapi:
    def _make_contract(self, **overrides: object) -> UacContractSpec:
        base = {
            "name": "petstore-api",
            "version": "2.1.0",
            "tenant_id": "acme",
            "display_name": "Petstore API",
            "description": "A sample pet store API",
            "classification": "H",
            "endpoints": [
                UacEndpointSpec(
                    path="/pets",
                    methods=["GET", "POST"],
                    backend_url="https://petstore.example.com/v1/pets",
                    operation_id="listPets",
                    input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                    output_schema={"type": "array", "items": {"type": "object"}},
                ),
                UacEndpointSpec(
                    path="/pets/{petId}",
                    methods=["GET", "DELETE"],
                    backend_url="https://petstore.example.com/v1/pets/{petId}",
                    operation_id="getPet",
                    output_schema={"type": "object"},
                ),
            ],
            "required_policies": ["rate-limit", "auth-jwt"],
            "status": "draft",
        }
        base.update(overrides)
        return UacContractSpec(**base)

    def test_basic_structure(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert spec["openapi"] == "3.1.0"
        assert spec["info"]["title"] == "Petstore API"
        assert spec["info"]["version"] == "2.1.0"

    def test_description_included(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert spec["info"]["description"] == "A sample pet store API"

    def test_description_omitted_when_none(self) -> None:
        contract = self._make_contract(description=None)
        spec = transform_uac_to_openapi(contract)
        assert "description" not in spec["info"]

    def test_display_name_used_as_title(self) -> None:
        contract = self._make_contract(display_name="My Pretty API")
        spec = transform_uac_to_openapi(contract)
        assert spec["info"]["title"] == "My Pretty API"

    def test_falls_back_to_name_for_title(self) -> None:
        contract = self._make_contract(display_name=None)
        spec = transform_uac_to_openapi(contract)
        assert spec["info"]["title"] == "petstore-api"

    def test_servers_extracted(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert len(spec["servers"]) == 1
        assert spec["servers"][0]["url"] == "https://petstore.example.com/v1"

    def test_paths_generated(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert "/pets" in spec["paths"]
        assert "/pets/{petId}" in spec["paths"]

    def test_methods_mapped(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert "get" in spec["paths"]["/pets"]
        assert "post" in spec["paths"]["/pets"]
        assert "get" in spec["paths"]["/pets/{petId}"]
        assert "delete" in spec["paths"]["/pets/{petId}"]

    def test_operation_id_preserved(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        assert spec["paths"]["/pets"]["get"]["operationId"] == "listPets"

    def test_request_body_on_post(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        post_op = spec["paths"]["/pets"]["post"]
        assert "requestBody" in post_op
        schema = post_op["requestBody"]["content"]["application/json"]["schema"]
        assert schema["type"] == "object"

    def test_no_request_body_on_get(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        get_op = spec["paths"]["/pets"]["get"]
        assert "requestBody" not in get_op

    def test_response_schema_on_get(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        get_op = spec["paths"]["/pets"]["get"]
        assert "200" in get_op["responses"]
        schema = get_op["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["type"] == "array"

    def test_delete_returns_204(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract)
        delete_op = spec["paths"]["/pets/{petId}"]["delete"]
        assert "204" in delete_op["responses"]

    def test_custom_openapi_version(self) -> None:
        contract = self._make_contract()
        spec = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        assert spec["openapi"] == "3.0.3"

    def test_empty_endpoints(self) -> None:
        contract = self._make_contract(endpoints=[])
        spec = transform_uac_to_openapi(contract)
        assert "paths" not in spec or spec.get("paths") == {}

    def test_no_servers_when_path_only_backends(self) -> None:
        contract = self._make_contract(
            endpoints=[
                UacEndpointSpec(
                    path="/health",
                    methods=["GET"],
                    backend_url="/health",
                ),
            ]
        )
        spec = transform_uac_to_openapi(contract)
        assert "servers" not in spec or spec.get("servers") == []


# ============ Round-Trip Fidelity ============


class TestRoundTrip:
    """OpenAPI → UAC → OpenAPI should preserve essential structure."""

    def test_petstore_round_trip_paths(self) -> None:
        """Round trip preserves all paths."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        assert set(result["paths"].keys()) == set(PETSTORE_SPEC["paths"].keys())

    def test_petstore_round_trip_methods(self) -> None:
        """Round trip preserves methods per path."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        for path, path_item in PETSTORE_SPEC["paths"].items():
            original_methods = {
                m for m in path_item if m in ("get", "post", "put", "patch", "delete", "head", "options")
            }
            result_methods = set(result["paths"][path].keys())
            assert original_methods == result_methods, f"Method mismatch on {path}"

    def test_petstore_round_trip_info(self) -> None:
        """Round trip preserves title, version, description."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        assert result["info"]["title"] == PETSTORE_SPEC["info"]["title"]
        assert result["info"]["version"] == PETSTORE_SPEC["info"]["version"]
        assert result["info"]["description"] == PETSTORE_SPEC["info"]["description"]

    def test_petstore_round_trip_server(self) -> None:
        """Round trip preserves server URL."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        assert result["servers"][0]["url"] == PETSTORE_SPEC["servers"][0]["url"]

    def test_petstore_round_trip_operation_ids(self) -> None:
        """Round trip preserves operationIds."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        # listPets is the first operationId in /pets
        assert result["paths"]["/pets"]["get"]["operationId"] == "listPets"

    def test_petstore_round_trip_request_schema(self) -> None:
        """Round trip preserves request body schema."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        post_schema = result["paths"]["/pets"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        original_schema = PETSTORE_SPEC["paths"]["/pets"]["post"]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        assert post_schema == original_schema

    def test_petstore_round_trip_response_schema(self) -> None:
        """Round trip preserves response schema on GET /pets."""
        contract = transform_openapi_to_uac(PETSTORE_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.3")
        result_schema = result["paths"]["/pets"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        original_schema = PETSTORE_SPEC["paths"]["/pets"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert result_schema == original_schema

    def test_minimal_spec_round_trip(self) -> None:
        """Minimal spec round-trips with preserved paths and info."""
        contract = transform_openapi_to_uac(MINIMAL_SPEC, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.0.0")
        assert result["info"]["title"] == MINIMAL_SPEC["info"]["title"]
        assert result["info"]["version"] == MINIMAL_SPEC["info"]["version"]
        assert "/health" in result["paths"]
        assert "get" in result["paths"]["/health"]

    def test_complex_spec_round_trip(self) -> None:
        """Complex spec with multiple paths and schemas round-trips."""
        complex_spec = {
            "openapi": "3.1.0",
            "info": {
                "title": "User Management API",
                "version": "3.0.0",
                "description": "Manage users and roles",
            },
            "servers": [{"url": "https://users.example.com/api"}],
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {"type": "object"},
                                        }
                                    }
                                }
                            }
                        },
                    },
                    "post": {
                        "operationId": "createUser",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "email": {"type": "string", "format": "email"},
                                        },
                                        "required": ["name", "email"],
                                    }
                                }
                            }
                        },
                        "responses": {"201": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                    },
                },
                "/users/{userId}": {
                    "get": {
                        "operationId": "getUser",
                        "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                    },
                    "put": {
                        "operationId": "updateUser",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                        },
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                    },
                    "delete": {
                        "operationId": "deleteUser",
                        "responses": {"204": {}},
                    },
                },
            },
        }
        contract = transform_openapi_to_uac(complex_spec, tenant_id="acme")
        result = transform_uac_to_openapi(contract, openapi_version="3.1.0")

        # Paths preserved
        assert set(result["paths"].keys()) == {"/users", "/users/{userId}"}

        # Methods preserved
        assert set(result["paths"]["/users"].keys()) == {"get", "post"}
        assert set(result["paths"]["/users/{userId}"].keys()) == {"get", "put", "delete"}

        # Server preserved
        assert result["servers"][0]["url"] == "https://users.example.com/api"

        # Request body schema preserved on POST
        post_schema = result["paths"]["/users"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert "email" in post_schema["properties"]
        assert post_schema["required"] == ["name", "email"]

        # PUT has request body
        assert "requestBody" in result["paths"]["/users/{userId}"]["put"]

        # DELETE has 204
        assert "204" in result["paths"]["/users/{userId}"]["delete"]["responses"]
