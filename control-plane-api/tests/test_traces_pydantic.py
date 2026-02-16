"""Tests for traces Pydantic models — TraceStep, PipelineTrace, TraceStore (CAB-1291)"""
from datetime import datetime

from src.models.traces import (
    PipelineTrace,
    TraceStatus,
    TraceStep,
    TraceStore,
)


# ── TraceStep ──


class TestTraceStep:
    def test_defaults(self):
        step = TraceStep(name="fetch")
        assert step.name == "fetch"
        assert step.status == TraceStatus.PENDING
        assert step.started_at is None
        assert step.completed_at is None
        assert step.duration_ms is None
        assert step.details is None
        assert step.error is None

    def test_start(self):
        step = TraceStep(name="fetch")
        step.start()
        assert step.status == TraceStatus.IN_PROGRESS
        assert step.started_at is not None

    def test_complete(self):
        step = TraceStep(name="fetch")
        step.start()
        step.complete(details={"rows": 42})
        assert step.status == TraceStatus.SUCCESS
        assert step.completed_at is not None
        assert step.duration_ms is not None
        assert step.duration_ms >= 0
        assert step.details == {"rows": 42}

    def test_complete_without_start(self):
        step = TraceStep(name="fetch")
        step.complete()
        assert step.status == TraceStatus.SUCCESS
        assert step.duration_ms is None  # no started_at

    def test_fail(self):
        step = TraceStep(name="fetch")
        step.start()
        step.fail("timeout", details={"retry": 3})
        assert step.status == TraceStatus.FAILED
        assert step.error == "timeout"
        assert step.details == {"retry": 3}
        assert step.duration_ms is not None

    def test_fail_without_start(self):
        step = TraceStep(name="fetch")
        step.fail("error")
        assert step.status == TraceStatus.FAILED
        assert step.duration_ms is None


# ── PipelineTrace ──


class TestPipelineTrace:
    def test_defaults(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        assert t.id is not None
        assert t.trigger_type == "manual"
        assert t.status == TraceStatus.PENDING
        assert t.steps == []
        assert t.created_at is not None

    def test_add_step(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        step = t.add_step("validate")
        assert isinstance(step, TraceStep)
        assert step.name == "validate"
        assert len(t.steps) == 1

    def test_get_step_found(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        t.add_step("validate")
        t.add_step("deploy")
        step = t.get_step("deploy")
        assert step is not None
        assert step.name == "deploy"

    def test_get_step_not_found(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        assert t.get_step("nonexistent") is None

    def test_start(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        t.start()
        assert t.status == TraceStatus.IN_PROGRESS

    def test_complete(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        t.start()
        t.complete()
        assert t.status == TraceStatus.SUCCESS
        assert t.completed_at is not None
        assert t.total_duration_ms is not None

    def test_fail(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        t.start()
        t.fail("deployment error")
        assert t.status == TraceStatus.FAILED
        assert t.error_summary == "deployment error"
        assert t.total_duration_ms is not None

    def test_to_summary(self):
        t = PipelineTrace(
            trigger_type="gitlab-push",
            trigger_source="gitlab",
            tenant_id="acme",
            api_name="weather",
            git_author="alice",
            git_commit_sha="abc1234567890",
            git_commit_message="feat: add endpoint",
        )
        t.add_step("validate")
        t.steps[0].start()
        t.steps[0].complete()
        t.add_step("deploy")

        summary = t.to_summary()
        assert summary["trigger_type"] == "gitlab-push"
        assert summary["tenant_id"] == "acme"
        assert summary["api_name"] == "weather"
        assert summary["git_commit_sha"] == "abc12345"  # truncated to 8
        assert summary["steps_count"] == 2
        assert summary["steps_completed"] == 1
        assert summary["steps_failed"] == 0

    def test_to_summary_no_sha(self):
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        summary = t.to_summary()
        assert summary["git_commit_sha"] is None


# ── TraceStore ──


class TestTraceStore:
    def test_save_and_get(self):
        store = TraceStore()
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        store.save(t)
        assert store.get(t.id) is t

    def test_get_not_found(self):
        store = TraceStore()
        assert store.get("nonexistent") is None

    def test_list_recent(self):
        store = TraceStore()
        for i in range(5):
            t = PipelineTrace(trigger_type="manual", trigger_source="api")
            store.save(t)
        traces = store.list_recent(limit=3)
        assert len(traces) == 3

    def test_list_recent_by_tenant(self):
        store = TraceStore()
        t1 = PipelineTrace(trigger_type="manual", trigger_source="api", tenant_id="acme")
        t2 = PipelineTrace(trigger_type="manual", trigger_source="api", tenant_id="corp")
        store.save(t1)
        store.save(t2)
        traces = store.list_recent(tenant_id="acme")
        assert len(traces) == 1
        assert traces[0].tenant_id == "acme"

    def test_list_by_status(self):
        store = TraceStore()
        t1 = PipelineTrace(trigger_type="manual", trigger_source="api")
        t1.start()
        t1.complete()
        t2 = PipelineTrace(trigger_type="manual", trigger_source="api")
        store.save(t1)
        store.save(t2)
        successes = store.list_by_status(TraceStatus.SUCCESS)
        assert len(successes) == 1

    def test_max_capacity(self):
        store = TraceStore(max_traces=3)
        ids = []
        for i in range(5):
            t = PipelineTrace(trigger_type="manual", trigger_source="api")
            store.save(t)
            ids.append(t.id)
        # First 2 should be evicted
        assert store.get(ids[0]) is None
        assert store.get(ids[1]) is None
        assert store.get(ids[2]) is not None
        assert store.get(ids[4]) is not None

    def test_update_existing(self):
        store = TraceStore()
        t = PipelineTrace(trigger_type="manual", trigger_source="api")
        store.save(t)
        t.start()
        store.save(t)  # should update, not duplicate
        traces = store.list_recent()
        assert len(traces) == 1
        assert traces[0].status == TraceStatus.IN_PROGRESS

    def test_get_stats_empty(self):
        store = TraceStore()
        stats = store.get_stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}
        assert stats["avg_duration_ms"] == 0
        assert stats["success_rate"] == 0

    def test_get_stats_with_data(self):
        store = TraceStore()
        t1 = PipelineTrace(trigger_type="manual", trigger_source="api")
        t1.start()
        t1.complete()
        t2 = PipelineTrace(trigger_type="manual", trigger_source="api")
        t2.start()
        t2.fail("error")
        t3 = PipelineTrace(trigger_type="manual", trigger_source="api")
        store.save(t1)
        store.save(t2)
        store.save(t3)

        stats = store.get_stats()
        assert stats["total"] == 3
        assert stats["by_status"]["success"] == 1
        assert stats["by_status"]["failed"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["avg_duration_ms"] >= 0
