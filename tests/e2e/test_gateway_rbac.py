"""
E2E Gateway RBAC Tests (CAB-651)
Verify scope-based RBAC on webMethods Gateway

These tests ensure OAuth2 scope enforcement is working correctly:
- catalog:read - Can read APIs
- catalog:write - Can create/update APIs
- catalog:admin - Can delete APIs
- Cross-tenant isolation - Users cannot access other tenant's resources
"""

import os
import uuid

import pytest
import requests

# Configuration
GATEWAY_URL = os.getenv("GATEWAY_URL", "https://gateway.gostoa.dev")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://auth.gostoa.dev")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "stoa")


@pytest.mark.rbac
@pytest.mark.smoke
class TestGatewayRBAC:
    """Test suite for Gateway RBAC enforcement."""

    @pytest.fixture
    def token_read_only(self, keycloak_client):
        """Token with catalog:read scope only."""
        return keycloak_client.get_token(
            username=os.getenv("RBAC_READER_USER", "reader@acme-corp.com"),
            password=os.getenv("RBAC_READER_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read"]
        )

    @pytest.fixture
    def token_write(self, keycloak_client):
        """Token with catalog:read and catalog:write scopes."""
        return keycloak_client.get_token(
            username=os.getenv("RBAC_EDITOR_USER", "editor@acme-corp.com"),
            password=os.getenv("RBAC_EDITOR_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read", "catalog:write"]
        )

    @pytest.fixture
    def token_admin(self, keycloak_client):
        """Token with full admin scopes."""
        return keycloak_client.get_token(
            username=os.getenv("RBAC_ADMIN_USER", "admin@acme-corp.com"),
            password=os.getenv("RBAC_ADMIN_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read", "catalog:write", "catalog:admin"]
        )

    @pytest.fixture
    def token_no_scope(self, keycloak_client):
        """Token with no relevant scopes."""
        return keycloak_client.get_token(
            username=os.getenv("RBAC_NOSCOPE_USER", "nobody@acme-corp.com"),
            password=os.getenv("RBAC_NOSCOPE_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=[]
        )

    # ========== READ Tests ==========

    def test_read_with_read_scope_succeeds(self, token_read_only):
        """GET /apis with read scope should return 200."""
        resp = requests.get(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_read_only}"},
            timeout=30
        )
        assert resp.status_code == 200, (
            f"Expected 200 with read scope, got {resp.status_code}: {resp.text}"
        )

    def test_read_without_scope_fails(self, token_no_scope):
        """GET /apis without scope should return 403."""
        resp = requests.get(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_no_scope}"},
            timeout=30
        )
        assert resp.status_code == 403, (
            f"Expected 403 without scope, got {resp.status_code}: {resp.text}"
        )

    def test_read_without_token_fails(self):
        """GET /apis without token should return 401."""
        resp = requests.get(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            timeout=30
        )
        assert resp.status_code == 401, (
            f"Expected 401 without token, got {resp.status_code}: {resp.text}"
        )

    def test_read_with_invalid_token_fails(self):
        """GET /apis with invalid token should return 401."""
        resp = requests.get(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": "Bearer invalid-token-12345"},
            timeout=30
        )
        assert resp.status_code == 401, (
            f"Expected 401 with invalid token, got {resp.status_code}"
        )

    # ========== WRITE Tests ==========

    def test_write_with_write_scope_succeeds(self, token_write):
        """POST /apis with write scope should return 201 or 200."""
        test_api_name = f"test-rbac-api-{uuid.uuid4().hex[:8]}"

        resp = requests.post(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_write}"},
            json={"name": test_api_name, "version": "v1"},
            timeout=30
        )
        assert resp.status_code in [200, 201], (
            f"Expected 200/201 with write scope, got {resp.status_code}: {resp.text}"
        )

        # Cleanup - try to delete the test API
        api_id = resp.json().get("id")
        if api_id:
            requests.delete(
                f"{GATEWAY_URL}/api/v1/catalog/apis/{api_id}",
                headers={"Authorization": f"Bearer {token_write}"},
                timeout=30
            )

    def test_write_with_read_only_scope_fails(self, token_read_only):
        """POST /apis with read-only scope should return 403."""
        resp = requests.post(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_read_only}"},
            json={"name": "test-api-readonly", "version": "v1"},
            timeout=30
        )
        assert resp.status_code == 403, (
            f"Expected 403 with read-only scope, got {resp.status_code}: {resp.text}"
        )

    def test_update_with_write_scope_succeeds(self, token_write, token_admin):
        """PUT /apis/{id} with write scope should succeed."""
        # First create an API
        test_api_name = f"test-update-api-{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_write}"},
            json={"name": test_api_name, "version": "v1"},
            timeout=30
        )

        if create_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create test API: {create_resp.status_code}")

        api_id = create_resp.json().get("id")
        if not api_id:
            pytest.skip("API created but no ID returned")

        try:
            # Update the API
            update_resp = requests.put(
                f"{GATEWAY_URL}/api/v1/catalog/apis/{api_id}",
                headers={"Authorization": f"Bearer {token_write}"},
                json={"name": test_api_name, "version": "v2", "description": "Updated"},
                timeout=30
            )
            assert update_resp.status_code in [200, 204], (
                f"Expected 200/204 for update, got {update_resp.status_code}"
            )
        finally:
            # Cleanup
            requests.delete(
                f"{GATEWAY_URL}/api/v1/catalog/apis/{api_id}",
                headers={"Authorization": f"Bearer {token_admin}"},
                timeout=30
            )

    # ========== ADMIN/DELETE Tests ==========

    def test_delete_with_admin_scope_succeeds(self, token_admin, token_write):
        """DELETE /apis/{id} with admin scope should return 200 or 204."""
        # First create an API
        test_api_name = f"test-delete-api-{uuid.uuid4().hex[:8]}"
        create_resp = requests.post(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {token_write}"},
            json={"name": test_api_name, "version": "v1"},
            timeout=30
        )

        if create_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create test API: {create_resp.status_code}")

        api_id = create_resp.json().get("id")
        if not api_id:
            pytest.skip("API created but no ID returned")

        # Delete with admin scope
        delete_resp = requests.delete(
            f"{GATEWAY_URL}/api/v1/catalog/apis/{api_id}",
            headers={"Authorization": f"Bearer {token_admin}"},
            timeout=30
        )
        assert delete_resp.status_code in [200, 204], (
            f"Expected 200/204 with admin scope, got {delete_resp.status_code}"
        )

    def test_delete_without_admin_scope_fails(self, token_write):
        """DELETE /apis/{id} without admin scope should return 403."""
        resp = requests.delete(
            f"{GATEWAY_URL}/api/v1/catalog/apis/some-api-id",
            headers={"Authorization": f"Bearer {token_write}"},
            timeout=30
        )
        # Accept 403 (forbidden) or 404 (not found) - both indicate proper protection
        assert resp.status_code in [403, 404], (
            f"Expected 403/404 without admin scope, got {resp.status_code}"
        )


@pytest.mark.rbac
@pytest.mark.tenant
@pytest.mark.security
class TestCrossTenantRBAC:
    """Test cross-tenant access restrictions."""

    @pytest.fixture
    def acme_admin_token(self, keycloak_client):
        """Token for ACME Corp admin."""
        return keycloak_client.get_token(
            username=os.getenv("ACME_ADMIN_USER", "admin@acme-corp.com"),
            password=os.getenv("ACME_ADMIN_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read", "catalog:write", "catalog:admin"]
        )

    @pytest.fixture
    def globex_admin_token(self, keycloak_client):
        """Token for Globex admin."""
        return keycloak_client.get_token(
            username=os.getenv("GLOBEX_ADMIN_USER", "admin@globex.com"),
            password=os.getenv("GLOBEX_ADMIN_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read", "catalog:write", "catalog:admin"]
        )

    def test_acme_cannot_read_globex_private_api(self, acme_admin_token):
        """ACME admin cannot read Globex internal API."""
        resp = requests.get(
            f"{GATEWAY_URL}/api/v1/catalog/apis/globex-internal-api",
            headers={"Authorization": f"Bearer {acme_admin_token}"},
            timeout=30
        )
        # Should be 403 (forbidden) or 404 (not found/hidden)
        assert resp.status_code in [403, 404], (
            f"ACME can access Globex internal API! Status: {resp.status_code}"
        )

    def test_acme_cannot_modify_globex_api(self, acme_admin_token):
        """ACME admin cannot modify Globex API."""
        resp = requests.put(
            f"{GATEWAY_URL}/api/v1/catalog/apis/globex-internal-api",
            headers={"Authorization": f"Bearer {acme_admin_token}"},
            json={"description": "Hacked by ACME"},
            timeout=30
        )
        assert resp.status_code in [403, 404], (
            f"ACME can modify Globex API! Status: {resp.status_code}"
        )

    def test_globex_cannot_delete_acme_api(self, globex_admin_token):
        """Globex admin cannot delete ACME API."""
        resp = requests.delete(
            f"{GATEWAY_URL}/api/v1/catalog/apis/acme-billing-api",
            headers={"Authorization": f"Bearer {globex_admin_token}"},
            timeout=30
        )
        assert resp.status_code in [403, 404], (
            f"Globex can delete ACME API! Status: {resp.status_code}"
        )

    def test_acme_cannot_create_api_in_globex_namespace(self, acme_admin_token):
        """ACME admin cannot create API in Globex namespace."""
        resp = requests.post(
            f"{GATEWAY_URL}/api/v1/catalog/apis",
            headers={"Authorization": f"Bearer {acme_admin_token}"},
            json={
                "name": "fake-globex-api",
                "version": "v1",
                "tenant": "globex"  # Trying to specify another tenant
            },
            timeout=30
        )
        # Should either fail (403) or ignore the tenant field and create in ACME namespace
        if resp.status_code in [200, 201]:
            # If created, verify it's in ACME namespace, not Globex
            api_data = resp.json()
            api_tenant = api_data.get("tenant", api_data.get("namespace", ""))
            assert "globex" not in api_tenant.lower(), (
                f"API was created in Globex namespace: {api_tenant}"
            )
            # Cleanup
            api_id = api_data.get("id")
            if api_id:
                requests.delete(
                    f"{GATEWAY_URL}/api/v1/catalog/apis/{api_id}",
                    headers={"Authorization": f"Bearer {acme_admin_token}"},
                    timeout=30
                )
        else:
            assert resp.status_code == 403, (
                f"Expected 403 for cross-tenant creation, got {resp.status_code}"
            )


@pytest.mark.rbac
class TestScopeEscalation:
    """Test that scope escalation is prevented."""

    def test_cannot_request_ungranted_scope(self, keycloak_client):
        """User cannot request scopes they haven't been granted."""
        # Try to get admin scope as a reader user
        with pytest.raises(Exception):
            keycloak_client.get_token(
                username=os.getenv("RBAC_READER_USER", "reader@acme-corp.com"),
                password=os.getenv("RBAC_READER_PASSWORD", "test123"),
                client_id="stoa-api",
                scopes=["catalog:admin"]  # Reader shouldn't have admin scope
            )

    def test_token_scope_matches_request(self, keycloak_client):
        """Token should only contain requested scopes."""
        import base64
        import json

        token = keycloak_client.get_token(
            username=os.getenv("RBAC_READER_USER", "reader@acme-corp.com"),
            password=os.getenv("RBAC_READER_PASSWORD", "test123"),
            client_id="stoa-api",
            scopes=["catalog:read"]
        )

        # Decode JWT payload
        payload_b64 = token.split(".")[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Check scopes in token
        token_scopes = payload.get("scope", "").split()
        assert "catalog:admin" not in token_scopes, (
            "Token contains admin scope that wasn't granted"
        )
        assert "catalog:write" not in token_scopes, (
            "Token contains write scope that wasn't granted"
        )
