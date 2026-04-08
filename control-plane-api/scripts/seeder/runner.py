"""Seeder runner — orchestrates steps based on profile."""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

from scripts.seeder.models import SeederResult, StepDefinition, StepResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("stoa.seeder")

VALID_PROFILES = ("dev", "staging", "prod")

VALID_STEPS = (
    "tenants",
    "gateway",
    "apis",
    "plans",
    "consumers",
    "mcp_servers",
    "prospects",
    "security_posture",
)


def _load_profile(profile: str) -> list[StepDefinition]:
    """Load step definitions for a profile."""
    mod = importlib.import_module(f"scripts.seeder.profiles.{profile}")
    return mod.STEPS


def _load_step_module(step_name: str):
    """Load the step module (scripts.seeder.steps.<name>)."""
    return importlib.import_module(f"scripts.seeder.steps.{step_name}")


class SeederRunner:
    """Orchestrates seeder steps for a given profile.

    Args:
        session: Async SQLAlchemy session.
        profile: One of dev, staging, prod.
        dry_run: Log operations without writing.
        check_only: Verify data exists, don't create.
        reset: Delete seed data before re-creating.
        step: Run only this step (None = all).

    Raises:
        ValueError: If profile is unknown, step is unknown, or reset+prod.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        profile: str,
        dry_run: bool = False,
        check_only: bool = False,
        reset: bool = False,
        step: str | None = None,
    ) -> None:
        if profile not in VALID_PROFILES:
            raise ValueError(f"Unknown profile: {profile}. Valid: {', '.join(VALID_PROFILES)}")

        if reset and profile == "prod":
            raise ValueError("Reset is not allowed in prod profile")

        if step is not None and step not in VALID_STEPS:
            raise ValueError(f"Unknown step: {step}. Valid: {', '.join(VALID_STEPS)}")

        self.session = session
        self.profile = profile
        self.dry_run = dry_run
        self.check_only = check_only
        self.reset = reset
        self.step_filter = step

        self._steps = _load_profile(profile)
        self._step_names = {s.name for s in self._steps}

        if step and step not in self._step_names:
            raise ValueError(
                f"Step '{step}' is not available in profile '{profile}'. "
                f"Available: {', '.join(sorted(self._step_names))}"
            )

    async def run(self) -> SeederResult:
        """Execute the seeder pipeline."""
        result = SeederResult()

        if self.check_only:
            return await self._run_check(result)

        if self.reset:
            await self._run_reset()

        steps_to_run = self._steps
        if self.step_filter:
            steps_to_run = [s for s in self._steps if s.name == self.step_filter]

        for step_def in steps_to_run:
            # Check dependencies
            if self.step_filter and step_def.deps:
                dep_error = await self._check_deps(step_def)
                if dep_error:
                    result.exit_code = 1
                    result.error = dep_error
                    return result

            step_mod = _load_step_module(step_def.name)
            try:
                step_result = await step_mod.seed(self.session, self.profile, dry_run=self.dry_run)
                result.steps.append(step_result)

                if not self.dry_run:
                    await self.session.flush()

                _log_step(step_result)

            except Exception as exc:
                sr = StepResult(name=step_def.name, error=str(exc))
                sr.failed = 1
                result.steps.append(sr)
                logger.error("Step %s failed: %s", step_def.name, exc)
                result.exit_code = 1
                result.error = f"Step {step_def.name} failed: {exc}"
                return result

        return result

    async def _run_check(self, result: SeederResult) -> SeederResult:
        """Run check mode — verify expected data exists."""
        for step_def in self._steps:
            step_mod = _load_step_module(step_def.name)
            missing = await step_mod.check(self.session, self.profile)
            result.missing.extend(missing)

        if result.missing:
            result.exit_code = 1
        return result

    async def _run_reset(self) -> None:
        """Delete seeder-tagged data before re-creating."""
        if self.profile == "staging":
            logger.warning("WARNING: Resetting staging seed data")
            print("  WARNING: Resetting staging seed data")

        # Reset in reverse order (FK dependencies)
        for step_def in reversed(self._steps):
            if self.step_filter and step_def.name != self.step_filter:
                continue
            step_mod = _load_step_module(step_def.name)
            deleted = await step_mod.reset(self.session, self.profile)
            if deleted > 0:
                print(f"  [RESET] {step_def.name}: deleted {deleted} rows")

        await self.session.flush()

    async def _check_deps(self, step_def: StepDefinition) -> str | None:
        """Check that dependencies exist when running a single step."""
        for dep_name in step_def.deps:
            dep_mod = _load_step_module(dep_name)
            missing = await dep_mod.check(self.session, self.profile)
            if missing:
                return f"Missing dependency: {dep_name} ({', '.join(missing)})"
        return None


def _log_step(step_result: StepResult) -> None:
    """Log step result in structured format."""
    print(
        f"  [STEP] {step_result.name}: "
        f"created {step_result.created} / "
        f"skipped {step_result.skipped} / "
        f"failed {step_result.failed}"
    )
