//! Token Budget Management — Per-tenant in-memory token counters (CAB-1337 Phase 2)
//!
//! Tracks token usage per tenant with configurable sliding-window limits.
//! Uses in-memory `AtomicU64` counters per tenant with a periodic background
//! sync to CP API (every 30s — scaffolded, CP API endpoint arrives in Phase 3).
//!
//! # Token estimation
//!
//! Token counting is **approximate**: `ceil(utf8_chars / 4)` — the standard
//! GPT-3 heuristic. Actual tokenizer not used to avoid adding heavy deps or
//! latency. Accuracy is sufficient for budget enforcement (±20% typical).
//!
//! # Window reset
//!
//! Uses a simple sliding window: when `now >= window_start + window_secs`,
//! the counter is atomically reset (first writer wins, concurrent resets are
//! harmless — the window_start CAS prevents double-reset).
//!
//! # Pipeline position
//!
//! ```text
//! Request → Auth → Rate Limit → Guardrails → [TOKEN BUDGET CHECK] → OPA → Cache → Tool Execute
//!                                                                                       ↓
//!                                                          [TOKEN BUDGET RECORD] ← Response
//! ```

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use parking_lot::RwLock;
use serde_json::Value;

// ============================================
// Token estimation
// ============================================

/// Estimate tokens in a UTF-8 string using the chars/4 heuristic.
///
/// Returns at least 1 for any non-empty input.
pub fn estimate_tokens(s: &str) -> u64 {
    let chars = s.chars().count() as u64;
    (chars / 4).max(if chars > 0 { 1 } else { 0 })
}

/// Recursively estimate tokens across all string values in a JSON value.
pub fn estimate_json(value: &Value) -> u64 {
    match value {
        Value::String(s) => estimate_tokens(s),
        Value::Array(arr) => arr.iter().map(estimate_json).sum(),
        Value::Object(map) => map.values().map(estimate_json).sum(),
        _ => 0,
    }
}

// ============================================
// Budget status
// ============================================

/// Result of a budget check for a tenant.
#[derive(Debug, PartialEq)]
pub enum BudgetStatus {
    /// Usage is below 80% of limit
    OK,
    /// Usage is at or above 80% but below 100% (pct = rounded usage %)
    Warning { pct: u8 },
    /// Usage has reached or exceeded 100% of limit
    Exceeded,
}

// ============================================
// Per-tenant budget state
// ============================================

struct TenantBudget {
    tokens_used: AtomicU64,
    /// Unix seconds when the current window started
    window_start: AtomicU64,
    limit: u64,
}

impl TenantBudget {
    fn new(limit: u64) -> Self {
        Self {
            tokens_used: AtomicU64::new(0),
            window_start: AtomicU64::new(unix_now()),
            limit,
        }
    }

    /// Record token usage, resetting the window if expired.
    fn record(&self, tokens: u64, window_secs: u64) {
        let now = unix_now();
        let ws = self.window_start.load(Ordering::Relaxed);
        if now >= ws + window_secs {
            // Claim the reset via CAS — first writer wins, others see updated window_start
            if self
                .window_start
                .compare_exchange(ws, now, Ordering::SeqCst, Ordering::Relaxed)
                .is_ok()
            {
                self.tokens_used.store(0, Ordering::SeqCst);
            }
        }
        self.tokens_used.fetch_add(tokens, Ordering::Relaxed);
    }

    /// Return current budget status (OK / Warning / Exceeded).
    fn status(&self) -> BudgetStatus {
        if self.limit == 0 {
            return BudgetStatus::OK;
        }
        let used = self.tokens_used.load(Ordering::Relaxed);
        if used >= self.limit {
            return BudgetStatus::Exceeded;
        }
        let pct = (used * 100 / self.limit) as u8;
        if pct >= 80 {
            BudgetStatus::Warning { pct }
        } else {
            BudgetStatus::OK
        }
    }
}

// ============================================
// TokenBudgetTracker
// ============================================

/// Per-tenant token budget tracker.
///
/// Holds one `TenantBudget` per tenant (created lazily on first use).
/// Thread-safe: outer `RwLock` only for insertions; per-tenant ops use atomics.
pub struct TokenBudgetTracker {
    tenants: RwLock<HashMap<String, Arc<TenantBudget>>>,
    default_limit: u64,
    window_secs: u64,
}

impl TokenBudgetTracker {
    /// Create a new tracker with a shared default limit and window.
    pub fn new(default_limit: u64, window_secs: u64) -> Self {
        Self {
            tenants: RwLock::new(HashMap::new()),
            default_limit,
            window_secs,
        }
    }

    /// Record token usage for a tenant.
    ///
    /// Creates the tenant's budget on first use. Thread-safe.
    pub fn record_usage(&self, tenant_id: &str, tokens: u64) {
        let budget = self.get_or_create(tenant_id);
        budget.record(tokens, self.window_secs);
    }

    /// Check budget status for a tenant (does NOT modify state).
    pub fn check_budget(&self, tenant_id: &str) -> BudgetStatus {
        let budget = self.get_or_create(tenant_id);
        budget.status()
    }

    /// Return usage percentage for a tenant (0.0–100.0+).
    pub fn usage_pct(&self, tenant_id: &str) -> f64 {
        let budget = self.get_or_create(tenant_id);
        if budget.limit == 0 {
            return 0.0;
        }
        let used = budget.tokens_used.load(Ordering::Relaxed) as f64;
        used / budget.limit as f64 * 100.0
    }

    /// Return remaining window seconds for a tenant.
    pub fn window_remaining_secs(&self, tenant_id: &str) -> u64 {
        let budget = self.get_or_create(tenant_id);
        let ws = budget.window_start.load(Ordering::Relaxed);
        let elapsed = unix_now().saturating_sub(ws);
        self.window_secs.saturating_sub(elapsed)
    }

    // Lazy-init per-tenant budget (read-lock path for existing tenants)
    fn get_or_create(&self, tenant_id: &str) -> Arc<TenantBudget> {
        // Fast path: read lock
        if let Some(b) = self.tenants.read().get(tenant_id) {
            return b.clone();
        }
        // Slow path: write lock + double-check
        let mut map = self.tenants.write();
        map.entry(tenant_id.to_string())
            .or_insert_with(|| Arc::new(TenantBudget::new(self.default_limit)))
            .clone()
    }

    /// Spawn background sync task.
    ///
    /// Currently logs a placeholder every 30s — the CP API endpoint
    /// for persisting budget state arrives in Phase 3 (CAB-1337-P3).
    pub fn spawn_sync_task(tracker: Arc<Self>) {
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(30));
            loop {
                interval.tick().await;
                let count = tracker.tenants.read().len();
                if count > 0 {
                    tracing::debug!(
                        tenants = count,
                        "Token budget sync tick (CP API sync not yet wired — Phase 3)"
                    );
                }
            }
        });
    }
}

fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

// ============================================
// Tests
// ============================================

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // --- Token estimator ---

    #[test]
    fn test_estimate_tokens_empty() {
        assert_eq!(estimate_tokens(""), 0);
    }

    #[test]
    fn test_estimate_tokens_short() {
        // "hi" = 2 chars → ceil(2/4) = 1 (clamped to 1)
        assert_eq!(estimate_tokens("hi"), 1);
    }

    #[test]
    fn test_estimate_tokens_typical() {
        // 100 chars → 25 tokens
        let s = "a".repeat(100);
        assert_eq!(estimate_tokens(&s), 25);
    }

    #[test]
    fn test_estimate_tokens_large() {
        let s = "x".repeat(4000);
        assert_eq!(estimate_tokens(&s), 1000);
    }

    #[test]
    fn test_estimate_json_string() {
        let v = json!("hello world"); // 11 chars → 2 tokens
        assert_eq!(estimate_json(&v), 2);
    }

    #[test]
    fn test_estimate_json_object() {
        let v = json!({"a": "hello", "b": "world"});
        // "hello" = 5 chars → 1 token, "world" = 5 chars → 1 token = 2 total
        assert_eq!(estimate_json(&v), 2);
    }

    #[test]
    fn test_estimate_json_array() {
        let v = json!(["aaaa", "bbbb", "cccc"]); // 3 × 4 chars → 3 tokens
        assert_eq!(estimate_json(&v), 3);
    }

    #[test]
    fn test_estimate_json_non_string_zero() {
        let v = json!({"count": 42, "active": true, "data": null});
        assert_eq!(estimate_json(&v), 0);
    }

    #[test]
    fn test_estimate_json_nested() {
        let v = json!({"outer": {"inner": "a".repeat(40)}});
        assert_eq!(estimate_json(&v), 10);
    }

    // --- BudgetStatus ---

    #[test]
    fn test_budget_status_ok() {
        let b = TenantBudget::new(1000);
        assert_eq!(b.status(), BudgetStatus::OK);
    }

    #[test]
    fn test_budget_status_warning_at_80pct() {
        let b = TenantBudget::new(1000);
        b.tokens_used.store(800, Ordering::Relaxed);
        assert_eq!(b.status(), BudgetStatus::Warning { pct: 80 });
    }

    #[test]
    fn test_budget_status_warning_at_90pct() {
        let b = TenantBudget::new(1000);
        b.tokens_used.store(900, Ordering::Relaxed);
        assert_eq!(b.status(), BudgetStatus::Warning { pct: 90 });
    }

    #[test]
    fn test_budget_status_exceeded_at_100pct() {
        let b = TenantBudget::new(1000);
        b.tokens_used.store(1000, Ordering::Relaxed);
        assert_eq!(b.status(), BudgetStatus::Exceeded);
    }

    #[test]
    fn test_budget_status_exceeded_over_limit() {
        let b = TenantBudget::new(1000);
        b.tokens_used.store(1500, Ordering::Relaxed);
        assert_eq!(b.status(), BudgetStatus::Exceeded);
    }

    #[test]
    fn test_budget_zero_limit_always_ok() {
        let b = TenantBudget::new(0);
        b.tokens_used.store(u64::MAX, Ordering::Relaxed);
        assert_eq!(b.status(), BudgetStatus::OK);
    }

    // --- TokenBudgetTracker ---

    #[test]
    fn test_tracker_record_and_check_ok() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("tenant-a", 100);
        assert_eq!(t.check_budget("tenant-a"), BudgetStatus::OK);
    }

    #[test]
    fn test_tracker_record_and_check_warning() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("tenant-b", 850);
        assert_eq!(
            t.check_budget("tenant-b"),
            BudgetStatus::Warning { pct: 85 }
        );
    }

    #[test]
    fn test_tracker_record_and_check_exceeded() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("tenant-c", 1200);
        assert_eq!(t.check_budget("tenant-c"), BudgetStatus::Exceeded);
    }

    #[test]
    fn test_tracker_tenant_isolation() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("tenant-x", 900);
        t.record_usage("tenant-y", 10);
        assert_eq!(
            t.check_budget("tenant-x"),
            BudgetStatus::Warning { pct: 90 }
        );
        assert_eq!(t.check_budget("tenant-y"), BudgetStatus::OK);
    }

    #[test]
    fn test_tracker_unknown_tenant_is_ok() {
        let t = TokenBudgetTracker::new(1000, 3600);
        assert_eq!(t.check_budget("new-tenant"), BudgetStatus::OK);
    }

    #[test]
    fn test_tracker_usage_pct() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("t", 500);
        let pct = t.usage_pct("t");
        assert!((pct - 50.0).abs() < 0.01, "expected ~50%, got {pct}");
    }

    #[test]
    fn test_tracker_window_remaining_secs() {
        let t = TokenBudgetTracker::new(1000, 3600);
        t.record_usage("t", 10);
        let remaining = t.window_remaining_secs("t");
        // Just started, should be close to 3600
        assert!(
            remaining > 3590,
            "expected > 3590s remaining, got {remaining}"
        );
    }

    #[test]
    fn test_tracker_window_reset() {
        // Set window_start to far in the past so the next record triggers a reset
        let t = TokenBudgetTracker::new(1000, 60);
        t.record_usage("tenant-reset", 500); // initial record
                                             // Manually expire the window
        let budget = t.get_or_create("tenant-reset");
        budget.window_start.store(0, Ordering::SeqCst); // epoch 0 → expired
                                                        // Next record should reset counter
        t.record_usage("tenant-reset", 10);
        assert_eq!(t.check_budget("tenant-reset"), BudgetStatus::OK);
    }

    #[test]
    fn test_new_creates_with_correct_defaults() {
        let t = TokenBudgetTracker::new(500_000, 86400);
        assert_eq!(t.default_limit, 500_000);
        assert_eq!(t.window_secs, 86400);
    }
}
