"""Tests for kopf handlers — GatewayInstance and GatewayBinding."""

import pytest
from src.handlers.gateway_binding import (
    on_gwb_create,
    on_gwb_delete,
    on_gwb_resume,
    on_gwb_update,
)
from src.handlers.gateway_instance import (
    on_gwi_create,
    on_gwi_delete,
    on_gwi_resume,
    on_gwi_update,
)


class FakePatch:
    """Mimics kopf.Patch for testing status writes."""

    def __init__(self):
        self.status = {}


# --- GatewayInstance tests ---


@pytest.mark.asyncio
async def test_gwi_create_sets_offline():
    patch = FakePatch()
    spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    result = await on_gwi_create(
        spec=spec,
        name="kong-prod",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["phase"] == "offline"
    assert patch.status["error"] == ""
    assert "lastHealthCheck" in patch.status
    assert "initialized" in result["message"]


@pytest.mark.asyncio
async def test_gwi_update_acknowledges():
    spec = {"gatewayType": "kong", "baseUrl": "http://kong:8001"}
    result = await on_gwi_update(
        spec=spec,
        old={"spec": spec},
        new={"spec": {**spec, "baseUrl": "http://kong:8002"}},
        name="kong-prod",
        namespace="stoa-system",
        diff=[],
    )
    assert "acknowledged" in result["message"]


@pytest.mark.asyncio
async def test_gwi_delete_does_not_crash():
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    await on_gwi_delete(spec=spec, name="stoa-gw", namespace="stoa-system")


@pytest.mark.asyncio
async def test_gwi_resume_logs_phase():
    spec = {"gatewayType": "stoa", "baseUrl": "http://gw:8080"}
    status = {"phase": "online"}
    await on_gwi_resume(
        spec=spec,
        status=status,
        name="stoa-gw",
        namespace="stoa-system",
    )


# --- GatewayBinding tests ---


@pytest.mark.asyncio
async def test_gwb_create_sets_pending():
    patch = FakePatch()
    spec = {
        "apiRef": {"name": "petstore"},
        "gatewayRef": {"name": "kong-prod"},
    }
    result = await on_gwb_create(
        spec=spec,
        name="petstore-kong",
        namespace="stoa-system",
        patch=patch,
    )
    assert patch.status["syncStatus"] == "pending"
    assert patch.status["syncAttempts"] == 0
    assert patch.status["syncError"] == ""
    assert "initialized" in result["message"]


@pytest.mark.asyncio
async def test_gwb_update_resets_on_spec_change():
    patch = FakePatch()
    old_spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    new_spec = {"apiRef": {"name": "petstore-v2"}, "gatewayRef": {"name": "kong-prod"}}
    result = await on_gwb_update(
        spec=new_spec,
        old={"spec": old_spec},
        new={"spec": new_spec},
        name="petstore-kong",
        namespace="stoa-system",
        diff=[],
        patch=patch,
    )
    assert patch.status["syncStatus"] == "pending"
    assert patch.status["syncAttempts"] == 0
    assert "acknowledged" in result["message"]


@pytest.mark.asyncio
async def test_gwb_update_skips_non_spec_change():
    patch = FakePatch()
    spec = {"apiRef": {"name": "petstore"}, "gatewayRef": {"name": "kong-prod"}}
    result = await on_gwb_update(
        spec=spec,
        old={"spec": spec, "metadata": {"labels": {}}},
        new={"spec": spec, "metadata": {"labels": {"new": "label"}}},
        name="petstore-kong",
        namespace="stoa-system",
        diff=[],
        patch=patch,
    )
    assert "syncStatus" not in patch.status
    assert "acknowledged" in result["message"]


@pytest.mark.asyncio
async def test_gwb_delete_does_not_crash():
    spec = {
        "apiRef": {"name": "petstore"},
        "gatewayRef": {"name": "kong-prod"},
    }
    await on_gwb_delete(spec=spec, name="petstore-kong", namespace="stoa-system")


@pytest.mark.asyncio
async def test_gwb_resume_logs_sync_status():
    spec = {
        "apiRef": {"name": "petstore"},
        "gatewayRef": {"name": "kong-prod"},
    }
    status = {"syncStatus": "synced"}
    await on_gwb_resume(
        spec=spec,
        status=status,
        name="petstore-kong",
        namespace="stoa-system",
    )
