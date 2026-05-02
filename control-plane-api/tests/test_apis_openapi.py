"""Tests for Console API OpenAPI retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from src.models.catalog import APICatalog


def _catalog_api(*, openapi_spec: dict | None = None) -> APICatalog:
    return APICatalog(
        tenant_id="acme",
        api_id="payment-api",
        api_name="payment-api",
        version="1.0.0",
        status="active",
        tags=[],
        portal_published=False,
        audience="public",
        api_metadata={
            "display_name": "Payment API",
            "description": "Payment initiation",
            "backend_url": "https://payments.example.invalid",
            "deployments": {"dev": True, "staging": False},
        },
        openapi_spec=openapi_spec,
        git_path="tenants/acme/apis/payment-api/api.yaml",
        git_commit_sha="a" * 40,
    )


def test_get_openapi_prefers_git_source(client_as_tenant_admin):
    git_spec = {
        "openapi": "3.0.3",
        "info": {"title": "Payment API", "version": "1.0.0"},
        "paths": {"/payments": {"post": {"responses": {"200": {"description": "ok"}}}}},
    }

    with (
        patch("src.routers.apis.CatalogRepository") as repo_cls,
        patch("src.routers.apis.git_service") as mock_git_service,
    ):
        repo = MagicMock()
        repo.get_api_by_id = AsyncMock(return_value=_catalog_api(openapi_spec={"openapi": "3.0.0"}))
        repo_cls.return_value = repo
        mock_git_service.get_api_openapi_spec = AsyncMock(return_value=git_spec)

        response = client_as_tenant_admin.get("/v1/tenants/acme/apis/payment-api/openapi")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "git"
    assert data["is_authoritative"] is True
    assert data["format"] == "openapi"
    assert data["git_path"] == "tenants/acme/apis/payment-api/openapi.yaml"
    assert data["spec"] == git_spec


def test_get_openapi_falls_back_to_db_cache(client_as_tenant_admin):
    db_spec = {
        "swagger": "2.0",
        "info": {"title": "Payment API", "version": "1.0.0"},
        "paths": {"/payments": {"post": {"responses": {"200": {"description": "ok"}}}}},
    }

    with (
        patch("src.routers.apis.CatalogRepository") as repo_cls,
        patch("src.routers.apis.git_service") as mock_git_service,
    ):
        repo = MagicMock()
        repo.get_api_by_id = AsyncMock(return_value=_catalog_api(openapi_spec=db_spec))
        repo_cls.return_value = repo
        mock_git_service.get_api_openapi_spec = AsyncMock(return_value=None)

        response = client_as_tenant_admin.get("/v1/tenants/acme/apis/payment-api/openapi")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "db_cache"
    assert data["is_authoritative"] is False
    assert data["format"] == "swagger"
    assert data["spec"] == db_spec


def test_get_openapi_returns_marked_generated_fallback(client_as_tenant_admin):
    with (
        patch("src.routers.apis.CatalogRepository") as repo_cls,
        patch("src.routers.apis.git_service") as mock_git_service,
    ):
        repo = MagicMock()
        repo.get_api_by_id = AsyncMock(return_value=_catalog_api(openapi_spec=None))
        repo_cls.return_value = repo
        mock_git_service.get_api_openapi_spec = AsyncMock(side_effect=RuntimeError("not connected"))

        response = client_as_tenant_admin.get("/v1/tenants/acme/apis/payment-api/openapi")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "generated_fallback"
    assert data["is_authoritative"] is False
    assert data["format"] == "openapi"
    assert data["spec"]["info"]["title"] == "Payment API"
    assert "/" in data["spec"]["paths"]
