"""Unit tests for prospects_service — CAB-1378

Tests the prospect data orchestration layer.
Due to deep SQLAlchemy coupling, these tests focus on the list/detail/metrics
functions with mocked db.execute results.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.services.prospects_service import (
    export_prospects_csv,
    get_prospect_detail,
    list_prospects,
)


def _mock_invite(**overrides):
    """Create a mock Invite object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "email": "test@example.com",
        "company": "Acme Corp",
        "status": "pending",
        "source": "website",
        "created_at": datetime(2026, 2, 1),
        "opened_at": None,
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(mock, k, v)
    return mock


class TestListProspects:
    """list_prospects function."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_response(self):
        """Returns ProspectListResponse with data and meta."""
        invite = _mock_invite()
        mock_row = (invite, None, None, None, None, 0)

        db = AsyncMock()
        # count query returns 1
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # data query returns rows
        data_result = MagicMock()
        data_result.all.return_value = [mock_row]

        db.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await list_prospects(db)

        assert result.meta.total == 1
        assert len(result.data) == 1
        assert result.data[0].email == "test@example.com"

    @pytest.mark.asyncio
    async def test_list_empty_results(self):
        """Returns empty list when no prospects."""
        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        data_result = MagicMock()
        data_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await list_prospects(db)

        assert result.meta.total == 0
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_nps_categorization(self):
        """NPS scores are categorized correctly."""
        # nps_score=10 → promoter
        invite = _mock_invite()
        mock_row = (invite, 10, "Great!", None, None, 3)

        db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        data_result = MagicMock()
        data_result.all.return_value = [mock_row]
        db.execute = AsyncMock(side_effect=[count_result, data_result])

        result = await list_prospects(db)

        assert result.data[0].nps_score == 10
        assert result.data[0].nps_category == "promoter"


class TestGetProspectDetail:
    """get_prospect_detail function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        """Returns None for unknown invite_id."""
        db = AsyncMock()
        result = MagicMock()
        result.first.return_value = None
        db.execute = AsyncMock(return_value=result)

        detail = await get_prospect_detail(db, uuid4())

        assert detail is None


class TestExportCSV:
    """export_prospects_csv function."""

    @pytest.mark.asyncio
    async def test_csv_header(self):
        """CSV export includes correct header row."""
        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        csv_content = await export_prospects_csv(db)

        lines = csv_content.strip().split("\n")
        assert "ID" in lines[0]
        assert "Email" in lines[0]
        assert "Company" in lines[0]
        assert "NPS Score" in lines[0]

    @pytest.mark.asyncio
    async def test_csv_with_data(self):
        """CSV export includes data rows."""
        invite = _mock_invite(opened_at=datetime(2026, 2, 1, 10, 0))
        mock_row = (invite, 9, "Nice!", datetime(2026, 2, 1, 10, 5))

        db = AsyncMock()
        result = MagicMock()
        result.all.return_value = [mock_row]
        db.execute = AsyncMock(return_value=result)

        csv_content = await export_prospects_csv(db)

        lines = csv_content.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert "test@example.com" in lines[1]
        assert "Acme Corp" in lines[1]
