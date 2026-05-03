"""Tests for APIs router — /v1/tenants/{tenant_id}/apis (DB-backed, no GitLab)"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.catalog import APICatalog

KAFKA_PATH = "src.routers.apis.kafka_service"


def _mock_catalog_api(**overrides) -> APICatalog:
    """Build a mock APICatalog row."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "api_id": "weather-api",
        "api_name": "Weather API",
        "version": "1.0.0",
        "status": "draft",
        "tags": [],
        "portal_published": False,
        "api_metadata": {
            "name": "weather-api",
            "display_name": "Weather API",
            "version": "1.0.0",
            "description": "Weather data",
            "backend_url": "https://api.weather.com",
            "status": "draft",
            "deployments": {"dev": False, "staging": False},
            "tags": [],
        },
        "openapi_spec": None,
        "synced_at": datetime.now(UTC),
        "deleted_at": None,
    }
    defaults.update(overrides)
    mock = MagicMock(spec=APICatalog)
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


CATALOG_REPO_PATH = "src.routers.apis.CatalogRepository"


class TestListAPIs:
    def test_list_returns_paginated(self, app_with_tenant_admin, client_as_tenant_admin):
        apis = [_mock_catalog_api(), _mock_catalog_api(api_id="maps-api", api_name="Maps API")]
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(return_value=(apis, 2))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_list_filter_by_env(self, app_with_tenant_admin, client_as_tenant_admin):
        apis = [
            _mock_catalog_api(
                api_metadata={
                    **_mock_catalog_api().api_metadata,
                    "deployments": {"dev": True, "staging": False},
                }
            ),
            _mock_catalog_api(
                api_id="api-2",
                api_metadata={
                    **_mock_catalog_api().api_metadata,
                    "deployments": {"dev": False, "staging": True},
                },
            ),
        ]
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(return_value=(apis, 2))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis?environment=staging")

        body = resp.json()
        assert body["total"] == 1

    def test_list_error_returns_503(self, app_with_tenant_admin, client_as_tenant_admin):
        """CAB-1917: list_apis must return 503 on backend errors, not swallow them."""
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(side_effect=RuntimeError("DB down"))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_other_tenant_forbidden(self, app_with_other_tenant, client_as_other_tenant):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(return_value=([], 0))
            resp = client_as_other_tenant.get("/v1/tenants/acme/apis")

        assert resp.status_code == 403

    def test_cpi_admin_cross_tenant(self, app_with_cpi_admin, client_as_cpi_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(return_value=([], 0))
            resp = client_as_cpi_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 200


class TestGetAPI:
    def test_get_success(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=_mock_catalog_api())
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/weather-api")

        assert resp.status_code == 200
        assert resp.json()["name"] == "weather-api"

    def test_get_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis/missing")

        assert resp.status_code == 404


class TestCreateAPI:
    def test_create_success(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "new-api",
                    "display_name": "New API",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "new-api"
        assert body["status"] == "draft"
        event_payload = mock_kafka.emit_api_created.call_args.kwargs["api_data"]
        assert event_payload["backend_url"] == "https://api.example.com"
        assert event_payload["display_name"] == "New API"
        assert "openapi_spec" in event_payload

    def test_create_event_contains_parsed_openapi(self, app_with_tenant_admin, client_as_tenant_admin):
        openapi_yaml = """
openapi: 3.0.0
info:
  title: New API
  version: 1.0.0
paths:
  /quotes:
    get:
      operationId: listQuotes
      responses:
        "200":
          description: ok
"""
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "quotes-api",
                    "display_name": "Quotes API",
                    "backend_url": "https://quotes.example.com",
                    "openapi_spec": openapi_yaml,
                },
            )

        assert resp.status_code == 200
        event_payload = mock_kafka.emit_api_created.call_args.kwargs["api_data"]
        assert event_payload["openapi_spec"]["paths"]["/quotes"]["get"]["operationId"] == "listQuotes"

    def test_create_duplicate_returns_409(self, app_with_tenant_admin, client_as_tenant_admin):
        from src.database import get_db

        mock_session = AsyncMock()
        # First execute call is TenantRepository.get_by_id → return None (skip trial check)
        # Second execute call is the INSERT → raise duplicate
        mock_session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),  # tenant lookup
                Exception("duplicate key violates unique constraint"),  # insert
            ]
        )
        mock_session.rollback = AsyncMock()
        mock_session.commit = AsyncMock()

        async def _override_db():
            yield mock_session

        app_with_tenant_admin.dependency_overrides[get_db] = _override_db

        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH):
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "dup-api",
                    "display_name": "Dup",
                    "backend_url": "https://api.example.com",
                },
            )

        app_with_tenant_admin.dependency_overrides.pop(get_db, None)
        assert resp.status_code == 409

    @pytest.mark.parametrize("portal_tag", ["portal:published", "promoted:portal", "portal-promoted"])
    def test_create_rejects_implicit_portal_publication_tag(
        self, app_with_tenant_admin, client_as_tenant_admin, portal_tag
    ):
        with patch(CATALOG_REPO_PATH), patch(KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "portal-api",
                    "display_name": "Portal API",
                    "backend_url": "https://api.example.com",
                    "tags": [portal_tag, "v1"],
                },
            )

        assert resp.status_code == 422
        assert "lifecycle/publications" in resp.json()["detail"]
        mock_kafka.emit_api_created.assert_not_called()


class TestUpdateAPI:
    def test_update_success(self, app_with_tenant_admin, client_as_tenant_admin):
        mock_api = _mock_catalog_api()
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=mock_api)
            with patch(KAFKA_PATH) as mock_kafka:
                mock_kafka.emit_api_updated = AsyncMock(return_value="evt-1")
                mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
                resp = client_as_tenant_admin.put(
                    "/v1/tenants/acme/apis/weather-api",
                    json={"description": "Updated desc"},
                )

        assert resp.status_code == 200

    def test_update_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
            with patch(KAFKA_PATH):
                resp = client_as_tenant_admin.put(
                    "/v1/tenants/acme/apis/missing",
                    json={"description": "test"},
                )

        assert resp.status_code == 404

    @pytest.mark.parametrize("portal_tag", ["portal:published", "promoted:portal", "portal-promoted"])
    def test_update_rejects_implicit_portal_publication_tag(
        self, app_with_tenant_admin, client_as_tenant_admin, portal_tag
    ):
        mock_api = _mock_catalog_api()
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=mock_api)
            with patch(KAFKA_PATH) as mock_kafka:
                mock_kafka.emit_api_updated = AsyncMock(return_value="evt-1")
                mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
                resp = client_as_tenant_admin.put(
                    "/v1/tenants/acme/apis/weather-api",
                    json={"tags": [portal_tag, "v1"]},
                )

        assert resp.status_code == 422
        assert "lifecycle/publications" in resp.json()["detail"]
        assert mock_api.portal_published is False
        mock_kafka.emit_api_updated.assert_not_called()


class TestDeleteAPI:
    def test_delete_success(self, app_with_tenant_admin, client_as_tenant_admin):
        mock_api = _mock_catalog_api()
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=mock_api)
            with patch(KAFKA_PATH) as mock_kafka:
                mock_kafka.emit_api_deleted = AsyncMock(return_value="evt-1")
                mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
                resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/weather-api")

        assert resp.status_code == 200

    def test_delete_not_found(self, app_with_tenant_admin, client_as_tenant_admin):
        with patch(CATALOG_REPO_PATH) as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
            with patch(KAFKA_PATH):
                resp = client_as_tenant_admin.delete("/v1/tenants/acme/apis/missing")

        assert resp.status_code == 404


class TestApiFromCatalog:
    def test_portal_promoted_detection_uses_catalog_field(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(tags=["v1"], portal_published=True)
        result = _api_from_catalog(api)
        assert result.portal_promoted is True

    def test_portal_tag_alone_does_not_mark_portal_promoted(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(tags=["portal:published", "v1"], portal_published=False)
        result = _api_from_catalog(api)
        assert result.portal_promoted is False

    def test_deployments_from_metadata(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(
            api_metadata={
                **_mock_catalog_api().api_metadata,
                "deployments": {"dev": True, "staging": True},
            }
        )
        result = _api_from_catalog(api)
        assert result.deployed_dev is True
        assert result.deployed_staging is True

    def test_catalog_release_metadata_exposed(self):
        from src.routers.apis import _api_from_catalog

        api = _mock_catalog_api(
            catalog_release_id="catalog-release:abc",
            catalog_release_tag="stoa/api/acme/weather-api/v1.0.0/abc123",
            catalog_pr_url="https://github.com/stoa-platform/stoa-catalog/pull/12",
            catalog_pr_number=12,
            catalog_source_branch="stoa/api/acme/weather-api/v1.0.0/hash",
            catalog_merge_commit_sha="abc123",
        )
        result = _api_from_catalog(api)

        assert result.catalog_release_id == "catalog-release:abc"
        assert result.catalog_release_tag == "stoa/api/acme/weather-api/v1.0.0/abc123"
        assert result.catalog_pr_url == "https://github.com/stoa-platform/stoa-catalog/pull/12"
        assert result.catalog_pr_number == 12
        assert result.catalog_source_branch == "stoa/api/acme/weather-api/v1.0.0/hash"
        assert result.catalog_merge_commit_sha == "abc123"
