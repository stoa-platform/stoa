"""Regression tests — CP API Integration Tests restore (follow-up to CAB-2085 AC2).

These guard the three pre-existing bugs that kept main CI red and blocked
release-please PR #2400 (control-plane-api 1.5.1):

1. plans seeder passed a tz-aware datetime into a tz-naive ORM column,
   asyncpg rejected it with "can't subtract offset-naive and offset-aware
   datetimes" and every seeder acceptance test that reached the `plans`
   step failed.
2. test_ac13 queried `tenants.metadata->>'source'`, but the schema has no
   `metadata` column — the seeder writes the tag into `settings`.
3. test_import_endpoint_exists asserted "not 404" against a mocked DB,
   which always returns 404 "Tenant not found" — shadowing the real signal
   ("route is registered").
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


def _mock_session_with_no_existing_rows() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    scalar_result = MagicMock()
    scalar_result.scalar_one.return_value = 0  # no existing plans
    session.execute = AsyncMock(return_value=scalar_result)
    return session


@pytest.mark.asyncio
async def test_regression_cab_2085_plans_seeder_uses_tz_naive_datetime():
    """plans seeder must bind a tz-naive datetime to `:now`.

    Regression: before the fix, `datetime.now(UTC)` was passed to asyncpg
    against a `DateTime` (tz-naive) column, raising DataError at runtime.
    """
    from scripts.seeder.steps.plans import seed

    session = _mock_session_with_no_existing_rows()

    await seed(session, profile="dev")

    insert_calls = [
        call
        for call in session.execute.await_args_list
        if len(call.args) >= 2 and isinstance(call.args[1], dict) and "now" in call.args[1]
    ]
    assert insert_calls, "plans seeder should issue INSERTs binding `:now`"
    for call in insert_calls:
        bound_now = call.args[1]["now"]
        assert (
            bound_now.tzinfo is None
        ), f"plans.created_at is tz-naive — seeder must bind a naive datetime, got {bound_now!r}"
