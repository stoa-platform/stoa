"""Tests for OpenAPI to MCP Tool converter."""

import pytest
import json

from src.services.openapi_converter import OpenAPIConverter, convert_openapi_to_tools
from src.models import Tool, ToolInputSchema


# =============================================================================
# Sample OpenAPI Specs
# =============================================================================


@pytest.fixture
def petstore_spec() -> dict:
    """Minimal Petstore OpenAPI spec."""
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Petstore API",
            "version": "1.0.0",
            "description": "A sample pet store API",
        },
        "servers": [{"url": "https://petstore.example.com/api/v1"}],
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "List all pets",
                    "description": "Returns all pets in the store",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Maximum number of pets to return",
                            "required": False,
                            "schema": {"type": "integer", "default": 20},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "description": "Filter by status",
                            "schema": {"type": "string", "enum": ["available", "pending", "sold"]},
                        },
                    ],
                },
                "post": {
                    "operationId": "createPet",
                    "summary": "Create a pet",
                    "tags": ["pets"],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "tag": {"type": "string"},
                                    },
                                    "required": ["name"],
                                }
                            }
                        },
                    },
                },
            },
            "/pets/{petId}": {
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "description": "The pet ID",
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "operationId": "getPetById",
                    "summary": "Get a pet by ID",
                    "tags": ["pets"],
                },
                "delete": {
                    "operationId": "deletePet",
                    "summary": "Delete a pet",
                    "tags": ["pets"],
                },
            },
        },
    }


@pytest.fixture
def swagger2_spec() -> dict:
    """Swagger 2.0 spec."""
    return {
        "swagger": "2.0",
        "info": {
            "title": "Legacy API",
            "version": "2.0.0",
        },
        "host": "api.legacy.com",
        "basePath": "/v2",
        "schemes": ["https"],
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "summary": "Get all users",
                    "parameters": [
                        {
                            "name": "page",
                            "in": "query",
                            "type": "integer",
                        }
                    ],
                }
            }
        },
    }


@pytest.fixture
def minimal_spec() -> dict:
    """Minimal valid OpenAPI spec."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "Minimal API", "version": "0.1.0"},
        "paths": {
            "/health": {
                "get": {
                    "summary": "Health check",
                }
            }
        },
    }


# =============================================================================
# Basic Conversion Tests
# =============================================================================


class TestOpenAPIConverterBasic:
    """Basic conversion tests."""

    def test_convert_empty_spec(self):
        """Test converting spec with no paths."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Empty", "version": "1.0.0"},
            "paths": {},
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)
        assert tools == []

    def test_convert_single_operation(self, minimal_spec: dict):
        """Test converting spec with single operation."""
        converter = OpenAPIConverter()
        tools = converter.convert(minimal_spec)

        assert len(tools) == 1
        assert tools[0].name == "get_health"
        assert tools[0].description == "Health check"
        assert tools[0].method == "GET"

    def test_convert_multiple_operations(self, petstore_spec: dict):
        """Test converting spec with multiple operations."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        assert len(tools) == 4  # listPets, createPet, getPetById, deletePet
        tool_names = [t.name for t in tools]
        assert "listpets" in tool_names
        assert "createpet" in tool_names
        assert "getpetbyid" in tool_names
        assert "deletepet" in tool_names


# =============================================================================
# Operation Conversion Tests
# =============================================================================


class TestOperationConversion:
    """Tests for individual operation conversion."""

    def test_operation_with_operation_id(self, petstore_spec: dict):
        """Test that operationId is used for tool name."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        list_pets = next(t for t in tools if t.name == "listpets")
        assert list_pets is not None

    def test_operation_without_operation_id(self):
        """Test name generation without operationId."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/users/{id}/profile": {
                    "put": {
                        "summary": "Update profile",
                    }
                }
            },
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)

        assert len(tools) == 1
        # Name should be generated from path and method
        assert "put" in tools[0].name.lower()
        assert "users" in tools[0].name.lower()

    def test_operation_description_from_summary(self, minimal_spec: dict):
        """Test description is taken from summary."""
        converter = OpenAPIConverter()
        tools = converter.convert(minimal_spec)

        assert tools[0].description == "Health check"

    def test_operation_description_from_description(self, petstore_spec: dict):
        """Test description is taken from description field if present."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        list_pets = next(t for t in tools if t.name == "listpets")
        assert "Returns all pets" in list_pets.description

    def test_operation_tags_preserved(self, petstore_spec: dict):
        """Test that operation tags are preserved."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        list_pets = next(t for t in tools if t.name == "listpets")
        assert "pets" in list_pets.tags
        assert "api" in list_pets.tags  # Always added

    def test_operation_http_method(self, petstore_spec: dict):
        """Test HTTP methods are correctly set."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        for tool in tools:
            assert tool.method in ["GET", "POST", "PUT", "DELETE", "PATCH"]


# =============================================================================
# Parameter Conversion Tests
# =============================================================================


class TestParameterConversion:
    """Tests for parameter conversion to input schema."""

    def test_query_parameters(self, petstore_spec: dict):
        """Test query parameters are converted."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        list_pets = next(t for t in tools if t.name == "listpets")
        schema = list_pets.input_schema

        assert "limit" in schema.properties
        assert schema.properties["limit"]["type"] == "integer"
        assert schema.properties["limit"]["default"] == 20

    def test_path_parameters(self, petstore_spec: dict):
        """Test path parameters are converted."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        get_pet = next(t for t in tools if t.name == "getpetbyid")
        schema = get_pet.input_schema

        assert "petId" in schema.properties
        assert "petId" in schema.required

    def test_enum_parameters(self, petstore_spec: dict):
        """Test enum parameters preserve enum values."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        list_pets = next(t for t in tools if t.name == "listpets")
        schema = list_pets.input_schema

        assert "status" in schema.properties
        assert schema.properties["status"]["enum"] == ["available", "pending", "sold"]

    def test_required_parameters(self, petstore_spec: dict):
        """Test required parameters are tracked."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        get_pet = next(t for t in tools if t.name == "getpetbyid")
        assert "petId" in get_pet.input_schema.required


# =============================================================================
# Request Body Conversion Tests
# =============================================================================


class TestRequestBodyConversion:
    """Tests for request body conversion."""

    def test_request_body_properties(self, petstore_spec: dict):
        """Test request body properties are extracted."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        create_pet = next(t for t in tools if t.name == "createpet")
        schema = create_pet.input_schema

        assert "name" in schema.properties
        assert "tag" in schema.properties
        assert "name" in schema.required


# =============================================================================
# Base URL Tests
# =============================================================================


class TestBaseURL:
    """Tests for base URL handling."""

    def test_base_url_from_servers(self, petstore_spec: dict):
        """Test base URL is extracted from servers."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        assert "petstore.example.com" in tools[0].endpoint

    def test_base_url_from_swagger2(self, swagger2_spec: dict):
        """Test base URL is constructed from Swagger 2.0 fields."""
        converter = OpenAPIConverter()
        tools = converter.convert(swagger2_spec)

        assert "https://api.legacy.com/v2" in tools[0].endpoint

    def test_base_url_override(self, petstore_spec: dict):
        """Test base URL can be overridden."""
        converter = OpenAPIConverter(base_url="https://custom.api.com")
        tools = converter.convert(petstore_spec)

        assert "custom.api.com" in tools[0].endpoint


# =============================================================================
# Metadata Tests
# =============================================================================


class TestMetadata:
    """Tests for STOA metadata."""

    def test_api_id_attached(self, minimal_spec: dict):
        """Test api_id is attached to tools."""
        converter = OpenAPIConverter(api_id="api-123")
        tools = converter.convert(minimal_spec)

        assert tools[0].api_id == "api-123"

    def test_tenant_id_attached(self, minimal_spec: dict):
        """Test tenant_id is attached to tools."""
        converter = OpenAPIConverter(tenant_id="tenant-456")
        tools = converter.convert(minimal_spec)

        assert tools[0].tenant_id == "tenant-456"

    def test_version_from_spec(self, petstore_spec: dict):
        """Test version is taken from spec."""
        converter = OpenAPIConverter()
        tools = converter.convert(petstore_spec)

        assert tools[0].version == "1.0.0"


# =============================================================================
# Name Sanitization Tests
# =============================================================================


class TestNameSanitization:
    """Tests for tool name sanitization."""

    def test_special_chars_removed(self):
        """Test special characters are replaced."""
        converter = OpenAPIConverter()
        name = converter._sanitize_name("get-user.profile")
        assert name == "get_user_profile"

    def test_consecutive_underscores_collapsed(self):
        """Test consecutive underscores are collapsed."""
        converter = OpenAPIConverter()
        name = converter._sanitize_name("get__user___profile")
        assert name == "get_user_profile"

    def test_lowercase(self):
        """Test names are lowercased."""
        converter = OpenAPIConverter()
        name = converter._sanitize_name("GetUserProfile")
        assert name == "getuserprofile"


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunction:
    """Tests for convert_openapi_to_tools function."""

    def test_dict_input(self, minimal_spec: dict):
        """Test function with dict input."""
        tools = convert_openapi_to_tools(minimal_spec)
        assert len(tools) == 1

    def test_json_string_input(self, minimal_spec: dict):
        """Test function with JSON string input."""
        json_str = json.dumps(minimal_spec)
        tools = convert_openapi_to_tools(json_str)
        assert len(tools) == 1

    def test_with_metadata(self, minimal_spec: dict):
        """Test function with metadata parameters."""
        tools = convert_openapi_to_tools(
            minimal_spec,
            api_id="test-api",
            tenant_id="test-tenant",
            base_url="https://override.com",
        )
        assert tools[0].api_id == "test-api"
        assert tools[0].tenant_id == "test-tenant"
        assert "override.com" in tools[0].endpoint


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_path_with_ref(self):
        """Test path with $ref is skipped gracefully."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/test": {
                    "get": {
                        "summary": "Test",
                        "parameters": [{"$ref": "#/components/parameters/SomeParam"}],
                    }
                }
            },
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)
        # Should not fail, just skip the ref
        assert len(tools) == 1

    def test_missing_schema(self):
        """Test parameter without schema."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/test": {
                    "get": {
                        "summary": "Test",
                        "parameters": [{"name": "q", "in": "query"}],
                    }
                }
            },
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)
        assert len(tools) == 1
        # Should default to string type
        assert tools[0].input_schema.properties["q"]["type"] == "string"

    def test_empty_paths(self):
        """Test spec with empty paths object."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {},
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)
        assert tools == []

    def test_non_dict_path_item(self):
        """Test non-dict path items are skipped."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/test": "invalid",  # Should be a dict
            },
        }
        converter = OpenAPIConverter()
        tools = converter.convert(spec)
        assert tools == []
