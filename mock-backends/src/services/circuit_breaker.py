"""Circuit Breaker simulation for Fraud Detection API.

CAB-1018: Mock APIs for Central Bank Demo
Simulates circuit breaker pattern with configurable latency spikes.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from src.config import settings
from src.logging_config import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Failing, reject requests
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


@dataclass
class CircuitBreakerState:
    """Mutable state for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_state_change: datetime = field(default_factory=datetime.utcnow)

    # Demo controls
    spike_active: bool = False
    spike_remaining_requests: int = 0
    forced_open: bool = False


class CircuitBreaker:
    """Circuit breaker implementation with demo controls.

    Demo features:
    - trigger_spike(): Activate 2s latency for N requests
    - force_open(): Force circuit to OPEN state
    - reset(): Reset to normal CLOSED state

    Normal operation:
    - Tracks failures and opens circuit after threshold
    - Attempts recovery after timeout
    """

    def __init__(self):
        self._state = CircuitBreakerState()
        self._failure_threshold = settings.circuit_breaker_failure_threshold
        self._recovery_timeout = settings.circuit_breaker_recovery_timeout
        self._normal_latency_ms = settings.circuit_breaker_normal_latency_ms
        self._spike_latency_ms = settings.circuit_breaker_spike_latency_ms

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        self._check_recovery()
        return self._state.state

    def _check_recovery(self) -> None:
        """Check if circuit should attempt recovery."""
        if self._state.state == CircuitState.OPEN and not self._state.forced_open:
            if self._state.last_failure_time:
                elapsed = datetime.utcnow() - self._state.last_failure_time
                if elapsed > timedelta(seconds=self._recovery_timeout):
                    self._state.state = CircuitState.HALF_OPEN
                    self._state.last_state_change = datetime.utcnow()
                    logger.info(
                        "Circuit breaker entering HALF_OPEN state",
                        elapsed_seconds=elapsed.total_seconds(),
                    )

    def should_allow(self) -> bool:
        """Check if request should be allowed through."""
        current_state = self.state

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.OPEN:
            return False
        elif current_state == CircuitState.HALF_OPEN:
            # Allow one request through for testing
            return True

        return True

    def record_success(self) -> None:
        """Record a successful request."""
        if self._state.state == CircuitState.HALF_OPEN:
            # Recovery successful
            self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.last_state_change = datetime.utcnow()
            logger.info("Circuit breaker recovered to CLOSED state")

    def record_failure(self) -> None:
        """Record a failed request."""
        self._state.failure_count += 1
        self._state.last_failure_time = datetime.utcnow()

        if self._state.state == CircuitState.HALF_OPEN:
            # Recovery failed, back to OPEN
            self._state.state = CircuitState.OPEN
            self._state.last_state_change = datetime.utcnow()
            logger.warning("Circuit breaker recovery failed, returning to OPEN")

        elif self._state.failure_count >= self._failure_threshold:
            self._state.state = CircuitState.OPEN
            self._state.last_state_change = datetime.utcnow()
            logger.warning(
                "Circuit breaker opened",
                failure_count=self._state.failure_count,
                threshold=self._failure_threshold,
            )

    # ========== Demo Controls ==========

    def trigger_spike(self, num_requests: int = 5) -> dict:
        """Activate latency spike for next N requests.

        Args:
            num_requests: Number of requests to affect

        Returns:
            Status dict
        """
        self._state.spike_active = True
        self._state.spike_remaining_requests = num_requests
        logger.info(
            "Demo: Latency spike activated",
            num_requests=num_requests,
            latency_ms=self._spike_latency_ms,
        )
        return {
            "action": "spike_activated",
            "requests_affected": num_requests,
            "latency_ms": self._spike_latency_ms,
        }

    def force_open(self) -> dict:
        """Force circuit breaker to OPEN state.

        Returns:
            Status dict
        """
        self._state.state = CircuitState.OPEN
        self._state.forced_open = True
        self._state.last_state_change = datetime.utcnow()
        logger.info("Demo: Circuit breaker forced OPEN")
        return {
            "action": "circuit_forced_open",
            "state": CircuitState.OPEN.value,
            "forced": True,
        }

    def reset(self) -> dict:
        """Reset circuit breaker to normal CLOSED state.

        Returns:
            Status dict
        """
        self._state.state = CircuitState.CLOSED
        self._state.forced_open = False
        self._state.spike_active = False
        self._state.spike_remaining_requests = 0
        self._state.failure_count = 0
        self._state.last_failure_time = None
        self._state.last_state_change = datetime.utcnow()
        logger.info("Demo: Circuit breaker reset to CLOSED")
        return {
            "action": "circuit_reset",
            "state": CircuitState.CLOSED.value,
        }

    def get_state(self) -> dict:
        """Get current circuit breaker state for /demo/state.

        Returns:
            State dict
        """
        return {
            "circuit_breaker": {
                "state": self.state.value,
                "failure_count": self._state.failure_count,
                "failure_threshold": self._failure_threshold,
                "forced_open": self._state.forced_open,
                "spike_active": self._state.spike_active,
                "spike_remaining_requests": self._state.spike_remaining_requests,
                "last_state_change": self._state.last_state_change.isoformat() + "Z",
                "recovery_timeout_seconds": self._recovery_timeout,
            }
        }

    async def apply_latency(self) -> int:
        """Apply simulated latency (normal or spike).

        Returns:
            Actual latency in milliseconds
        """
        if self._state.spike_active and self._state.spike_remaining_requests > 0:
            # Apply spike latency
            self._state.spike_remaining_requests -= 1
            latency_ms = self._spike_latency_ms

            if self._state.spike_remaining_requests == 0:
                self._state.spike_active = False
                logger.info("Demo: Latency spike exhausted")
        else:
            # Normal latency
            latency_ms = self._normal_latency_ms

        # Actually sleep
        await asyncio.sleep(latency_ms / 1000.0)
        return latency_ms


# Singleton instance
_circuit_breaker: Optional[CircuitBreaker] = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get the singleton circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker
