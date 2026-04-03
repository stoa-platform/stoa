"""Regression test for CAB-1965: portal search LIKE doesn't match numeric sequences.

PR: #TBD
Ticket: CAB-1965
Root cause: get_portal_apis() search filter didn't include the `version` column,
  so searching for version numbers (e.g., "2.0", "3.1") returned no results.
  Also, api_name wasn't wrapped in coalesce() — NULL api_name + NULL description
  + non-matching api_id made some APIs invisible to search.
Invariant: Portal search matches against api_name, description, api_id, AND version.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.repositories.catalog import CatalogRepository, escape_like


class TestEscapeLikeNumeric:
    """escape_like must not interfere with numeric sequences."""

    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("123", "123"),
            ("20022", "20022"),
            ("v2.0", "v2.0"),
            ("3.1.0", "3.1.0"),
            ("api_123", "api\\_123"),  # underscore escaped, digits preserved
            ("100%", "100\\%"),
        ],
    )
    def test_escape_like_preserves_digits(self, input_val, expected):
        assert escape_like(input_val) == expected


class TestPortalSearchIncludesVersion:
    """get_portal_apis() search must include the version column (CAB-1965)."""

    @pytest.mark.asyncio
    async def test_search_with_numeric_version(self):
        """Searching for a version number must produce a query that includes version."""
        db = MagicMock()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()

        mock_api = MagicMock()
        mock_api.api_id = "siren-api"
        mock_api.api_name = "SIREN API"
        mock_api.version = "2.0.0"
        mock_api.api_metadata = {"description": "French business registry"}
        mock_api.portal_published = True
        mock_api.deleted_at = None
        mock_api.status = "active"
        mock_api.category = "government"
        mock_api.tags = []
        mock_api.audience = "public"

        mock_list.scalars.return_value.all.return_value = [mock_api]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        _items, total = await repo.get_portal_apis(search="2.0")
        assert total == 1
        # Verify the execute was called (query was built without error)
        assert db.execute.call_count == 2

        # Verify the compiled query text includes version column reference
        # (the second call is the list query with the search filter)
        list_query = db.execute.call_args_list[1][0][0]
        compiled = str(list_query.compile(compile_kwargs={"literal_binds": True}))
        assert "version" in compiled.lower()
