"""Tests for environments router — GET /v1/environments"""


class TestListEnvironments:
    def test_list_returns_three_envs(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        assert resp.status_code == 200
        envs = resp.json()["environments"]
        assert len(envs) == 3
        names = [e["name"] for e in envs]
        assert names == ["dev", "staging", "prod"]

    def test_environments_contain_expected_fields(self, client_as_tenant_admin):
        resp = client_as_tenant_admin.get("/v1/environments")
        env = resp.json()["environments"][0]
        assert "name" in env
        assert "label" in env
        assert "mode" in env
        assert "color" in env

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/v1/environments")
        assert resp.status_code == 401
