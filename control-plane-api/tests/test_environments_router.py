"""Tests for Environments Router — CAB-1448 / CAB-1659

Covers: GET /v1/environments with connection URLs for multi-backend switching.
"""


class TestListEnvironments:
    """Tests for GET /v1/environments."""

    def test_list_environments_tenant_admin(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")

        assert resp.status_code == 200
        data = resp.json()
        envs = data["environments"]
        assert len(envs) == 3
        names = [e["name"] for e in envs]
        assert "dev" in names
        assert "staging" in names
        assert "production" in names
        assert "current" in data

    def test_list_environments_cpi_admin(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.get("/v1/environments")
        assert resp.status_code == 200
        assert len(resp.json()["environments"]) == 3

    def test_list_environments_modes(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["mode"] == "full"
        assert envs["staging"]["mode"] == "full"
        assert envs["production"]["mode"] == "read-only"

    def test_list_environments_colors(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["color"] == "#22c55e"
        assert envs["staging"]["color"] == "#f59e0b"
        assert envs["production"]["color"] == "#ef4444"

    def test_list_environments_labels(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["label"] == "Development"
        assert envs["staging"]["label"] == "Staging"
        assert envs["production"]["label"] == "Production"


class TestEnvironmentEndpoints:
    """Tests for environment connection URLs (CAB-1659)."""

    def test_environments_include_endpoints(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}

        for name, env in envs.items():
            assert env["endpoints"] is not None, f"{name} missing endpoints"
            endpoints = env["endpoints"]
            assert "api_url" in endpoints
            assert "keycloak_url" in endpoints
            assert "keycloak_realm" in endpoints
            assert "mcp_url" in endpoints

    def test_production_endpoints_use_base_domain(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        prod = envs["production"]["endpoints"]

        assert "api." in prod["api_url"]
        assert "auth." in prod["keycloak_url"]
        assert "mcp." in prod["mcp_url"]
        assert prod["keycloak_realm"] == "stoa"

    def test_staging_endpoints_use_staging_prefix(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        staging = envs["staging"]["endpoints"]

        assert "staging-api." in staging["api_url"]
        assert "staging-auth." in staging["keycloak_url"]
        assert "staging-mcp." in staging["mcp_url"]

    def test_dev_endpoints_use_dev_prefix(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        dev = envs["dev"]["endpoints"]

        assert "dev-api." in dev["api_url"]
        assert "dev-auth." in dev["keycloak_url"]
        assert "dev-mcp." in dev["mcp_url"]

    def test_current_environment_marked(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        data = resp.json()

        # current field references a valid environment name
        assert data["current"] in [e["name"] for e in data["environments"]]


class TestPublicEnvironments:
    """Tests for GET /v1/environments/public — no auth required (CAB-1663)."""

    def test_public_environments_no_auth(self, client):
        """Public endpoint should return 200 without any Bearer token."""
        resp = client.get("/v1/environments/public")
        assert resp.status_code == 200

    def test_public_environments_shape(self, client):
        """Public response must only expose safe fields, never keycloak_url or mcp_url."""
        resp = client.get("/v1/environments/public")
        data = resp.json()
        assert "environments" in data
        assert "current" in data
        assert len(data["environments"]) >= 2

        for env in data["environments"]:
            # Expected public fields
            assert "name" in env
            assert "label" in env
            assert "mode" in env
            assert "color" in env
            assert "health_url" in env
            # Must NOT expose sensitive fields
            assert "keycloak_url" not in env
            assert "mcp_url" not in env
            assert "endpoints" not in env

    def test_public_environments_health_url_format(self, client):
        """Each health_url should end with /health and use public-facing URLs."""
        resp = client.get("/v1/environments/public")
        for env in resp.json()["environments"]:
            assert env["health_url"].endswith("/health")
            # Should use https:// public-facing URLs, not internal K8s service names
            assert "https://" in env["health_url"] or env["health_url"] == ""

    def test_authenticated_environments_requires_auth(self, client):
        """GET /v1/environments (authenticated) should return 401 without token."""
        resp = client.get("/v1/environments")
        assert resp.status_code == 401
