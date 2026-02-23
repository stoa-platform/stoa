"""Unit tests for the demo scenario manager."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# The module is named scenario-manager.py (with hyphen), so we use importlib
_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

# Import module with hyphen in filename
_spec = importlib.util.spec_from_file_location(
    "scenario_manager",
    Path(__file__).resolve().parent.parent / "scenario-manager.py",
)
sm = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(sm)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCENARIO = {
    "name": "test-scenario",
    "display_name": "Test Scenario",
    "description": "A test scenario",
    "theme": "testing",
    "tenant": {
        "id": "test-tenant",
        "ref": "tenants/test-tenant/tenant.yaml",
    },
    "personas": [
        {
            "username": "alice",
            "email": "alice@test.demo",
            "first_name": "Alice",
            "last_name": "Smith",
            "role": "tenant-admin",
            "password": "Alice2026!",
            "description": "Admin user",
        },
    ],
    "compliance": {
        "frameworks": ["DORA"],
        "disclaimer": "This is a test disclaimer.",
    },
    "plans": [
        {
            "slug": "standard",
            "display_name": "Standard Plan",
            "rate_limit_per_minute": 100,
            "requires_approval": False,
        },
    ],
    "applications": [
        {
            "name": "Test App",
            "plan": "standard",
            "apis": ["test-api"],
        },
    ],
}


@pytest.fixture
def scenario_dir(tmp_path: Path) -> Path:
    """Create a temporary scenario directory with a valid manifest."""
    sdir = tmp_path / "scenarios" / "test-scenario"
    sdir.mkdir(parents=True)
    manifest = sdir / "scenario.yaml"
    manifest.write_text(yaml.dump(SAMPLE_SCENARIO))

    # Create tenant dir with API
    tenant_dir = tmp_path / "tenants" / "test-tenant" / "apis" / "test-api"
    tenant_dir.mkdir(parents=True)
    (tmp_path / "tenants" / "test-tenant" / "tenant.yaml").write_text(
        yaml.dump({"apiVersion": "stoa.io/v1", "kind": "Tenant", "metadata": {"name": "test-tenant"}})
    )
    (tenant_dir / "api.yaml").write_text(
        yaml.dump(
            {
                "id": "test-api",
                "name": "test-api",
                "display_name": "Test API",
                "version": "1.0.0",
                "description": "A test API",
                "backend_url": "https://httpbin.org/anything",
                "status": "active",
            }
        )
    )
    return tmp_path


# ---------------------------------------------------------------------------
# load_scenario tests
# ---------------------------------------------------------------------------


class TestLoadScenario:
    def test_load_valid_scenario(self, scenario_dir: Path) -> None:
        with patch.object(sm, "SCENARIOS_DIR", scenario_dir / "scenarios"):
            result = sm.load_scenario("test-scenario")
        assert result["name"] == "test-scenario"
        assert result["display_name"] == "Test Scenario"
        assert result["tenant"]["id"] == "test-tenant"

    def test_load_missing_scenario_exits(self, scenario_dir: Path) -> None:
        with patch.object(sm, "SCENARIOS_DIR", scenario_dir / "scenarios"):
            with pytest.raises(SystemExit):
                sm.load_scenario("nonexistent")

    def test_load_scenario_missing_fields_exits(self, scenario_dir: Path) -> None:
        # Write an incomplete manifest
        bad_manifest = scenario_dir / "scenarios" / "bad" / "scenario.yaml"
        bad_manifest.parent.mkdir(parents=True)
        bad_manifest.write_text(yaml.dump({"name": "bad"}))
        with patch.object(sm, "SCENARIOS_DIR", scenario_dir / "scenarios"):
            with pytest.raises(SystemExit):
                sm.load_scenario("bad")


# ---------------------------------------------------------------------------
# discover_apis tests
# ---------------------------------------------------------------------------


class TestDiscoverApis:
    def test_discover_apis_finds_apis(self, scenario_dir: Path) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            apis = sm.discover_apis("test-tenant")
        assert len(apis) == 1
        assert apis[0]["id"] == "test-api"

    def test_discover_apis_empty_for_missing_tenant(self, scenario_dir: Path) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            apis = sm.discover_apis("nonexistent")
        assert apis == []


# ---------------------------------------------------------------------------
# cmd_setup dry-run tests
# ---------------------------------------------------------------------------


class TestSetupDryRun:
    def test_dry_run_returns_zero(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            result = sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "test-tenant" in captured.out

    def test_dry_run_shows_personas(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "alice" in captured.out
        assert "tenant-admin" in captured.out

    def test_dry_run_shows_apis(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "test-api" in captured.out

    def test_dry_run_shows_compliance_disclaimer(
        self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "test disclaimer" in captured.out

    def test_dry_run_shows_plans(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "standard" in captured.out
        assert "100/min" in captured.out

    def test_dry_run_shows_applications(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "REPO_ROOT", scenario_dir):
            sm.cmd_setup(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "Test App" in captured.out


# ---------------------------------------------------------------------------
# cmd_teardown dry-run tests
# ---------------------------------------------------------------------------


class TestTeardownDryRun:
    def test_dry_run_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = sm.cmd_teardown(SAMPLE_SCENARIO, dry_run=True)
        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out

    def test_dry_run_shows_persona_deletion(self, capsys: pytest.CaptureFixture[str]) -> None:
        sm.cmd_teardown(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "alice" in captured.out
        assert "DELETE" in captured.out

    def test_dry_run_shows_tenant_deletion(self, capsys: pytest.CaptureFixture[str]) -> None:
        sm.cmd_teardown(SAMPLE_SCENARIO, dry_run=True)
        captured = capsys.readouterr()
        assert "test-tenant" in captured.out


# ---------------------------------------------------------------------------
# cmd_list tests
# ---------------------------------------------------------------------------


class TestList:
    def test_list_finds_scenarios(self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(sm, "SCENARIOS_DIR", scenario_dir / "scenarios"):
            result = sm.cmd_list()
        assert result == 0
        captured = capsys.readouterr()
        assert "test-scenario" in captured.out

    def test_list_empty_dir(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with patch.object(sm, "SCENARIOS_DIR", empty):
            result = sm.cmd_list()
        assert result == 0
        captured = capsys.readouterr()
        assert "No scenarios found" in captured.out


# ---------------------------------------------------------------------------
# Setup with mocked HTTP tests
# ---------------------------------------------------------------------------


class TestSetupWithMockedHTTP:
    def test_setup_handles_connection_error(
        self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Setup should return 1 when CP API is unreachable."""
        import httpx

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.close = MagicMock()

        with (
            patch.object(sm, "REPO_ROOT", scenario_dir),
            patch.object(sm, "ADMIN_PASSWORD", ""),
            patch.object(sm, "create_api_client", return_value=mock_client),
            patch.object(sm, "get_api_token", return_value=None),
        ):
            # Scenario without personas to skip Keycloak
            no_persona = {**SAMPLE_SCENARIO, "personas": []}
            result = sm.cmd_setup(no_persona, dry_run=False)

        assert result == 1

    def test_setup_creates_tenant_successfully(
        self, scenario_dir: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Setup should handle 201 from tenant creation."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 201

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.post.return_value = mock_response
        mock_client.close = MagicMock()

        with (
            patch.object(sm, "REPO_ROOT", scenario_dir),
            patch.object(sm, "ADMIN_PASSWORD", ""),
            patch.object(sm, "create_api_client", return_value=mock_client),
            patch.object(sm, "get_api_token", return_value=None),
        ):
            no_persona = {**SAMPLE_SCENARIO, "personas": []}
            result = sm.cmd_setup(no_persona, dry_run=False)

        assert result == 0
        captured = capsys.readouterr()
        assert "setup complete" in captured.out


# ---------------------------------------------------------------------------
# Keycloak helper tests
# ---------------------------------------------------------------------------


class TestKeycloakHelpers:
    def test_get_admin_token_no_password(self) -> None:
        with patch.object(sm, "ADMIN_PASSWORD", ""):
            assert sm.get_keycloak_admin_token() is None

    def test_get_admin_token_success(self) -> None:
        mock_post = MagicMock(return_value=MagicMock(status_code=200, json=lambda: {"access_token": "tok123"}))
        with patch.object(sm, "ADMIN_PASSWORD", "secret"), patch.object(sm.httpx, "post", mock_post):
            token = sm.get_keycloak_admin_token()
        assert token == "tok123"

    def test_create_user_success(self) -> None:
        mock_post = MagicMock(return_value=MagicMock(status_code=201))
        with patch.object(sm.httpx, "post", mock_post):
            persona = {"username": "test", "email": "test@demo", "first_name": "T", "last_name": "U"}
            assert sm.create_keycloak_user("token", persona, "tenant") is True

    def test_create_user_conflict(self) -> None:
        mock_post = MagicMock(return_value=MagicMock(status_code=409))
        with patch.object(sm.httpx, "post", mock_post):
            persona = {"username": "test"}
            assert sm.create_keycloak_user("token", persona, "tenant") is True

    def test_delete_user_not_found(self) -> None:
        mock_get = MagicMock(return_value=MagicMock(status_code=200, json=lambda: []))
        with patch.object(sm.httpx, "get", mock_get):
            assert sm.delete_keycloak_user("token", "nobody") is False
