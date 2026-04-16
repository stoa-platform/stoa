"""
Regression test for CAB-1977 — alembic must never have multiple heads.

After PR #2297 (migration 092, drop execution_logs) landed alongside
093_add_security_posture_tables + 094_seed_gateway_deployments that had
independently branched off 091, alembic had two concurrent heads on main.
`alembic upgrade head` errored with "Multiple head revisions are present"
and prod stayed stuck at 090 — migration 092 (the whole point of #2297)
could not run.

PR #2386 added 095_merge_heads (no-op merge migration) to collapse the
graph back to one head. This test asserts the same property at CI time
so the next divergence is caught before it hits prod.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_regression_cab_1977_single_alembic_head():
    """Alembic migration tree must have exactly one head."""
    repo_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, (
        f"alembic has {len(heads)} heads ({heads!r}); expected exactly 1. "
        "Add a merge migration listing all heads as down_revision tuple to reconcile."
    )
