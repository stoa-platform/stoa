"""Business logic services for Mock Backends.

Contains:
- circuit_breaker.py: Latency spike simulation
- data_generator.py: Faker-based synthetic data
- idempotency.py: In-memory idempotency store
- saga.py: Saga orchestrator for settlement
- semantic_cache.py: Simple normalized key cache
- sanctions_lists.py: Mock sanctions database
"""

from src.services.circuit_breaker import CircuitBreaker, get_circuit_breaker, CircuitState
from src.services.data_generator import generate_fraud_score, generate_risk_factors_description
from src.services.idempotency import IdempotencyStore, get_idempotency_store
from src.services.saga import SagaOrchestrator, get_saga_orchestrator
from src.services.semantic_cache import SemanticCache, get_semantic_cache, normalize
from src.services.sanctions_lists import SanctionsDatabase, get_sanctions_database

__all__ = [
    # Circuit breaker
    "CircuitBreaker",
    "get_circuit_breaker",
    "CircuitState",
    # Data generator
    "generate_fraud_score",
    "generate_risk_factors_description",
    # Idempotency
    "IdempotencyStore",
    "get_idempotency_store",
    # Saga
    "SagaOrchestrator",
    "get_saga_orchestrator",
    # Semantic cache
    "SemanticCache",
    "get_semantic_cache",
    "normalize",
    # Sanctions
    "SanctionsDatabase",
    "get_sanctions_database",
]
