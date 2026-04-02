"""Tests for SyncStepTracker helper (CAB-1945)."""

import pytest

from src.services.sync_step_tracker import SyncStepTracker


class TestSyncStepTracker:
    """Core tracker operations."""

    def test_empty_tracker(self) -> None:
        tracker = SyncStepTracker()
        assert tracker.to_list() == []
        assert tracker.first_error() is None

    def test_start_creates_running_step(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        steps = tracker.to_list()
        assert len(steps) == 1
        assert steps[0]["name"] == "spec_push"
        assert steps[0]["status"] == "running"
        assert steps[0]["started_at"] is not None
        assert steps[0]["completed_at"] is None

    def test_complete_marks_success(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push", detail="200 OK")
        steps = tracker.to_list()
        assert steps[0]["status"] == "success"
        assert steps[0]["completed_at"] is not None
        assert steps[0]["detail"] == "200 OK"

    def test_complete_without_detail(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push")
        steps = tracker.to_list()
        assert steps[0]["status"] == "success"
        assert steps[0]["detail"] is None

    def test_fail_marks_failed(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("policy_apply")
        tracker.fail("policy_apply", detail="rate-limit rejected")
        steps = tracker.to_list()
        assert steps[0]["status"] == "failed"
        assert steps[0]["detail"] == "rate-limit rejected"
        assert steps[0]["completed_at"] is not None

    def test_skip_records_skipped_step(self) -> None:
        tracker = SyncStepTracker()
        tracker.skip("activation", reason="already active")
        steps = tracker.to_list()
        assert len(steps) == 1
        assert steps[0]["name"] == "activation"
        assert steps[0]["status"] == "skipped"
        assert steps[0]["detail"] == "already active"

    def test_skip_without_reason(self) -> None:
        tracker = SyncStepTracker()
        tracker.skip("activation")
        steps = tracker.to_list()
        assert steps[0]["detail"] is None

    def test_multi_step_pipeline(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push")
        tracker.start("policy_apply")
        tracker.complete("policy_apply")
        tracker.start("activation")
        tracker.complete("activation")
        steps = tracker.to_list()
        assert len(steps) == 3
        assert all(s["status"] == "success" for s in steps)

    def test_multi_step_with_failure(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push")
        tracker.start("policy_apply")
        tracker.fail("policy_apply", detail="quota exceeded")
        tracker.skip("activation", reason="previous step failed")
        steps = tracker.to_list()
        assert len(steps) == 3
        assert steps[0]["status"] == "success"
        assert steps[1]["status"] == "failed"
        assert steps[2]["status"] == "skipped"


class TestFirstError:
    """sync_error derivation from step trace."""

    def test_no_error_returns_none(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push")
        assert tracker.first_error() is None

    def test_first_failed_step_detail(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.fail("spec_push", detail="connection refused")
        assert tracker.first_error() == "connection refused"

    def test_first_failed_step_without_detail(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.fail("spec_push")
        assert tracker.first_error() == "Step 'spec_push' failed"

    def test_multiple_failures_returns_first(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.fail("spec_push", detail="first error")
        tracker.start("policy_apply")
        tracker.fail("policy_apply", detail="second error")
        assert tracker.first_error() == "first error"


class TestFromList:
    """Reconstruct tracker from serialized steps."""

    def test_roundtrip(self) -> None:
        tracker = SyncStepTracker()
        tracker.start("spec_push")
        tracker.complete("spec_push")
        tracker.start("policy_apply")
        tracker.fail("policy_apply", detail="rejected")

        serialized = tracker.to_list()
        restored = SyncStepTracker.from_list(serialized)

        assert restored.to_list() == serialized
        assert restored.first_error() == "rejected"

    def test_from_empty_list(self) -> None:
        restored = SyncStepTracker.from_list([])
        assert restored.to_list() == []
        assert restored.first_error() is None


class TestCompleteOnUnknownStep:
    """Edge cases: complete/fail on non-existent step."""

    def test_complete_unknown_is_noop(self) -> None:
        tracker = SyncStepTracker()
        tracker.complete("nonexistent")
        assert tracker.to_list() == []

    def test_fail_unknown_is_noop(self) -> None:
        tracker = SyncStepTracker()
        tracker.fail("nonexistent")
        assert tracker.to_list() == []
