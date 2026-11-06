"""Exercise permission decisions against a real isolated database."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from src.models.tenant_tool_permission import TenantToolPermission
from src.routers.tenant_tool_permissions import _permission_cache, check_tool_allowed


@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("rule", [None, False, True])
async def test_regression_explicit_allow_required(scoped: bool, rule: bool | None) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    server = uuid.uuid4()
    tenant = str(uuid.uuid4())
    try:
        async with engine.begin() as connection:
            await connection.run_sync(TenantToolPermission.__table__.create)
        async with AsyncSession(engine) as db:
            db.add(
                TenantToolPermission(
                    tenant_id=tenant,
                    mcp_server_id=server,
                    tool_name="unrelated",
                    allowed=True,
                    created_by="test",
                )
            )
            if rule is not None:
                db.add(
                    TenantToolPermission(
                        tenant_id=tenant,
                        mcp_server_id=server,
                        tool_name="target",
                        allowed=rule,
                        created_by="test",
                    )
                )
            await db.commit()
            scope = server if scoped else None
            # Both the initial database load and the subsequent cache hit must agree.
            for _ in range(2):
                assert await check_tool_allowed(tenant, "target", db, scope) is (rule is True)
            assert await check_tool_allowed(tenant, "target", db, uuid.uuid4()) is False
            assert await check_tool_allowed(str(uuid.uuid4()), "target", db, scope) is False
    finally:
        await _permission_cache.clear()
        await engine.dispose()
