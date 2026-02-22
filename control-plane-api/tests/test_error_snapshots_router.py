"""Tests for error_snapshots router (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.features.error_snapshots.router import (
    _compute_stats,
    _empty_filters_response,
    _empty_list_response,
    _empty_stats,
    _require_service,
    delete_snapshot,
    generate_replay,
    get_available_filters,
    get_snapshot,
    get_snapshot_stats,
    get_snapshot_stats_summary,
    list_snapshots,
    update_snapshot_resolution,
)


def _make_user(tenant_id: str = "acme"):
    user = MagicMock()
    user.tenant_id = tenant_id
    return user


def _make_snapshot_item():
    item = MagicMock()
    item.trigger = MagicMock()
    item.trigger.value = "5xx"
    item.source = "kong"
    item.status = 500
    item.resolution_status = MagicMock()
    item.resolution_status.value = "unresolved"
    item.masked_fields = []
    return item


def _make_list_result(items=None, total: int = 1):
    result = MagicMock()
    result.items = items or []
    result.total = total
    return result


# ── Helpers ──


class TestHelpers:
    def test_empty_list_response(self):
        result = _empty_list_response(1, 20)
        assert result.items == []
        assert result.total == 0
        assert result.page == 1
        assert result.page_size == 20

    def test_empty_list_response_custom_page(self):
        result = _empty_list_response(3, 50)
        assert result.page == 3
        assert result.page_size == 50

    def test_empty_stats(self):
        result = _empty_stats()
        assert result["total"] == 0
        assert "by_trigger" in result
        assert "resolution_stats" in result

    def test_empty_filters_response(self):
        result = _empty_filters_response()
        assert isinstance(result.triggers, list)
        assert isinstance(result.sources, list)
        assert len(result.resolution_statuses) > 0

    def test_require_service_raises_503_when_none(self):
        with pytest.raises(HTTPException) as exc_info:
            _require_service(None)
        assert exc_info.value.status_code == 503

    def test_require_service_returns_service_when_set(self):
        mock_svc = MagicMock()
        result = _require_service(mock_svc)
        assert result is mock_svc


# ── list_snapshots ──


class TestListSnapshots:
    async def test_returns_empty_when_no_service(self):
        user = _make_user()
        result = await list_snapshots(user=user, service=None)
        assert result.items == []
        assert result.total == 0

    async def test_calls_service_and_returns_result(self):
        user = _make_user()
        mock_service = AsyncMock()
        list_result = _make_list_result([_make_snapshot_item()], total=1)
        mock_service.list = AsyncMock(return_value=list_result)

        result = await list_snapshots(user=user, service=mock_service)
        assert result is list_result
        mock_service.list.assert_awaited_once()

    async def test_returns_empty_on_storage_exception(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.list = AsyncMock(side_effect=Exception("storage down"))

        result = await list_snapshots(user=user, service=mock_service)
        assert result.items == []
        assert result.total == 0

    async def test_uses_unknown_when_tenant_id_is_none(self):
        user = _make_user(tenant_id=None)
        mock_service = AsyncMock()
        mock_service.list = AsyncMock(return_value=_make_list_result())

        await list_snapshots(user=user, service=mock_service)
        call_kwargs = mock_service.list.call_args[1]
        assert call_kwargs["tenant_id"] == "unknown"


# ── get_snapshot_stats / get_snapshot_stats_summary ──


class TestGetSnapshotStats:
    async def test_stats_returns_empty_when_no_service(self):
        user = _make_user()
        result = await get_snapshot_stats(user=user, service=None)
        assert result["total"] == 0

    async def test_stats_summary_returns_empty_when_no_service(self):
        user = _make_user()
        result = await get_snapshot_stats_summary(user=user, service=None)
        assert result["total"] == 0

    async def test_stats_with_items(self):
        user = _make_user()
        mock_service = AsyncMock()
        item = _make_snapshot_item()
        list_result = _make_list_result([item], total=1)
        mock_service.list = AsyncMock(return_value=list_result)

        result = await get_snapshot_stats(user=user, service=mock_service)
        assert result["total"] == 1

    async def test_stats_returns_empty_on_exception(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.list = AsyncMock(side_effect=Exception("oops"))

        result = await get_snapshot_stats(user=user, service=mock_service)
        assert result["total"] == 0


# ── get_available_filters ──


class TestGetAvailableFilters:
    async def test_returns_empty_when_no_service(self):
        user = _make_user()
        result = await get_available_filters(user=user, service=None)
        assert isinstance(result.triggers, list)

    async def test_extracts_filters_from_items(self):
        user = _make_user()
        mock_service = AsyncMock()
        item = _make_snapshot_item()
        list_result = _make_list_result([item], total=1)
        mock_service.list = AsyncMock(return_value=list_result)

        result = await get_available_filters(user=user, service=mock_service)
        assert "kong" in result.sources
        assert 500 in result.status_codes

    async def test_returns_empty_filters_on_exception(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.list = AsyncMock(side_effect=Exception("storage error"))

        result = await get_available_filters(user=user, service=mock_service)
        assert isinstance(result.triggers, list)


# ── get_snapshot ──


class TestGetSnapshot:
    async def test_raises_503_when_no_service(self):
        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await get_snapshot("snap-1", user=user, service=None)
        assert exc_info.value.status_code == 503

    async def test_returns_snapshot_when_found(self):
        user = _make_user()
        mock_service = AsyncMock()
        snapshot = MagicMock()
        mock_service.get = AsyncMock(return_value=snapshot)

        result = await get_snapshot("snap-1", user=user, service=mock_service)
        assert result is snapshot

    async def test_raises_404_when_not_found(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_snapshot("snap-missing", user=user, service=mock_service)
        assert exc_info.value.status_code == 404


# ── update_snapshot_resolution ──


class TestUpdateSnapshotResolution:
    async def test_raises_503_when_no_service(self):
        from src.features.error_snapshots.models import ResolutionStatus, ResolutionUpdate

        user = _make_user()
        body = ResolutionUpdate(resolution_status=ResolutionStatus.RESOLVED)
        with pytest.raises(HTTPException) as exc_info:
            await update_snapshot_resolution("snap-1", body, user=user, service=None)
        assert exc_info.value.status_code == 503

    async def test_raises_404_when_not_found(self):
        from src.features.error_snapshots.models import ResolutionStatus, ResolutionUpdate

        user = _make_user()
        mock_service = AsyncMock()
        mock_service.get = AsyncMock(return_value=None)
        body = ResolutionUpdate(resolution_status=ResolutionStatus.RESOLVED)

        with pytest.raises(HTTPException) as exc_info:
            await update_snapshot_resolution("snap-x", body, user=user, service=mock_service)
        assert exc_info.value.status_code == 404

    async def test_updates_and_returns_snapshot(self):
        from src.features.error_snapshots.models import ResolutionStatus, ResolutionUpdate

        user = _make_user()
        mock_service = AsyncMock()
        snapshot = MagicMock()
        snapshot.masked_fields = []
        mock_service.get = AsyncMock(return_value=snapshot)
        mock_service.save = AsyncMock()
        body = ResolutionUpdate(resolution_status=ResolutionStatus.RESOLVED, resolution_notes="fixed")

        result = await update_snapshot_resolution("snap-1", body, user=user, service=mock_service)
        assert result is snapshot
        mock_service.save.assert_awaited_once_with(snapshot)

    async def test_skips_notes_when_none(self):
        from src.features.error_snapshots.models import ResolutionStatus, ResolutionUpdate

        user = _make_user()
        mock_service = AsyncMock()
        snapshot = MagicMock()
        mock_service.get = AsyncMock(return_value=snapshot)
        mock_service.save = AsyncMock()
        body = ResolutionUpdate(resolution_status=ResolutionStatus.INVESTIGATING)

        await update_snapshot_resolution("snap-1", body, user=user, service=mock_service)
        mock_service.save.assert_awaited_once()


# ── delete_snapshot ──


class TestDeleteSnapshot:
    async def test_raises_503_when_no_service(self):
        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await delete_snapshot("snap-1", user=user, service=None)
        assert exc_info.value.status_code == 503

    async def test_raises_404_when_not_deleted(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.delete = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await delete_snapshot("snap-x", user=user, service=mock_service)
        assert exc_info.value.status_code == 404

    async def test_deletes_successfully(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.delete = AsyncMock(return_value=True)

        # Should not raise
        await delete_snapshot("snap-1", user=user, service=mock_service)
        mock_service.delete.assert_awaited_once()


# ── generate_replay ──


class TestGenerateReplay:
    async def test_raises_503_when_no_service(self):
        user = _make_user()
        with pytest.raises(HTTPException) as exc_info:
            await generate_replay("snap-1", user=user, service=None)
        assert exc_info.value.status_code == 503

    async def test_raises_404_when_not_found(self):
        user = _make_user()
        mock_service = AsyncMock()
        mock_service.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await generate_replay("snap-x", user=user, service=mock_service)
        assert exc_info.value.status_code == 404

    async def test_returns_replay_response(self):
        user = _make_user()
        mock_service = AsyncMock()
        snapshot = MagicMock()
        snapshot.masked_fields = []
        mock_service.get = AsyncMock(return_value=snapshot)
        mock_service.generate_replay_curl = MagicMock(return_value="curl http://example.com")

        result = await generate_replay("snap-1", user=user, service=mock_service)
        assert result.curl_command == "curl http://example.com"
        assert result.warning is None

    async def test_includes_warning_when_masked_fields(self):
        user = _make_user()
        mock_service = AsyncMock()
        snapshot = MagicMock()
        snapshot.masked_fields = ["Authorization"]
        mock_service.get = AsyncMock(return_value=snapshot)
        mock_service.generate_replay_curl = MagicMock(return_value="curl ...")

        result = await generate_replay("snap-1", user=user, service=mock_service)
        assert result.warning is not None
        assert "REDACTED" in result.warning


# ── _compute_stats ──


class TestComputeStats:
    async def test_returns_empty_when_no_service(self):
        user = _make_user()
        result = await _compute_stats(None, None, user, None)
        assert result["total"] == 0

    async def test_aggregates_items(self):
        user = _make_user()
        mock_service = AsyncMock()
        item1 = _make_snapshot_item()
        item1.trigger.value = "5xx"
        item1.status = 500
        item1.resolution_status.value = "resolved"
        list_result = _make_list_result([item1], total=1)
        mock_service.list = AsyncMock(return_value=list_result)

        result = await _compute_stats(None, None, user, mock_service)
        assert result["total"] == 1
        assert result["by_trigger"]["5xx"] == 1
        assert result["by_status_code"][500] == 1
