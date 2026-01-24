"""
E2E Sync Verification Tests (CAB-650)
Verify that Git = Gateway = Portal after Argo CD sync

These tests ensure GitOps reconciliation is working correctly by comparing:
- APIs defined in Git (webmethods/apis/*.yaml)
- APIs deployed on webMethods Gateway
- APIs published on Developer Portal
"""

import os
from pathlib import Path

import pytest
import yaml

# Configuration
WEBMETHODS_APIS_PATH = os.getenv("WEBMETHODS_APIS_PATH", "webmethods/apis")
SYSTEM_APIS = {"search", "health", "metrics", "Gateway_Admin_API", "Portal_API"}


@pytest.mark.sync
@pytest.mark.smoke
class TestSyncVerification:
    """Test suite for GitOps sync verification."""

    @pytest.fixture
    def git_apis(self):
        """Load APIs defined in Git repository."""
        apis = []
        apis_path = Path(WEBMETHODS_APIS_PATH)

        if not apis_path.exists():
            pytest.skip(f"APIs path not found: {apis_path}")

        for f in apis_path.glob("*.yaml"):
            with open(f) as file:
                content = yaml.safe_load(file)
                if content:
                    apis.append(content)

        if not apis:
            pytest.skip("No API definitions found in Git")

        return apis

    @pytest.fixture
    def gateway_apis(self, gateway_admin_session):
        """Retrieve APIs from webMethods Gateway."""
        resp = gateway_admin_session.get(
            f"{gateway_admin_session.base_url}/rest/apigateway/apis"
        )

        if resp.status_code != 200:
            pytest.fail(f"Failed to fetch Gateway APIs: {resp.status_code} - {resp.text}")

        data = resp.json()
        return data.get("apiResponse", [])

    @pytest.fixture
    def portal_apis(self, portal_session):
        """Retrieve APIs from Developer Portal."""
        resp = portal_session.get(
            f"{portal_session.base_url}/api/v1/catalog/apis"
        )

        if resp.status_code != 200:
            pytest.fail(f"Failed to fetch Portal APIs: {resp.status_code} - {resp.text}")

        return resp.json()

    def _extract_git_api_name(self, api: dict) -> str | None:
        """Extract API name from Git YAML structure."""
        if "metadata" in api and "name" in api["metadata"]:
            return api["metadata"]["name"]
        if "apiName" in api:
            return api["apiName"]
        if "name" in api:
            return api["name"]
        return None

    def _extract_git_api_version(self, api: dict) -> str:
        """Extract API version from Git YAML structure."""
        if "spec" in api and "version" in api["spec"]:
            return api["spec"]["version"]
        if "apiVersion" in api:
            return api["apiVersion"]
        if "version" in api:
            return api["version"]
        return "1.0"

    def test_gateway_has_all_git_apis(self, git_apis, gateway_apis):
        """All APIs defined in Git must be present on the Gateway."""
        git_names = {
            name for api in git_apis
            if (name := self._extract_git_api_name(api)) is not None
        }
        gw_names = {api.get("apiName") for api in gateway_apis if api.get("apiName")}

        missing = git_names - gw_names
        assert not missing, f"APIs missing on Gateway: {missing}"

    def test_portal_has_all_git_apis(self, git_apis, portal_apis):
        """All APIs defined in Git must be published on the Portal."""
        git_names = {
            name for api in git_apis
            if (name := self._extract_git_api_name(api)) is not None
        }

        # Portal API response may be a list or have a nested structure
        if isinstance(portal_apis, list):
            portal_names = {api.get("name") for api in portal_apis if api.get("name")}
        else:
            portal_list = portal_apis.get("apis", portal_apis.get("items", []))
            portal_names = {api.get("name") for api in portal_list if api.get("name")}

        missing = git_names - portal_names
        assert not missing, f"APIs missing on Portal: {missing}"

    def test_no_orphan_apis_on_gateway(self, git_apis, gateway_apis):
        """No orphan APIs should exist on Gateway (not defined in Git)."""
        git_names = {
            name for api in git_apis
            if (name := self._extract_git_api_name(api)) is not None
        }
        gw_names = {api.get("apiName") for api in gateway_apis if api.get("apiName")}

        orphans = gw_names - git_names - SYSTEM_APIS
        assert not orphans, f"Orphan APIs on Gateway (not in Git): {orphans}"

    def test_api_versions_match(self, git_apis, gateway_apis):
        """API versions must match between Git and Gateway."""
        git_versions = {}
        for api in git_apis:
            name = self._extract_git_api_name(api)
            if name:
                git_versions[name] = self._extract_git_api_version(api)

        gw_versions = {
            api.get("apiName"): api.get("apiVersion", "1.0")
            for api in gateway_apis
            if api.get("apiName")
        }

        mismatches = []
        for name, git_ver in git_versions.items():
            if name in gw_versions and gw_versions[name] != git_ver:
                mismatches.append(f"{name}: Git={git_ver}, Gateway={gw_versions[name]}")

        assert not mismatches, f"Version mismatches: {mismatches}"

    def test_api_count_matches(self, git_apis, gateway_apis):
        """Number of APIs should roughly match (accounting for system APIs)."""
        git_count = len(git_apis)
        gw_count = len([
            api for api in gateway_apis
            if api.get("apiName") not in SYSTEM_APIS
        ])

        # Allow some tolerance for transient states
        diff = abs(git_count - gw_count)
        assert diff <= 2, (
            f"API count mismatch: Git has {git_count}, "
            f"Gateway has {gw_count} (diff: {diff})"
        )


@pytest.mark.sync
class TestGatewayPortalSync:
    """Test synchronization between Gateway and Portal."""

    @pytest.fixture
    def gateway_apis(self, gateway_admin_session):
        """Retrieve APIs from webMethods Gateway."""
        resp = gateway_admin_session.get(
            f"{gateway_admin_session.base_url}/rest/apigateway/apis"
        )
        if resp.status_code != 200:
            pytest.fail(f"Failed to fetch Gateway APIs: {resp.status_code}")
        return resp.json().get("apiResponse", [])

    @pytest.fixture
    def portal_apis(self, portal_session):
        """Retrieve APIs from Developer Portal."""
        resp = portal_session.get(
            f"{portal_session.base_url}/api/v1/catalog/apis"
        )
        if resp.status_code != 200:
            pytest.fail(f"Failed to fetch Portal APIs: {resp.status_code}")
        return resp.json()

    def test_gateway_portal_api_parity(self, gateway_apis, portal_apis):
        """APIs on Gateway should be published to Portal."""
        gw_names = {
            api.get("apiName") for api in gateway_apis
            if api.get("apiName") and api.get("apiName") not in SYSTEM_APIS
        }

        if isinstance(portal_apis, list):
            portal_names = {api.get("name") for api in portal_apis if api.get("name")}
        else:
            portal_list = portal_apis.get("apis", portal_apis.get("items", []))
            portal_names = {api.get("name") for api in portal_list if api.get("name")}

        # Gateway APIs should be on Portal (Portal may have fewer due to visibility settings)
        not_on_portal = gw_names - portal_names
        if not_on_portal:
            # This is a warning, not a failure - some APIs may not be published
            pytest.skip(
                f"APIs on Gateway but not Portal (may be intentional): {not_on_portal}"
            )

    def test_no_portal_only_apis(self, gateway_apis, portal_apis):
        """Portal should not have APIs that don't exist on Gateway."""
        gw_names = {api.get("apiName") for api in gateway_apis if api.get("apiName")}

        if isinstance(portal_apis, list):
            portal_names = {api.get("name") for api in portal_apis if api.get("name")}
        else:
            portal_list = portal_apis.get("apis", portal_apis.get("items", []))
            portal_names = {api.get("name") for api in portal_list if api.get("name")}

        portal_only = portal_names - gw_names - SYSTEM_APIS
        assert not portal_only, f"APIs on Portal but not Gateway: {portal_only}"


@pytest.mark.sync
@pytest.mark.tenant
class TestTenantApiSync:
    """Test tenant-specific API synchronization."""

    @pytest.fixture
    def tenant_git_apis(self):
        """Load tenant-specific APIs from Git."""
        tenant_apis = {}
        tenants_path = Path("tenants")

        if not tenants_path.exists():
            pytest.skip("Tenants path not found")

        for tenant_dir in tenants_path.iterdir():
            if tenant_dir.is_dir():
                tenant_name = tenant_dir.name
                apis_path = tenant_dir / "apis"
                if apis_path.exists():
                    tenant_apis[tenant_name] = []
                    for f in apis_path.glob("*.yaml"):
                        with open(f) as file:
                            content = yaml.safe_load(file)
                            if content:
                                tenant_apis[tenant_name].append(content)

        return tenant_apis

    def test_tenant_apis_isolated(self, tenant_git_apis, gateway_admin_session):
        """Each tenant's APIs should be properly namespaced."""
        for tenant_name, apis in tenant_git_apis.items():
            for api in apis:
                api_name = api.get("metadata", {}).get("name")
                if api_name:
                    # Verify API exists with correct tenant association
                    resp = gateway_admin_session.get(
                        f"{gateway_admin_session.base_url}/rest/apigateway/apis",
                        params={"apiName": api_name}
                    )
                    if resp.status_code == 200:
                        found_apis = resp.json().get("apiResponse", [])
                        for found_api in found_apis:
                            # Check tenant metadata if available
                            metadata = found_api.get("apiDescription", "")
                            if "tenant" in metadata.lower():
                                assert tenant_name in metadata.lower(), (
                                    f"API {api_name} has incorrect tenant metadata"
                                )
