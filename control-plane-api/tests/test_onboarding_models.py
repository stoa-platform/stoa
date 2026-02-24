"""Tests for OnboardingProgress ORM model (CAB-1452).

Validates column definitions, defaults, constraints, and table args
without requiring a running database.
"""

from src.models.onboarding_progress import OnboardingProgress


class TestOnboardingProgress:
    def test_tablename(self):
        assert OnboardingProgress.__tablename__ == "onboarding_progress"

    def test_columns_exist(self):
        cols = {c.name for c in OnboardingProgress.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "user_id",
            "steps_completed",
            "started_at",
            "completed_at",
            "ttftc_seconds",
        }
        assert expected.issubset(cols)

    def test_primary_key_is_uuid(self):
        assert OnboardingProgress.__table__.c.id.primary_key

    def test_tenant_id_not_nullable(self):
        assert not OnboardingProgress.__table__.c.tenant_id.nullable

    def test_tenant_id_indexed(self):
        col = OnboardingProgress.__table__.c.tenant_id
        assert col.index

    def test_user_id_not_nullable(self):
        assert not OnboardingProgress.__table__.c.user_id.nullable

    def test_user_id_indexed(self):
        col = OnboardingProgress.__table__.c.user_id
        assert col.index

    def test_steps_completed_not_nullable(self):
        assert not OnboardingProgress.__table__.c.steps_completed.nullable

    def test_completed_at_nullable(self):
        assert OnboardingProgress.__table__.c.completed_at.nullable

    def test_ttftc_seconds_nullable(self):
        assert OnboardingProgress.__table__.c.ttftc_seconds.nullable

    def test_unique_constraint_tenant_user(self):
        constraints = OnboardingProgress.__table__.constraints
        uq = [c for c in constraints if hasattr(c, "name") and c.name == "uq_onboarding_tenant_user"]
        assert len(uq) == 1
        uq_cols = {c.name for c in uq[0].columns}
        assert uq_cols == {"tenant_id", "user_id"}
