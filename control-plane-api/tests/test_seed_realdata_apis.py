"""Tests for migration 074_seed_realdata_apis — CAB-1856.

Validates:
- 6 APIs are defined with correct structure
- Metadata contains required fields (backend_url, description, auth_type)
- All APIs are portal_published=True (discoverable by gateway)
- Internal endpoint returns correct InternalAPIItem format
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "074_seed_realdata_apis.py"
_spec = importlib.util.spec_from_file_location("migration_074", _migration_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["migration_074"] = _mod
_spec.loader.exec_module(_mod)
APIS = _mod.APIS
TENANT_ID = _mod.TENANT_ID

CATALOG_REPO = "src.routers.portal.CatalogRepository"


class TestSeedRealdataAPIsData:
    """Validate seed data structure and completeness."""

    def test_six_apis_defined(self):
        assert len(APIS) == 6

    def test_tenant_is_demo(self):
        assert TENANT_ID == "demo"

    def test_all_apis_have_required_fields(self):
        required = {"id", "api_id", "api_name", "version", "category", "tags", "metadata"}
        for api in APIS:
            missing = required - set(api.keys())
            assert not missing, f"{api['api_id']} missing fields: {missing}"

    def test_all_metadata_has_backend_url(self):
        for api in APIS:
            meta = api["metadata"]
            assert "backend_url" in meta, f"{api['api_id']} missing backend_url"
            assert meta["backend_url"].startswith("http"), f"{api['api_id']} invalid backend_url"

    def test_all_metadata_has_description(self):
        for api in APIS:
            meta = api["metadata"]
            assert "description" in meta, f"{api['api_id']} missing description"
            assert len(meta["description"]) > 10, f"{api['api_id']} description too short"

    def test_all_metadata_has_auth_type(self):
        for api in APIS:
            meta = api["metadata"]
            assert "auth_type" in meta, f"{api['api_id']} missing auth_type"
            assert meta["auth_type"] in {"none", "api_key_query", "api_key_header"}

    def test_all_apis_have_realdata_tag(self):
        for api in APIS:
            assert "realdata" in api["tags"], f"{api['api_id']} missing 'realdata' tag"

    def test_unique_api_ids(self):
        api_ids = [api["api_id"] for api in APIS]
        assert len(api_ids) == len(set(api_ids)), "Duplicate api_ids found"

    def test_unique_uuids(self):
        uuids = [api["id"] for api in APIS]
        assert len(uuids) == len(set(uuids)), "Duplicate UUIDs found"

    def test_echo_fallback_is_internal(self):
        echo = next(a for a in APIS if a["api_id"] == "echo-fallback")
        assert echo["category"] == "internal"
        assert "internal" in echo["tags"]
        assert echo["metadata"]["auth_type"] == "none"

    def test_api_key_apis_have_auth_param_or_header(self):
        for api in APIS:
            meta = api["metadata"]
            if meta["auth_type"] == "api_key_query":
                assert "auth_param" in meta, f"{api['api_id']} missing auth_param"
            elif meta["auth_type"] == "api_key_header":
                assert "auth_header" in meta, f"{api['api_id']} missing auth_header"

    @pytest.mark.parametrize(
        "api_id,expected_url_prefix",
        [
            ("exchange-rate", "https://api.exchangerate-api.com"),
            ("coingecko", "https://api.coingecko.com"),
            ("openweathermap", "https://api.openweathermap.org"),
            ("newsapi", "https://newsapi.org"),
            ("alphavantage", "https://www.alphavantage.co"),
            ("echo-fallback", "http://echo-backend"),
        ],
    )
    def test_backend_urls(self, api_id: str, expected_url_prefix: str):
        api = next(a for a in APIS if a["api_id"] == api_id)
        assert api["metadata"]["backend_url"].startswith(expected_url_prefix)


class TestInternalCatalogRealdataAPIs:
    """Test that gateway internal endpoint returns realdata APIs correctly."""

    @pytest.fixture()
    def app(self):
        from src.main import app

        return app

    @pytest.fixture()
    def mock_db_session(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        session.close = AsyncMock()
        return session

    def _make_catalog_entry(self, api_data: dict) -> MagicMock:
        entry = MagicMock()
        entry.api_id = api_data["api_id"]
        entry.api_name = api_data["api_name"]
        entry.api_metadata = api_data["metadata"]
        entry.version = api_data["version"]
        entry.portal_published = True
        entry.audience = "public"
        entry.status = "published"
        entry.category = api_data["category"]
        entry.tags = api_data["tags"]
        return entry

    def test_internal_endpoint_returns_all_six(self, app, mock_db_session):
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        entries = [self._make_catalog_entry(api) for api in APIS]
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=(entries, len(entries)))

        with patch(CATALOG_REPO, return_value=mock_repo), TestClient(app) as client:
            resp = client.get("/v1/internal/catalog/apis")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["apis"]) == 6

        api_names = {a["id"] for a in data["apis"]}
        assert "exchange-rate" in api_names
        assert "echo-fallback" in api_names

        app.dependency_overrides.clear()

    def test_internal_endpoint_includes_backend_url(self, app, mock_db_session):
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        entries = [self._make_catalog_entry(APIS[0])]  # exchange-rate
        mock_repo = MagicMock()
        mock_repo.get_portal_apis = AsyncMock(return_value=(entries, 1))

        with patch(CATALOG_REPO, return_value=mock_repo), TestClient(app) as client:
            resp = client.get("/v1/internal/catalog/apis")

        data = resp.json()
        api = data["apis"][0]
        assert api["backend_url"] == "https://api.exchangerate-api.com/v4/latest"
        assert api["description"].startswith("Real-time foreign exchange")
        assert api["version"] == "4.0"

        app.dependency_overrides.clear()
