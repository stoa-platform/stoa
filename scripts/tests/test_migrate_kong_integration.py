"""
Integration test: Kong Docker -> migrate-kong.py -> STOA YAML.

Requires Docker. Spins up Kong with declarative config, runs the migration
against the Admin API, and validates the output.

Run:
  pytest tests/test_migrate_kong_integration.py -v -m integration

Skip in CI without Docker:
  pytest -m "not integration"
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
_mod = importlib.import_module("migrate-kong")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_KONG = FIXTURES / "sample-kong.yaml"

KONG_IMAGE = "kong/kong:3.9"
KONG_CONTAINER = "stoa-migrate-test-kong"
KONG_ADMIN_PORT = 18001


def _docker_available() -> bool:
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _wait_for_kong(url: str, retries: int = 30, delay: float = 1.0) -> bool:
    for _ in range(retries):
        try:
            resp = urlopen(url, timeout=2)  # noqa: S310
            if resp.status == 200:
                return True
        except (URLError, OSError):
            pass
        time.sleep(delay)
    return False


@pytest.fixture(scope="module")
def kong_admin_url():
    """Start Kong in DB-less mode with sample config, yield admin URL, tear down."""
    if not _docker_available():
        pytest.skip("Docker not available")

    # Stop any leftover container
    subprocess.run(
        ["docker", "rm", "-f", KONG_CONTAINER],
        capture_output=True,
    )

    # Start Kong DB-less with declarative config
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            KONG_CONTAINER,
            "-e",
            "KONG_DATABASE=off",
            "-e",
            f"KONG_DECLARATIVE_CONFIG=/kong/kong.yaml",
            "-e",
            "KONG_ADMIN_LISTEN=0.0.0.0:8001",
            "-e",
            "KONG_PROXY_LISTEN=0.0.0.0:8000",
            "-v",
            f"{SAMPLE_KONG}:/kong/kong.yaml:ro",
            "-p",
            f"{KONG_ADMIN_PORT}:8001",
            KONG_IMAGE,
        ],
        check=True,
        capture_output=True,
    )

    url = f"http://localhost:{KONG_ADMIN_PORT}"

    if not _wait_for_kong(url):
        # Grab logs for debugging
        logs = subprocess.run(
            ["docker", "logs", KONG_CONTAINER],
            capture_output=True,
            text=True,
        )
        subprocess.run(["docker", "rm", "-f", KONG_CONTAINER], capture_output=True)
        pytest.fail(f"Kong did not start.\nLogs:\n{logs.stdout}\n{logs.stderr}")

    yield url

    # Teardown
    subprocess.run(["docker", "rm", "-f", KONG_CONTAINER], capture_output=True)


@pytest.mark.integration
class TestKongAdminAPIMigration:
    """Full integration: Kong Docker -> Admin API -> migrate-kong.py -> STOA."""

    def test_admin_api_accessible(self, kong_admin_url: str):
        resp = urlopen(kong_admin_url, timeout=5)  # noqa: S310
        data = json.loads(resp.read())
        assert "version" in data

    def test_services_loaded(self, kong_admin_url: str):
        resp = urlopen(f"{kong_admin_url}/services", timeout=5)  # noqa: S310
        data = json.loads(resp.read())
        names = {s["name"] for s in data.get("data", [])}
        assert "petstore-service" in names
        assert "crm-api-service" in names
        assert "payment-gateway" in names

    def test_full_migration_from_admin_api(self, kong_admin_url: str, tmp_path: Path):
        main = _mod.main

        out = tmp_path / "stoa-output"
        rc = main(["--from", kong_admin_url, "--to", str(out)])
        assert rc == 0

        # Validate output files exist
        assert (out / "stoa-apis.yaml").exists()
        assert (out / "migration-report.md").exists()

        # Validate YAML structure
        parsed = yaml.safe_load((out / "stoa-apis.yaml").read_text())
        assert parsed["apiVersion"] == "stoa.io/v1"
        assert parsed["kind"] == "StoaExport"
        assert len(parsed["spec"]["apis"]) == 3

    def test_dry_run_from_admin_api(self, kong_admin_url: str, capsys):
        main = _mod.main

        rc = main(["--from", kong_admin_url, "--dry-run"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        assert "3 APIs" in captured.out

    def test_verbose_from_admin_api(self, kong_admin_url: str, tmp_path: Path, capsys):
        main = _mod.main

        out = tmp_path / "verbose-out"
        rc = main(["--from", kong_admin_url, "--to", str(out), "--verbose"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "route" in captured.out
