"""Keep imported guard tests compatible with the application's session loop."""

import asyncio
from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def guard_loop(event_loop: asyncio.AbstractEventLoop) -> Generator[None, None, None]:
    """Restore loop selection around unittest's independent asyncio Runner."""
    policy = asyncio.get_event_loop_policy()
    try:
        previous = policy.get_event_loop()
    except RuntimeError:
        previous = None
    policy.set_event_loop(event_loop)
    try:
        yield
    finally:
        policy.set_event_loop(previous if previous is not None and not previous.is_closed() else None)
