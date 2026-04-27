"""Tests for ``services.gitops_writer.paths``.

Spec §6.1, §6.5 step 6, §6.10, §6.14, §6.4 (CAB-2187 B10, CAB-2183 B-LAYOUT).
"""

from __future__ import annotations

import pytest

from src.services.gitops_writer.paths import (
    canonical_catalog_path,
    is_uuid_shaped,
    parse_canonical_path,
)

_VALID_UUID_LOWER = "12345678-1234-1234-1234-123456789012"
_VALID_UUID_UPPER = "12345678-1234-1234-1234-123456789012".upper()


class TestIsUuidShaped:
    def test_lowercase_uuid_detected(self) -> None:
        assert is_uuid_shaped(_VALID_UUID_LOWER) is True

    def test_uppercase_uuid_detected(self) -> None:
        assert is_uuid_shaped(_VALID_UUID_UPPER) is True

    def test_slug_not_uuid_shaped(self) -> None:
        assert is_uuid_shaped("payment-api") is False
        assert is_uuid_shaped("petstore") is False
        assert is_uuid_shaped("a") is False

    def test_almost_uuid_not_detected(self) -> None:
        assert is_uuid_shaped("12345678-1234-1234-1234-12345678901") is False  # 11 chars
        assert is_uuid_shaped("12345678-1234-1234-1234-1234567890123") is False  # 13 chars
        assert is_uuid_shaped("not-a-uuid-12345678-1234-1234-1234-123456789012") is False
        assert is_uuid_shaped("12345678123412341234123456789012") is False  # no dashes


class TestCanonicalCatalogPath:
    def test_happy_path(self) -> None:
        assert canonical_catalog_path("demo", "petstore") == "tenants/demo/apis/petstore/api.yaml"

    def test_tenant_with_dashes(self) -> None:
        assert canonical_catalog_path("demo-gitops", "manual-test") == "tenants/demo-gitops/apis/manual-test/api.yaml"

    def test_uuid_api_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="UUID-shaped not allowed"):
            canonical_catalog_path("demo", _VALID_UUID_LOWER)

    def test_uuid_api_name_uppercase_rejected(self) -> None:
        with pytest.raises(ValueError, match="UUID-shaped"):
            canonical_catalog_path("demo", _VALID_UUID_UPPER)

    def test_uuid_tenant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="tenant_id UUID-shaped"):
            canonical_catalog_path(_VALID_UUID_LOWER, "petstore")

    def test_traversal_in_api_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsafe path segment"):
            canonical_catalog_path("demo", "../etc/passwd")

    def test_slash_in_api_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsafe path segment"):
            canonical_catalog_path("demo", "with/slash")

    def test_leading_dot_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsafe path segment"):
            canonical_catalog_path("demo", ".hidden")

    def test_empty_api_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            canonical_catalog_path("demo", "")

    def test_empty_tenant_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            canonical_catalog_path("", "petstore")

    def test_whitespace_in_segment_rejected(self) -> None:
        with pytest.raises(ValueError, match="unsafe path segment"):
            canonical_catalog_path("demo", "with space")


class TestParseCanonicalPath:
    def test_happy_path(self) -> None:
        assert parse_canonical_path("tenants/demo/apis/petstore/api.yaml") == ("demo", "petstore")

    def test_tenant_with_dashes(self) -> None:
        assert parse_canonical_path("tenants/demo-gitops/apis/manual-test/api.yaml") == (
            "demo-gitops",
            "manual-test",
        )

    def test_uuid_segment_rejected(self) -> None:
        with pytest.raises(ValueError, match="UUID-shaped segment"):
            parse_canonical_path(f"tenants/demo/apis/{_VALID_UUID_LOWER}/api.yaml")

    def test_uuid_tenant_segment_rejected(self) -> None:
        with pytest.raises(ValueError, match="UUID-shaped segment"):
            parse_canonical_path(f"tenants/{_VALID_UUID_LOWER}/apis/petstore/api.yaml")

    def test_non_canonical_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-canonical"):
            parse_canonical_path("apis/petstore/api.yaml")

    def test_wrong_filename_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-canonical"):
            parse_canonical_path("tenants/demo/apis/petstore/openapi.yaml")

    def test_extra_path_segments_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-canonical"):
            parse_canonical_path("tenants/demo/apis/petstore/v2/api.yaml")


class TestRoundtrip:
    @pytest.mark.parametrize(
        ("tenant_id", "api_name"),
        [
            ("demo", "petstore"),
            ("demo-gitops", "manual-test"),
            ("banking-demo", "fraud-detection-api"),
            ("ioi", "a"),
            ("oasis", "customer-360-api"),
        ],
    )
    def test_roundtrip(self, tenant_id: str, api_name: str) -> None:
        path = canonical_catalog_path(tenant_id, api_name)
        assert parse_canonical_path(path) == (tenant_id, api_name)
