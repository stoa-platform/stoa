"""Regression test for demo AT-0: fresh DB migrations must reach health probes."""

from pathlib import Path


def test_regression_cab_2149_alembic_version_widened_before_long_revision() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    migration = repo_root / "alembic" / "versions" / "053_add_rejected_subscription_status.py"
    source = migration.read_text(encoding="utf-8")

    widen_version = "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)"
    add_enum_value = "ALTER TYPE subscriptionstatus ADD VALUE"

    assert len("053_add_rejected_subscription_status") > 32
    assert widen_version in source
    assert source.index(widen_version) < source.index(add_enum_value)
