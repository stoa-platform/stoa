"""SQLAlchemy models for pipeline traces (PostgreSQL persistence)"""
import enum
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Text, Integer, DateTime, Enum, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TraceStatusDB(str, enum.Enum):
    """Trace status enum for database."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineTraceDB(Base):
    """SQLAlchemy model for pipeline traces."""
    __tablename__ = "pipeline_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Trigger info
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Git info
    git_commit_sha: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    git_commit_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    git_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_author_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_project: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    git_files_changed: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    # Target info
    tenant_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    api_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    api_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    environment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timing
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    status: Mapped[TraceStatusDB] = mapped_column(
        Enum(TraceStatusDB, values_callable=lambda x: [e.value for e in x], name="tracestatus", create_type=False),
        nullable=False,
        default=TraceStatusDB.PENDING,
        index=True
    )
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Steps as JSONB
    steps: Mapped[List[dict]] = mapped_column(JSONB, nullable=False, default=list)

    # Additional indexes
    __table_args__ = (
        Index('idx_traces_created_at', 'created_at'),
        Index('idx_traces_trigger_type', 'trigger_type'),
    )

    def to_summary(self) -> dict:
        """Return a summary for list views."""
        steps_completed = len([s for s in self.steps if s.get("status") == "success"])
        steps_failed = len([s for s in self.steps if s.get("status") == "failed"])

        return {
            "id": self.id,
            "trigger_type": self.trigger_type,
            "trigger_source": self.trigger_source,
            "tenant_id": self.tenant_id,
            "api_name": self.api_name,
            "git_author": self.git_author,
            "git_commit_sha": self.git_commit_sha[:8] if self.git_commit_sha else None,
            "git_commit_message": self.git_commit_message,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_duration_ms": self.total_duration_ms,
            "steps_count": len(self.steps),
            "steps_completed": steps_completed,
            "steps_failed": steps_failed,
        }

    def to_dict(self) -> dict:
        """Return full trace as dict."""
        return {
            "id": self.id,
            "trigger_type": self.trigger_type,
            "trigger_source": self.trigger_source,
            "git_commit_sha": self.git_commit_sha,
            "git_commit_message": self.git_commit_message,
            "git_branch": self.git_branch,
            "git_author": self.git_author,
            "git_author_email": self.git_author_email,
            "git_project": self.git_project,
            "git_files_changed": self.git_files_changed,
            "tenant_id": self.tenant_id,
            "api_id": self.api_id,
            "api_name": self.api_name,
            "environment": self.environment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_duration_ms": self.total_duration_ms,
            "status": self.status.value,
            "error_summary": self.error_summary,
            "steps": self.steps,
        }
