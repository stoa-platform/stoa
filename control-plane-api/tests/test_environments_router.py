"""Tests for Environments Router — CAB-1448

Covers: GET /v1/environments (single endpoint, returns hardcoded defaults).
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
        assert "prod" in names

    def test_list_environments_cpi_admin(self, client_as_cpi_admin):
        resp = client_as_cpi_admin.get("/v1/environments")
        assert resp.status_code == 200
        assert len(resp.json()["environments"]) == 3

    def test_list_environments_modes(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["mode"] == "full"
        assert envs["staging"]["mode"] == "full"
        assert envs["prod"]["mode"] == "read-only"

    def test_list_environments_colors(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["color"] == "green"
        assert envs["staging"]["color"] == "amber"
        assert envs["prod"]["color"] == "red"

    def test_list_environments_labels(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        envs = {e["name"]: e for e in resp.json()["environments"]}
        assert envs["dev"]["label"] == "Development"
        assert envs["staging"]["label"] == "Staging"
        assert envs["prod"]["label"] == "Production"
