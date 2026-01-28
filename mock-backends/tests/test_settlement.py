"""Tests for Settlement API.

CAB-1018: Mock APIs for Central Bank Demo
"""

import pytest
from fastapi.testclient import TestClient


class TestSettlementCreation:
    """Tests for settlement creation."""

    def test_create_settlement_success(self, client: TestClient, demo_settlement):
        """Creating settlement with valid data should succeed."""
        response = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-idem-001"},
            json=demo_settlement,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["settlement_id"] == demo_settlement["settlement_id"]
        # Could be COMPLETED or ROLLED_BACK (5% random failure)
        assert data["status"] in ["COMPLETED", "ROLLED_BACK"]
        assert data["idempotency_hit"] is False
        assert len(data["steps"]) >= 4  # At least the 4 main steps

    def test_idempotency_same_key_returns_cached(self, client: TestClient, demo_settlement):
        """Same idempotency key should return cached response."""
        idempotency_key = "test-idem-same-001"

        # First request
        response1 = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": idempotency_key},
            json=demo_settlement,
        )
        assert response1.status_code == 201
        data1 = response1.json()

        # Second request with same key
        response2 = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": idempotency_key},
            json=demo_settlement,
        )
        assert response2.status_code == 201
        data2 = response2.json()

        # Should be idempotency hit
        assert data2["idempotency_hit"] is True
        assert data2["settlement_id"] == data1["settlement_id"]
        assert data2["status"] == data1["status"]

    def test_idempotency_different_key_creates_new(self, client: TestClient, demo_settlement):
        """Different idempotency key should create new settlement."""
        # First request
        response1 = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-idem-diff-001"},
            json=demo_settlement,
        )
        assert response1.status_code == 201
        data1 = response1.json()
        assert data1["idempotency_hit"] is False

        # Second request with different key (different settlement_id)
        demo_settlement["settlement_id"] = "SETL-TEST-002"
        response2 = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-idem-diff-002"},
            json=demo_settlement,
        )
        assert response2.status_code == 201
        data2 = response2.json()
        assert data2["idempotency_hit"] is False

    def test_idempotency_missing_header_error(self, client: TestClient, demo_settlement):
        """Missing Idempotency-Key header should return 422."""
        response = client.post(
            "/v1/settlements",
            json=demo_settlement,
        )

        # FastAPI returns 422 for missing required header
        assert response.status_code == 422

    def test_response_has_demo_headers(self, client: TestClient, demo_settlement):
        """Response should have demo headers."""
        response = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-headers-001"},
            json=demo_settlement,
        )

        assert response.status_code == 201
        assert response.headers.get("X-Demo-Mode") == "true"
        assert response.headers.get("X-Data-Classification") == "SYNTHETIC"


class TestSettlementRollback:
    """Tests for settlement rollback functionality."""

    def test_rollback_triggered_has_compensation_steps(self, client: TestClient, demo_settlement):
        """Forced rollback should have compensation steps."""
        # Trigger rollback for next settlement
        trigger_response = client.post("/demo/trigger/rollback")
        assert trigger_response.status_code == 200

        # Create settlement - should fail and rollback
        response = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-rollback-001"},
            json=demo_settlement,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "ROLLED_BACK"

        # Check for compensation steps
        step_names = [s["name"] for s in data["steps"]]
        assert "execute_transfer" in step_names

        # Check for compensated status
        compensated_steps = [s for s in data["steps"] if s["status"] == "COMPENSATED"]
        assert len(compensated_steps) >= 1

        # Check for compensation steps (reverse_transfer, release_funds)
        compensation_steps = [s for s in data["steps"] if s.get("compensation_of")]
        assert len(compensation_steps) >= 1


class TestSettlementStatus:
    """Tests for settlement status retrieval."""

    def test_get_status_returns_audit_trail(self, client: TestClient, demo_settlement):
        """Get status should return settlement with audit trail."""
        # Create settlement first
        create_response = client.post(
            "/v1/settlements",
            headers={"Idempotency-Key": "test-status-001"},
            json=demo_settlement,
        )
        assert create_response.status_code == 201

        # Get status
        status_response = client.get(
            f"/v1/settlements/{demo_settlement['settlement_id']}/status"
        )

        assert status_response.status_code == 200
        data = status_response.json()
        assert data["settlement_id"] == demo_settlement["settlement_id"]
        assert "audit_trail" in data
        assert len(data["audit_trail"]) > 0

        # Check audit trail structure
        first_entry = data["audit_trail"][0]
        assert "timestamp" in first_entry
        assert "action" in first_entry
        assert "status" in first_entry
        assert "actor" in first_entry

    def test_get_status_not_found(self, client: TestClient):
        """Non-existent settlement should return 404."""
        response = client.get("/v1/settlements/NONEXISTENT-001/status")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
