"""Readiness must not wait on a secrets store that stops answering.

/health/ready used to call the store synchronously inside the async handler,
with hvac's 30 s default timeout, while the probe gives up after 5 s. A store
that accepts connections but never answers then took every replica out of
service and froze its event loop.
"""

import asyncio
import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.config import settings
from src.routers import health
from src.services import vault_client as vault_module
from src.services.vault_client import VaultClient


@pytest.fixture(autouse=True)
def _fresh_cache():
    health._reset_vault_readiness_cache()
    yield
    health._reset_vault_readiness_cache()


@pytest.fixture
def silent_store():
    """A TCP listener that accepts connections and never answers."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(16)
    yield f"http://127.0.0.1:{server.getsockname()[1]}"
    server.close()


@pytest.fixture
def healthy_deps():
    with (
        patch.object(health, "_check_keycloak_connected", return_value=True),
        patch.object(health, "_check_git_connected", return_value=True),
        patch.object(health, "_check_gateway_connected", return_value=True),
        patch.object(health, "_check_kafka_connected", return_value=True),
    ):
        yield


def _blocking_vault(release: threading.Event) -> MagicMock:
    vault = MagicMock()
    vault.enabled = True
    vault.health_check.side_effect = lambda: release.wait(10) and False
    return vault


def test_default_client_timeout_is_short():
    assert settings.VAULT_TIMEOUT_SECONDS == 3.0
    assert VaultClient(vault_addr="http://store.invalid").timeout == 3.0


def test_global_client_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings, "VAULT_TIMEOUT_SECONDS", 1.5)
    monkeypatch.setattr(vault_module, "_vault_client", None)
    try:
        assert vault_module.get_vault_client().timeout == 1.5
    finally:
        vault_module._vault_client = None


def test_hvac_client_receives_timeout():
    vc = VaultClient(vault_addr="http://store.invalid", vault_token="t", timeout=2.5)  # noqa: S106
    with patch("src.services.vault_client.hvac.Client") as client_cls:
        client_cls.return_value.is_authenticated.return_value = True
        vc._get_client()
    assert client_cls.call_args.kwargs["timeout"] == 2.5


def test_health_check_gives_up_on_silent_store(silent_store):
    vc = VaultClient(vault_addr=silent_store, vault_token="t", timeout=0.3)  # noqa: S106
    started = time.monotonic()
    assert vc.health_check() is False
    assert time.monotonic() - started < 2.0


@pytest.mark.asyncio
async def test_ready_answers_fast_when_store_hangs(monkeypatch, healthy_deps):
    monkeypatch.setattr(health, "VAULT_READINESS_TIMEOUT_SECONDS", 0.2)
    release = threading.Event()
    try:
        with patch.object(health, "get_vault_client", return_value=_blocking_vault(release)):
            started = time.monotonic()
            response = await health.readiness()
            first = time.monotonic() - started

            started = time.monotonic()
            again = await health.readiness()
            second = time.monotonic() - started
    finally:
        release.set()

    assert response.checks["vault"] == "timeout"
    assert response.status == "healthy"  # the store stays non-critical
    assert first < 1.0
    assert again.checks["vault"] == "timeout"
    assert second < 0.1  # cached: no new wait


@pytest.mark.asyncio
async def test_event_loop_keeps_running_during_store_check(monkeypatch, healthy_deps):
    monkeypatch.setattr(health, "VAULT_READINESS_TIMEOUT_SECONDS", 0.5)
    release = threading.Event()
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        with patch.object(health, "get_vault_client", return_value=_blocking_vault(release)):
            await health.readiness()
    finally:
        release.set()
        task.cancel()
    assert ticks >= 10


@pytest.mark.asyncio
async def test_only_one_store_check_in_flight(monkeypatch):
    monkeypatch.setattr(health, "VAULT_READINESS_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(health, "VAULT_READINESS_CACHE_TTL_SECONDS", 0.0)
    release = threading.Event()
    vault = _blocking_vault(release)
    try:
        with patch.object(health, "get_vault_client", return_value=vault):
            assert await health._vault_readiness_status() == "timeout"
            assert await health._vault_readiness_status() == "timeout"
    finally:
        release.set()
    assert vault.health_check.call_count == 1


@pytest.mark.asyncio
async def test_status_values_and_cache_expiry(monkeypatch):
    vault = MagicMock(enabled=True)
    vault.health_check.return_value = True
    with patch.object(health, "get_vault_client", return_value=vault):
        assert await health._vault_readiness_status() == "ok"
        vault.health_check.return_value = False
        assert await health._vault_readiness_status() == "ok"  # cached
        monkeypatch.setattr(health, "VAULT_READINESS_CACHE_TTL_SECONDS", 0.0)
        assert await health._vault_readiness_status() == "disconnected"
        vault.health_check.side_effect = RuntimeError("boom")
        assert await health._vault_readiness_status() == "error"


@pytest.mark.asyncio
async def test_disabled_store():
    with patch.object(health, "get_vault_client", return_value=MagicMock(enabled=False)):
        assert await health._vault_readiness_status() == "disabled"
