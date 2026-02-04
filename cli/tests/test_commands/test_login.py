"""Tests for stoa login / logout commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from src.config import Credentials, save_credentials
from src.main import app

runner = CliRunner()


class TestLogin:
    def test_login_success(self, tmp_stoa_dir: Path, sample_credentials: Credentials):
        with patch("src.commands.login.login_interactive") as mock_login:
            mock_login.return_value = sample_credentials
            result = runner.invoke(app, ["login"])

        assert result.exit_code == 0
        assert "Logged in as" in result.output

    def test_login_failure(self, tmp_stoa_dir: Path):
        with patch("src.commands.login.login_interactive") as mock_login:
            mock_login.side_effect = RuntimeError("Connection refused")
            result = runner.invoke(app, ["login"])

        assert result.exit_code == 1
        assert "Login failed" in result.output

    def test_login_with_custom_server(
        self, tmp_stoa_dir: Path, sample_credentials: Credentials
    ):
        with patch("src.commands.login.login_interactive") as mock_login:
            mock_login.return_value = sample_credentials
            result = runner.invoke(
                app, ["login", "--server", "https://custom.api.dev"]
            )

        assert result.exit_code == 0


class TestLogout:
    def test_logout_clears_credentials(
        self, tmp_stoa_dir: Path, sample_credentials: Credentials
    ):
        save_credentials(sample_credentials)
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
        assert "Logged out" in result.output

    def test_logout_no_credentials(self, tmp_stoa_dir: Path):
        result = runner.invoke(app, ["logout"])
        assert result.exit_code == 0
