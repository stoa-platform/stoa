"""Migration rollback must preserve the GDPR read/write path and chain state."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration() -> ModuleType:
    spec = spec_from_file_location("audit_migration", VERSIONS / "107_audit_immutability_pseudonymization.py")
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql(direction: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        getattr(_migration(), direction)()
    return output.getvalue()


def test_regression_downgrade_only_removes_immutability_enforcement() -> None:
    """Whitelist rollback DDL so neither data nor redaction dependencies vanish."""
    statements = [statement.strip() for statement in _sql("downgrade").split(";") if statement.strip()]
    assert statements == [
        "DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events",
        "DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events",
        "DROP FUNCTION IF EXISTS audit_events_immutable()",
    ]


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
        "ADD COLUMN IF NOT EXISTS row_hash BYTEA",
        "CREATE TABLE IF NOT EXISTS audit_chain_heads",
        "CREATE TABLE IF NOT EXISTS pseudonymized_audit_erasures",
        "CREATE INDEX IF NOT EXISTS idx_pseudo_erasures_actor_ids",
        "CREATE INDEX IF NOT EXISTS idx_pseudo_erasures_event_ids",
        "CREATE OR REPLACE FUNCTION _audit_is_redacted(",
        "CREATE OR REPLACE VIEW audit_events_redacted AS",
    ],
)
def test_regression_reupgrade_reuses_retained_schema(statement: str) -> None:
    assert statement in _sql("upgrade")


def test_regression_reupgrade_restores_both_immutability_triggers() -> None:
    sql = _sql("upgrade")
    assert "CREATE OR REPLACE FUNCTION audit_events_immutable()" in sql
    for action in ("update", "delete"):
        drop = f"DROP TRIGGER IF EXISTS audit_events_no_{action} ON audit_events"
        create = f"CREATE TRIGGER audit_events_no_{action}"
        assert sql.index(drop) < sql.index(create)
