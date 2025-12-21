"""Pipeline trace models for end-to-end monitoring"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum
import uuid


class TraceStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TraceStep(BaseModel):
    """Individual step in a pipeline trace"""
    name: str
    status: TraceStatus = TraceStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    details: Optional[dict] = None
    error: Optional[str] = None

    def start(self):
        self.status = TraceStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()

    def complete(self, details: Optional[dict] = None):
        self.status = TraceStatus.SUCCESS
        self.completed_at = datetime.utcnow()
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        if details:
            self.details = details

    def fail(self, error: str, details: Optional[dict] = None):
        self.status = TraceStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error = error
        if self.started_at:
            self.duration_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
        if details:
            self.details = details


class PipelineTrace(BaseModel):
    """Complete pipeline trace from trigger to completion"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Trigger info
    trigger_type: str  # gitlab-push, gitlab-mr, api-call, manual
    trigger_source: str  # gitlab, ui, api

    # Git info (for GitLab triggers)
    git_commit_sha: Optional[str] = None
    git_commit_message: Optional[str] = None
    git_branch: Optional[str] = None
    git_author: Optional[str] = None
    git_author_email: Optional[str] = None
    git_project: Optional[str] = None
    git_files_changed: Optional[List[str]] = None

    # Target info
    tenant_id: Optional[str] = None
    api_id: Optional[str] = None
    api_name: Optional[str] = None
    environment: Optional[str] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_duration_ms: Optional[int] = None

    # Overall status
    status: TraceStatus = TraceStatus.PENDING

    # Pipeline steps
    steps: List[TraceStep] = Field(default_factory=list)

    # Error summary
    error_summary: Optional[str] = None

    def add_step(self, name: str) -> TraceStep:
        """Add a new step to the trace"""
        step = TraceStep(name=name)
        self.steps.append(step)
        return step

    def get_step(self, name: str) -> Optional[TraceStep]:
        """Get a step by name"""
        for step in self.steps:
            if step.name == name:
                return step
        return None

    def start(self):
        """Mark trace as in progress"""
        self.status = TraceStatus.IN_PROGRESS

    def complete(self):
        """Mark trace as completed successfully"""
        self.status = TraceStatus.SUCCESS
        self.completed_at = datetime.utcnow()
        self.total_duration_ms = int((self.completed_at - self.created_at).total_seconds() * 1000)

    def fail(self, error: str):
        """Mark trace as failed"""
        self.status = TraceStatus.FAILED
        self.error_summary = error
        self.completed_at = datetime.utcnow()
        self.total_duration_ms = int((self.completed_at - self.created_at).total_seconds() * 1000)

    def to_summary(self) -> dict:
        """Return a summary for list views"""
        return {
            "id": self.id,
            "trigger_type": self.trigger_type,
            "trigger_source": self.trigger_source,
            "tenant_id": self.tenant_id,
            "api_name": self.api_name,
            "git_author": self.git_author,
            "git_commit_sha": self.git_commit_sha[:8] if self.git_commit_sha else None,
            "git_commit_message": self.git_commit_message,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "total_duration_ms": self.total_duration_ms,
            "steps_count": len(self.steps),
            "steps_completed": len([s for s in self.steps if s.status == TraceStatus.SUCCESS]),
            "steps_failed": len([s for s in self.steps if s.status == TraceStatus.FAILED]),
        }


# In-memory store for traces (in production, use Redis or PostgreSQL)
class TraceStore:
    """In-memory trace storage with max capacity"""

    def __init__(self, max_traces: int = 1000):
        self._traces: dict[str, PipelineTrace] = {}
        self._order: list[str] = []  # Keep insertion order
        self._max_traces = max_traces

    def save(self, trace: PipelineTrace) -> None:
        """Save or update a trace"""
        if trace.id not in self._traces:
            self._order.append(trace.id)
            # Remove oldest if at capacity
            while len(self._order) > self._max_traces:
                oldest_id = self._order.pop(0)
                del self._traces[oldest_id]
        self._traces[trace.id] = trace

    def get(self, trace_id: str) -> Optional[PipelineTrace]:
        """Get a trace by ID"""
        return self._traces.get(trace_id)

    def list_recent(self, limit: int = 50, tenant_id: Optional[str] = None) -> List[PipelineTrace]:
        """List recent traces, optionally filtered by tenant"""
        traces = list(self._traces.values())
        if tenant_id:
            traces = [t for t in traces if t.tenant_id == tenant_id]
        # Sort by created_at descending
        traces.sort(key=lambda t: t.created_at, reverse=True)
        return traces[:limit]

    def list_by_status(self, status: TraceStatus, limit: int = 50) -> List[PipelineTrace]:
        """List traces by status"""
        traces = [t for t in self._traces.values() if t.status == status]
        traces.sort(key=lambda t: t.created_at, reverse=True)
        return traces[:limit]

    def get_stats(self) -> dict:
        """Get statistics about traces"""
        traces = list(self._traces.values())
        if not traces:
            return {
                "total": 0,
                "by_status": {},
                "avg_duration_ms": 0,
                "success_rate": 0,
            }

        by_status = {}
        for status in TraceStatus:
            by_status[status.value] = len([t for t in traces if t.status == status])

        completed = [t for t in traces if t.total_duration_ms]
        avg_duration = sum(t.total_duration_ms for t in completed) / len(completed) if completed else 0

        total_finished = by_status.get("success", 0) + by_status.get("failed", 0)
        success_rate = (by_status.get("success", 0) / total_finished * 100) if total_finished > 0 else 0

        return {
            "total": len(traces),
            "by_status": by_status,
            "avg_duration_ms": int(avg_duration),
            "success_rate": round(success_rate, 1),
        }


# Global trace store
trace_store = TraceStore()
