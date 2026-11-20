//! Unified atomic admission controller for the autonomous PoC:
//! - Bounded per-`chain_id` revocation table (fail-closed when saturated, entries
//!   retained until the latest token expiration of the chain) with an expiration
//!   priority queue and fixed-size SHA-256 keys.
//! - Atomic all-or-nothing two-level budget debit (chain budget + stable caller budget).
//! - Revoking one chain blocks tokens and budget for that chain without resetting
//!   the shared budget of a caller participating in other active chains.
//! - State is per-process in memory: it does not persist across restarts and is
//!   not replicated across instances.

use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap};
use std::sync::Arc;

use parking_lot::Mutex;
use sha2::{Digest, Sha256};
use thiserror::Error;

/// Default maximum capacity of the bounded `chain_id` revocation table.
pub const DEFAULT_MAX_REVOKED_CHAINS: usize = 10_000;

/// Maximum permitted length in bytes for `chain_id` and `caller_id`.
pub const MAX_ADMISSION_ID_LEN: usize = 128;

/// Default per-chain call budget when not overridden by configuration.
pub const DEFAULT_CHAIN_BUDGET: u64 = 50;

/// Default per-caller call budget when not overridden by configuration.
pub const DEFAULT_CALLER_BUDGET: u64 = 100;

/// Minimum retention window (seconds) when revoking a chain whose expiry was not recorded.
const FALLBACK_REVOCATION_RETENTION_SECS: i64 = 900;

fn hash_id(raw: &str) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    hasher.finalize().into()
}

/// Configuration for [`PocAdmissionController`].
#[derive(Debug, Clone)]
pub struct PocAdmissionConfig {
    pub max_revoked_chains: usize,
    pub default_chain_budget: u64,
    pub default_caller_budget: u64,
}

impl Default for PocAdmissionConfig {
    fn default() -> Self {
        Self {
            max_revoked_chains: DEFAULT_MAX_REVOKED_CHAINS,
            default_chain_budget: DEFAULT_CHAIN_BUDGET,
            default_caller_budget: DEFAULT_CALLER_BUDGET,
        }
    }
}

/// Errors produced by atomic admission or revocation.
#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum AdmissionError {
    #[error("revocation table is saturated; failing closed")]
    RevocationTableFull,

    #[error("delegation chain has been revoked")]
    ChainRevoked,

    #[error("chain budget exceeded")]
    ChainBudgetExceeded,

    #[error("caller budget exceeded")]
    CallerBudgetExceeded,

    #[error("invalid admission parameters: {0}")]
    InvalidInput(&'static str),
}

/// Inputs for admitting and debiting a single tool call.
#[derive(Debug, Clone)]
pub struct AdmitCallRequest<'a> {
    pub chain_id: &'a str,
    pub caller_id: &'a str,
    pub cost: u64,
    pub chain_limit: Option<u64>,
    pub caller_limit: Option<u64>,
    pub now_epoch: i64,
}

/// Result returned when a call is atomically admitted and debited.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AdmissionReceipt {
    pub chain_used: u64,
    pub chain_remaining: u64,
    pub caller_used: u64,
    pub caller_remaining: u64,
}

/// Result returned when a `chain_id` is atomically revoked.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RevocationReceipt {
    pub chain_id: String,
    pub retain_until_epoch: i64,
}

#[derive(Debug, Default)]
struct AdmissionState {
    /// `SHA-256(chain_id) -> retain_until_epoch` (kept until latest expiry in the chain).
    revoked_chains: HashMap<[u8; 32], i64>,
    /// Min-heap expiration queue `(retain_until_epoch, SHA-256(chain_id))` to avoid O(n) scans.
    revocation_expiry_queue: BinaryHeap<Reverse<(i64, [u8; 32])>>,
    /// `SHA-256(chain_id) -> max_exp` observed across issued tokens in this chain.
    chain_max_exp: HashMap<[u8; 32], i64>,
    /// `SHA-256(chain_id) -> debited units`.
    chain_used: HashMap<[u8; 32], u64>,
    /// `SHA-256(stable_caller_id) -> debited units` (persists across chains for the same caller).
    caller_used: HashMap<[u8; 32], u64>,
}

impl AdmissionState {
    fn prune_expired_revocations(&mut self, now_epoch: i64) {
        while let Some(&Reverse((retain_until, chain_hash))) = self.revocation_expiry_queue.peek() {
            if retain_until > now_epoch {
                break;
            }
            self.revocation_expiry_queue.pop();
            if self.revoked_chains.get(&chain_hash).copied() == Some(retain_until) {
                self.revoked_chains.remove(&chain_hash);
            }
        }
    }

    fn is_revoked(&self, chain_hash: &[u8; 32], now_epoch: i64) -> bool {
        self.revoked_chains
            .get(chain_hash)
            .is_some_and(|&retain_until| retain_until > now_epoch)
    }
}

/// Shared, thread-safe per-process in-memory admission controller (revocation + 2-level budgets).
#[derive(Debug, Clone)]
pub struct PocAdmissionController {
    config: PocAdmissionConfig,
    state: Arc<Mutex<AdmissionState>>,
}

impl PocAdmissionController {
    pub fn new(config: PocAdmissionConfig) -> Self {
        Self {
            config,
            state: Arc::new(Mutex::new(AdmissionState::default())),
        }
    }

    /// Record the latest token expiration for `chain_id` so any subsequent revocation
    /// retains the entry until at least the last token in the chain expires.
    pub fn record_token_expiry(&self, chain_id: &str, exp: i64) {
        let trimmed = chain_id.trim();
        if trimmed.is_empty() || trimmed.len() > MAX_ADMISSION_ID_LEN {
            return;
        }
        let chain_hash = hash_id(trimmed);
        let mut st = self.state.lock();
        let entry = st.chain_max_exp.entry(chain_hash).or_insert(exp);
        if exp > *entry {
            *entry = exp;
        }
    }

    /// Verify that `chain_id` is active and the revocation table is not saturated
    /// (used prior to delegating a child token).
    pub fn check_chain_active(&self, chain_id: &str, now_epoch: i64) -> Result<(), AdmissionError> {
        let trimmed = chain_id.trim();
        if trimmed.is_empty() {
            return Err(AdmissionError::InvalidInput("empty chain_id"));
        }
        if trimmed.len() > MAX_ADMISSION_ID_LEN {
            return Err(AdmissionError::InvalidInput("chain_id exceeds max length"));
        }
        let chain_hash = hash_id(trimmed);
        let mut st = self.state.lock();
        st.prune_expired_revocations(now_epoch);
        if st.revoked_chains.len() >= self.config.max_revoked_chains {
            return Err(AdmissionError::RevocationTableFull);
        }
        if st.is_revoked(&chain_hash, now_epoch) {
            return Err(AdmissionError::ChainRevoked);
        }
        Ok(())
    }

    /// Atomically revoke `chain_id` across both tokens and chain budget.
    ///
    /// - Fails closed with [`AdmissionError::RevocationTableFull`] if the table is at
    ///   capacity after evicting expired entries from the expiration queue.
    /// - Retains the entry until at least the chain's latest known token `exp`.
    /// - Does NOT reset the shared budget of any caller participating in other chains.
    pub fn revoke_chain(
        &self,
        chain_id: &str,
        explicit_retain_until: Option<i64>,
        now_epoch: i64,
    ) -> Result<RevocationReceipt, AdmissionError> {
        let trimmed = chain_id.trim();
        if trimmed.is_empty() {
            return Err(AdmissionError::InvalidInput("empty chain_id"));
        }
        if trimmed.len() > MAX_ADMISSION_ID_LEN {
            return Err(AdmissionError::InvalidInput("chain_id exceeds max length"));
        }
        let chain_hash = hash_id(trimmed);
        let mut st = self.state.lock();
        st.prune_expired_revocations(now_epoch);
        if !st.revoked_chains.contains_key(&chain_hash)
            && st.revoked_chains.len() >= self.config.max_revoked_chains
        {
            return Err(AdmissionError::RevocationTableFull);
        }

        let recorded_exp = st.chain_max_exp.get(&chain_hash).copied().unwrap_or(0);
        let explicit_exp = explicit_retain_until.unwrap_or(0);
        let fallback_exp = now_epoch.saturating_add(FALLBACK_REVOCATION_RETENTION_SECS);
        let existing_exp = st.revoked_chains.get(&chain_hash).copied().unwrap_or(0);
        let retain_until = recorded_exp
            .max(explicit_exp)
            .max(fallback_exp)
            .max(existing_exp);

        if existing_exp != retain_until {
            st.revoked_chains.insert(chain_hash, retain_until);
            st.revocation_expiry_queue
                .push(Reverse((retain_until, chain_hash)));
        }
        // Clear chain budget state; caller budget is deliberately preserved across chains.
        st.chain_used.remove(&chain_hash);

        Ok(RevocationReceipt {
            chain_id: trimmed.to_string(),
            retain_until_epoch: retain_until,
        })
    }

    /// Atomically verify revocation + table capacity and debit BOTH chain and caller
    /// budgets all-or-nothing under a single critical section.
    pub fn admit_call(
        &self,
        req: &AdmitCallRequest<'_>,
    ) -> Result<AdmissionReceipt, AdmissionError> {
        let chain_id = req.chain_id.trim();
        let caller_id = req.caller_id.trim();
        if chain_id.is_empty() || caller_id.is_empty() {
            return Err(AdmissionError::InvalidInput("empty chain_id or caller_id"));
        }
        if chain_id.len() > MAX_ADMISSION_ID_LEN || caller_id.len() > MAX_ADMISSION_ID_LEN {
            return Err(AdmissionError::InvalidInput(
                "chain_id or caller_id exceeds max length",
            ));
        }
        if req.cost == 0 {
            return Err(AdmissionError::InvalidInput("cost must be >= 1"));
        }

        let chain_limit = req.chain_limit.unwrap_or(self.config.default_chain_budget);
        let caller_limit = req
            .caller_limit
            .unwrap_or(self.config.default_caller_budget);
        let chain_hash = hash_id(chain_id);
        let caller_hash = hash_id(caller_id);

        let mut st = self.state.lock();
        st.prune_expired_revocations(req.now_epoch);
        if st.revoked_chains.len() >= self.config.max_revoked_chains {
            return Err(AdmissionError::RevocationTableFull);
        }

        if st.is_revoked(&chain_hash, req.now_epoch) {
            return Err(AdmissionError::ChainRevoked);
        }

        let curr_chain = st.chain_used.get(&chain_hash).copied().unwrap_or(0);
        let curr_caller = st.caller_used.get(&caller_hash).copied().unwrap_or(0);

        let next_chain = curr_chain
            .checked_add(req.cost)
            .filter(|&v| v <= chain_limit)
            .ok_or(AdmissionError::ChainBudgetExceeded)?;
        let next_caller = curr_caller
            .checked_add(req.cost)
            .filter(|&v| v <= caller_limit)
            .ok_or(AdmissionError::CallerBudgetExceeded)?;

        // Commit both counters atomically only after both limits succeed.
        st.chain_used.insert(chain_hash, next_chain);
        st.caller_used.insert(caller_hash, next_caller);

        Ok(AdmissionReceipt {
            chain_used: next_chain,
            chain_remaining: chain_limit - next_chain,
            caller_used: next_caller,
            caller_remaining: caller_limit - next_caller,
        })
    }

    /// Snapshot current debited units for a chain.
    pub fn chain_used(&self, chain_id: &str) -> u64 {
        let chain_hash = hash_id(chain_id.trim());
        self.state
            .lock()
            .chain_used
            .get(&chain_hash)
            .copied()
            .unwrap_or(0)
    }

    /// Snapshot current debited units for a stable caller.
    pub fn caller_used(&self, caller_id: &str) -> u64 {
        let caller_hash = hash_id(caller_id.trim());
        self.state
            .lock()
            .caller_used
            .get(&caller_hash)
            .copied()
            .unwrap_or(0)
    }

    /// Number of currently stored revocation entries.
    pub fn revoked_count(&self) -> usize {
        self.state.lock().revoked_chains.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Barrier;

    #[test]
    fn concurrency_same_chain_no_double_debit() {
        let ctrl = Arc::new(PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 100,
            default_chain_budget: 10,
            default_caller_budget: 100,
        }));
        let workers = 64;
        let barrier = Arc::new(Barrier::new(workers));
        let admitted = Arc::new(AtomicUsize::new(0));
        let denied = Arc::new(AtomicUsize::new(0));

        let mut handles = Vec::with_capacity(workers);
        for _ in 0..workers {
            let c = Arc::clone(&ctrl);
            let b = Arc::clone(&barrier);
            let ok = Arc::clone(&admitted);
            let no = Arc::clone(&denied);
            handles.push(std::thread::spawn(move || {
                b.wait();
                match c.admit_call(&AdmitCallRequest {
                    chain_id: "chain-1",
                    caller_id: "acme:agent-parent",
                    cost: 1,
                    chain_limit: None,
                    caller_limit: None,
                    now_epoch: 1_700_000_000,
                }) {
                    Ok(_) => {
                        ok.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(AdmissionError::ChainBudgetExceeded) => {
                        no.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(other) => panic!("unexpected error: {other}"),
                }
            }));
        }
        for h in handles {
            h.join().unwrap();
        }

        assert_eq!(admitted.load(Ordering::SeqCst), 10);
        assert_eq!(denied.load(Ordering::SeqCst), 54);
        assert_eq!(ctrl.chain_used("chain-1"), 10);
        assert_eq!(ctrl.caller_used("acme:agent-parent"), 10);
    }

    #[test]
    fn concurrency_shared_caller_across_8_chains_all_or_nothing() {
        let ctrl = Arc::new(PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 100,
            default_chain_budget: 20,
            default_caller_budget: 15,
        }));
        let workers = 64;
        let barrier = Arc::new(Barrier::new(workers));
        let admitted = Arc::new(AtomicUsize::new(0));
        let denied = Arc::new(AtomicUsize::new(0));

        let mut handles = Vec::with_capacity(workers);
        for i in 0..workers {
            let c = Arc::clone(&ctrl);
            let b = Arc::clone(&barrier);
            let ok = Arc::clone(&admitted);
            let no = Arc::clone(&denied);
            let chain_id = format!("chain-{}", i % 8);
            handles.push(std::thread::spawn(move || {
                b.wait();
                match c.admit_call(&AdmitCallRequest {
                    chain_id: &chain_id,
                    caller_id: "acme:shared-caller",
                    cost: 1,
                    chain_limit: None,
                    caller_limit: None,
                    now_epoch: 1_700_000_000,
                }) {
                    Ok(_) => {
                        ok.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(AdmissionError::CallerBudgetExceeded) => {
                        no.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(other) => panic!("unexpected error: {other}"),
                }
            }));
        }
        for h in handles {
            h.join().unwrap();
        }

        assert_eq!(admitted.load(Ordering::SeqCst), 15);
        assert_eq!(denied.load(Ordering::SeqCst), 49);
        assert_eq!(ctrl.caller_used("acme:shared-caller"), 15);
        // All-or-nothing check: sum of per-chain debits MUST equal exact admitted count.
        let sum_chains: u64 = (0..8).map(|i| ctrl.chain_used(&format!("chain-{i}"))).sum();
        assert_eq!(sum_chains, 15);
    }

    #[test]
    fn concurrency_revocation_vs_admission_race_and_shared_caller_preservation() {
        let ctrl = Arc::new(PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 100,
            default_chain_budget: 100,
            default_caller_budget: 100,
        }));
        let now = 1_700_000_000;
        ctrl.record_token_expiry("chain-A", now + 600);

        let workers = 32;
        let barrier = Arc::new(Barrier::new(workers + 1));
        let admitted = Arc::new(AtomicUsize::new(0));
        let revoked_err = Arc::new(AtomicUsize::new(0));

        let mut handles = Vec::with_capacity(workers + 1);
        for _ in 0..workers {
            let c = Arc::clone(&ctrl);
            let b = Arc::clone(&barrier);
            let ok = Arc::clone(&admitted);
            let rev = Arc::clone(&revoked_err);
            handles.push(std::thread::spawn(move || {
                b.wait();
                match c.admit_call(&AdmitCallRequest {
                    chain_id: "chain-A",
                    caller_id: "acme:shared-caller",
                    cost: 1,
                    chain_limit: None,
                    caller_limit: None,
                    now_epoch: now,
                }) {
                    Ok(_) => {
                        ok.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(AdmissionError::ChainRevoked) => {
                        rev.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(other) => panic!("unexpected error: {other}"),
                }
            }));
        }
        {
            let c = Arc::clone(&ctrl);
            let b = Arc::clone(&barrier);
            handles.push(std::thread::spawn(move || {
                b.wait();
                c.revoke_chain("chain-A", None, now)
                    .expect("revocation succeeds");
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        let admitted_count = admitted.load(Ordering::SeqCst);
        let denied_count = revoked_err.load(Ordering::SeqCst);
        assert_eq!(admitted_count + denied_count, workers);
        // Caller budget reflects exact calls admitted before revocation — NOT reset!
        assert_eq!(
            ctrl.caller_used("acme:shared-caller"),
            admitted_count as u64
        );

        // Post-revocation calls on chain-A ALWAYS fail closed.
        assert_eq!(
            ctrl.admit_call(&AdmitCallRequest {
                chain_id: "chain-A",
                caller_id: "acme:shared-caller",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                now_epoch: now + 1,
            })
            .unwrap_err(),
            AdmissionError::ChainRevoked
        );
        assert_eq!(
            ctrl.check_chain_active("chain-A", now + 1).unwrap_err(),
            AdmissionError::ChainRevoked
        );

        // Another active chain for the same caller continues and increments from preserved count.
        let receipt = ctrl
            .admit_call(&AdmitCallRequest {
                chain_id: "chain-B",
                caller_id: "acme:shared-caller",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                now_epoch: now + 1,
            })
            .expect("chain-B still active");
        assert_eq!(receipt.caller_used, admitted_count as u64 + 1);
    }

    #[test]
    fn bounded_revocation_table_fails_closed_when_saturated_and_recovers_after_expiry() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 3,
            default_chain_budget: 10,
            default_caller_budget: 10,
        });
        let now = 1_700_000_000;
        for i in 0..3 {
            let cid = format!("revoked-{i}");
            ctrl.revoke_chain(&cid, Some(now + 100), now)
                .expect("fills up to cap");
        }
        assert_eq!(ctrl.revoked_count(), 3);

        // 4th revocation fails closed.
        assert_eq!(
            ctrl.revoke_chain("revoked-3", Some(now + 100), now)
                .unwrap_err(),
            AdmissionError::RevocationTableFull
        );

        // Non-revoked active chain ALSO fails closed while table is saturated!
        assert_eq!(
            ctrl.admit_call(&AdmitCallRequest {
                chain_id: "active-chain",
                caller_id: "acme:agent",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                now_epoch: now + 10,
            })
            .unwrap_err(),
            AdmissionError::RevocationTableFull
        );

        // Once retention expires (> now + 900 fallback), pruning frees the table.
        let after_expiry = now + FALLBACK_REVOCATION_RETENTION_SECS + 1;
        assert!(ctrl
            .admit_call(&AdmitCallRequest {
                chain_id: "active-chain",
                caller_id: "acme:agent",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                now_epoch: after_expiry,
            })
            .is_ok());
        assert_eq!(ctrl.revoked_count(), 0);
    }

    #[test]
    fn revocation_table_enforces_length_bound_and_heap_expiry_with_extended_retention() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 4,
            default_chain_budget: 10,
            default_caller_budget: 10,
        });
        let now = 1_700_000_000;

        // Overlong chain_id (> 128 bytes) rejected without mutating table.
        let long_id = "c".repeat(MAX_ADMISSION_ID_LEN + 1);
        assert_eq!(
            ctrl.revoke_chain(&long_id, None, now).unwrap_err(),
            AdmissionError::InvalidInput("chain_id exceeds max length")
        );
        assert_eq!(ctrl.revoked_count(), 0);

        // Revoke chain-short with fallback 900s, then re-revoke with extended 1800s retention.
        ctrl.revoke_chain("chain-ext", Some(now + 900), now)
            .unwrap();
        ctrl.revoke_chain("chain-ext", Some(now + 1_800), now)
            .unwrap();
        ctrl.revoke_chain("chain-short", Some(now + 900), now)
            .unwrap();
        assert_eq!(ctrl.revoked_count(), 2);

        // At now + 901: chain-short is evicted via heap, while chain-ext MUST remain revoked!
        assert!(ctrl.check_chain_active("chain-short", now + 901).is_ok());
        assert_eq!(
            ctrl.check_chain_active("chain-ext", now + 901).unwrap_err(),
            AdmissionError::ChainRevoked
        );
        assert_eq!(ctrl.revoked_count(), 1);

        // At now + 1801: chain-ext expires cleanly.
        assert!(ctrl.check_chain_active("chain-ext", now + 1_801).is_ok());
        assert_eq!(ctrl.revoked_count(), 0);
    }
}
