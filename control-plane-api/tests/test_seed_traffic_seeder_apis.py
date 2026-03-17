"""Tests for migration 075_seed_traffic_seeder_apis — traffic seeder APIs.

Validates:
- 6 APIs are defined with correct structure
- Metadata contains required fields (backend_url, auth_type, methods, deployment_mode)
- All APIs have 'realdata' tag
- No overlap with migration 074 IDs
- Auth types are from the known set
- Deployment modes are valid
"""

import importlib
import sys
import uuid
from pathlib import Path

import pytest

# Load migration modules from file (filenames start with digits)
_versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

_spec_075 = importlib.util.spec_from_file_location(
    "migration_075", _versions_dir / "075_seed_traffic_seeder_apis.py"
)
_mod_075 = importlib.util.module_from_spec(_spec_075)
sys.modules["migration_075"] = _mod_075
_spec_075.loader.exec_module(_mod_075)
APIS_075 = _mod_075.APIS

_spec_074 = importlib.util.spec_from_file_location(
    "migration_074", _versions_dir / "074_seed_realdata_apis.py"
)
_mod_074 = importlib.util.module_from_spec(_spec_074)
sys.modules["migration_074"] = _mod_074
_spec_074.loader.exec_module(_mod_074)
APIS_074 = _mod_074.APIS


class TestSeedTrafficSeederAPIsData:
    """Validate seed data structure and completeness."""

    def test_six_apis_defined(self):
        assert len(APIS_075) == 6

    def test_tenant_is_demo(self):
        assert _mod_075.TENANT_ID == "demo"

    def test_all_apis_have_required_fields(self):
        required = {"id", "api_id", "api_name", "version", "category", "tags", "metadata"}
        for api in APIS_075:
            missing = required - set(api.keys())
            assert not missing, f"{api['api_id']} missing fields: {missing}"

    def test_unique_ids(self):
        ids = [api["id"] for api in APIS_075]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {ids}"

    def test_unique_api_ids(self):
        api_ids = [api["api_id"] for api in APIS_075]
        assert len(api_ids) == len(set(api_ids)), f"Duplicate api_ids: {api_ids}"

    def test_valid_uuid4(self):
        for api in APIS_075:
            parsed = uuid.UUID(api["id"])
            assert parsed.version == 4, f"UUID {api['id']} is not v4"

    def test_all_metadata_has_backend_url(self):
        for api in APIS_075:
            meta = api["metadata"]
            assert "backend_url" in meta, f"{api['api_id']} missing backend_url"
            assert meta["backend_url"].startswith("http"), f"{api['api_id']} invalid backend_url"

    def test_all_metadata_has_auth_type(self):
        valid_auth = {"none", "oauth2_cc", "bearer", "fapi_baseline", "fapi_advanced"}
        for api in APIS_075:
            meta = api["metadata"]
            assert "auth_type" in meta, f"{api['api_id']} missing auth_type"
            assert meta["auth_type"] in valid_auth, f"{api['api_id']} unknown auth: {meta['auth_type']}"

    def test_all_metadata_has_methods(self):
        for api in APIS_075:
            meta = api["metadata"]
            assert "methods" in meta, f"{api['api_id']} missing methods"
            assert len(meta["methods"]) > 0, f"{api['api_id']} empty methods"

    def test_all_metadata_has_deployment_mode(self):
        valid_modes = {"edge-mcp", "sidecar", "connect"}
        for api in APIS_075:
            meta = api["metadata"]
            assert "deployment_mode" in meta, f"{api['api_id']} missing deployment_mode"
            assert meta["deployment_mode"] in valid_modes, f"{api['api_id']} invalid mode: {meta['deployment_mode']}"

    def test_all_apis_have_realdata_tag(self):
        for api in APIS_075:
            assert "realdata" in api["tags"], f"{api['api_id']} missing 'realdata' tag"

    def test_no_id_overlap_with_074(self):
        ids_074 = {api["id"] for api in APIS_074}
        ids_075 = {api["id"] for api in APIS_075}
        overlap = ids_074 & ids_075
        assert not overlap, f"ID overlap with 074: {overlap}"

    def test_no_api_id_overlap_with_074(self):
        api_ids_074 = {api["api_id"] for api in APIS_074}
        api_ids_075 = {api["api_id"] for api in APIS_075}
        overlap = api_ids_074 & api_ids_075
        assert not overlap, f"api_id overlap with 074: {overlap}"

    def test_revision_chain(self):
        assert _mod_075.down_revision == "074_seed_realdata_apis"
        assert _mod_075.revision == "075_seed_traffic_seeder_apis"

    @pytest.mark.parametrize(
        "api_id,expected_mode",
        [
            ("ecb-financial-data", "sidecar"),
            ("eurostat", "connect"),
            ("echo-oauth2", "edge-mcp"),
            ("echo-bearer", "connect"),
            ("fapi-accounts", "edge-mcp"),
            ("fapi-transfers", "edge-mcp"),
        ],
    )
    def test_deployment_modes(self, api_id: str, expected_mode: str):
        api = next(a for a in APIS_075 if a["api_id"] == api_id)
        assert api["metadata"]["deployment_mode"] == expected_mode

    @pytest.mark.parametrize(
        "api_id,expected_auth",
        [
            ("ecb-financial-data", "none"),
            ("eurostat", "none"),
            ("echo-oauth2", "oauth2_cc"),
            ("echo-bearer", "bearer"),
            ("fapi-accounts", "fapi_baseline"),
            ("fapi-transfers", "fapi_advanced"),
        ],
    )
    def test_auth_types(self, api_id: str, expected_auth: str):
        api = next(a for a in APIS_075 if a["api_id"] == api_id)
        assert api["metadata"]["auth_type"] == expected_auth

    def test_fapi_apis_have_banking_category(self):
        fapi = [a for a in APIS_075 if a["api_id"].startswith("fapi-")]
        assert len(fapi) == 2
        for api in fapi:
            assert api["category"] == "banking"
            assert "fapi" in api["tags"]

    def test_eu_apis_have_eu_public_tag(self):
        eu_apis = [a for a in APIS_075 if a["api_id"] in ("ecb-financial-data", "eurostat")]
        assert len(eu_apis) == 2
        for api in eu_apis:
            assert "eu-public" in api["tags"]
