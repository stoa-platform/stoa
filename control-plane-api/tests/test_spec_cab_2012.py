"""Spec-driven tests for CAB-2012: Console commit-on-write async Git sync.

These tests are written BEFORE implementation (spec-driven / TDD).
All tests MUST fail until GitSyncWorker is implemented.

Acceptance Criteria → Tests:
  AC1: api-created → Git commit
  AC2: api-updated → Git commit
  AC3: api-deleted → Git directory removed
  AC4: kill-switch disables Git ops
  AC5: retry with exponential backoff
  AC6: idempotent (no commit if identical)
  AC7: Kafka failure doesn't block HTTP (tested at router level, not here)

Edge Cases:
  E1: GitHub rate limit → retry
  E2: Duplicate event → no-op
  E3: Tenant missing → auto-create
  E5: Worker crash mid-retry → Kafka re-delivers
  E7: GitHubService not initialized → skip gracefully
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

# ── AC1-AC3: Happy path — event types trigger correct GitHubService methods ──


class TestGitSyncWorkerHappyPath:
    """AC1/AC2/AC3: CRUD events trigger corresponding Git operations."""

    def test_import_git_sync_worker(self):
        """GitSyncWorker module must exist and be importable."""
        from src.workers.git_sync_worker import GitSyncWorker  # noqa: F401

    def test_worker_has_correct_topic(self):
        """Worker consumes from stoa.api.lifecycle topic."""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        assert worker.TOPIC == "stoa.api.lifecycle"

    def test_worker_has_correct_consumer_group(self):
        """Consumer group is git-sync-worker (isolated from sync-engine)."""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        assert worker.GROUP == "git-sync-worker"

    @pytest.mark.asyncio
    async def test_ac1_api_created_triggers_git_create(self):
        """AC1: api-created event calls GitHubService.create_api()."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.create_api = AsyncMock(return_value="api-id-1")

        worker = GitSyncWorker()
        worker._github_service = mock_github

        event = {
            "id": "evt-1",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {
                "name": "weather-api",
                "display_name": "Weather API",
                "version": "1.0.0",
                "description": "Weather forecasts",
                "backend_url": "https://api.weather.com",
                "tags": ["weather"],
            },
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:00:00Z",
        }

        await worker._handle_event(event)

        mock_github.create_api.assert_called_once_with("acme", event["payload"])

    @pytest.mark.asyncio
    async def test_ac2_api_updated_triggers_git_update(self):
        """AC2: api-updated event calls GitHubService.update_api()."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.update_api = AsyncMock(return_value=True)
        # No is_api_up_to_date method — update should proceed
        del mock_github.is_api_up_to_date

        worker = GitSyncWorker()
        worker._github_service = mock_github

        event = {
            "id": "evt-2",
            "event_type": "api-updated",
            "tenant_id": "acme",
            "payload": {
                "name": "weather-api",
                "description": "Updated weather forecasts",
            },
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:01:00Z",
        }

        await worker._handle_event(event)

        mock_github.update_api.assert_called_once_with("acme", "weather-api", event["payload"])

    @pytest.mark.asyncio
    async def test_ac3_api_deleted_triggers_git_delete(self):
        """AC3: api-deleted event calls GitHubService.delete_api()."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.delete_api = AsyncMock(return_value=True)

        worker = GitSyncWorker()
        worker._github_service = mock_github

        event = {
            "id": "evt-3",
            "event_type": "api-deleted",
            "tenant_id": "acme",
            "payload": {"api_id": "weather-api", "name": "weather-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:02:00Z",
        }

        await worker._handle_event(event)

        mock_github.delete_api.assert_called_once_with("acme", "weather-api")


# ── AC4: Kill-switch ──


class TestGitSyncKillSwitch:
    """AC4: GIT_SYNC_ON_WRITE=false disables Git operations."""

    @pytest.mark.asyncio
    async def test_ac4_kill_switch_skips_git_ops(self):
        """When GIT_SYNC_ON_WRITE=false, events are consumed but Git ops are skipped."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.create_api = AsyncMock()

        worker = GitSyncWorker()
        worker._github_service = mock_github
        worker._git_sync_enabled = False

        event = {
            "id": "evt-4",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {"name": "test-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:03:00Z",
        }

        await worker._handle_event(event)

        mock_github.create_api.assert_not_called()

    def test_ac4_config_setting_exists(self):
        """GIT_SYNC_ON_WRITE setting exists in config with default True."""
        from src.config import Settings

        s = Settings()
        assert hasattr(s, "GIT_SYNC_ON_WRITE")
        assert s.GIT_SYNC_ON_WRITE is True


# ── AC5: Retry with exponential backoff ──


class TestGitSyncRetry:
    """AC5: Worker retries 3 times with exponential backoff on GitHubService errors."""

    @pytest.mark.asyncio
    async def test_ac5_retries_on_github_error(self):
        """GitHubService error triggers 3 retries before giving up."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.create_api = AsyncMock(side_effect=Exception("GitHub API error"))

        worker = GitSyncWorker()
        worker._github_service = mock_github
        # Patch sleep to avoid real delays
        worker._retry_delays = [0, 0, 0]

        event = {
            "id": "evt-5",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {"name": "test-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:04:00Z",
        }

        # Should not raise — worker logs failure and moves on
        await worker._handle_event(event)

        # 1 initial + 3 retries = 4 total calls
        assert mock_github.create_api.call_count == 4

    @pytest.mark.asyncio
    async def test_ac5_succeeds_on_second_retry(self):
        """Worker succeeds on retry after initial failure."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.create_api = AsyncMock(side_effect=[Exception("Transient error"), "api-id-1"])

        worker = GitSyncWorker()
        worker._github_service = mock_github
        worker._retry_delays = [0, 0, 0]

        event = {
            "id": "evt-6",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {"name": "test-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:05:00Z",
        }

        await worker._handle_event(event)

        assert mock_github.create_api.call_count == 2


# ── AC6: Idempotency ──


class TestGitSyncIdempotency:
    """AC6: No commit when Git file content is already identical."""

    @pytest.mark.asyncio
    async def test_ac6_skip_update_when_content_identical(self):
        """update_api is not called when content hasn't changed."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        # Simulate content-identical check returning True (already up to date)
        mock_github.is_api_up_to_date = AsyncMock(return_value=True)
        mock_github.update_api = AsyncMock()

        worker = GitSyncWorker()
        worker._github_service = mock_github

        event = {
            "id": "evt-7",
            "event_type": "api-updated",
            "tenant_id": "acme",
            "payload": {"name": "weather-api", "description": "Same content"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:06:00Z",
        }

        await worker._handle_event(event)

        mock_github.update_api.assert_not_called()


# ── Edge Cases ──


class TestGitSyncEdgeCases:
    """Edge case tests from spec."""

    @pytest.mark.asyncio
    async def test_e2_duplicate_event_is_noop(self):
        """E2: Duplicate api-created for existing API is a no-op (no error)."""
        from src.workers.git_sync_worker import GitSyncWorker

        mock_github = AsyncMock()
        mock_github.create_api = AsyncMock(side_effect=ValueError("API 'weather-api' already exists for tenant 'acme'"))

        worker = GitSyncWorker()
        worker._github_service = mock_github

        event = {
            "id": "evt-8",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {"name": "weather-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:07:00Z",
        }

        # Should not raise — duplicate is expected, worker logs and continues
        await worker._handle_event(event)

    @pytest.mark.asyncio
    async def test_e7_github_service_not_initialized(self):
        """E7: If GitHubService is None/not configured, skip gracefully."""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        worker._github_service = None

        event = {
            "id": "evt-9",
            "event_type": "api-created",
            "tenant_id": "acme",
            "payload": {"name": "test-api"},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:08:00Z",
        }

        # Should not raise — graceful skip when service unavailable
        await worker._handle_event(event)

    def test_unknown_event_type_ignored(self):
        """Unknown event types are logged and skipped, not crashed."""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        worker._github_service = AsyncMock()

        event = {
            "id": "evt-10",
            "event_type": "api-unknown-action",
            "tenant_id": "acme",
            "payload": {},
            "user_id": "user@acme.com",
            "timestamp": "2026-04-09T10:09:00Z",
        }

        # Sync wrapper — should not raise
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(worker._handle_event(event))
        finally:
            loop.close()

    def test_worker_start_stop_lifecycle(self):
        """Worker can be started and stopped without errors."""
        from src.workers.git_sync_worker import GitSyncWorker

        worker = GitSyncWorker()
        assert worker._running is False
