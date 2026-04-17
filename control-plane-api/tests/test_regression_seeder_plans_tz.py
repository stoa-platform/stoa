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
    # Steps use SELECT COUNT(*) → scalar_one() == 0 OR SELECT id/slug →
    # scalar_one_or_none() is None, both meaning "row does not exist yet".
    scalar_result.scalar_one.return_value = 0
    scalar_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=scalar_result)
    return session


# Steps whose target table uses `DateTime` (tz-naive) columns in the ORM.
# asyncpg rejects tz-aware datetimes against those columns, so each of
# these seeder steps must bind a naive UTC value.
TZ_NAIVE_STEPS = [
    "plans",
    "consumers",
    "mcp_servers",
    "security_posture",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("step_name", TZ_NAIVE_STEPS)
async def test_regression_cab_2085_seeder_steps_bind_tz_naive_datetime(step_name: str):
    """Every seeder step writing into tz-naive columns must bind a naive `:now`.

    Regression: `datetime.now(UTC)` was passed to asyncpg against `DateTime`
    (tz-naive) columns, raising DataError at runtime and blocking
    release-please PR #2400 for cp-api 1.5.1.
    """
    import importlib

    module = importlib.import_module(f"scripts.seeder.steps.{step_name}")

    session = _mock_session_with_no_existing_rows()
    await module.seed(session, profile="dev")

    insert_calls = [
        call
        for call in session.execute.await_args_list
        if len(call.args) >= 2 and isinstance(call.args[1], dict) and "now" in call.args[1]
    ]
    assert insert_calls, f"{step_name} seeder should issue INSERTs binding `:now`"
    for call in insert_calls:
        bound_now = call.args[1]["now"]
        assert bound_now.tzinfo is None, (
            f"{step_name}: target column is tz-naive — seeder must bind a " f"naive datetime, got {bound_now!r}"
        )
