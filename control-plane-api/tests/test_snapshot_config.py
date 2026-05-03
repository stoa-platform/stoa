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
        """Phase 3-D — uses canonical STOA_API_SNAPSHOT_* prefix.

        Migrated from legacy STOA_SNAPSHOTS_* per CAB-2199 plan §2.6.d.
        Closes BH-INFRA1a-010 — pre-Phase-3-D this test passed only via
        the AliasChoices alias path, leaving the canonical prefix
        unexercised by the bulk of the snapshot test suite.
        """
        env = {
            "STOA_API_SNAPSHOT_ENABLED": "false",
            "STOA_API_SNAPSHOT_CAPTURE_ON_4XX": "true",
            "STOA_API_SNAPSHOT_RETENTION_DAYS": "7",
            "STOA_API_SNAPSHOT_STORAGE_TYPE": "s3",
            "STOA_API_SNAPSHOT_STORAGE_USE_SSL": "true",
            "STOA_API_SNAPSHOT_MAX_BODY_SIZE": "50000",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = SnapshotSettings()
        assert settings.enabled is False
        assert settings.capture_on_4xx is True
        assert settings.retention_days == 7
        assert settings.storage_type == "s3"
        assert settings.storage_use_ssl is True
        assert settings.max_body_size == 50000

    def test_legacy_prefix_still_works_via_alias(self):
        """Phase 3-D — keep ONE regression test on the legacy prefix so
        the AliasChoices surface stays exercised until CAB-2203 sunset."""
        env = {
            "STOA_SNAPSHOTS_ENABLED": "false",
            "STOA_SNAPSHOTS_RETENTION_DAYS": "14",
        }
        with patch.dict("os.environ", env, clear=True):
            settings = SnapshotSettings()
        assert settings.enabled is False
        assert settings.retention_days == 14


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
