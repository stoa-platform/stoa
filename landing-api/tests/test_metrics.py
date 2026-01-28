# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for metrics endpoint."""

import pytest
from httpx import AsyncClient


class TestMetrics:
    """Tests for GET /api/v1/invites/{invite_id}/metrics."""

    async def test_metrics_empty_invite(self, client: AsyncClient):
        """Test metrics for invite with no events."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Get metrics
        response = await client.get(f"/api/v1/invites/{invite_id}/metrics")

        assert response.status_code == 200
        data = response.json()

        assert data["invite_id"] == invite_id
        assert data["email"] == "test@test.com"
        assert data["company"] == "Test"
        assert data["total_events"] == 0
        assert data["timeline"] == []
        assert data["metrics"]["time_to_sandbox_seconds"] is None
        assert data["metrics"]["time_to_first_tool_seconds"] is None
        assert data["metrics"]["tools_called_count"] == 0

    async def test_metrics_time_to_sandbox(self, client: AsyncClient):
        """Test time_to_sandbox calculation."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        token = invite_response.json()["token"]

        # Open invite (records invite_opened)
        await client.get(f"/welcome/{token}", follow_redirects=False)

        # Record sandbox_created
        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "sandbox_created",
                "metadata": {},
            },
        )

        # Get metrics
        response = await client.get(f"/api/v1/invites/{invite_id}/metrics")
        data = response.json()

        # time_to_sandbox should be calculated (small value since events are close)
        assert data["metrics"]["time_to_sandbox_seconds"] is not None
        assert data["metrics"]["time_to_sandbox_seconds"] >= 0

    async def test_metrics_time_to_first_tool(self, client: AsyncClient):
        """Test time_to_first_tool calculation."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record sandbox_created
        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "sandbox_created",
                "metadata": {},
            },
        )

        # Record tool_called
        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "tool_called",
                "metadata": {"tool": "list_apis"},
            },
        )

        # Get metrics
        response = await client.get(f"/api/v1/invites/{invite_id}/metrics")
        data = response.json()

        assert data["metrics"]["time_to_first_tool_seconds"] is not None
        assert data["metrics"]["time_to_first_tool_seconds"] >= 0

    async def test_metrics_event_counts(self, client: AsyncClient):
        """Test event count calculations."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record various events
        for _ in range(3):
            await client.post(
                "/api/v1/events",
                json={
                    "invite_id": invite_id,
                    "event_type": "tool_called",
                    "metadata": {},
                },
            )

        for _ in range(2):
            await client.post(
                "/api/v1/events",
                json={
                    "invite_id": invite_id,
                    "event_type": "page_viewed",
                    "metadata": {},
                },
            )

        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "error_encountered",
                "metadata": {"error": "test"},
            },
        )

        # Get metrics
        response = await client.get(f"/api/v1/invites/{invite_id}/metrics")
        data = response.json()

        assert data["total_events"] == 6
        assert data["metrics"]["tools_called_count"] == 3
        assert data["metrics"]["pages_viewed_count"] == 2
        assert data["metrics"]["errors_encountered_count"] == 1

    async def test_metrics_timeline_order(self, client: AsyncClient):
        """Test that timeline is in chronological order."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        token = invite_response.json()["token"]

        # Record events in sequence
        await client.get(f"/welcome/{token}", follow_redirects=False)
        await client.post(
            "/api/v1/events",
            json={"invite_id": invite_id, "event_type": "sandbox_created", "metadata": {}},
        )
        await client.post(
            "/api/v1/events",
            json={"invite_id": invite_id, "event_type": "tool_called", "metadata": {}},
        )

        # Get metrics
        response = await client.get(f"/api/v1/invites/{invite_id}/metrics")
        timeline = response.json()["timeline"]

        assert len(timeline) == 3
        assert timeline[0]["event_type"] == "invite_opened"
        assert timeline[1]["event_type"] == "sandbox_created"
        assert timeline[2]["event_type"] == "tool_called"

    async def test_metrics_not_found(self, client: AsyncClient):
        """Test metrics for non-existent invite."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/invites/{fake_id}/metrics")

        assert response.status_code == 404
