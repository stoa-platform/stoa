"""Tests for error_snapshots __init__ module (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI


class TestAddErrorSnapshotMiddleware:
    def test_returns_false_when_disabled(self):
        from src.features.error_snapshots import add_error_snapshot_middleware

        mock_settings = MagicMock()
        mock_settings.enabled = False

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            app = MagicMock(spec=FastAPI)
            result = add_error_snapshot_middleware(app)
            assert result is False

    def test_returns_true_when_enabled(self):
        from src.features.error_snapshots import add_error_snapshot_middleware

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.capture_on_4xx = True
        mock_settings.capture_on_5xx = True

        mock_storage = MagicMock()
        mock_service = MagicMock()

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            with patch("src.features.error_snapshots.SnapshotStorage", return_value=mock_storage):
                with patch("src.features.error_snapshots.SnapshotService", return_value=mock_service):
                    with patch("src.features.error_snapshots.set_snapshot_service"):
                        app = MagicMock(spec=FastAPI)
                        result = add_error_snapshot_middleware(app)
                        assert result is True
                        app.add_middleware.assert_called_once()
                        app.include_router.assert_called_once()

    def test_returns_false_on_exception(self):
        from src.features.error_snapshots import add_error_snapshot_middleware

        mock_settings = MagicMock()
        mock_settings.enabled = True

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            with patch("src.features.error_snapshots.SnapshotStorage", side_effect=RuntimeError("storage fail")):
                app = MagicMock(spec=FastAPI)
                result = add_error_snapshot_middleware(app)
                assert result is False


class TestConnectErrorSnapshots:
    async def test_returns_none_when_not_initialized(self):
        import src.features.error_snapshots as module

        original_storage = module._snapshot_storage
        original_settings = module._settings
        try:
            module._snapshot_storage = None
            module._settings = None
            result = await module.connect_error_snapshots()
            assert result is None
        finally:
            module._snapshot_storage = original_storage
            module._settings = original_settings

    async def test_connects_successfully(self):
        import src.features.error_snapshots as module

        mock_storage = AsyncMock()
        mock_service = MagicMock()
        mock_settings = MagicMock()
        mock_settings.storage_bucket = "test-bucket"
        mock_settings.retention_days = 7

        original_storage = module._snapshot_storage
        original_service = module._snapshot_service
        original_settings = module._settings
        try:
            module._snapshot_storage = mock_storage
            module._snapshot_service = mock_service
            module._settings = mock_settings
            result = await module.connect_error_snapshots()
            assert result is mock_service
            mock_storage.connect.assert_called_once()
        finally:
            module._snapshot_storage = original_storage
            module._snapshot_service = original_service
            module._settings = original_settings

    async def test_returns_none_on_connection_failure(self):
        import src.features.error_snapshots as module

        mock_storage = AsyncMock()
        mock_storage.connect.side_effect = RuntimeError("connection refused")
        mock_settings = MagicMock()

        original_storage = module._snapshot_storage
        original_settings = module._settings
        try:
            module._snapshot_storage = mock_storage
            module._settings = mock_settings
            result = await module.connect_error_snapshots()
            assert result is None
        finally:
            module._snapshot_storage = original_storage
            module._settings = original_settings


class TestGetSnapshotService:
    def test_returns_current_service(self):
        import src.features.error_snapshots as module

        mock_service = MagicMock()
        original = module._snapshot_service
        try:
            module._snapshot_service = mock_service
            result = module.get_snapshot_service()
            assert result is mock_service
        finally:
            module._snapshot_service = original

    def test_returns_none_when_not_set(self):
        import src.features.error_snapshots as module

        original = module._snapshot_service
        try:
            module._snapshot_service = None
            result = module.get_snapshot_service()
            assert result is None
        finally:
            module._snapshot_service = original


class TestSetupErrorSnapshots:
    async def test_returns_none_when_disabled(self):
        from src.features.error_snapshots import setup_error_snapshots

        mock_settings = MagicMock()
        mock_settings.enabled = False

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            app = MagicMock(spec=FastAPI)
            result = await setup_error_snapshots(app)
            assert result is None

    async def test_returns_service_when_enabled(self):
        from src.features.error_snapshots import setup_error_snapshots

        mock_settings = MagicMock()
        mock_settings.enabled = True
        mock_settings.storage_bucket = "test"
        mock_settings.capture_on_4xx = True
        mock_settings.capture_on_5xx = True
        mock_settings.capture_on_timeout = False
        mock_settings.retention_days = 7

        mock_storage = AsyncMock()
        mock_service = MagicMock()

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            with patch("src.features.error_snapshots.SnapshotStorage", return_value=mock_storage):
                with patch("src.features.error_snapshots.SnapshotService", return_value=mock_service):
                    with patch("src.features.error_snapshots.set_snapshot_service"):
                        app = MagicMock(spec=FastAPI)
                        result = await setup_error_snapshots(app)
                        assert result is mock_service

    async def test_returns_none_on_exception(self):
        from src.features.error_snapshots import setup_error_snapshots

        mock_settings = MagicMock()
        mock_settings.enabled = True

        with patch("src.features.error_snapshots.get_snapshot_settings", return_value=mock_settings):
            with patch("src.features.error_snapshots.SnapshotStorage", side_effect=RuntimeError("fail")):
                app = MagicMock(spec=FastAPI)
                result = await setup_error_snapshots(app)
                assert result is None
