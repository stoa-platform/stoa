# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Pytest fixtures for Mock Backends tests.

CAB-1018: Mock APIs for Central Bank Demo
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.circuit_breaker import get_circuit_breaker
from src.services.idempotency import get_idempotency_store
from src.services.saga import get_saga_orchestrator
from src.services.semantic_cache import get_semantic_cache


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all service state between tests.

    This ensures tests are isolated and don't affect each other.
    """
    # Reset before test
    circuit_breaker = get_circuit_breaker()
    circuit_breaker.reset()

    saga = get_saga_orchestrator()
    saga.reset()

    idempotency = get_idempotency_store()
    idempotency.clear()

    cache = get_semantic_cache()
    cache.clear()

    yield

    # Reset after test (cleanup)
    circuit_breaker.reset()
    saga.reset()
    idempotency.clear()
    cache.clear()


# ==================== Fraud Detection Fixtures ====================

@pytest.fixture
def demo_transaction():
    """Standard demo transaction for fraud scoring tests."""
    return {
        "transaction_id": "TXN-DEMO-001",
        "amount": 5000.00,
        "currency": "EUR",
        "sender_iban": "FR7630006000011234567890189",
        "receiver_iban": "FR7630006000011234567890190",
    }


@pytest.fixture
def high_amount_transaction():
    """High amount cross-border transaction for review/deny tests."""
    return {
        "transaction_id": "TXN-HIGH-001",
        "amount": 75000.00,
        "currency": "EUR",
        "sender_iban": "FR7630006000011234567890189",
        "receiver_iban": "DE89370400440532013000",  # German IBAN = cross-border
    }


# ==================== Settlement Fixtures ====================

@pytest.fixture
def demo_settlement():
    """Standard demo settlement for saga tests."""
    return {
        "settlement_id": "SETL-DEMO-001",
        "amount": 50000.00,
        "currency": "EUR",
        "debtor_iban": "FR7630006000011234567890189",
        "creditor_iban": "DE89370400440532013000",
        "reference": "Invoice INV-2026-001",
    }


# ==================== Sanctions Screening Fixtures ====================

@pytest.fixture
def sanctioned_entity():
    """Known sanctioned entity for HIT tests (Ivan Petrov from OFAC)."""
    return {
        "entity_name": "Ivan Petrov",
        "entity_type": "PERSON",
        "country": "RU",
    }


@pytest.fixture
def clean_entity():
    """Clean entity for NO_HIT tests."""
    return {
        "entity_name": "Jean Dupont",
        "entity_type": "PERSON",
        "country": "FR",
    }


@pytest.fixture
def organization_entity():
    """Sanctioned organization for HIT tests."""
    return {
        "entity_name": "Omega Trading Corp",
        "entity_type": "ORGANIZATION",
        "country": "IR",
    }
