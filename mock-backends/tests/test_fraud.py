# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Fraud Detection API.

CAB-1018: Mock APIs for Central Bank Demo
"""

import pytest
from fastapi.testclient import TestClient

from src.services.circuit_breaker import get_circuit_breaker


class TestFraudScoring:
    """Tests for transaction fraud scoring."""

    def test_score_low_amount_allow(self, client: TestClient):
        """Low amount domestic transaction should be ALLOW."""
        response = client.post(
            "/v1/transactions/score",
            json={
                "transaction_id": "TXN-LOW-001",
                "amount": 1000.00,
                "currency": "EUR",
                "sender_iban": "FR7630006000011234567890189",
                "receiver_iban": "FR7630006000011234567890190",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "ALLOW"
        assert data["score"] < 30
        assert data["circuit_state"] == "CLOSED"
        assert data["fallback_used"] is False

    def test_score_high_amount_review_or_deny(self, client: TestClient, high_amount_transaction):
        """High amount cross-border transaction should be REVIEW or DENY."""
        response = client.post(
            "/v1/transactions/score",
            json=high_amount_transaction,
        )

        assert response.status_code == 200
        data = response.json()
        # High amount (75000) + cross-border = at least 50 points
        assert data["decision"] in ["REVIEW", "DENY"]
        assert data["score"] >= 30

    def test_score_cross_border_has_risk_factor(self, client: TestClient):
        """Cross-border transaction should have CROSS_BORDER risk factor."""
        response = client.post(
            "/v1/transactions/score",
            json={
                "transaction_id": "TXN-CROSS-001",
                "amount": 5000.00,
                "currency": "EUR",
                "sender_iban": "FR7630006000011234567890189",
                "receiver_iban": "DE89370400440532013000",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "CROSS_BORDER" in data["risk_factors"]

    def test_score_very_high_amount_risk_factor(self, client: TestClient):
        """Very high amount (>100k) should have VERY_HIGH_AMOUNT risk factor."""
        response = client.post(
            "/v1/transactions/score",
            json={
                "transaction_id": "TXN-VERYHIGH-001",
                "amount": 150000.00,
                "currency": "EUR",
                "sender_iban": "FR7630006000011234567890189",
                "receiver_iban": "FR7630006000011234567890190",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "VERY_HIGH_AMOUNT" in data["risk_factors"]

    def test_response_headers(self, client: TestClient, demo_transaction):
        """Response should have demo headers."""
        response = client.post(
            "/v1/transactions/score",
            json=demo_transaction,
        )

        assert response.status_code == 200
        assert response.headers.get("X-Demo-Mode") == "true"
        assert response.headers.get("X-Data-Classification") == "SYNTHETIC"
        assert "X-Trace-Id" in response.headers


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_circuit_breaker_spike_increases_latency(self, client: TestClient, demo_transaction):
        """Triggering spike should increase latency significantly."""
        # Trigger spike for 1 request
        spike_response = client.post("/demo/trigger/spike?num_requests=1")
        assert spike_response.status_code == 200

        # Make fraud request - should have high latency
        response = client.post(
            "/v1/transactions/score",
            json=demo_transaction,
        )

        assert response.status_code == 200
        data = response.json()
        # Spike latency is 2000ms, so processing time should be > 1500ms
        assert data["processing_time_ms"] > 1500

    def test_circuit_breaker_open_returns_503(self, client: TestClient, demo_transaction):
        """Circuit breaker OPEN should return 503 with fallback."""
        # Force circuit open
        open_response = client.post("/demo/trigger/circuit-open")
        assert open_response.status_code == 200

        # Make fraud request - should get 503
        response = client.post(
            "/v1/transactions/score",
            json=demo_transaction,
        )

        assert response.status_code == 503
        data = response.json()
        assert data["detail"]["fallback_used"] is True
        assert data["detail"]["circuit_state"] == "OPEN"
        assert data["detail"]["decision"] == "ALLOW"

    def test_circuit_breaker_reset(self, client: TestClient, demo_transaction):
        """Reset should restore normal operation."""
        # Force circuit open
        client.post("/demo/trigger/circuit-open")

        # Reset
        reset_response = client.post("/demo/trigger/reset")
        assert reset_response.status_code == 200

        # Should work normally now
        response = client.post(
            "/v1/transactions/score",
            json=demo_transaction,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["circuit_state"] == "CLOSED"


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_check(self, client: TestClient):
        """Health endpoint should return healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "mock-backends"
        assert data["demo_mode"] is True

    def test_readiness_probe(self, client: TestClient):
        """Readiness probe should return ready status."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True

    def test_metrics_endpoint(self, client: TestClient):
        """Metrics endpoint should return Prometheus format."""
        response = client.get("/metrics")

        assert response.status_code == 200
        assert "stoa_mock" in response.text
