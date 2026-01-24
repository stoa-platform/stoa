"""Tests for event tracking endpoints."""

import pytest
from httpx import AsyncClient


class TestRecordEvent:
    """Tests for POST /api/v1/events."""

    async def test_record_event_success(self, client: AsyncClient):
        """Test successful event recording."""
        # First create an invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record an event
        response = await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "tool_called",
                "metadata": {"tool_name": "search_apis", "duration_ms": 150},
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert data["recorded"] is True
        assert "id" in data

    async def test_record_event_invalid_invite(self, client: AsyncClient):
        """Test event recording with invalid invite ID."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.post(
            "/api/v1/events",
            json={
                "invite_id": fake_id,
                "event_type": "tool_called",
                "metadata": {},
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "invite_not_found"

    async def test_record_event_invalid_type(self, client: AsyncClient):
        """Test event recording with invalid event type."""
        # First create an invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        response = await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "invalid_event_type",
                "metadata": {},
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_record_event_metadata_stored(self, client: AsyncClient):
        """Test that event metadata is stored correctly."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record event with metadata
        metadata = {
            "tool_name": "list_apis",
            "duration_ms": 250,
            "result_count": 5,
        }

        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "tool_called",
                "metadata": metadata,
            },
        )

        # Get events and verify metadata
        response = await client.get(f"/api/v1/events?invite_id={invite_id}")
        events = response.json()["events"]

        assert len(events) == 1
        assert events[0]["metadata"] == metadata

    async def test_sandbox_created_marks_invite_converted(self, client: AsyncClient):
        """Test that sandbox_created event marks invite as converted."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        assert invite_response.json()["status"] == "pending"

        # Record sandbox_created event
        await client.post(
            "/api/v1/events",
            json={
                "invite_id": invite_id,
                "event_type": "sandbox_created",
                "metadata": {"api_key_id": "key-123"},
            },
        )

        # Check invite status
        invite = await client.get(f"/api/v1/invites/{invite_id}")
        assert invite.json()["status"] == "converted"


class TestListEvents:
    """Tests for GET /api/v1/events."""

    async def test_list_events_empty(self, client: AsyncClient):
        """Test listing events for invite with no events."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        response = await client.get(f"/api/v1/events?invite_id={invite_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["events"] == []
        assert data["total"] == 0

    async def test_list_events_with_data(self, client: AsyncClient):
        """Test listing events after recording some."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record multiple events
        event_types = ["page_viewed", "tool_called", "tool_called"]
        for event_type in event_types:
            await client.post(
                "/api/v1/events",
                json={
                    "invite_id": invite_id,
                    "event_type": event_type,
                    "metadata": {},
                },
            )

        response = await client.get(f"/api/v1/events?invite_id={invite_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert len(data["events"]) == 3

    async def test_list_events_filter_by_type(self, client: AsyncClient):
        """Test filtering events by type."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]

        # Record different event types
        await client.post(
            "/api/v1/events",
            json={"invite_id": invite_id, "event_type": "page_viewed", "metadata": {}},
        )
        await client.post(
            "/api/v1/events",
            json={"invite_id": invite_id, "event_type": "tool_called", "metadata": {}},
        )
        await client.post(
            "/api/v1/events",
            json={"invite_id": invite_id, "event_type": "tool_called", "metadata": {}},
        )

        # Filter by tool_called
        response = await client.get(
            f"/api/v1/events?invite_id={invite_id}&event_type=tool_called"
        )

        data = response.json()
        assert data["total"] == 2
        assert all(e["event_type"] == "tool_called" for e in data["events"])

    async def test_list_events_invalid_invite(self, client: AsyncClient):
        """Test listing events for non-existent invite."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = await client.get(f"/api/v1/events?invite_id={fake_id}")

        assert response.status_code == 404
