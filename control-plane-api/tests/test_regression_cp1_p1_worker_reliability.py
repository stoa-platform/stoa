"""Regression guards for CP-1 P1 — git sync worker reliability.

Closes:
- H.7 (Kafka enable_auto_commit=True → events lost on crash)
- H.8 (blanket ValueError classified as success masks functional bugs)

Invariants pinned:
- Kafka consumer is created with enable_auto_commit=False.
- Offset commit happens AFTER a successful _handle_event, synchronously
  from _dispatch_event.
- On handler failure or timeout, NO commit is issued — Kafka will
  redeliver.
- ValueError is classified as "idempotent success" ONLY if the message
  contains "already exists" or "not found". Other ValueErrors flow
  through the retry path like any real failure.

regression for CP-1 H.7
regression for CP-1 H.8
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────
# H.7 — Kafka consumer config + manual commit
# ──────────────────────────────────────────────────────────────────


class TestKafkaManualCommit:
    def test_consumer_disables_auto_commit(self):
        """regression for CP-1 H.7"""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        with patch("src.workers.git_sync_worker.KafkaConsumer") as mock_consumer_cls:
            worker._create_consumer()
            # The kafka config is the second argument (kwargs dict).
            _, kwargs = mock_consumer_cls.call_args
            assert kwargs["enable_auto_commit"] is False, (
                "CP-1 H.7: enable_auto_commit MUST be False to avoid "
                "losing events between auto-advance and handler run"
            )

    def test_commit_called_only_after_handler_success(self):
        """Success path: future.result() returns → consumer.commit() is called.

        regression for CP-1 H.7
        """
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        mock_consumer = MagicMock()
        worker._consumer = mock_consumer

        # Spin a real asyncio loop in a thread so run_coroutine_threadsafe
        # behaves like in production.
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        worker._loop = loop

        async def _ok_handler(_event):
            return None

        try:
            with patch.object(worker, "_handle_event", _ok_handler):
                message = MagicMock()
                message.value = {"event_type": "api-created", "tenant_id": "acme", "payload": {}}
                worker._dispatch_event(message)

            # commit MUST have been called exactly once.
            assert mock_consumer.commit.call_count == 1
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=1.0)
            loop.close()

    def test_commit_NOT_called_when_handler_raises(self):
        """regression for CP-1 H.7"""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        mock_consumer = MagicMock()
        worker._consumer = mock_consumer

        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        worker._loop = loop

        async def _bad_handler(_event):
            raise RuntimeError("kaboom")

        try:
            with patch.object(worker, "_handle_event", _bad_handler):
                message = MagicMock()
                message.value = {"event_type": "api-created", "tenant_id": "acme", "payload": {}}
                worker._dispatch_event(message)

            mock_consumer.commit.assert_not_called()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=1.0)
            loop.close()

    def test_commit_NOT_called_on_handler_timeout(self):
        """regression for CP-1 H.7"""
        from src.workers import git_sync_worker as mod
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        mock_consumer = MagicMock()
        worker._consumer = mock_consumer

        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        worker._loop = loop

        async def _slow_handler(_event):
            await asyncio.sleep(10)

        try:
            with (
                patch.object(worker, "_handle_event", _slow_handler),
                patch.object(mod, "HANDLER_RESULT_TIMEOUT_S", 0.05),
            ):
                message = MagicMock()
                message.value = {"event_type": "api-created", "tenant_id": "acme", "payload": {}}
                worker._dispatch_event(message)

            mock_consumer.commit.assert_not_called()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=1.0)
            loop.close()


# ──────────────────────────────────────────────────────────────────
# H.8 — ValueError discrimination
# ──────────────────────────────────────────────────────────────────


class TestValueErrorDiscriminator:
    @pytest.mark.asyncio
    async def test_value_error_already_exists_is_success(self):
        """regression for CP-1 H.8"""
        from src.workers.git_sync_worker import GIT_SYNC_TOTAL, GitSyncWorker

        worker = GitSyncWorker()
        worker._github_service = AsyncMock()
        worker._github_service.create_api = AsyncMock(
            side_effect=ValueError("API 'foo' already exists for tenant 'acme'")
        )

        before = GIT_SYNC_TOTAL.labels(status="success", operation="created")._value.get()
        await worker._handle_event(
            {"event_type": "api-created", "tenant_id": "acme", "payload": {"name": "foo"}}
        )
        after = GIT_SYNC_TOTAL.labels(status="success", operation="created")._value.get()

        assert after - before == 1, (
            "ValueError with 'already exists' MUST increment success counter"
        )

    @pytest.mark.asyncio
    async def test_value_error_not_found_is_success(self):
        """regression for CP-1 H.8"""
        from src.workers.git_sync_worker import GIT_SYNC_TOTAL, GitSyncWorker

        worker = GitSyncWorker()
        worker._github_service = AsyncMock()
        worker._github_service.is_api_up_to_date = AsyncMock(return_value=False)
        worker._github_service.update_api = AsyncMock(
            side_effect=ValueError("API 'missing' not found for tenant 'acme'")
        )

        before = GIT_SYNC_TOTAL.labels(status="success", operation="updated")._value.get()
        await worker._handle_event(
            {
                "event_type": "api-updated",
                "tenant_id": "acme",
                "payload": {"name": "missing"},
            }
        )
        after = GIT_SYNC_TOTAL.labels(status="success", operation="updated")._value.get()

        assert after - before == 1

    @pytest.mark.asyncio
    async def test_unknown_value_error_is_error_not_success(self):
        """An unrelated ValueError (e.g. 'unknown action') must NOT be
        classified as success — it is a real failure that the prior
        blanket except swallowed into the success counter.

        regression for CP-1 H.8
        """
        from src.workers.git_sync_worker import GIT_SYNC_TOTAL, GitSyncWorker

        worker = GitSyncWorker()
        worker._github_service = AsyncMock()
        worker._github_service.create_api = AsyncMock(
            side_effect=ValueError("unknown action: something_else")
        )
        # Kill the retry delays so the test runs fast.
        worker._retry_delays = [0]

        success_before = GIT_SYNC_TOTAL.labels(
            status="success", operation="created"
        )._value.get()
        error_before = GIT_SYNC_TOTAL.labels(
            status="error", operation="created"
        )._value.get()

        await worker._handle_event(
            {"event_type": "api-created", "tenant_id": "acme", "payload": {"name": "x"}}
        )

        success_after = GIT_SYNC_TOTAL.labels(
            status="success", operation="created"
        )._value.get()
        error_after = GIT_SYNC_TOTAL.labels(
            status="error", operation="created"
        )._value.get()

        assert success_after == success_before, (
            "Unknown ValueError must NOT increment success counter"
        )
        assert error_after - error_before == 1, (
            "Unknown ValueError must increment error counter after retries"
        )
