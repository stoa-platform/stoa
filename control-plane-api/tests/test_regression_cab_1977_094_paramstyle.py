"""
Regression test for CAB-1977 / migration 094_seed_gateway_deployments.

The original SQL in migration 094 mixed SQLAlchemy bind syntax with a
PostgreSQL cast (`:desired_state::jsonb`). SQLAlchemy's regex parser
cannot disambiguate `:name::type` and emits a literal `:name` into the
final psycopg2 query, which then rejects it:

    sqlalchemy.exc.ProgrammingError: (psycopg2.errors.SyntaxError)
    syntax error at or near ":"

Fix: use `CAST(:desired_state AS JSONB)` which is unambiguous.

This test compiles the offending statement under the live postgresql+
psycopg2 dialect with `literal_binds=False` (what alembic actually
uses) and asserts no stray `:`-prefixed bind survives into the
rendered SQL.
"""

import re

from sqlalchemy import text
from sqlalchemy.dialects import postgresql


# Kept identical to the SQL in
# control-plane-api/alembic/versions/094_seed_gateway_deployments.py.
# If the migration changes, update this block in lockstep.
INSERT_SQL = """
    INSERT INTO gateway_deployments
        (id, api_catalog_id, gateway_instance_id, desired_state,
         desired_at, sync_status, sync_attempts)
    VALUES
        (gen_random_uuid(), :api_catalog_id, :gateway_id,
         CAST(:desired_state AS JSONB), NOW(), 'pending', 0)
    ON CONFLICT ON CONSTRAINT uq_deployment_api_gateway DO NOTHING
"""


def test_regression_cab_1977_094_paramstyle_compiles():
    """Migration 094's INSERT must compile under postgresql+psycopg2 without stray `:` bindparams."""
    stmt = text(INSERT_SQL)
    compiled = stmt.compile(dialect=postgresql.dialect())
    rendered = str(compiled)

    # Every named bind should have been rewritten to %(name)s pyformat.
    # A surviving `:name` would indicate the old paramstyle-mix bug.
    assert not re.search(r":\w+", rendered), (
        f"migration 094 SQL still contains unbound `:name` placeholders; "
        f"rendered: {rendered!r}"
    )
    assert "%(api_catalog_id)s" in rendered
    assert "%(gateway_id)s" in rendered
    assert "%(desired_state)s" in rendered
    assert "CAST(%(desired_state)s AS JSONB)" in rendered
