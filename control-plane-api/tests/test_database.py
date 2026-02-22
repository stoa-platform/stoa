"""Tests for database module init_db / close_db (CAB-1388)."""

from unittest.mock import AsyncMock, MagicMock, patch

import src.database as db_module
from src.database import close_db, init_db


class TestInitDb:
    async def test_calls_create_all(self):
        mock_conn = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin = MagicMock(return_value=mock_ctx)

        with patch("src.database._get_engine", return_value=mock_engine):
            await init_db()

        mock_conn.run_sync.assert_awaited_once()

    async def test_passes_create_all_callable(self):
        """run_sync should receive a callable named create_all."""
        mock_conn = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin = MagicMock(return_value=mock_ctx)

        with patch("src.database._get_engine", return_value=mock_engine):
            await init_db()

        args, _ = mock_conn.run_sync.call_args
        assert callable(args[0])
        assert args[0].__name__ == "create_all"


class TestCloseDb:
    async def test_disposes_engine_when_set(self):
        mock_engine = AsyncMock()
        original = db_module._engine
        db_module._engine = mock_engine
        try:
            await close_db()
            mock_engine.dispose.assert_awaited_once()
        finally:
            db_module._engine = original

    async def test_no_op_when_engine_is_none(self):
        original = db_module._engine
        db_module._engine = None
        try:
            await close_db()  # must not raise
        finally:
            db_module._engine = original
