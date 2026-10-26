"""Native generator cleanup without changing event routing or authentication."""

import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest

from src.auth.dependencies import User
from src.events.event_bus import EventBus, Subscriber, event_bus
from src.routers import events, gateway_internal


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def until(predicate: Callable[[], bool]) -> None:
    async with asyncio.timeout(1):
        while not predicate():
            ready = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(ready.set_result, None)
            await ready


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["tenant", "link"])
@pytest.mark.parametrize("json_error", [False, True], ids=["close", "json-error"])
async def test_regression_cab_2256_sse_cleanup_preserves_other_consumer(
    monkeypatch: pytest.MonkeyPatch, kind: str, json_error: bool
) -> None:
    assert event_bus.subscriber_count == 0
    assert events.event_bus is event_bus
    listeners: list[tuple[Subscriber, AsyncGenerator[dict, None]]] = []
    original_listen = event_bus.listen

    def record_listener(subscriber: Subscriber) -> AsyncGenerator[dict, None]:
        listener = original_listen(subscriber)
        assert listener.ag_code is EventBus.listen.__code__
        listeners.append((subscriber, listener))  # Strong reference prevents GC from closing it.
        return listener

    monkeypatch.setattr(event_bus, "listen", record_listener)
    user = User(id="fixture", email="fixture@example.test", username="fixture", roles=["viewer"])

    def consumer(types: list[str]) -> AsyncGenerator[dict, None]:
        request = ConnectedRequest()
        if kind == "tenant":
            return events.event_generator(request, "tenant", user, types)
        return gateway_internal._link_event_generator(request, "gateway", types)

    victim = consumer(["sync-deployment", "sync-policy"])
    survivor = consumer(["sync-deployment"])
    first = [asyncio.create_task(anext(stream)) for stream in (victim, survivor)]
    try:
        await until(lambda: event_bus.subscriber_count == 2 and len(listeners) == 2)
        assert await event_bus.publish("tenant", "sync-deployment", {"revision": 0}, "gateway") == 2
        assert [message["data"] for message in await asyncio.gather(*first)] == ['{"revision": 0}'] * 2
        victim_sub, victim_listener = listeners[0]
        survivor_sub, survivor_listener = listeners[1]
        assert victim_sub.queue is not survivor_sub.queue
        assert await event_bus.publish("tenant", "sync-deployment", {"revision": 1}, "gateway") == 2
        assert (await anext(victim))["data"] == '{"revision": 1}'
        if json_error:
            assert await event_bus.publish("tenant", "sync-policy", {"value": object()}, "gateway") == 1
            with pytest.raises(TypeError) as caught:
                await anext(victim)
            assert caught.value.__cause__ is None
            assert caught.value.__context__ is None
        else:
            await victim.aclose()
        assert victim.ag_frame is None
        assert victim_listener.ag_frame is None, "inner listener must close in the consumer task"
        assert event_bus._subscribers == {survivor_sub.id: survivor_sub}
        assert survivor_listener.ag_frame is not None
        assert await event_bus.publish("tenant", "sync-deployment", {"revision": 2}, "gateway") == 1
        assert [(await anext(survivor))["data"] for _ in range(2)] == [
            '{"revision": 1}',
            '{"revision": 2}',
        ]
        await survivor.aclose()
        assert survivor_listener.ag_frame is None
        assert event_bus.subscriber_count == 0
    finally:
        for task in first:
            if not task.done():
                task.cancel()
        await asyncio.gather(*first, return_exceptions=True)
        for stream in (victim, survivor):
            await stream.aclose()
        for _, listener in listeners:
            await listener.aclose()
    assert event_bus.subscriber_count == 0
