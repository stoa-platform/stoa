"""Publish Link notifications only once desired state is visible to readers."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.events.event_bus import event_bus

_PENDING = "stoa_link_events"


def queue_link_event(session: AsyncSession, *, tenant_id: str, event_type: str, data: dict, gateway_id: str) -> None:
    if session.in_nested_transaction():
        raise ValueError("Link notifications require a top-level transaction")
    session.info.setdefault(_PENDING, []).append(
        {"tenant_id": tenant_id, "event_type": event_type, "data": data, "gateway_id": gateway_id}
    )


@event.listens_for(Session, "after_commit")
def publish_committed(session: Session) -> None:
    if not session.in_nested_transaction():
        for payload in session.info.pop(_PENDING, []):
            event_bus.publish_nowait(**payload)


@event.listens_for(Session, "after_rollback")
def discard_rolled_back(session: Session) -> None:
    if not session.in_nested_transaction():
        session.info.pop(_PENDING, None)
