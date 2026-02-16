"""Tests for SnapshotStorage operations (CAB-1291)"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.features.error_snapshots.config import SnapshotSettings
from src.features.error_snapshots.storage import SnapshotStorage


def _make_settings(**overrides):
    """Create SnapshotSettings with test defaults."""
    defaults = {
        "STOA_SNAPSHOTS_STORAGE_BUCKET": "test-bucket",
        "STOA_SNAPSHOTS_STORAGE_ACCESS_KEY": "test-key",
        "STOA_SNAPSHOTS_STORAGE_SECRET_KEY": "test-secret",
        "STOA_SNAPSHOTS_STORAGE_ENDPOINT": "localhost:9000",
        "STOA_SNAPSHOTS_STORAGE_REGION": "us-east-1",
        "STOA_SNAPSHOTS_RETENTION_DAYS": "30",
    }
    defaults.update(overrides)
    with patch.dict("os.environ", defaults, clear=False):
        return SnapshotSettings()


def _make_snapshot(**kwargs):
    """Create mock ErrorSnapshot."""
    snap = MagicMock()
    snap.id = kwargs.get("id", "SNP-20260216-100000-a1b2c3d4")
    snap.tenant_id = kwargs.get("tenant_id", "acme")
    snap.timestamp = kwargs.get("timestamp", datetime(2026, 2, 16, 10, 0, 0))
    snap.trigger = MagicMock(value="5xx")
    snap.response = MagicMock(status=500, duration_ms=150)
    snap.request = MagicMock(method="POST", path="/api/v1/test")
    snap.source = "gateway"
    snap.resolution_status = "open"
    snap.model_dump_json.return_value = '{"id": "SNP-20260216-100000-a1b2c3d4"}'
    return snap


# ── Init ──


class TestInit:
    def test_defaults(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        assert storage.settings is settings
        assert storage._session is None
        assert storage._connected is False


# ── _get_object_key ──


class TestGetObjectKey:
    def test_generates_key(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        snap = _make_snapshot()
        key = storage._get_object_key(snap)
        assert key == "acme/2026/02/16/SNP-20260216-100000-a1b2c3d4.json.gz"


# ── _parse_object_key ──


class TestParseObjectKey:
    def test_valid_key(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        meta = storage._parse_object_key("acme/2026/02/16/SNP-123.json.gz")
        assert meta["tenant_id"] == "acme"
        assert meta["year"] == 2026
        assert meta["month"] == 2
        assert meta["day"] == 16
        assert meta["snapshot_id"] == "SNP-123"

    def test_invalid_key(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        meta = storage._parse_object_key("bad/path")
        assert meta == {}


# ── connect ──


class TestConnect:
    async def test_bucket_exists(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        mock_client = AsyncMock()
        mock_client.head_bucket = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            await storage.connect()
        assert storage._connected is True

    async def test_bucket_create_on_404(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "404"}}
        mock_client = AsyncMock()
        mock_client.head_bucket = AsyncMock(
            side_effect=ClientError(error_response, "HeadBucket")
        )
        mock_client.create_bucket = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            await storage.connect()
        mock_client.create_bucket.assert_awaited_once()
        assert storage._connected is True

    async def test_bucket_other_error_raises(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "403"}}
        mock_client = AsyncMock()
        mock_client.head_bucket = AsyncMock(
            side_effect=ClientError(error_response, "HeadBucket")
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            with pytest.raises(ClientError):
                await storage.connect()

    async def test_connection_failure(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("refused"))
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            with pytest.raises(Exception, match="refused"):
                await storage.connect()


# ── save ──


class TestSave:
    async def test_success(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        snap = _make_snapshot()

        mock_client = AsyncMock()
        mock_client.put_object = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            url = await storage.save(snap)
        assert url.startswith("s3://test-bucket/")
        mock_client.put_object.assert_awaited_once()


# ── get ──


class TestGet:
    async def test_invalid_snapshot_id(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        result = await storage.get("bad-id", "acme")
        assert result is None

    async def test_not_found(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "NoSuchKey"}}
        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            result = await storage.get("SNP-20260216-100000-a1b2c3d4", "acme")
        assert result is None

    async def test_other_error_raises(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "500"}}
        mock_client = AsyncMock()
        mock_client.get_object = AsyncMock(
            side_effect=ClientError(error_response, "GetObject")
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            with pytest.raises(ClientError):
                await storage.get("SNP-20260216-100000-a1b2c3d4", "acme")


# ── delete ──


class TestDelete:
    async def test_invalid_id(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)
        result = await storage.delete("bad-id", "acme")
        assert result is False

    async def test_success(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        mock_client = AsyncMock()
        mock_client.delete_object = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            result = await storage.delete("SNP-20260216-100000-a1b2c3d4", "acme")
        assert result is True

    async def test_not_found(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "404"}}
        mock_client = AsyncMock()
        mock_client.delete_object = AsyncMock(
            side_effect=ClientError(error_response, "DeleteObject")
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            result = await storage.delete("SNP-20260216-100000-a1b2c3d4", "acme")
        assert result is False

    async def test_other_error_raises(self):
        settings = _make_settings()
        storage = SnapshotStorage(settings)

        error_response = {"Error": {"Code": "500"}}
        mock_client = AsyncMock()
        mock_client.delete_object = AsyncMock(
            side_effect=ClientError(error_response, "DeleteObject")
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(storage, "_get_client", return_value=mock_ctx):
            with pytest.raises(ClientError):
                await storage.delete("SNP-20260216-100000-a1b2c3d4", "acme")


# ── SnapshotSettings ──


class TestSnapshotSettings:
    def test_storage_url_http(self):
        settings = _make_settings()
        assert settings.storage_url == "http://localhost:9000"

    def test_storage_url_https(self):
        settings = _make_settings(STOA_SNAPSHOTS_STORAGE_USE_SSL="true")
        assert settings.storage_url.startswith("https://")

    def test_exclude_paths_list(self):
        settings = _make_settings()
        paths = settings.exclude_paths_list
        assert isinstance(paths, list)
        assert "/health" in paths

    def test_exclude_paths_list_invalid_json(self):
        settings = _make_settings()
        settings.exclude_paths = "not-json"
        paths = settings.exclude_paths_list
        assert paths == []

    def test_masking_config(self):
        settings = _make_settings()
        config = settings.masking_config
        assert config is not None

    def test_masking_config_with_extras(self):
        settings = _make_settings(
            STOA_SNAPSHOTS_MASKING_EXTRA_HEADERS='["X-Custom"]',
            STOA_SNAPSHOTS_MASKING_EXTRA_BODY_PATHS='["$.secret"]',
        )
        config = settings.masking_config
        assert "X-Custom" in config.headers

    def test_masking_config_invalid_json(self):
        settings = _make_settings()
        settings.masking_extra_headers = "bad-json"
        settings.masking_extra_body_paths = "bad-json"
        config = settings.masking_config
        assert config is not None

    def test_parse_exclude_paths_list_input(self):
        """Validator should handle list input."""
        result = SnapshotSettings.parse_exclude_paths(["/health", "/metrics"])
        assert result == '["/health", "/metrics"]'

    def test_parse_exclude_paths_string_input(self):
        result = SnapshotSettings.parse_exclude_paths('["/health"]')
        assert result == '["/health"]'
