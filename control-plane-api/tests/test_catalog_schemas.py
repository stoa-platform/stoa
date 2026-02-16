"""Tests for catalog schemas (CAB-1291)"""
from datetime import datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.schemas.catalog import (
    APICatalogDetailResponse,
    APICatalogListResponse,
    APICatalogResponse,
    CatalogStatsResponse,
    CategoriesResponse,
    SyncHistoryResponse,
    SyncStatusEnum,
    SyncStatusResponse,
    SyncTriggerResponse,
    SyncTypeEnum,
    TagsResponse,
)


class TestEnums:
    def test_sync_type_values(self):
        assert SyncTypeEnum.FULL == "full"
        assert SyncTypeEnum.TENANT == "tenant"
        assert SyncTypeEnum.API == "api"

    def test_sync_status_values(self):
        assert SyncStatusEnum.RUNNING == "running"
        assert SyncStatusEnum.SUCCESS == "success"
        assert SyncStatusEnum.FAILED == "failed"


class TestAPICatalogResponse:
    def test_minimal(self):
        resp = APICatalogResponse(
            id=uuid4(), tenant_id="acme", api_id="api-1", synced_at=datetime(2026, 1, 1),
        )
        assert resp.api_name is None
        assert resp.tags == []
        assert resp.portal_published is False
        assert resp.status == "active"

    def test_from_db_model(self):
        db = MagicMock()
        db.id = uuid4()
        db.tenant_id = "acme"
        db.api_id = "weather-api"
        db.api_name = "Weather API"
        db.version = "1.0.0"
        db.status = "active"
        db.category = "public"
        db.tags = ["weather", "rest"]
        db.portal_published = True
        db.api_metadata = {"display_name": "Weather", "description": "Forecast", "backend_url": "http://api.local"}
        db.git_path = "apis/weather/openapi.yaml"
        db.git_commit_sha = "abc123"
        db.synced_at = datetime(2026, 2, 1)

        resp = APICatalogResponse.from_db_model(db)
        assert resp.display_name == "Weather"
        assert resp.description == "Forecast"
        assert resp.backend_url == "http://api.local"
        assert resp.tags == ["weather", "rest"]

    def test_from_db_model_no_metadata(self):
        db = MagicMock()
        db.id = uuid4()
        db.tenant_id = "t"
        db.api_id = "a"
        db.api_name = "API"
        db.version = None
        db.status = "active"
        db.category = None
        db.tags = None
        db.portal_published = False
        db.api_metadata = None
        db.git_path = None
        db.git_commit_sha = None
        db.synced_at = datetime(2026, 1, 1)

        resp = APICatalogResponse.from_db_model(db)
        assert resp.tags == []
        assert resp.display_name == "API"


class TestAPICatalogDetailResponse:
    def test_from_db_model(self):
        db = MagicMock()
        db.id = uuid4()
        db.tenant_id = "acme"
        db.api_id = "test"
        db.api_name = "Test"
        db.version = "1.0.0"
        db.status = "active"
        db.category = None
        db.tags = []
        db.portal_published = False
        db.api_metadata = {"description": "A test API"}
        db.git_path = None
        db.git_commit_sha = None
        db.synced_at = datetime(2026, 1, 1)
        db.openapi_spec = {"openapi": "3.0.0"}

        resp = APICatalogDetailResponse.from_db_model(db)
        assert resp.openapi_spec == {"openapi": "3.0.0"}
        assert resp.metadata == {"description": "A test API"}


class TestAPICatalogListResponse:
    def test_defaults(self):
        resp = APICatalogListResponse(apis=[], total=0)
        assert resp.page == 1
        assert resp.page_size == 20


class TestSyncStatusResponse:
    def test_from_db_model(self):
        db = MagicMock()
        db.id = uuid4()
        db.sync_type = "full"
        db.status = "success"
        db.started_at = datetime(2026, 1, 1)
        db.completed_at = datetime(2026, 1, 1, 0, 5)
        db.items_synced = 42
        db.errors = [{"msg": "warn"}]
        db.git_commit_sha = "abc"
        db.duration_seconds = 300.5

        resp = SyncStatusResponse.from_db_model(db)
        assert resp.sync_type == SyncTypeEnum.FULL
        assert resp.status == SyncStatusEnum.SUCCESS
        assert resp.items_synced == 42
        assert resp.duration_seconds == 300.5

    def test_defaults(self):
        resp = SyncStatusResponse(
            id=uuid4(), sync_type=SyncTypeEnum.TENANT,
            status=SyncStatusEnum.RUNNING, started_at=datetime(2026, 1, 1),
        )
        assert resp.completed_at is None
        assert resp.items_synced == 0
        assert resp.errors == []


class TestSyncTriggerResponse:
    def test_defaults(self):
        resp = SyncTriggerResponse()
        assert resp.status == "sync_started"
        assert resp.sync_id is None


class TestSyncHistoryResponse:
    def test_construction(self):
        resp = SyncHistoryResponse(syncs=[], total=0)
        assert resp.syncs == []


class TestCatalogStatsResponse:
    def test_construction(self):
        resp = CatalogStatsResponse(
            total_apis=10, published_apis=7, unpublished_apis=3,
            by_tenant={"acme": 5, "globex": 5},
            by_category={"public": 8, "internal": 2},
        )
        assert resp.total_apis == 10
        assert resp.last_sync is None

    def test_defaults(self):
        resp = CatalogStatsResponse(total_apis=0, published_apis=0, unpublished_apis=0)
        assert resp.by_tenant == {}
        assert resp.by_category == {}


class TestCategoriesAndTags:
    def test_categories(self):
        resp = CategoriesResponse(categories=["public", "internal", "partner"])
        assert len(resp.categories) == 3

    def test_tags(self):
        resp = TagsResponse(tags=["rest", "graphql", "grpc"])
        assert "rest" in resp.tags
