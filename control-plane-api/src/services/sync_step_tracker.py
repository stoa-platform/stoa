"""SyncStepTracker — builds an ordered list of sync steps for deployment observability.

Each step records its name, status, timestamps, and optional detail.
Used by the SyncEngine (push mode) and stoa-connect (pull mode) to trace
individual operations within a single deployment sync cycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict


class SyncStep(TypedDict, total=False):
    """A single step in a sync pipeline."""

    name: str
    status: str  # running | success | failed | skipped
    started_at: str
    completed_at: str | None
    detail: str | None


class SyncStepTracker:
    """Accumulates sync steps and derives aggregate status.

    Usage::

        tracker = SyncStepTracker()
        tracker.start("spec_push")
        # ... do work ...
        tracker.complete("spec_push")
        tracker.start("policy_apply")
        tracker.fail("policy_apply", detail="rate-limit policy rejected")
        deployment.sync_steps = tracker.to_list()
        deployment.sync_error = tracker.first_error()
    """

    def __init__(self) -> None:
        self._steps: list[SyncStep] = []

    @classmethod
    def from_list(cls, steps: list[dict]) -> SyncStepTracker:
        """Reconstruct a tracker from a serialized step list."""
        tracker = cls()
        tracker._steps = [SyncStep(**s) for s in steps]  # type: ignore[arg-type]
        return tracker

    def start(self, name: str) -> None:
        """Record a step as running."""
        self._steps.append(
            SyncStep(
                name=name,
                status="running",
                started_at=_now_iso(),
                completed_at=None,
                detail=None,
            )
        )

    def complete(self, name: str, detail: str | None = None) -> None:
        """Mark a running step as success."""
        step = self._find(name)
        if step is not None:
            step["status"] = "success"
            step["completed_at"] = _now_iso()
            if detail:
                step["detail"] = detail

    def fail(self, name: str, detail: str | None = None) -> None:
        """Mark a running step as failed."""
        step = self._find(name)
        if step is not None:
            step["status"] = "failed"
            step["completed_at"] = _now_iso()
            if detail:
                step["detail"] = detail

    def skip(self, name: str, reason: str | None = None) -> None:
        """Record a step as skipped (never started)."""
        self._steps.append(
            SyncStep(
                name=name,
                status="skipped",
                started_at=_now_iso(),
                completed_at=_now_iso(),
                detail=reason,
            )
        )

    def to_list(self) -> list[dict]:
        """Return steps as a JSON-serializable list."""
        return [dict(s) for s in self._steps]

    def first_error(self) -> str | None:
        """Return detail of the first failed step, or None if all succeeded.

        This is used to derive ``GatewayDeployment.sync_error`` for backward
        compatibility with callers that only inspect the scalar field.
        """
        for step in self._steps:
            if step.get("status") == "failed":
                detail = step.get("detail")
                name = step.get("name", "unknown")
                return detail if detail else f"Step '{name}' failed"
        return None

    def _find(self, name: str) -> SyncStep | None:
        """Find the last step with the given name (most recent if duplicates)."""
        for step in reversed(self._steps):
            if step.get("name") == name:
                return step
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
