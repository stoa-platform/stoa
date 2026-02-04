"""Tests for stoa status command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.config import Credentials, StoaConfig, save_config, save_credentials
from src.main import app
from src.models import HealthResponse

runner = CliRunner()


class TestStatus:
    def test_status_authenticated(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        save_config(sample_config)
        save_credentials(sample_credentials)

        with patch("src.commands.status.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.health.return_value = HealthResponse(
                status="ok", version="2.0.0"
            )
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "john.doe" in result.output
        assert "ok" in result.output

    def test_status_not_authenticated(self, tmp_stoa_dir: Path):
        with patch("src.commands.status.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.health.return_value = HealthResponse(status="ok")
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "not authenticated" in result.output

    def test_status_api_unreachable(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        save_config(sample_config)
        save_credentials(sample_credentials)

        with patch("src.commands.status.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.health.side_effect = Exception("Connection refused")
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0
        assert "unreachable" in result.output


class TestVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        # Typer no_args_is_help returns exit code 0
        # but some versions return 2 for missing required args
        assert result.exit_code in (0, 2)
        assert "STOA" in result.output or "Usage" in result.output
