"""Tests for error snapshot config (CAB-1291)"""
import json
from unittest.mock import patch

import pytest

from src.features.error_snapshots.config import SnapshotSettings


class TestSnapshotSettingsDefaults:
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings()
        assert settings.enabled is True
        assert settings.capture_on_4xx is False
        assert settings.capture_on_5xx is True
        assert settings.capture_on_timeout is True
        assert settings.timeout_threshold_ms == 30000
        assert settings.storage_type == "minio"
        assert settings.storage_bucket == "error-snapshots"
        assert settings.storage_use_ssl is False
        assert settings.retention_days == 30
        assert settings.max_body_size == 10_000
        assert settings.max_logs_per_snapshot == 100
        assert settings.async_capture is True

    def test_custom_env(self):
        env = {
            "STOA_SNAPSHOTS_ENABLED": "false",
            "STOA_SNAPSHOTS_CAPTURE_ON_4XX": "true",
            "STOA_SNAPSHOTS_RETENTION_DAYS": "7",
            "STOA_SNAPSHOTS_STORAGE_TYPE": "s3",
            "STOA_SNAPSHOTS_STORAGE_USE_SSL": "true",
            "STOA_SNAPSHOTS_MAX_BODY_SIZE": "50000",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = SnapshotSettings()
        assert settings.enabled is False
        assert settings.capture_on_4xx is True
        assert settings.retention_days == 7
        assert settings.storage_type == "s3"
        assert settings.storage_use_ssl is True
        assert settings.max_body_size == 50000


class TestExcludePaths:
    def test_default_list(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings()
        paths = settings.exclude_paths_list
        assert "/health" in paths
        assert "/metrics" in paths

    def test_parse_from_list(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(exclude_paths=["/a", "/b"])
        assert settings.exclude_paths == json.dumps(["/a", "/b"])
        assert settings.exclude_paths_list == ["/a", "/b"]

    def test_invalid_json(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(exclude_paths="not-json")
        assert settings.exclude_paths_list == []


class TestStorageUrl:
    def test_http(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(storage_endpoint="minio:9000", storage_use_ssl=False)
        assert settings.storage_url == "http://minio:9000"

    def test_https(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(storage_endpoint="s3.aws.com", storage_use_ssl=True)
        assert settings.storage_url == "https://s3.aws.com"


class TestMaskingConfig:
    def test_default_config(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings()
        config = settings.masking_config
        assert config is not None

    def test_extra_headers(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(masking_extra_headers='["X-Custom-Secret"]')
        config = settings.masking_config
        assert "X-Custom-Secret" in config.headers

    def test_extra_body_paths(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(masking_extra_body_paths='["$.data.ssn"]')
        config = settings.masking_config
        assert "$.data.ssn" in config.body_paths

    def test_invalid_json_ignored(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = SnapshotSettings(
                masking_extra_headers="not-json",
                masking_extra_body_paths="not-json",
            )
        config = settings.masking_config
        assert config is not None
