# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for invite endpoints."""

import pytest
from httpx import AsyncClient

from control_plane.models.invite import InviteStatus


class TestCreateInvite:
    """Tests for POST /api/v1/invites."""

    async def test_create_invite_success(self, client: AsyncClient):
        """Test successful invite creation."""
        response = await client.post(
            "/api/v1/invites",
            json={
                "email": "pierre.dupont@engie.com",
                "company": "ENGIE",
                "source": "demo-26-jan",
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert data["email"] == "pierre.dupont@engie.com"
        assert data["company"] == "ENGIE"
        assert data["source"] == "demo-26-jan"
        assert data["status"] == "pending"
        assert "token" in data
        assert len(data["token"]) == 43  # secrets.token_urlsafe(32) produces 43 chars
        assert "invite_link" in data
        assert data["token"] in data["invite_link"]
        assert "id" in data
        assert "created_at" in data
        assert "expires_at" in data

    async def test_create_invite_minimal(self, client: AsyncClient):
        """Test invite creation with minimal required fields."""
        response = await client.post(
            "/api/v1/invites",
            json={
                "email": "test@example.com",
                "company": "Test Corp",
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert data["email"] == "test@example.com"
        assert data["company"] == "Test Corp"
        assert data["source"] is None
        assert data["status"] == "pending"

    async def test_create_invite_invalid_email(self, client: AsyncClient):
        """Test invite creation with invalid email."""
        response = await client.post(
            "/api/v1/invites",
            json={
                "email": "not-an-email",
                "company": "Test Corp",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_create_invite_missing_company(self, client: AsyncClient):
        """Test invite creation without required company field."""
        response = await client.post(
            "/api/v1/invites",
            json={
                "email": "test@example.com",
            },
        )

        assert response.status_code == 422

    async def test_create_invite_empty_company(self, client: AsyncClient):
        """Test invite creation with empty company name."""
        response = await client.post(
            "/api/v1/invites",
            json={
                "email": "test@example.com",
                "company": "",
            },
        )

        assert response.status_code == 422


class TestListInvites:
    """Tests for GET /api/v1/invites."""

    async def test_list_invites_empty(self, client: AsyncClient):
        """Test listing invites when none exist."""
        response = await client.get("/api/v1/invites")

        assert response.status_code == 200
        data = response.json()

        assert data["invites"] == []
        assert data["total"] == 0

    async def test_list_invites_with_data(self, client: AsyncClient):
        """Test listing invites after creating some."""
        # Create two invites
        await client.post(
            "/api/v1/invites",
            json={"email": "a@test.com", "company": "Company A"},
        )
        await client.post(
            "/api/v1/invites",
            json={"email": "b@test.com", "company": "Company B"},
        )

        response = await client.get("/api/v1/invites")

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert len(data["invites"]) == 2

    async def test_list_invites_pagination(self, client: AsyncClient):
        """Test pagination of invites."""
        # Create 5 invites
        for i in range(5):
            await client.post(
                "/api/v1/invites",
                json={"email": f"user{i}@test.com", "company": f"Company {i}"},
            )

        # Get first page
        response = await client.get("/api/v1/invites?skip=0&limit=2")
        data = response.json()

        assert data["total"] == 5
        assert len(data["invites"]) == 2

        # Get second page
        response = await client.get("/api/v1/invites?skip=2&limit=2")
        data = response.json()

        assert data["total"] == 5
        assert len(data["invites"]) == 2


class TestGetInvite:
    """Tests for GET /api/v1/invites/{invite_id}."""

    async def test_get_invite_success(self, client: AsyncClient):
        """Test getting an invite by ID."""
        # Create an invite
        create_response = await client.post(
            "/api/v1/invites",
            json={"email": "test@test.com", "company": "Test"},
        )
        invite_id = create_response.json()["id"]

        # Get the invite
        response = await client.get(f"/api/v1/invites/{invite_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["id"] == invite_id
        assert data["email"] == "test@test.com"

    async def test_get_invite_not_found(self, client: AsyncClient):
        """Test getting a non-existent invite."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/invites/{fake_id}")

        assert response.status_code == 404
        data = response.json()

        assert data["detail"]["code"] == "invite_not_found"


class TestTokenUniqueness:
    """Tests for token generation."""

    async def test_tokens_are_unique(self, client: AsyncClient):
        """Test that generated tokens are unique."""
        tokens = set()

        for i in range(10):
            response = await client.post(
                "/api/v1/invites",
                json={"email": f"user{i}@test.com", "company": "Test"},
            )
            token = response.json()["token"]
            tokens.add(token)

        assert len(tokens) == 10  # All tokens should be unique
