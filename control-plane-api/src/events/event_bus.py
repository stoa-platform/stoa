"""In-memory event bus for SSE fan-out (CAB-1420).

Multiple SSE clients subscribe to the bus. Events published here are
fanned out to every subscriber whose filter matches. This replaces the
heartbeat-only SSE generator with real Kafka-backed events.

Architecture:
    Kafka consumer (background task) → event_bus.publish() → N SSE queues
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Subscriber:
    """A connected SSE client."""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    tenant_id: str = "*"
    event_types: list[str] | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))

    def accepts(self, tenant_id: str, event_type: str) -> bool:
        if self.tenant_id != "*" and self.tenant_id != tenant_id:
            return False
        return not (self.event_types and event_type not in self.event_types)


class EventBus:
    """Pub/sub bus with tenant-scoped fan-out."""

    def __init__(self) -> None:
        self._subscribers: dict[str, Subscriber] = {}

    def subscribe(self, tenant_id: str = "*", event_types: list[str] | None = None) -> Subscriber:
        sub = Subscriber(tenant_id=tenant_id, event_types=event_types)
        self._subscribers[sub.id] = sub
        logger.debug("SSE subscriber %s added (tenant=%s)", sub.id, tenant_id)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        self._subscribers.pop(sub.id, None)
        logger.debug("SSE subscriber %s removed", sub.id)

    async def publish(self, tenant_id: str, event_type: str, data: dict) -> int:
        """Fan-out an event to all matching subscribers. Returns delivery count."""
        delivered = 0
        for sub in list(self._subscribers.values()):
            if sub.accepts(tenant_id, event_type):
                try:
                    sub.queue.put_nowait({"event": event_type, "data": data})
                    delivered += 1
                except asyncio.QueueFull:
                    logger.warning("SSE queue full for subscriber %s, dropping event", sub.id)
        return delivered

    async def listen(self, sub: Subscriber) -> AsyncGenerator[dict, None]:
        """Yield events from a subscriber's queue (for SSE generator)."""
        try:
            while True:
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=25.0)
                    yield event
                except TimeoutError:
                    yield {"event": "heartbeat", "data": {"status": "connected"}}
        except asyncio.CancelledError:
            pass
        finally:
            self.unsubscribe(sub)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Singleton instance
event_bus = EventBus()
