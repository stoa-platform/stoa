"""Tests for ``render_api_catalog_projection`` and ``row_matches_projection``.

Spec §6.5 step 14, §6.6, §6.9, §6.10 (CAB-2186 B-WORKER, CAB-2180 B-CATALOG).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.services.catalog_reconciler.projection import (
    ApiCatalogProjection,
    render_api_catalog_projection,
    row_matches_projection,
)

_VALID_UUID = "12345678-1234-1234-1234-123456789012"


def _minimal_yaml(
    *,
    name: str = "petstore",
    id_value: str | None = None,
    version: str = "1.0.0",
    status: str = "active",
    display_name: str = "Petstore",
    description: str = "",
    backend_url: str = "http://example.invalid",
    category: str | None = None,
    tags: list[str] | None = None,
    audience: str | None = None,
    deployments: dict[str, bool] | None = None,
) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "id": id_value if id_value is not None else name,
        "name": name,
        "display_name": display_name,
        "version": version,
        "status": status,
        "description": description,
        "backend_url": backend_url,
        "deployments": deployments or {"dev": True, "staging": False},
    }
    if category is not None:
        parsed["category"] = category
    if tags is not None:
        parsed["tags"] = tags
    if audience is not None:
        parsed["audience"] = audience
    return parsed


class TestRenderApiCatalogProjection:
    def test_minimal_happy_path(self) -> None:
        proj = render_api_catalog_projection(
            parsed_content=_minimal_yaml(),
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/demo/apis/petstore/api.yaml",
        )
        assert proj.tenant_id == "demo"
        assert proj.api_id == "petstore"
        assert proj.api_name == "petstore"
        assert proj.version == "1.0.0"
        assert proj.status == "active"
        assert proj.category is None
        assert proj.tags == []
        assert proj.portal_published is False
        assert proj.audience == "public"
        assert proj.api_metadata == {
            "name": "petstore",
            "display_name": "Petstore",
            "version": "1.0.0",
            "description": "",
            "backend_url": "http://example.invalid",
            "status": "active",
            "deployments": {"dev": True, "staging": False},
            "tags": [],
            "audience": "public",
        }
        assert proj.git_path == "tenants/demo/apis/petstore/api.yaml"
        assert proj.git_commit_sha == "a" * 40
        assert proj.catalog_content_hash == "b" * 64

    @pytest.mark.parametrize("portal_tag", ["portal:published", "promoted:portal", "portal-promoted"])
    def test_portal_publication_tags_are_stripped_and_do_not_publish(self, portal_tag: str) -> None:
        proj = render_api_catalog_projection(
            parsed_content=_minimal_yaml(tags=[portal_tag, "banking"]),
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/demo/apis/petstore/api.yaml",
        )
        assert proj.portal_published is False
        assert proj.tags == ["banking"]
        assert proj.api_metadata["tags"] == ["banking"]

    def test_portal_not_published_when_tag_absent(self) -> None:
        proj = render_api_catalog_projection(
            parsed_content=_minimal_yaml(tags=["banking"]),
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/demo/apis/petstore/api.yaml",
        )
        assert proj.portal_published is False

    def test_category_propagated(self) -> None:
        proj = render_api_catalog_projection(
            parsed_content=_minimal_yaml(category="Banking"),
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/demo/apis/petstore/api.yaml",
        )
        assert proj.category == "Banking"

    def test_kubernetes_style_api_definition_is_normalized(self) -> None:
        proj = render_api_catalog_projection(
            parsed_content={
                "apiVersion": "stoa.cab-i.com/v1",
                "kind": "API",
                "metadata": {"name": "billing-api", "version": "3.0.0"},
                "spec": {
                    "displayName": "Billing & Invoicing API",
                    "description": "Generate invoices and manage subscriptions",
                    "status": "published",
                    "category": "integration",
                    "tags": ["rest", "billing"],
                    "backend": {"url": "https://billing.example.invalid/api/v3"},
                    "deployments": {"dev": True, "staging": True},
                    "documentation": {"openapi": "openapi.yaml"},
                },
            },
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/acme-corp/apis/billing-api/api.yaml",
        )
        assert proj.tenant_id == "acme-corp"
        assert proj.api_id == "billing-api"
        assert proj.version == "3.0.0"
        assert proj.status == "published"
        assert proj.category == "integration"
        assert proj.api_metadata["backend_url"] == "https://billing.example.invalid/api/v3"

    def test_audience_explicit_overrides_default(self) -> None:
        proj = render_api_catalog_projection(
            parsed_content=_minimal_yaml(audience="internal"),
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            git_path="tenants/demo/apis/petstore/api.yaml",
        )
        assert proj.audience == "internal"
        assert proj.api_metadata["audience"] == "internal"

    def test_backend_url_is_required_for_console_projection(self) -> None:
        with pytest.raises(ValueError, match="'backend_url'"):
            render_api_catalog_projection(
                parsed_content=_minimal_yaml(backend_url=""),
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )

    def test_id_not_equal_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="id != name"):
            render_api_catalog_projection(
                parsed_content=_minimal_yaml(name="petstore", id_value="not-petstore"),
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )

    def test_name_not_matching_path_slug_rejected(self) -> None:
        with pytest.raises(ValueError, match="name mismatch"):
            render_api_catalog_projection(
                parsed_content=_minimal_yaml(name="other-name"),
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )

    def test_uuid_path_rejected_via_parse_canonical(self) -> None:
        # parse_canonical_path raises before we even check name; the message
        # mentions UUID-shaped segments.
        with pytest.raises(ValueError, match="UUID-shaped segment"):
            render_api_catalog_projection(
                parsed_content=_minimal_yaml(name=_VALID_UUID),
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path=f"tenants/demo/apis/{_VALID_UUID}/api.yaml",
            )

    def test_missing_name_rejected(self) -> None:
        parsed = _minimal_yaml()
        del parsed["name"]
        with pytest.raises(ValueError, match="missing required field 'name'"):
            render_api_catalog_projection(
                parsed_content=parsed,
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )

    def test_missing_version_rejected(self) -> None:
        parsed = _minimal_yaml()
        del parsed["version"]
        with pytest.raises(ValueError, match="'version'"):
            render_api_catalog_projection(
                parsed_content=parsed,
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )

    def test_non_canonical_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-canonical"):
            render_api_catalog_projection(
                parsed_content=_minimal_yaml(),
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="apis/petstore/api.yaml",
            )

    def test_tags_must_be_list(self) -> None:
        parsed = _minimal_yaml()
        parsed["tags"] = "banking"  # str instead of list
        with pytest.raises(ValueError, match="tags must be a list"):
            render_api_catalog_projection(
                parsed_content=parsed,
                git_commit_sha="a" * 40,
                catalog_content_hash="b" * 64,
                git_path="tenants/demo/apis/petstore/api.yaml",
            )


class TestRowMatchesProjection:
    @pytest.fixture
    def projection(self) -> ApiCatalogProjection:
        return ApiCatalogProjection(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            category="Banking",
            tags=["banking"],
            portal_published=False,
            audience="public",
            api_metadata={
                "name": "petstore",
                "display_name": "Petstore",
                "version": "1.0.0",
                "description": "",
                "backend_url": "http://example.invalid",
                "status": "active",
                "deployments": {"dev": True, "staging": False},
                "tags": ["banking"],
                "audience": "public",
            },
            git_path="tenants/demo/apis/petstore/api.yaml",
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
        )

    @pytest.fixture
    def matching_row(self, projection: ApiCatalogProjection) -> dict[str, Any]:
        return {
            "tenant_id": projection.tenant_id,
            "api_id": projection.api_id,
            "api_name": projection.api_name,
            "version": projection.version,
            "status": projection.status,
            "category": projection.category,
            "tags": list(projection.tags),
            "portal_published": projection.portal_published,
            "audience": projection.audience,
            "api_metadata": dict(projection.api_metadata),
            "openapi_spec": projection.openapi_spec,
            "git_path": projection.git_path,
            "git_commit_sha": projection.git_commit_sha,
            "catalog_content_hash": projection.catalog_content_hash,
        }

    def test_matching_row_returns_true(self, projection: ApiCatalogProjection, matching_row: dict[str, Any]) -> None:
        assert row_matches_projection(matching_row, projection) is True

    def test_target_gateways_ignored(self, projection: ApiCatalogProjection, matching_row: dict[str, Any]) -> None:
        # Add unrelated columns — projection ignores them.
        matching_row["target_gateways"] = ["webmethods-prod"]
        matching_row["id"] = "00000000-0000-0000-0000-000000000001"
        matching_row["synced_at"] = "2026-04-27T00:00:00Z"
        matching_row["deleted_at"] = None
        assert row_matches_projection(matching_row, projection) is True

    def test_openapi_spec_mismatch_returns_false(self, matching_row: dict[str, Any]) -> None:
        projection = ApiCatalogProjection(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            category="Banking",
            tags=["portal:published"],
            portal_published=True,
            audience="public",
            api_metadata=matching_row["api_metadata"],
            git_path="tenants/demo/apis/petstore/api.yaml",
            git_commit_sha="a" * 40,
            catalog_content_hash="b" * 64,
            openapi_spec={"openapi": "3.0.3", "info": {"title": "Git"}, "paths": {}},
        )
        matching_row["openapi_spec"] = {"openapi": "3.0.3", "info": {"title": "DB"}, "paths": {}}
        assert row_matches_projection(matching_row, projection) is False

    def test_git_path_mismatch_returns_false(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["git_path"] = "tenants/demo/apis/00000000-0000-0000-0000-000000000000/api.yaml"
        assert row_matches_projection(matching_row, projection) is False

    def test_api_metadata_mismatch_returns_false(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["api_metadata"] = {**projection.api_metadata, "backend_url": "https://other.example"}
        assert row_matches_projection(matching_row, projection) is False

    def test_lifecycle_metadata_is_ignored_by_gitops_projection(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["api_metadata"] = {
            **projection.api_metadata,
            "lifecycle": {
                "portal_publications": {
                    "dev:00000000-0000-4000-8000-000000000001": {
                        "publication_status": "published",
                        "source": "api_lifecycle",
                    }
                }
            },
        }
        assert row_matches_projection(matching_row, projection) is True

    def test_catalog_content_hash_mismatch_returns_false(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["catalog_content_hash"] = "c" * 64
        assert row_matches_projection(matching_row, projection) is False

    def test_tags_order_matters(self, projection: ApiCatalogProjection, matching_row: dict[str, Any]) -> None:
        # Add a second tag in projection
        proj = ApiCatalogProjection(**{**projection.__dict__, "tags": ["banking", "regulated"]})
        matching_row["tags"] = ["regulated", "banking"]
        assert row_matches_projection(matching_row, proj) is False

    def test_status_mismatch_returns_false(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["status"] = "draft"
        assert row_matches_projection(matching_row, projection) is False

    def test_portal_published_is_ignored_by_gitops_projection(
        self, projection: ApiCatalogProjection, matching_row: dict[str, Any]
    ) -> None:
        matching_row["portal_published"] = True
        assert row_matches_projection(matching_row, projection) is True

    def test_missing_field_returns_false(self, projection: ApiCatalogProjection, matching_row: dict[str, Any]) -> None:
        del matching_row["catalog_content_hash"]
        assert row_matches_projection(matching_row, projection) is False
