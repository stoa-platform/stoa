"""Tests for stoa apply -f <file.yaml>."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.config import Credentials, StoaConfig, save_config, save_credentials
from src.main import app
from src.models import APIResponse

runner = CliRunner()


def _setup_auth(
    tmp_stoa_dir: Path,
    sample_config: StoaConfig,
    sample_credentials: Credentials,
) -> None:
    save_config(sample_config)
    save_credentials(sample_credentials)


VALID_API_YAML = """\
kind: API
metadata:
  name: weather-api
spec:
  displayName: Weather API
  version: "1.0.0"
  description: Real-time weather data
  backendUrl: https://api.weather.com/v1
  tags:
    - weather
    - public
"""

MULTI_DOC_YAML = """\
kind: API
metadata:
  name: api-one
spec:
  displayName: API One
  backendUrl: https://one.example.com
---
kind: API
metadata:
  name: api-two
spec:
  displayName: API Two
  backendUrl: https://two.example.com
"""

INVALID_KIND_YAML = """\
kind: Subscription
metadata:
  name: my-sub
spec:
  apiId: weather
"""

MISSING_BACKEND_YAML = """\
kind: API
metadata:
  name: no-backend
spec:
  displayName: No Backend
"""


class TestApplyCreate:
    def test_apply_creates_api(
        self,
        tmp_stoa_dir: Path,
        tmp_path: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)
        manifest = tmp_path / "api.yaml"
        manifest.write_text(VALID_API_YAML)

        with patch("src.commands.apply.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.side_effect = RuntimeError("not found")
            mock_client.create_api.return_value = {"id": "new"}
            result = runner.invoke(app, ["apply", "-f", str(manifest)])

        assert result.exit_code == 0
        assert "created" in result.output
        assert "1 resource(s) applied" in result.output

    def test_apply_updates_existing_api(
        self,
        tmp_stoa_dir: Path,
        tmp_path: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)
        manifest = tmp_path / "api.yaml"
        manifest.write_text(VALID_API_YAML)

        existing = APIResponse(
            id="existing-id", name="weather-api",
            display_name="Old Name", version="0.9",
        )

        with patch("src.commands.apply.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.return_value = existing
            mock_client.update_api.return_value = {"id": "existing-id"}
            result = runner.invoke(app, ["apply", "-f", str(manifest)])

        assert result.exit_code == 0
        assert "updated" in result.output


class TestApplyMultiDoc:
    def test_apply_multi_document(
        self,
        tmp_stoa_dir: Path,
        tmp_path: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)
        manifest = tmp_path / "multi.yaml"
        manifest.write_text(MULTI_DOC_YAML)

        with patch("src.commands.apply.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.side_effect = RuntimeError("not found")
            mock_client.create_api.return_value = {"id": "new"}
            result = runner.invoke(app, ["apply", "-f", str(manifest)])

        assert result.exit_code == 0
        assert "2 resource(s) applied" in result.output


class TestApplyErrors:
    def test_unsupported_kind(
        self,
        tmp_stoa_dir: Path,
        tmp_path: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)
        manifest = tmp_path / "bad.yaml"
        manifest.write_text(INVALID_KIND_YAML)

        with patch("src.commands.apply.StoaClient"):
            result = runner.invoke(app, ["apply", "-f", str(manifest)])

        assert result.exit_code == 1
        assert "Unsupported kind" in result.output

    def test_missing_backend_url(
        self,
        tmp_stoa_dir: Path,
        tmp_path: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)
        manifest = tmp_path / "bad.yaml"
        manifest.write_text(MISSING_BACKEND_YAML)

        with patch("src.commands.apply.StoaClient"):
            result = runner.invoke(app, ["apply", "-f", str(manifest)])

        assert result.exit_code == 1
        assert "backendUrl is required" in result.output
