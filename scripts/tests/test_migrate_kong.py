"""Tests for Kong -> STOA migration adapter."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# Allow importing the script (hyphenated filename) from parent dir
import importlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_mod = importlib.import_module("migrate-kong")
KongToStoaMigrator = _mod.KongToStoaMigrator
_slugify = _mod._slugify
load_from_file = _mod.load_from_file
_count_kong_objects = _mod._count_kong_objects

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_KONG = FIXTURES / "sample-kong.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def kong_config() -> dict:
    return load_from_file(str(SAMPLE_KONG))


@pytest.fixture()
def migrated(kong_config: dict) -> KongToStoaMigrator:
    m = KongToStoaMigrator(kong_config)
    m.migrate()
    return m


# ---------------------------------------------------------------------------
# Unit: slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self):
        assert _slugify("petstore-service") == "petstore-service"

    def test_spaces_and_caps(self):
        assert _slugify("My Cool Service") == "my-cool-service"

    def test_special_chars(self):
        assert _slugify("api@v2!") == "api-v2"

    def test_leading_trailing(self):
        assert _slugify("---hello---") == "hello"


# ---------------------------------------------------------------------------
# Unit: load_from_file
# ---------------------------------------------------------------------------


class TestLoadFromFile:
    def test_loads_sample(self, kong_config: dict):
        assert "_format_version" in kong_config
        assert "services" in kong_config
        assert len(kong_config["services"]) == 3

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_from_file("/nonexistent/kong.yaml")

    def test_has_upstreams(self, kong_config: dict):
        assert "upstreams" in kong_config
        assert len(kong_config["upstreams"]) == 2

    def test_has_consumers(self, kong_config: dict):
        assert "consumers" in kong_config
        assert len(kong_config["consumers"]) == 3


# ---------------------------------------------------------------------------
# Unit: _count_kong_objects
# ---------------------------------------------------------------------------


class TestCountKongObjects:
    def test_counts(self, kong_config: dict):
        svc, routes, plugins = _count_kong_objects(kong_config)
        assert svc == 3
        assert routes == 4
        assert plugins == 10  # 8 service plugins + 2 global


# ---------------------------------------------------------------------------
# Integration: service -> API mapping
# ---------------------------------------------------------------------------


class TestServiceMigration:
    def test_all_services_migrated(self, migrated: KongToStoaMigrator):
        assert len(migrated.apis) == 3

    def test_petstore_api(self, migrated: KongToStoaMigrator):
        pet = next(a for a in migrated.apis if a["id"] == "petstore-service")
        assert pet["backend_url"] == "https://petstore.swagger.io/v2"
        assert pet["status"] == "draft"
        assert "petstore" in pet["tags"]

    def test_crm_api_has_auth(self, migrated: KongToStoaMigrator):
        crm = next(a for a in migrated.apis if a["id"] == "crm-api-service")
        assert crm["auth"]["required"] is True

    def test_payment_api_has_auth(self, migrated: KongToStoaMigrator):
        pay = next(a for a in migrated.apis if a["id"] == "payment-gateway")
        assert pay["auth"]["required"] is True


# ---------------------------------------------------------------------------
# Integration: route -> resource mapping
# ---------------------------------------------------------------------------


class TestRouteMigration:
    def test_petstore_has_one_resource(self, migrated: KongToStoaMigrator):
        pet = next(a for a in migrated.apis if a["id"] == "petstore-service")
        assert len(pet["resources"]) == 1
        assert pet["resources"][0]["path"] == "/petstore/*"

    def test_crm_has_two_resources(self, migrated: KongToStoaMigrator):
        crm = next(a for a in migrated.apis if a["id"] == "crm-api-service")
        assert len(crm["resources"]) == 2
        paths = {r["path"] for r in crm["resources"]}
        assert "/crm/v2/*" in paths
        assert "/crm/search/*" in paths

    def test_route_methods(self, migrated: KongToStoaMigrator):
        pay = next(a for a in migrated.apis if a["id"] == "payment-gateway")
        assert pay["resources"][0]["methods"] == ["POST"]


# ---------------------------------------------------------------------------
# Integration: plugin -> policy mapping
# ---------------------------------------------------------------------------


class TestPluginMigration:
    def test_rate_limit_policies_created(self, migrated: KongToStoaMigrator):
        rl_policies = [p for p in migrated.policies if p["type"] == "rate-limit"]
        assert len(rl_policies) >= 2  # petstore + crm + payment

    def test_cors_policy_created(self, migrated: KongToStoaMigrator):
        cors_policies = [p for p in migrated.policies if p["type"] == "cors"]
        assert len(cors_policies) == 1
        cfg = cors_policies[0]["config"]
        assert "https://portal.example.com" in cfg["allowOrigins"]

    def test_unsupported_plugin_in_manual_actions(self, migrated: KongToStoaMigrator):
        manual = migrated.report.manual_actions
        assert any("request-transformer" in a for a in manual)
        assert any("ip-restriction" in a for a in manual)


# ---------------------------------------------------------------------------
# Integration: consumer -> tenant/application mapping
# ---------------------------------------------------------------------------


class TestConsumerMigration:
    def test_tenants_created(self, migrated: KongToStoaMigrator):
        assert len(migrated.tenants) == 2  # acme-corp, beta-team

    def test_applications_created(self, migrated: KongToStoaMigrator):
        assert len(migrated.applications) == 1  # monitoring-bot

    def test_acme_tenant_has_rate_limit(self, migrated: KongToStoaMigrator):
        acme = next(t for t in migrated.tenants if t["id"] == "tenant-acme")
        assert "rateLimit" in acme["settings"]
        assert acme["settings"]["rateLimit"]["requests"] == 500

    def test_monitoring_bot_is_application(self, migrated: KongToStoaMigrator):
        app = migrated.applications[0]
        assert app["id"] == "monitoring-bot"
        assert app["type"] == "service"


# ---------------------------------------------------------------------------
# Integration: upstream -> backend targets
# ---------------------------------------------------------------------------


class TestUpstreamMigration:
    def test_petstore_has_upstream(self, migrated: KongToStoaMigrator):
        pet = next(a for a in migrated.apis if a["id"] == "petstore-service")
        assert "backend" in pet
        assert pet["backend"]["algorithm"] == "round-robin"
        assert len(pet["backend"]["targets"]) == 2

    def test_upstream_healthcheck(self, migrated: KongToStoaMigrator):
        pet = next(a for a in migrated.apis if a["id"] == "petstore-service")
        assert "healthCheck" in pet["backend"]
        assert pet["backend"]["healthCheck"]["path"] == "/health"


# ---------------------------------------------------------------------------
# Integration: stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_stats_keys(self, migrated: KongToStoaMigrator):
        st = migrated.stats()
        assert st["apis"] == 3
        assert st["tenants"] == 2
        assert st["applications"] == 1
        assert st["policies"] == 4
        assert st["migrated"] > 0
        assert st["manual"] > 0

    def test_skipped_count(self, migrated: KongToStoaMigrator):
        st = migrated.stats()
        assert st["skipped"] == 2  # prometheus + file-log


# ---------------------------------------------------------------------------
# Integration: YAML output
# ---------------------------------------------------------------------------


class TestYamlOutput:
    def test_valid_yaml(self, migrated: KongToStoaMigrator):
        output = migrated.to_stoa_yaml()
        parsed = yaml.safe_load(output)
        assert parsed["apiVersion"] == "stoa.io/v1"
        assert parsed["kind"] == "StoaExport"

    def test_has_all_sections(self, migrated: KongToStoaMigrator):
        output = migrated.to_stoa_yaml()
        parsed = yaml.safe_load(output)
        spec = parsed["spec"]
        assert "apis" in spec
        assert "policies" in spec
        assert "tenants" in spec
        assert "applications" in spec

    def test_apis_count(self, migrated: KongToStoaMigrator):
        output = migrated.to_stoa_yaml()
        parsed = yaml.safe_load(output)
        assert len(parsed["spec"]["apis"]) == 3


# ---------------------------------------------------------------------------
# Integration: migration report
# ---------------------------------------------------------------------------


class TestMigrationReport:
    def test_report_is_markdown(self, migrated: KongToStoaMigrator):
        report = migrated.report.render()
        assert "# Kong" in report
        assert "STOA Migration Report" in report

    def test_report_has_migrated(self, migrated: KongToStoaMigrator):
        report = migrated.report.render()
        assert "## Migrated" in report
        assert "petstore-service" in report

    def test_report_has_manual_actions(self, migrated: KongToStoaMigrator):
        report = migrated.report.render()
        assert "## Manual Actions Required" in report

    def test_report_has_summary_table(self, migrated: KongToStoaMigrator):
        report = migrated.report.render()
        assert "## Migration Summary" in report
        assert "| Migrated |" in report


# ---------------------------------------------------------------------------
# Integration: CLI (main function)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_main_file_input(self, tmp_path: Path):
        main = _mod.main

        out = tmp_path / "output"
        rc = main(["--from", str(SAMPLE_KONG), "--to", str(out)])
        assert rc == 0
        assert (out / "stoa-apis.yaml").exists()
        assert (out / "migration-report.md").exists()

        # Validate output YAML
        parsed = yaml.safe_load((out / "stoa-apis.yaml").read_text())
        assert parsed["apiVersion"] == "stoa.io/v1"
        assert len(parsed["spec"]["apis"]) == 3

    def test_main_missing_source(self, tmp_path: Path):
        main = _mod.main

        rc = main(["--from", "/nonexistent.yaml", "--to", str(tmp_path)])
        assert rc == 1

    def test_main_verbose(self, tmp_path: Path, capsys):
        main = _mod.main

        out = tmp_path / "output"
        rc = main(["--from", str(SAMPLE_KONG), "--to", str(out), "--verbose"])
        assert rc == 0
        captured = capsys.readouterr()
        # Verbose shows detail lines with indentation
        assert "route" in captured.out
        assert "plugin" in captured.out or "upstream" in captured.out

    def test_main_quiet(self, tmp_path: Path, capsys):
        main = _mod.main

        out = tmp_path / "output"
        rc = main(["--from", str(SAMPLE_KONG), "--to", str(out), "--quiet"])
        assert rc == 0
        captured = capsys.readouterr()
        # Quiet mode: no progress lines (but output_files still prints)
        assert "Migrating" not in captured.out


# ---------------------------------------------------------------------------
# Integration: dry-run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_files(self, tmp_path: Path):
        main = _mod.main

        rc = main(["--from", str(SAMPLE_KONG), "--dry-run"])
        assert rc == 0
        # No files should be written anywhere
        assert not (tmp_path / "stoa-apis.yaml").exists()

    def test_dry_run_output(self, capsys):
        main = _mod.main

        rc = main(["--from", str(SAMPLE_KONG), "--dry-run"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        assert "Would produce" in captured.out
        assert "3 APIs" in captured.out

    def test_dry_run_with_to_still_no_files(self, tmp_path: Path):
        """Even if --to is given with --dry-run, no files are written."""
        main = _mod.main

        out = tmp_path / "dry-output"
        rc = main(["--from", str(SAMPLE_KONG), "--to", str(out), "--dry-run"])
        assert rc == 0
        assert not out.exists()

    def test_no_to_without_dry_run(self):
        """--to is required when --dry-run is not set."""
        main = _mod.main

        with pytest.raises(SystemExit):
            main(["--from", str(SAMPLE_KONG)])


# ---------------------------------------------------------------------------
# Integration: error UX
# ---------------------------------------------------------------------------


class TestErrorUX:
    def test_missing_file_error_message(self, capsys, tmp_path: Path):
        main = _mod.main

        rc = main(["--from", "/no/such/kong.yaml", "--to", str(tmp_path)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Cannot read Kong config" in captured.err
        assert "Expected: kong.yaml" in captured.err

    def test_connection_error_message(self, capsys, tmp_path: Path):
        main = _mod.main

        rc = main(["--from", "http://localhost:19999", "--to", str(tmp_path)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Cannot connect to Kong" in captured.err
        assert "Is Kong running?" in captured.err
