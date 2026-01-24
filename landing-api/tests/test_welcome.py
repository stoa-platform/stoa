"""Tests for welcome endpoint."""

import pytest
from httpx import AsyncClient


class TestWelcome:
    """Tests for GET /welcome/{token}."""

    async def test_welcome_valid_token(self, client: AsyncClient):
        """Test welcome with valid token redirects."""
        # Create an invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        token = invite_response.json()["token"]

        # Call welcome endpoint (don't follow redirects)
        response = await client.get(
            f"/welcome/{token}",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "Location" in response.headers
        assert token in response.headers["Location"]
        assert "X-Invite-Id" in response.headers

    async def test_welcome_invalid_token(self, client: AsyncClient):
        """Test welcome with invalid token returns 404."""
        response = await client.get(
            "/welcome/invalid-token-that-does-not-exist",
            follow_redirects=False,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["code"] == "invite_not_found"

    async def test_welcome_tracks_invite_opened_event(self, client: AsyncClient):
        """Test that welcome endpoint records invite_opened event."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        token = invite_response.json()["token"]

        # Call welcome
        await client.get(f"/welcome/{token}", follow_redirects=False)

        # Check events
        events_response = await client.get(f"/api/v1/events?invite_id={invite_id}")
        events = events_response.json()["events"]

        assert len(events) == 1
        assert events[0]["event_type"] == "invite_opened"

    async def test_welcome_marks_invite_as_opened(self, client: AsyncClient):
        """Test that welcome endpoint marks invite as opened."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        token = invite_response.json()["token"]

        # Verify initial status
        assert invite_response.json()["status"] == "pending"

        # Call welcome
        await client.get(f"/welcome/{token}", follow_redirects=False)

        # Check invite status
        invite = await client.get(f"/api/v1/invites/{invite_id}")
        assert invite.json()["status"] == "opened"
        assert invite.json()["opened_at"] is not None

    async def test_welcome_idempotent(self, client: AsyncClient):
        """Test that calling welcome multiple times is idempotent for status."""
        # Create invite
        invite_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = invite_response.json()["id"]
        token = invite_response.json()["token"]

        # Call welcome twice
        await client.get(f"/welcome/{token}", follow_redirects=False)
        await client.get(f"/welcome/{token}", follow_redirects=False)

        # Status should still be opened (not changed)
        invite = await client.get(f"/api/v1/invites/{invite_id}")
        assert invite.json()["status"] == "opened"

        # But events should be recorded both times (for analytics)
        events_response = await client.get(f"/api/v1/events?invite_id={invite_id}")
        events = events_response.json()["events"]
        assert len(events) == 2  # Two invite_opened events
