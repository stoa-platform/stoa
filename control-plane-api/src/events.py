"""
Simple Event Bus for Internal Events

CAB-865: Prepare for CAB-866 Keycloak sync

Pattern: Publish/Subscribe with async handlers.
Future: Replace with Kafka for distributed events.
"""
import asyncio
import logging
from typing import Callable, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base event structure."""
    event_type: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str = ""


class EventBus:
    """
    Simple in-process event bus.

    Events:
    - client.created
    - client.deleted
    - client.certificate.created
    - client.certificate.renewed
    - client.certificate.revoked

    Usage:
        from src.events import event_bus, EVENT_CERTIFICATE_CREATED

        # Subscribe to events
        @event_bus.on(EVENT_CERTIFICATE_CREATED)
        async def handle_cert_created(event: Event):
            # Sync to Keycloak (CAB-866)
            pass

        # Publish events
        await event_bus.publish(EVENT_CERTIFICATE_CREATED, {
            "client_id": "...",
            "fingerprint": "..."
        })
    """

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Handler subscribed to {event_type}")

    def on(self, event_type: str) -> Callable:
        """Decorator to subscribe to an event type."""
        def decorator(handler: Callable) -> Callable:
            self.subscribe(event_type, handler)
            return handler
        return decorator

    async def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish an event to all subscribers."""
        event = Event(event_type=event_type, payload=payload)

        handlers = self._handlers.get(event_type, [])
        logger.info(f"Publishing event {event_type} to {len(handlers)} handlers")

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler failed for {event_type}: {e}", exc_info=True)


# Global event bus instance
event_bus = EventBus()

# Pre-register event types for documentation
EVENT_CLIENT_CREATED = "client.created"
EVENT_CLIENT_UPDATED = "client.updated"
EVENT_CLIENT_DELETED = "client.deleted"
EVENT_CERTIFICATE_CREATED = "client.certificate.created"
EVENT_CERTIFICATE_RENEWED = "client.certificate.renewed"
EVENT_CERTIFICATE_REVOKED = "client.certificate.revoked"
