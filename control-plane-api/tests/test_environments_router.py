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
