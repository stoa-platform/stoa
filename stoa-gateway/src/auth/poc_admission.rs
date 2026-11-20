//! Unified atomic admission controller for the autonomous PoC.
//!
//! Chain, caller and revocation state is bounded and lives in one process.
//! Both budgets are debited together. Chains live until the root token expires,
//! and caller windows start at the first successful debit across all chains.

use std::collections::{BTreeSet, HashMap};
use std::sync::Arc;

use parking_lot::Mutex;
use sha2::{Digest, Sha256};
use thiserror::Error;

/// Default maximum capacity of the bounded revocation table.
pub const DEFAULT_MAX_REVOKED_CHAINS: usize = 10_000;

/// Default entry limit, applied separately to active chains and caller budgets.
pub const DEFAULT_MAX_ADMISSION_ENTRIES: usize = 10_000;

/// Default fixed caller window, opened by the first successful debit.
pub const DEFAULT_CALLER_BUDGET_WINDOW_SECS: u32 = 900;

/// Maximum permitted length in bytes for chain and caller identifiers.
pub const MAX_ADMISSION_ID_LEN: usize = 128;

/// Default per-chain call budget when not overridden by configuration.
pub const DEFAULT_CHAIN_BUDGET: u64 = 50;

/// Default per-caller call budget when not overridden by configuration.
pub const DEFAULT_CALLER_BUDGET: u64 = 100;

/// Minimum retention when revoking a chain.
const FALLBACK_REVOCATION_RETENTION_SECS: i64 = 900;

type AdmissionKey = [u8; 32];

fn hash_id(raw: &str) -> AdmissionKey {
    let mut hasher = Sha256::new();
    hasher.update(raw.as_bytes());
    hasher.finalize().into()
}

/// Configuration for [PocAdmissionController].
#[derive(Debug, Clone)]
pub struct PocAdmissionConfig {
    pub max_revoked_chains: usize,
    pub default_chain_budget: u64,
    pub default_caller_budget: u64,
    pub max_admission_entries: usize,
    pub caller_budget_window_secs: u32,
}

impl Default for PocAdmissionConfig {
    fn default() -> Self {
        Self {
            max_revoked_chains: DEFAULT_MAX_REVOKED_CHAINS,
            default_chain_budget: DEFAULT_CHAIN_BUDGET,
            default_caller_budget: DEFAULT_CALLER_BUDGET,
            max_admission_entries: DEFAULT_MAX_ADMISSION_ENTRIES,
            caller_budget_window_secs: DEFAULT_CALLER_BUDGET_WINDOW_SECS,
        }
    }
}

/// Errors produced by atomic admission or revocation.
#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum AdmissionError {
    #[error("revocation table is saturated; failing closed")]
    RevocationTableFull,

    #[error("active chains or caller budgets are at capacity")]
    AdmissionTableFull,

    #[error("delegation chain has been revoked")]
    ChainRevoked,

    #[error("delegation chain is unregistered or expired")]
    ChainInactive,

    #[error("session has expired")]
    SessionExpired,

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
    pub session_expires_at: i64,
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

/// Result returned when a delegation chain is atomically revoked.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RevocationReceipt {
    pub chain_id: String,
    pub retain_until_epoch: i64,
}

#[derive(Debug)]
struct TimedEntry<T> {
    expires_at: i64,
    value: T,
}

/// Exactly one deadline per live entry, including entries whose deadline changes.
#[derive(Debug, Default)]
struct ExpiryTable<T> {
    entries: HashMap<AdmissionKey, TimedEntry<T>>,
    deadlines: BTreeSet<(i64, AdmissionKey)>,
}

impl<T> ExpiryTable<T> {
    fn insert(&mut self, key: AdmissionKey, expires_at: i64, value: T) {
        if let Some(previous) = self.entries.insert(key, TimedEntry { expires_at, value }) {
            self.deadlines.remove(&(previous.expires_at, key));
        }
        self.deadlines.insert((expires_at, key));
    }

    fn remove(&mut self, key: &AdmissionKey) {
        if let Some(entry) = self.entries.remove(key) {
            self.deadlines.remove(&(entry.expires_at, *key));
        }
    }

    fn prune(&mut self, now_epoch: i64) {
        while let Some(&(expires_at, key)) = self.deadlines.first() {
            if expires_at > now_epoch {
                break;
            }
            self.remove(&key);
        }
    }
}

#[derive(Debug, Default)]
struct AdmissionState {
    chains: ExpiryTable<u64>,
    callers: ExpiryTable<u64>,
    revoked_chains: ExpiryTable<()>,
    last_now_epoch: Option<i64>,
}

impl AdmissionState {
    fn advance_time(&mut self, now_epoch: i64) -> i64 {
        // A delayed request or a backward clock adjustment cannot undo expiry.
        let now_epoch = self
            .last_now_epoch
            .map_or(now_epoch, |last| last.max(now_epoch));
        self.last_now_epoch = Some(now_epoch);
        self.chains.prune(now_epoch);
        self.callers.prune(now_epoch);
        self.revoked_chains.prune(now_epoch);
        now_epoch
    }
}

/// Shared, thread-safe per-process in-memory admission controller.
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

    /// Reserve the chain before publishing the root token. Child tokens never
    /// outlive the root token. Re-registering an active chain is rejected.
    pub fn register_chain(
        &self,
        chain_id: &str,
        expires_at: i64,
        now_epoch: i64,
    ) -> Result<(), AdmissionError> {
        let chain_hash = chain_key(chain_id)?;
        let mut st = self.state.lock();
        let now_epoch = st.advance_time(now_epoch);
        self.check_revocations(&st, &chain_hash)?;
        if expires_at <= now_epoch {
            return Err(AdmissionError::ChainInactive);
        }
        if st.chains.entries.contains_key(&chain_hash) {
            return Err(AdmissionError::InvalidInput("chain is already registered"));
        }
        if st.chains.entries.len() >= self.config.max_admission_entries {
            return Err(AdmissionError::AdmissionTableFull);
        }
        st.chains.insert(chain_hash, expires_at, 0);
        Ok(())
    }

    /// Record the current time when a request stops before admission.
    pub(crate) fn observe_time(&self, now_epoch: i64) {
        self.state.lock().advance_time(now_epoch);
    }

    /// Verify that the session is current and its chain is active.
    pub fn check_chain_active(
        &self,
        chain_id: &str,
        session_expires_at: i64,
        now_epoch: i64,
    ) -> Result<(), AdmissionError> {
        let chain_hash = chain_key(chain_id)?;
        let mut st = self.state.lock();
        let now_epoch = st.advance_time(now_epoch);
        check_session(session_expires_at, now_epoch)?;
        self.check_revocations(&st, &chain_hash)?;
        if !st.chains.entries.contains_key(&chain_hash) {
            return Err(AdmissionError::ChainInactive);
        }
        Ok(())
    }

    fn check_revocations(
        &self,
        state: &AdmissionState,
        chain_hash: &AdmissionKey,
    ) -> Result<(), AdmissionError> {
        if state.revoked_chains.entries.len() >= self.config.max_revoked_chains {
            return Err(AdmissionError::RevocationTableFull);
        }
        if state.revoked_chains.entries.contains_key(chain_hash) {
            return Err(AdmissionError::ChainRevoked);
        }
        Ok(())
    }

    /// Revoke the chain atomically. The caller's budget window keeps its debit.
    pub fn revoke_chain(
        &self,
        chain_id: &str,
        explicit_retain_until: Option<i64>,
        now_epoch: i64,
    ) -> Result<RevocationReceipt, AdmissionError> {
        let chain_hash = chain_key(chain_id)?;
        let mut st = self.state.lock();
        let now_epoch = st.advance_time(now_epoch);
        let existing = st.revoked_chains.entries.get(&chain_hash);
        if existing.is_none() && st.revoked_chains.entries.len() >= self.config.max_revoked_chains {
            return Err(AdmissionError::RevocationTableFull);
        }

        let retain_until = [
            explicit_retain_until,
            st.chains
                .entries
                .get(&chain_hash)
                .map(|chain| chain.expires_at),
            existing.map(|entry| entry.expires_at),
        ]
        .into_iter()
        .flatten()
        .fold(
            now_epoch.saturating_add(FALLBACK_REVOCATION_RETENTION_SECS),
            i64::max,
        );
        if retain_until <= now_epoch {
            return Err(AdmissionError::InvalidInput(
                "revocation deadline out of range",
            ));
        }

        st.revoked_chains.insert(chain_hash, retain_until, ());
        st.chains.remove(&chain_hash);

        Ok(RevocationReceipt {
            chain_id: chain_id.trim().to_string(),
            retain_until_epoch: retain_until,
        })
    }

    /// Debit both budgets atomically, without allocating or charging either
    /// budget if the admission fails.
    pub fn admit_call(
        &self,
        req: &AdmitCallRequest<'_>,
    ) -> Result<AdmissionReceipt, AdmissionError> {
        let (chain_hash, caller_hash) = budget_keys(req.chain_id, req.caller_id)?;
        if req.cost == 0 {
            return Err(AdmissionError::InvalidInput("cost must be >= 1"));
        }

        let chain_limit = req.chain_limit.unwrap_or(self.config.default_chain_budget);
        let caller_limit = req
            .caller_limit
            .unwrap_or(self.config.default_caller_budget);
        let mut guard = self.state.lock();
        let st = &mut *guard;
        let now_epoch = st.advance_time(req.now_epoch);
        check_session(req.session_expires_at, now_epoch)?;
        self.check_revocations(st, &chain_hash)?;
        let chain = st
            .chains
            .entries
            .get_mut(&chain_hash)
            .ok_or(AdmissionError::ChainInactive)?;
        let caller = st.callers.entries.get_mut(&caller_hash);

        let next_chain = chain
            .value
            .checked_add(req.cost)
            .filter(|&used| used <= chain_limit)
            .ok_or(AdmissionError::ChainBudgetExceeded)?;
        let next_caller = caller
            .as_ref()
            .map_or(0, |entry| entry.value)
            .checked_add(req.cost)
            .filter(|&used| used <= caller_limit)
            .ok_or(AdmissionError::CallerBudgetExceeded)?;

        if let Some(caller) = caller {
            caller.value = next_caller;
        } else {
            if st.callers.entries.len() >= self.config.max_admission_entries {
                return Err(AdmissionError::AdmissionTableFull);
            }
            let deadline = now_epoch
                .checked_add(i64::from(self.config.caller_budget_window_secs))
                .filter(|&deadline| deadline > now_epoch)
                .ok_or(AdmissionError::InvalidInput(
                    "caller window deadline out of range",
                ))?;
            st.callers.insert(caller_hash, deadline, next_caller);
        }
        chain.value = next_chain;

        Ok(AdmissionReceipt {
            chain_used: next_chain,
            chain_remaining: chain_limit - next_chain,
            caller_used: next_caller,
            caller_remaining: caller_limit - next_caller,
        })
    }

    /// Read a live chain and caller budget without starting a window or debiting.
    pub fn budget_snapshot(
        &self,
        chain_id: &str,
        caller_id: &str,
        session_expires_at: i64,
        now_epoch: i64,
    ) -> Result<AdmissionReceipt, AdmissionError> {
        let (chain_hash, caller_hash) = budget_keys(chain_id, caller_id)?;
        let mut st = self.state.lock();
        let now_epoch = st.advance_time(now_epoch);
        check_session(session_expires_at, now_epoch)?;
        self.check_revocations(&st, &chain_hash)?;
        let chain_used = st
            .chains
            .entries
            .get(&chain_hash)
            .ok_or(AdmissionError::ChainInactive)?
            .value;
        let caller_used = st
            .callers
            .entries
            .get(&caller_hash)
            .map_or(0, |entry| entry.value);
        Ok(AdmissionReceipt {
            chain_used,
            caller_used,
            chain_remaining: self.config.default_chain_budget.saturating_sub(chain_used),
            caller_remaining: self
                .config
                .default_caller_budget
                .saturating_sub(caller_used),
        })
    }

    /// Chain debit as of the last processed admission time.
    pub fn chain_used(&self, chain_id: &str) -> u64 {
        let key = hash_id(chain_id.trim());
        self.state
            .lock()
            .chains
            .entries
            .get(&key)
            .map_or(0, |entry| entry.value)
    }

    /// Caller debit as of the last processed admission time.
    pub fn caller_used(&self, caller_id: &str) -> u64 {
        let key = hash_id(caller_id.trim());
        self.state
            .lock()
            .callers
            .entries
            .get(&key)
            .map_or(0, |entry| entry.value)
    }

    /// Revocation entries as of the last processed admission time.
    pub fn revoked_count(&self) -> usize {
        self.state.lock().revoked_chains.entries.len()
    }
}

fn check_session(session_expires_at: i64, now_epoch: i64) -> Result<(), AdmissionError> {
    if session_expires_at <= now_epoch {
        return Err(AdmissionError::SessionExpired);
    }
    Ok(())
}

fn chain_key(chain_id: &str) -> Result<AdmissionKey, AdmissionError> {
    let chain_id = chain_id.trim();
    if chain_id.is_empty() {
        return Err(AdmissionError::InvalidInput("empty chain_id"));
    }
    if chain_id.len() > MAX_ADMISSION_ID_LEN {
        return Err(AdmissionError::InvalidInput("chain_id exceeds max length"));
    }
    Ok(hash_id(chain_id))
}

fn budget_keys(
    chain_id: &str,
    caller_id: &str,
) -> Result<(AdmissionKey, AdmissionKey), AdmissionError> {
    let caller_id = caller_id.trim();
    if caller_id.is_empty() {
        return Err(AdmissionError::InvalidInput("empty caller_id"));
    }
    if caller_id.len() > MAX_ADMISSION_ID_LEN {
        return Err(AdmissionError::InvalidInput("caller_id exceeds max length"));
    }
    Ok((chain_key(chain_id)?, hash_id(caller_id)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Barrier;

    #[test]
    fn budget_snapshot_is_non_debiting_and_respects_chain_admission() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 2,
            default_chain_budget: 1,
            default_caller_budget: 2,
            ..Default::default()
        });
        for chain in ["chain-a", "chain-b", "chain-c"] {
            ctrl.register_chain(chain, 1100, 1000).unwrap();
        }
        let debit = AdmitCallRequest {
            chain_id: "chain-a",
            caller_id: "acme:root",
            cost: 1,
            chain_limit: None,
            caller_limit: None,
            session_expires_at: i64::MAX,
            now_epoch: 1000,
        };
        ctrl.admit_call(&debit).unwrap();

        for _ in 0..2 {
            let a = ctrl
                .budget_snapshot("chain-a", "acme:root", i64::MAX, 1000)
                .unwrap();
            let b = ctrl
                .budget_snapshot("chain-b", "acme:root", i64::MAX, 1000)
                .unwrap();
            let other = ctrl
                .budget_snapshot("chain-c", "acme:other", i64::MAX, 1000)
                .unwrap();
            assert_eq!((a.chain_remaining, a.caller_remaining), (0, 1));
            assert_eq!((b.chain_remaining, b.caller_remaining), (1, 1));
            assert_eq!((other.chain_remaining, other.caller_remaining), (1, 2));
        }
        ctrl.revoke_chain("chain-a", None, 1000).unwrap();
        assert_eq!(
            ctrl.budget_snapshot("chain-a", "acme:root", i64::MAX, 1000)
                .unwrap_err(),
            AdmissionError::ChainRevoked
        );
        assert_eq!(
            ctrl.budget_snapshot("chain-b", "acme:root", i64::MAX, 1000)
                .unwrap()
                .caller_remaining,
            1
        );
        ctrl.revoke_chain("chain-c", None, 1000).unwrap();
        assert_eq!(
            ctrl.budget_snapshot("chain-b", "acme:root", i64::MAX, 1000)
                .unwrap_err(),
            AdmissionError::RevocationTableFull
        );
    }

    #[test]
    fn concurrency_same_chain_no_double_debit() {
        let ctrl = Arc::new(PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 100,
            default_chain_budget: 10,
            default_caller_budget: 100,
            ..Default::default()
        }));
        let now = 1_700_000_000;
        ctrl.register_chain("chain-1", now + 600, now).unwrap();
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
                    session_expires_at: i64::MAX,
                    now_epoch: now,
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
            ..Default::default()
        }));
        let now = 1_700_000_000;
        for i in 0..8 {
            ctrl.register_chain(&format!("chain-{i}"), now + 600, now)
                .unwrap();
        }
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
                    session_expires_at: i64::MAX,
                    now_epoch: now,
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
            ..Default::default()
        }));
        let now = 1_700_000_000;
        ctrl.register_chain("chain-A", now + 600, now).unwrap();
        ctrl.register_chain("chain-B", now + 600, now).unwrap();

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
                    session_expires_at: i64::MAX,
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
                session_expires_at: i64::MAX,
                now_epoch: now + 1,
            })
            .unwrap_err(),
            AdmissionError::ChainRevoked
        );
        assert_eq!(
            ctrl.check_chain_active("chain-A", i64::MAX, now + 1)
                .unwrap_err(),
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
                session_expires_at: i64::MAX,
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
            ..Default::default()
        });
        let now = 1_700_000_000;
        ctrl.register_chain("active-chain", now + 600, now).unwrap();
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
                session_expires_at: i64::MAX,
                now_epoch: now + 10,
            })
            .unwrap_err(),
            AdmissionError::RevocationTableFull
        );

        // Once retention expires (> now + 900 fallback), pruning frees the table.
        let after_expiry = now + FALLBACK_REVOCATION_RETENTION_SECS + 1;
        assert_eq!(
            ctrl.check_chain_active("active-chain", i64::MAX, after_expiry),
            Err(AdmissionError::ChainInactive)
        );
        ctrl.register_chain("new-chain", after_expiry + 600, after_expiry)
            .unwrap();
        assert!(ctrl
            .admit_call(&AdmitCallRequest {
                chain_id: "new-chain",
                caller_id: "acme:agent",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                session_expires_at: i64::MAX,
                now_epoch: after_expiry,
            })
            .is_ok());
        assert_eq!(ctrl.revoked_count(), 0);
    }

    #[test]
    fn revocation_table_enforces_length_bound_and_expiry_with_extended_retention() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 4,
            default_chain_budget: 10,
            default_caller_budget: 10,
            ..Default::default()
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

        // The short revocation expires, while the extended deadline stays in force.
        assert_eq!(
            ctrl.check_chain_active("chain-short", i64::MAX, now + 901),
            Err(AdmissionError::ChainInactive)
        );
        assert_eq!(
            ctrl.check_chain_active("chain-ext", i64::MAX, now + 901)
                .unwrap_err(),
            AdmissionError::ChainRevoked
        );
        assert_eq!(ctrl.revoked_count(), 1);

        // At now + 1801: chain-ext expires cleanly.
        assert_eq!(
            ctrl.check_chain_active("chain-ext", i64::MAX, now + 1_801),
            Err(AdmissionError::ChainInactive)
        );
        assert_eq!(ctrl.revoked_count(), 0);
    }

    fn debit(
        ctrl: &PocAdmissionController,
        chain_id: &str,
        caller_id: &str,
        now_epoch: i64,
    ) -> Result<AdmissionReceipt, AdmissionError> {
        ctrl.admit_call(&AdmitCallRequest {
            chain_id,
            caller_id,
            cost: 1,
            chain_limit: None,
            caller_limit: None,
            session_expires_at: i64::MAX,
            now_epoch,
        })
    }

    #[test]
    fn caller_window_begins_at_first_debit_and_survives_chain_expiry() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            default_chain_budget: 5,
            default_caller_budget: 2,
            max_admission_entries: 1,
            caller_budget_window_secs: 10,
            ..Default::default()
        });
        ctrl.register_chain("short", 105, 100).unwrap();
        assert_eq!(
            ctrl.budget_snapshot("short", "root", i64::MAX, 101)
                .unwrap()
                .caller_used,
            0
        );
        assert!(ctrl.state.lock().callers.entries.is_empty());
        assert_eq!(debit(&ctrl, "short", "root", 102).unwrap().caller_used, 1);
        assert_eq!(
            ctrl.register_chain("long", 140, 104),
            Err(AdmissionError::AdmissionTableFull)
        );
        ctrl.register_chain("long", 140, 105).unwrap();
        assert_eq!(
            ctrl.check_chain_active("short", i64::MAX, 105),
            Err(AdmissionError::ChainInactive)
        );
        assert_eq!(debit(&ctrl, "long", "root", 105).unwrap().caller_used, 2);
        assert_eq!(
            debit(&ctrl, "long", "root", 111),
            Err(AdmissionError::CallerBudgetExceeded)
        );
        assert_eq!(ctrl.chain_used("long"), 1);

        let after_boundary = debit(&ctrl, "long", "root", 112).unwrap();
        assert_eq!(
            (after_boundary.chain_used, after_boundary.caller_used),
            (2, 1)
        );
        let state = ctrl.state.lock();
        assert_eq!(state.chains.entries.len(), 1);
        assert_eq!(state.chains.deadlines.len(), 1);
        assert_eq!(state.callers.entries.len(), 1);
        assert_eq!(state.callers.deadlines.len(), 1);
    }

    #[test]
    fn full_caller_table_denies_new_callers_without_partial_debit() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_admission_entries: 2,
            caller_budget_window_secs: 20,
            ..Default::default()
        });
        ctrl.register_chain("a", 102, 100).unwrap();
        ctrl.register_chain("b", 140, 100).unwrap();
        debit(&ctrl, "a", "first", 100).unwrap();
        debit(&ctrl, "b", "second", 101).unwrap();
        ctrl.register_chain("c", 140, 102).unwrap();

        assert_eq!(
            debit(&ctrl, "c", "third", 119),
            Err(AdmissionError::AdmissionTableFull)
        );
        assert_eq!(ctrl.chain_used("c"), 0);
        assert_eq!(ctrl.caller_used("first"), 1);
        assert_eq!(ctrl.caller_used("second"), 1);
        assert_eq!(ctrl.caller_used("third"), 0);
        assert_eq!(debit(&ctrl, "b", "second", 119).unwrap().caller_used, 2);

        assert_eq!(debit(&ctrl, "c", "third", 120).unwrap().caller_used, 1);
        let st = ctrl.state.lock();
        assert_eq!(st.callers.entries.len(), 2);
        assert_eq!(st.callers.deadlines.len(), 2);
    }

    #[test]
    fn delayed_requests_cannot_reopen_an_expired_chain_or_caller_window() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            default_caller_budget: 1,
            caller_budget_window_secs: 10,
            ..Default::default()
        });
        ctrl.register_chain("short", 105, 100).unwrap();
        ctrl.register_chain("long", 150, 100).unwrap();
        debit(&ctrl, "short", "root", 100).unwrap();
        debit(&ctrl, "long", "root", 110).unwrap();

        assert_eq!(
            ctrl.check_chain_active("short", i64::MAX, 104),
            Err(AdmissionError::ChainInactive)
        );
        assert_eq!(
            ctrl.register_chain("short", 105, 104),
            Err(AdmissionError::ChainInactive)
        );
        assert_eq!(
            debit(&ctrl, "long", "root", 109),
            Err(AdmissionError::CallerBudgetExceeded)
        );
        assert_eq!(
            debit(&ctrl, "long", "root", 119),
            Err(AdmissionError::CallerBudgetExceeded)
        );
        assert_eq!(debit(&ctrl, "long", "root", 120).unwrap().caller_used, 1);
    }

    #[test]
    fn expired_child_session_cannot_use_a_live_root_chain() {
        let root_expires_at = 150;
        let child_expires_at = 110;
        let previous_epoch = child_expires_at - 1;
        for now_epoch in [child_expires_at, previous_epoch] {
            let ctrl = PocAdmissionController::new(PocAdmissionConfig::default());
            ctrl.register_chain("chain", root_expires_at, 100).unwrap();
            let child = AdmitCallRequest {
                chain_id: "chain",
                caller_id: "root",
                cost: 1,
                chain_limit: None,
                caller_limit: None,
                session_expires_at: child_expires_at,
                now_epoch: previous_epoch,
            };
            assert_eq!(ctrl.admit_call(&child).unwrap().chain_used, 1);

            if now_epoch == previous_epoch {
                ctrl.observe_time(child_expires_at);
            }

            assert_eq!(
                ctrl.check_chain_active("chain", child_expires_at, now_epoch),
                Err(AdmissionError::SessionExpired)
            );
            assert_eq!(
                ctrl.budget_snapshot("chain", "root", child_expires_at, now_epoch),
                Err(AdmissionError::SessionExpired)
            );
            assert_eq!(
                ctrl.admit_call(&AdmitCallRequest { now_epoch, ..child }),
                Err(AdmissionError::SessionExpired)
            );

            ctrl.check_chain_active("chain", root_expires_at, now_epoch)
                .unwrap();
            let root = ctrl
                .budget_snapshot("chain", "root", root_expires_at, now_epoch)
                .unwrap();
            assert_eq!((root.chain_used, root.caller_used), (1, 1));
        }
    }

    #[test]
    fn repeated_revocation_extensions_keep_a_single_index_entry_per_chain() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            max_revoked_chains: 2,
            ..Default::default()
        });
        let now = 1000;
        let mut latest = 0;
        for extension in 0..200 {
            latest = now + FALLBACK_REVOCATION_RETENTION_SECS + extension;
            ctrl.revoke_chain("chain", Some(latest), now).unwrap();
            let st = ctrl.state.lock();
            assert_eq!(st.revoked_chains.entries.len(), 1);
            assert_eq!(st.revoked_chains.deadlines.len(), 1);
        }
        assert_eq!(
            ctrl.check_chain_active("chain", i64::MAX, latest - 1),
            Err(AdmissionError::ChainRevoked)
        );
        assert_eq!(
            ctrl.check_chain_active("chain", i64::MAX, latest),
            Err(AdmissionError::ChainInactive)
        );
        let st = ctrl.state.lock();
        assert!(st.revoked_chains.entries.is_empty());
        assert!(st.revoked_chains.deadlines.is_empty());
    }

    #[test]
    fn rejected_debit_and_duplicate_registration_leave_state_unchanged() {
        let ctrl = PocAdmissionController::new(PocAdmissionConfig {
            default_chain_budget: 1,
            ..Default::default()
        });
        ctrl.register_chain("chain", 140, 100).unwrap();
        debit(&ctrl, "chain", "root", 100).unwrap();
        assert_eq!(
            ctrl.register_chain("chain", 150, 101),
            Err(AdmissionError::InvalidInput("chain is already registered"))
        );
        assert_eq!(
            debit(&ctrl, "chain", "other", 101),
            Err(AdmissionError::ChainBudgetExceeded)
        );
        assert_eq!(ctrl.chain_used("chain"), 1);
        assert_eq!(ctrl.caller_used("other"), 0);
        assert_eq!(ctrl.state.lock().callers.entries.len(), 1);
        assert_eq!(
            ctrl.check_chain_active("chain", i64::MAX, 140),
            Err(AdmissionError::ChainInactive)
        );
    }
}
