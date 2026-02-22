"""Tests for stoa.yaml spec model and JSON Schema export (CAB-1410)."""
import json

import pytest
from pydantic import ValidationError

from src.schemas.stoa_yaml import (
    AuthType,
    HttpMethod,
    StoaAuth,
    StoaEndpoint,
    StoaRateLimit,
    StoaYamlSpec,
    export_json_schema,
)


class TestStoaEndpoint:
    def test_defaults(self):
        ep = StoaEndpoint(path="/pets")
        assert ep.path == "/pets"
        assert ep.method == HttpMethod.GET
        assert ep.tags == []

    def test_all_fields(self):
        ep = StoaEndpoint(path="/pets/{id}", method="DELETE", description="Remove a pet", tags=["admin"])
        assert ep.method == HttpMethod.DELETE
        assert ep.description == "Remove a pet"
        assert ep.tags == ["admin"]

    def test_invalid_method(self):
        with pytest.raises(ValidationError):
            StoaEndpoint(path="/x", method="INVALID")


class TestStoaRateLimit:
    def test_defaults(self):
        rl = StoaRateLimit()
        assert rl.requests_per_minute == 60
        assert rl.burst == 10

    def test_custom(self):
        rl = StoaRateLimit(requests_per_minute=100, burst=20)
        assert rl.requests_per_minute == 100

    def test_zero_rpm_invalid(self):
        with pytest.raises(ValidationError):
            StoaRateLimit(requests_per_minute=0)

    def test_zero_burst_invalid(self):
        with pytest.raises(ValidationError):
            StoaRateLimit(burst=0)


class TestStoaAuth:
    def test_defaults(self):
        auth = StoaAuth()
        assert auth.type == AuthType.JWT
        assert auth.required is True

    def test_api_key_type(self):
        auth = StoaAuth(type="api_key", header="X-API-Key")
        assert auth.type == AuthType.API_KEY
        assert auth.header == "X-API-Key"

    def test_none_auth(self):
        auth = StoaAuth(type="none", required=False)
        assert auth.type == AuthType.NONE


class TestStoaYamlSpec:
    def _minimal(self, **kw) -> StoaYamlSpec:
        defaults = {"name": "petstore"}
        defaults.update(kw)
        return StoaYamlSpec(**defaults)

    def test_minimal_valid(self):
        spec = self._minimal()
        assert spec.name == "petstore"
        assert spec.version == "1.0.0"
        assert spec.endpoints == []
        assert spec.tags == []

    def test_full_spec(self):
        spec = StoaYamlSpec(
            name="payments-api",
            version="2.1.0",
            endpoints=[
                {"path": "/payments", "method": "POST"},
                {"path": "/payments/{id}", "method": "GET"},
            ],
            rate_limit={"requests_per_minute": 200, "burst": 50},
            auth={"type": "jwt", "issuer": "https://auth.example.com"},
            tags=["payments", "internal"],
        )
        assert spec.version == "2.1.0"
        assert len(spec.endpoints) == 2
        assert spec.rate_limit.requests_per_minute == 200  # type: ignore[union-attr]
        assert spec.auth.type == AuthType.JWT  # type: ignore[union-attr]
        assert "payments" in spec.tags

    def test_name_required(self):
        with pytest.raises(ValidationError):
            StoaYamlSpec()

    def test_empty_name_invalid(self):
        with pytest.raises(ValidationError):
            StoaYamlSpec(name="")

    def test_version_pattern_valid(self):
        spec = self._minimal(version="0.0.1-alpha")
        assert spec.version == "0.0.1-alpha"

    def test_version_pattern_invalid(self):
        with pytest.raises(ValidationError):
            self._minimal(version="v1")

    def test_no_rate_limit_ok(self):
        spec = self._minimal()
        assert spec.rate_limit is None

    def test_no_auth_ok(self):
        spec = self._minimal()
        assert spec.auth is None


class TestExportJsonSchema:
    def test_returns_dict(self):
        schema = export_json_schema()
        assert isinstance(schema, dict)

    def test_title(self):
        schema = export_json_schema()
        assert schema.get("title") == "stoa.yaml"

    def test_required_properties(self):
        schema = export_json_schema()
        props = schema.get("properties", {})
        assert "name" in props
        assert "version" in props
        assert "endpoints" in props
        assert "rate_limit" in props
        assert "auth" in props
        assert "tags" in props

    def test_json_serialisable(self):
        schema = export_json_schema()
        serialised = json.dumps(schema)
        assert isinstance(serialised, str)
        assert len(serialised) > 100
