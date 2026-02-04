"""Tests for stoa get apis / stoa get api <name>."""

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


class TestGetAPIs:
    def test_get_apis_table(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        mock_apis = [
            APIResponse(
                id="1", name="weather", display_name="Weather API",
                version="1.0.0", status="active",
            ),
            APIResponse(
                id="2", name="payments", display_name="Payments API",
                version="2.0.0", status="draft",
            ),
        ]

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.list_apis.return_value = mock_apis
            result = runner.invoke(app, ["get", "apis"])

        assert result.exit_code == 0
        assert "weather" in result.output
        assert "payments" in result.output
        assert "2 API(s) found" in result.output

    def test_get_apis_json(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        mock_apis = [
            APIResponse(
                id="1", name="weather", display_name="Weather API",
                version="1.0.0", status="active",
            ),
        ]

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.list_apis.return_value = mock_apis
            result = runner.invoke(app, ["get", "apis", "-o", "json"])

        assert result.exit_code == 0
        assert "weather" in result.output

    def test_get_apis_empty(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.list_apis.return_value = []
            result = runner.invoke(app, ["get", "apis"])

        assert result.exit_code == 0
        assert "No APIs found" in result.output

    def test_get_apis_error(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.list_apis.side_effect = RuntimeError("Not authenticated")
            result = runner.invoke(app, ["get", "apis"])

        assert result.exit_code == 1
        assert "Error" in result.output


class TestGetAPI:
    def test_get_api_detail(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        mock_api = APIResponse(
            id="api-123",
            name="weather",
            display_name="Weather API",
            version="1.0.0",
            status="active",
            backend_url="https://api.weather.com",
            description="Real-time weather data",
            tags=["weather", "public"],
        )

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.return_value = mock_api
            result = runner.invoke(app, ["get", "api", "weather"])

        assert result.exit_code == 0
        assert "Weather API" in result.output
        assert "api.weather.com" in result.output

    def test_get_api_json(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        mock_api = APIResponse(
            id="1", name="weather", display_name="Weather", version="1.0",
        )

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.return_value = mock_api
            result = runner.invoke(app, ["get", "api", "weather", "-o", "json"])

        assert result.exit_code == 0
        assert "weather" in result.output

    def test_get_api_not_found(
        self,
        tmp_stoa_dir: Path,
        sample_config: StoaConfig,
        sample_credentials: Credentials,
    ):
        _setup_auth(tmp_stoa_dir, sample_config, sample_credentials)

        with patch("src.commands.get.StoaClient") as mock_cls:
            mock_client = mock_cls.return_value
            mock_client.get_api.side_effect = RuntimeError("API 'x' not found.")
            result = runner.invoke(app, ["get", "api", "x"])

        assert result.exit_code == 1
        assert "not found" in result.output
