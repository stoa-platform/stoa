"""Tests for SnapshotStorage key parsing (CAB-1291)"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.features.error_snapshots.config import SnapshotSettings
from src.features.error_snapshots.storage import SnapshotStorage


@pytest.fixture
def storage():
    with patch.dict("os.environ", {}, clear=True):
        settings = SnapshotSettings()
    return SnapshotStorage(settings)


class TestGetObjectKey:
    def test_standard_key(self, storage):
        snapshot = MagicMock()
        snapshot.tenant_id = "acme"
        snapshot.id = "SNP-20260215-093000-abc12345"
        snapshot.timestamp = datetime(2026, 2, 15, 9, 30, 0)

        key = storage._get_object_key(snapshot)
        assert key == "acme/2026/02/15/SNP-20260215-093000-abc12345.json.gz"

    def test_single_digit_month_day(self, storage):
        snapshot = MagicMock()
        snapshot.tenant_id = "globex"
        snapshot.id = "SNP-20260103-010000-xyz"
        snapshot.timestamp = datetime(2026, 1, 3, 1, 0, 0)

        key = storage._get_object_key(snapshot)
        assert key == "globex/2026/01/03/SNP-20260103-010000-xyz.json.gz"


class TestParseObjectKey:
    def test_valid_key(self, storage):
        key = "acme/2026/02/15/SNP-20260215-093000-abc12345.json.gz"
        meta = storage._parse_object_key(key)
        assert meta["tenant_id"] == "acme"
        assert meta["year"] == 2026
        assert meta["month"] == 2
        assert meta["day"] == 15
        assert meta["snapshot_id"] == "SNP-20260215-093000-abc12345"

    def test_invalid_key_wrong_parts(self, storage):
        assert storage._parse_object_key("too/few/parts") == {}
        assert storage._parse_object_key("a/b/c/d/e/f") == {}

    def test_round_trip(self, storage):
        snapshot = MagicMock()
        snapshot.tenant_id = "test"
        snapshot.id = "SNP-20261231-235959-ffffffff"
        snapshot.timestamp = datetime(2026, 12, 31, 23, 59, 59)

        key = storage._get_object_key(snapshot)
        meta = storage._parse_object_key(key)
        assert meta["tenant_id"] == "test"
        assert meta["snapshot_id"] == "SNP-20261231-235959-ffffffff"


class TestGetClient:
    def test_creates_session_if_none(self, storage):
        assert storage._session is None
        with patch("src.features.error_snapshots.storage.aioboto3") as mock_boto:
            mock_session = MagicMock()
            mock_boto.Session.return_value = mock_session
            storage._get_client()
            assert storage._session is mock_session
