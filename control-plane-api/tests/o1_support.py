"""Real SQLAlchemy sessions for O1 tests; PostgreSQL is an explicit test opt-in."""

import os
import re
from collections.abc import AsyncGenerator
from uuid import uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.schema import CreateSchema, DropSchema

from src.models.catalog import APICatalog
from src.models.gateway_deployment import GatewayDeployment
from src.models.gateway_instance import GatewayInstance
from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding
from src.models.promotion import Promotion


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


def postgres_test_url(value: str) -> str:
    """Refuse implicit app databases and keep DSNs out of validation errors."""
    try:
        parsed = make_url(value)
        valid = (
            parsed.drivername == "postgresql+asyncpg"
            and parsed.database is not None
            and re.fullmatch(r"stoa_o1_test_[a-z0-9_]{1,40}", parsed.database) is not None
            and not parsed.query
        )
    except Exception:
        valid = False
    if not valid:
        raise ValueError("An explicit PostgreSQL stoa_o1_test_* database URL is required") from None
    return value


async def local_session(url: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    pg_override = os.environ.get("STOA_O1_PG_TEST_URL")
    if url is None:
        url = postgres_test_url(pg_override) if pg_override is not None else "sqlite+aiosqlite:///:memory:"
    try:
        driver = make_url(url).drivername
    except Exception:
        raise ValueError("Invalid test database URL") from None
    schema = None
    connect_args = {}
    if driver == "postgresql+asyncpg":
        postgres_test_url(url)
        schema = "stoa_o1_" + uuid4().hex
        connect_args = {"server_settings": {"search_path": schema}}
    elif driver != "sqlite+aiosqlite":
        raise ValueError("Only SQLite or the explicit PostgreSQL test database is supported")
    engine = create_async_engine(url, echo=False, hide_parameters=True, connect_args=connect_args)
    try:
        async with engine.begin() as conn:
            if schema:
                await conn.execute(CreateSchema(schema))
            models = (APICatalog, GatewayInstance, GatewayDeployment, GatewayPolicy, GatewayPolicyBinding)
            if schema:
                # Real FK target must exist before GatewayDeployment on PostgreSQL.
                models = (APICatalog, GatewayInstance, Promotion, GatewayDeployment, GatewayPolicy, GatewayPolicyBinding)
            for model in models:
                await conn.run_sync(model.__table__.create)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        try:
            if schema:
                async with engine.begin() as conn:
                    await conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            await engine.dispose()
