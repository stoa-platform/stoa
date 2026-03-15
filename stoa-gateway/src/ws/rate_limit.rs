//! Per-connection WebSocket message rate limiter (CAB-1758).
//!
//! Token bucket algorithm: each connection gets `capacity` tokens,
//! refilled at `refill_rate` tokens/second. Each message costs 1 token.

use std::time::Instant;

/// Token bucket rate limiter for a single WebSocket connection.
pub struct WsRateLimiter {
    capacity: f64,
    tokens: f64,
    refill_rate: f64,
    last_refill: Instant,
}

impl WsRateLimiter {
    /// Create a new rate limiter.
    ///
    /// - `messages_per_second`: sustained message rate allowed
    /// - `burst`: max burst size (tokens available at once)
    pub fn new(messages_per_second: f64, burst: usize) -> Self {
        let capacity = burst as f64;
        Self {
            capacity,
            tokens: capacity,
            refill_rate: messages_per_second,
            last_refill: Instant::now(),
        }
    }

    /// Try to consume one token. Returns true if allowed, false if rate-limited.
    pub fn try_acquire(&mut self) -> bool {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.capacity);
        self.last_refill = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_allows_within_burst() {
        let mut rl = WsRateLimiter::new(10.0, 5);
        for _ in 0..5 {
            assert!(rl.try_acquire());
        }
        // Burst exhausted
        assert!(!rl.try_acquire());
    }

    #[test]
    fn test_refills_over_time() {
        let mut rl = WsRateLimiter::new(100.0, 10);
        // Exhaust burst
        for _ in 0..10 {
            assert!(rl.try_acquire());
        }
        assert!(!rl.try_acquire());

        // Simulate time passing (manually set last_refill back)
        rl.last_refill = Instant::now() - std::time::Duration::from_millis(100);
        // 100ms * 100/s = 10 tokens refilled
        assert!(rl.try_acquire());
    }

    #[test]
    fn test_capacity_capped() {
        let mut rl = WsRateLimiter::new(1000.0, 5);
        // Even with high refill rate, tokens capped at burst capacity
        rl.last_refill = Instant::now() - std::time::Duration::from_secs(10);
        rl.refill();
        // Should be capped at 5
        for _ in 0..5 {
            assert!(rl.try_acquire());
        }
        assert!(!rl.try_acquire());
    }
}
