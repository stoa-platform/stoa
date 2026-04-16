"""
Spec-driven tests for the unified Docker Seeder.

Each test maps to an Acceptance Criterion (AC) or Edge Case from SPEC.md.
All tests MUST fail (red) until implementation is complete.

Run: cd control-plane-api && pytest tests/test_spec_seeder.py -v
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# AC1-AC3: Profile data creation
# ---------------------------------------------------------------------------


class TestProfileDataCreation:
    """AC1/AC2/AC3: Each profile creates the correct dataset."""

    def test_ac1_dev_profile_module_importable(self):
        """AC1: The seeder module exists and is importable."""
        from scripts.seeder import profiles  # noqa: F401
        from scripts.seeder.profiles.dev import STEPS as dev_steps

        assert len(dev_steps) >= 7, (
            "Dev profile must define at least 7 steps: "
            "tenants, gateway, apis, plans, consumers, mcp_servers, security_posture"
        )

    def test_ac1_dev_profile_has_all_step_types(self):
        """AC1: Dev profile includes all step types."""
        from scripts.seeder.profiles.dev import STEPS

        step_names = {s.name for s in STEPS}
        expected = {
            "tenants",
            "gateway",
            "apis",
            "plans",
            "consumers",
            "mcp_servers",
            "security_posture",
        }
        assert expected.issubset(step_names), f"Dev profile missing steps: {expected - step_names}"

    def test_ac2_staging_profile_reduced_dataset(self):
        """AC2: Staging profile has reduced steps (no prospects)."""
        from scripts.seeder.profiles.staging import STEPS

        step_names = {s.name for s in STEPS}
        assert "prospects" not in step_names, "Staging must NOT include prospects"
        assert "tenants" in step_names, "Staging must include tenants"
        assert "apis" in step_names, "Staging must include apis"

    def test_ac3_prod_profile_bootstrap_only(self):
        """AC3: Prod profile creates only admin tenant + gateway."""
        from scripts.seeder.profiles.prod import STEPS

        step_names = {s.name for s in STEPS}
        assert step_names == {"tenants", "gateway"}, f"Prod profile must only have tenants+gateway, got: {step_names}"


# ---------------------------------------------------------------------------
# AC4: Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    """AC4: Running seeder twice produces no duplicates."""

    @pytest.mark.integration
    async def test_ac4_double_run_no_duplicates(self, integration_db):
        """AC4: Second run with same profile skips existing data."""
        from scripts.seeder.runner import SeederRunner

        runner = SeederRunner(session=integration_db, profile="dev")

        result1 = await runner.run()
        assert result1.exit_code == 0

        result2 = await runner.run()
        assert result2.exit_code == 0
        # Second run should have created=0 for all steps
        for step_result in result2.steps:
            assert step_result.created == 0, (
                f"Step '{step_result.name}' created {step_result.created} rows " f"on second run (expected 0)"
            )


# ---------------------------------------------------------------------------
# AC5: Dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    """AC5: --dry-run logs operations without writing."""

    @pytest.mark.integration
    async def test_ac5_dry_run_no_writes(self, integration_db):
        """AC5: Dry run does not insert any rows."""
        from scripts.seeder.runner import SeederRunner
        from sqlalchemy import text

        count_before = (await integration_db.execute(text("SELECT COUNT(*) FROM tenants"))).scalar_one()

        runner = SeederRunner(session=integration_db, profile="dev", dry_run=True)
        result = await runner.run()
        assert result.exit_code == 0

        count_after = (await integration_db.execute(text("SELECT COUNT(*) FROM tenants"))).scalar_one()
        assert count_after == count_before, "Dry run must not insert rows"


# ---------------------------------------------------------------------------
# AC6: Check mode
# ---------------------------------------------------------------------------


class TestCheckMode:
    """AC6: --check verifies expected data exists."""

    @pytest.mark.integration
    async def test_ac6_check_empty_db_exits_1(self, integration_db):
        """AC6: Check on empty DB reports missing entities."""
        from scripts.seeder.runner import SeederRunner

        runner = SeederRunner(session=integration_db, profile="dev", check_only=True)
        result = await runner.run()
        assert result.exit_code == 1
        assert len(result.missing) > 0, "Check must report missing entities"

    @pytest.mark.integration
    async def test_ac6_check_after_seed_exits_0(self, integration_db):
        """AC6: Check after seeding reports all present."""
        from scripts.seeder.runner import SeederRunner

        # Seed first
        runner = SeederRunner(session=integration_db, profile="dev")
        await runner.run()

        # Check
        checker = SeederRunner(session=integration_db, profile="dev", check_only=True)
        result = await checker.run()
        assert result.exit_code == 0
        assert len(result.missing) == 0


# ---------------------------------------------------------------------------
# AC7: Reset blocked in prod
# ---------------------------------------------------------------------------


class TestResetProdBlocked:
    """AC7: --reset with prod profile is refused."""

    def test_ac7_reset_prod_exits_1(self):
        """AC7: Reset + prod = error."""
        from scripts.seeder.runner import SeederRunner

        with pytest.raises(ValueError, match="Reset is not allowed in prod profile"):
            SeederRunner(session=AsyncMock(), profile="prod", reset=True)


# ---------------------------------------------------------------------------
# AC8: Reset in dev
# ---------------------------------------------------------------------------


class TestResetDev:
    """AC8: --reset with dev deletes and re-creates seed data."""

    @pytest.mark.integration
    async def test_ac8_reset_dev_recreates(self, integration_db):
        """AC8: Reset deletes seeder-tagged rows then re-creates."""
        from scripts.seeder.runner import SeederRunner
        from sqlalchemy import text

        # Initial seed
        runner = SeederRunner(session=integration_db, profile="dev")
        await runner.run()

        count_after_seed = (await integration_db.execute(text("SELECT COUNT(*) FROM tenants"))).scalar_one()
        assert count_after_seed > 0

        # Reset
        resetter = SeederRunner(session=integration_db, profile="dev", reset=True)
        result = await resetter.run()
        assert result.exit_code == 0

        # Data still exists (re-created)
        count_after_reset = (await integration_db.execute(text("SELECT COUNT(*) FROM tenants"))).scalar_one()
        assert count_after_reset > 0


# ---------------------------------------------------------------------------
# AC10: Single step execution
# ---------------------------------------------------------------------------


class TestSingleStep:
    """AC10: --step runs only the specified step."""

    @pytest.mark.integration
    async def test_ac10_single_step_tenants(self, integration_db):
        """AC10: --step tenants runs only tenants."""
        from scripts.seeder.runner import SeederRunner

        runner = SeederRunner(session=integration_db, profile="dev", step="tenants")
        result = await runner.run()
        assert result.exit_code == 0
        assert len(result.steps) == 1
        assert result.steps[0].name == "tenants"


# ---------------------------------------------------------------------------
# AC11: Structured logging
# ---------------------------------------------------------------------------


class TestStructuredLogging:
    """AC11: Each step logs created/skipped/failed counts."""

    @pytest.mark.integration
    async def test_ac11_step_result_has_counts(self, integration_db):
        """AC11: Step results include created/skipped/failed."""
        from scripts.seeder.runner import SeederRunner

        runner = SeederRunner(session=integration_db, profile="dev")
        result = await runner.run()

        for step_result in result.steps:
            assert hasattr(step_result, "created"), f"{step_result.name}: missing 'created'"
            assert hasattr(step_result, "skipped"), f"{step_result.name}: missing 'skipped'"
            assert hasattr(step_result, "failed"), f"{step_result.name}: missing 'failed'"
            assert isinstance(step_result.created, int)
            assert isinstance(step_result.skipped, int)
            assert isinstance(step_result.failed, int)


# ---------------------------------------------------------------------------
# AC12: Step ordering and dependency validation
# ---------------------------------------------------------------------------


class TestStepOrdering:
    """AC12: Steps execute in dependency order."""

    def test_ac12_dev_step_order(self):
        """AC12: Dev profile steps are in topological order."""
        from scripts.seeder.profiles.dev import STEPS

        step_names = [s.name for s in STEPS]
        # tenants must come before consumers, apis, mcp_servers
        assert step_names.index("tenants") < step_names.index("apis")
        assert step_names.index("tenants") < step_names.index("consumers")
        assert step_names.index("tenants") < step_names.index("mcp_servers")
        assert step_names.index("plans") < step_names.index("consumers")

    @pytest.mark.integration
    async def test_ac12_step_without_dependency_exits_1(self, integration_db):
        """AC12: Running --step consumers on empty DB fails with dependency error."""
        from scripts.seeder.runner import SeederRunner

        runner = SeederRunner(session=integration_db, profile="dev", step="consumers")
        result = await runner.run()
        assert result.exit_code == 1
        assert "Missing dependency" in str(result.error)


# ---------------------------------------------------------------------------
# AC13: Source tagging
# ---------------------------------------------------------------------------


class TestSourceTagging:
    """AC13: All seeder rows carry source=seeder."""

    @pytest.mark.integration
    async def test_ac13_tenants_have_source_tag(self, integration_db):
        """AC13: Created tenants are tagged with source=seeder."""
        from scripts.seeder.runner import SeederRunner
        from sqlalchemy import text

        runner = SeederRunner(session=integration_db, profile="dev")
        await runner.run()

        # Check that seeder-created tenants have the source tag
        # The exact column depends on implementation (metadata JSON or dedicated column)
        result = await integration_db.execute(
            text("SELECT id FROM tenants WHERE " "metadata->>'source' = 'seeder' OR source = 'seeder'")
        )
        rows = result.fetchall()
        assert len(rows) > 0, "Seeder tenants must have source=seeder tag"


# ---------------------------------------------------------------------------
# AC14: Reset staging with warning
# ---------------------------------------------------------------------------


class TestResetStaging:
    """AC14: --reset with staging succeeds with warning."""

    def test_ac14_reset_staging_allowed(self):
        """AC14: Reset + staging does not raise (unlike prod)."""
        from scripts.seeder.runner import SeederRunner

        # Should NOT raise — staging reset is allowed
        runner = SeederRunner(session=AsyncMock(), profile="staging", reset=True)
        assert runner.reset is True


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases from SPEC.md."""

    def test_edge_unknown_profile(self):
        """Unknown profile raises clear error."""
        from scripts.seeder.runner import SeederRunner

        with pytest.raises(ValueError, match=r"Unknown profile: qa\. Valid: dev, staging, prod"):
            SeederRunner(session=AsyncMock(), profile="qa")

    def test_edge_unknown_step(self):
        """Unknown step raises clear error."""
        from scripts.seeder.runner import SeederRunner

        with pytest.raises(ValueError, match="Unknown step: foo"):
            SeederRunner(session=AsyncMock(), profile="dev", step="foo")

    @pytest.mark.integration
    async def test_edge_partial_previous_run(self, integration_db):
        """Partial previous run: seeder fills in missing data."""

        from scripts.seeder.runner import SeederRunner

        # Run only tenants step
        runner = SeederRunner(session=integration_db, profile="dev", step="tenants")
        await runner.run()

        # Now run full — should create remaining data without errors
        full_runner = SeederRunner(session=integration_db, profile="dev")
        result = await full_runner.run()
        assert result.exit_code == 0
        # Tenants step should have skipped (already exist)
        tenants_step = next(s for s in result.steps if s.name == "tenants")
        assert tenants_step.created == 0
        assert tenants_step.skipped > 0


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


class TestCLIEntrypoint:
    """Verify the CLI entrypoint exists and parses args."""

    _CWD = str(Path(__file__).resolve().parent.parent)

    def test_cli_module_importable(self):
        """The __main__.py module exists."""
        from scripts.seeder import __main__  # noqa: F401

    def test_cli_help_exits_0(self):
        """--help exits 0 with usage info."""
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "scripts.seeder", "--help"],
            capture_output=True,
            text=True,
            cwd=self._CWD,
        )
        assert result.returncode == 0
        assert "--profile" in result.stdout
        assert "--dry-run" in result.stdout

    def test_cli_unknown_profile_exits_nonzero(self):
        """Unknown profile exits non-zero with error message."""
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "scripts.seeder", "--profile", "qa"],
            capture_output=True,
            text=True,
            cwd=self._CWD,
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr or "Unknown profile" in result.stderr
