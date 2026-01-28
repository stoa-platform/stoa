# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Data generator for synthetic fraud detection data.

CAB-1018: Mock APIs for Central Bank Demo
Uses Faker with fixed seed for reproducible results.
"""

from faker import Faker

from src.config import settings
from src.schemas.fraud import RiskFactor

# Initialize Faker with fixed seed for reproducibility
fake = Faker()
Faker.seed(settings.faker_seed)

# High-risk country codes (ISO 3166-1 alpha-2)
HIGH_RISK_COUNTRIES = {"RU", "IR", "KP", "SY", "CU", "VE", "MM", "BY"}

# IBAN country code mapping (first 2 chars)
def extract_country_code(iban: str) -> str:
    """Extract country code from IBAN."""
    if len(iban) >= 2:
        return iban[:2].upper()
    return "XX"


def generate_fraud_score(
    amount: float,
    sender_iban: str,
    receiver_iban: str,
    transaction_id: str = "",
) -> tuple[int, list[RiskFactor]]:
    """Generate fraud score based on transaction characteristics.

    Scoring rules:
    - amount > 50,000 → +30 points
    - amount > 100,000 → +20 additional points
    - Cross-border (different countries) → +20 points
    - High-risk country involved → +25 points
    - Round amount (ends in 000) → +5 points
    - Random factor based on transaction_id → ±10 points

    Args:
        amount: Transaction amount
        sender_iban: Sender IBAN
        receiver_iban: Receiver IBAN
        transaction_id: Transaction ID for deterministic randomness

    Returns:
        Tuple of (score, risk_factors)
    """
    score = 0
    risk_factors: list[RiskFactor] = []

    sender_country = extract_country_code(sender_iban)
    receiver_country = extract_country_code(receiver_iban)

    # Amount-based scoring
    if amount > 100_000:
        score += 50
        risk_factors.append(RiskFactor.VERY_HIGH_AMOUNT)
    elif amount > 50_000:
        score += 30
        risk_factors.append(RiskFactor.HIGH_AMOUNT)

    # Cross-border check
    if sender_country != receiver_country:
        score += 20
        risk_factors.append(RiskFactor.CROSS_BORDER)

    # High-risk country check
    if sender_country in HIGH_RISK_COUNTRIES or receiver_country in HIGH_RISK_COUNTRIES:
        score += 25
        risk_factors.append(RiskFactor.HIGH_RISK_COUNTRY)

    # Round amount check
    if amount >= 1000 and amount % 1000 == 0:
        score += 5
        risk_factors.append(RiskFactor.ROUND_AMOUNT)

    # Deterministic random factor based on transaction_id
    if transaction_id:
        # Use hash of transaction_id for reproducible randomness
        hash_value = hash(transaction_id) % 21 - 10  # -10 to +10
        score += hash_value

    # Clamp score to 0-100
    score = max(0, min(100, score))

    return score, risk_factors


def generate_risk_factors_description(risk_factors: list[RiskFactor]) -> list[dict]:
    """Generate human-readable descriptions for risk factors.

    Args:
        risk_factors: List of risk factors

    Returns:
        List of factor descriptions
    """
    descriptions = {
        RiskFactor.HIGH_AMOUNT: {
            "code": "HIGH_AMOUNT",
            "description": "Transaction amount exceeds €50,000 threshold",
            "weight": 30,
        },
        RiskFactor.VERY_HIGH_AMOUNT: {
            "code": "VERY_HIGH_AMOUNT",
            "description": "Transaction amount exceeds €100,000 threshold",
            "weight": 50,
        },
        RiskFactor.CROSS_BORDER: {
            "code": "CROSS_BORDER",
            "description": "Cross-border transaction detected",
            "weight": 20,
        },
        RiskFactor.HIGH_RISK_COUNTRY: {
            "code": "HIGH_RISK_COUNTRY",
            "description": "Transaction involves high-risk jurisdiction",
            "weight": 25,
        },
        RiskFactor.NEW_RECEIVER: {
            "code": "NEW_RECEIVER",
            "description": "First transaction to this receiver",
            "weight": 15,
        },
        RiskFactor.UNUSUAL_TIME: {
            "code": "UNUSUAL_TIME",
            "description": "Transaction outside normal business hours",
            "weight": 10,
        },
        RiskFactor.VELOCITY_SPIKE: {
            "code": "VELOCITY_SPIKE",
            "description": "Unusual transaction frequency detected",
            "weight": 20,
        },
        RiskFactor.ROUND_AMOUNT: {
            "code": "ROUND_AMOUNT",
            "description": "Suspiciously round transaction amount",
            "weight": 5,
        },
    }

    return [descriptions.get(rf, {"code": rf.value, "description": "Unknown", "weight": 0})
            for rf in risk_factors]


def generate_fake_iban(country_code: str = "FR") -> str:
    """Generate a fake IBAN for testing.

    Args:
        country_code: ISO country code (default: FR)

    Returns:
        Fake IBAN string
    """
    return fake.iban()


def generate_fake_transaction_id() -> str:
    """Generate a fake transaction ID.

    Returns:
        Transaction ID string
    """
    return f"TXN-{fake.uuid4()[:8].upper()}"
