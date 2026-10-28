"""A Link subscription must receive only explicitly targeted events."""

import pytest

from src.events.event_bus import EventBus


@pytest.mark.asyncio
async def test_regression_cab_2256_targeted_link() -> None:
    bus = EventBus()
    own = bus.subscribe(gateway_id="own", event_types=["sync-deployment"])
    observer = bus.subscribe(tenant_id="tenant")
    assert await bus.publish("tenant", "sync-deployment", {}, gateway_id="own") == 2
    assert await bus.publish("tenant", "sync-deployment", {}, gateway_id="other") == 1
    assert await bus.publish("tenant", "sync-deployment", {}) == 1
    assert own.queue.qsize() == 1
    assert observer.queue.qsize() == 3
