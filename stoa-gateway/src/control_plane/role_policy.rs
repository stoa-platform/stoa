//! Signed local agent-role policy artifacts with durable anti-rollback floor
//! (`0600`, atomic write), 15-minute maximum validity, deterministic v1 argument
//! constraints, and monotonic session anti-widening enforcement.
//!
//! Uses a dedicated compact JWS `typ` (`stoa-agent-role-policy+jws`) verified
//! with the same pinned Ed25519 trust store (`PolicyTrustStore`) as Control
//! Plane tool policies, avoiding any schema conflict with `stoa-tool-policy+jws`.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, SystemTime};

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use jsonwebtoken::{Algorithm, Validation};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use thiserror::Error;
use tracing::warn;
use uuid::Uuid;

use super::policy_trust::PolicyTrustStore;

/// Distinct compact JWS `typ` for signed agent-role artifacts.
pub const ROLE_POLICY_ARTIFACT_TYP: &str = "stoa-agent-role-policy+jws";

/// Maximum permitted validity window for a signed role policy artifact (15 minutes).
pub const MAX_ROLE_POLICY_VALIDITY: Duration = Duration::from_secs(900);

/// Maximum tolerated clock skew for `issued_at`.
const MAX_CLOCK_SKEW_SECS: i64 = 30;

/// Maximum artifact file size (1 MiB).
const MAX_ROLE_POLICY_BYTES: usize = 1024 * 1024;

/// Maximum number of historical versions kept per tenant for session intersection.
const MAX_VERSION_HISTORY: usize = 64;

/// Hard upper bound on the number of tenants tracked in memory by [`RolePolicyStore`].
pub const MAX_TRACKED_TENANTS: usize = 1024;

static KID_FORMAT: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^cp-policy-[0-9]{4}(0[1-9]|1[0-2])-[1-9][0-9]*$").expect("kid regex")
});

/// Maximum raw JSON number lexeme length accepted for exact `MaxNumber` validation.
const MAX_NUMBER_LEXEME_LEN: usize = 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
enum CanonicalDecimal {
    Zero,
    NonZero {
        negative: bool,
        digits: String,
        exponent: i64,
    },
}

fn parse_canonical_decimal(raw: &str) -> Option<CanonicalDecimal> {
    if raw.is_empty() || raw.len() > MAX_NUMBER_LEXEME_LEN {
        return None;
    }
    let bytes = raw.as_bytes();
    let mut idx = 0;

    let negative = if bytes[idx] == b'-' {
        idx += 1;
        if idx == bytes.len() {
            return None;
        }
        true
    } else {
        false
    };

    let int_start = idx;
    if bytes[idx] == b'0' {
        idx += 1;
        if idx < bytes.len() && bytes[idx].is_ascii_digit() {
            return None;
        }
    } else if bytes[idx].is_ascii_digit() {
        while idx < bytes.len() && bytes[idx].is_ascii_digit() {
            idx += 1;
        }
    } else {
        return None;
    }
    let int_part = &raw[int_start..idx];

    let frac_part = if idx < bytes.len() && bytes[idx] == b'.' {
        idx += 1;
        let frac_start = idx;
        while idx < bytes.len() && bytes[idx].is_ascii_digit() {
            idx += 1;
        }
        if idx == frac_start {
            return None;
        }
        &raw[frac_start..idx]
    } else {
        ""
    };

    let exp_val = if idx < bytes.len() && (bytes[idx] == b'e' || bytes[idx] == b'E') {
        idx += 1;
        if idx == bytes.len() {
            return None;
        }
        let exp_neg = match bytes[idx] {
            b'-' => {
                idx += 1;
                true
            }
            b'+' => {
                idx += 1;
                false
            }
            _ => false,
        };
        let exp_start = idx;
        while idx < bytes.len() && bytes[idx].is_ascii_digit() {
            idx += 1;
        }
        if idx == exp_start {
            return None;
        }
        let mut exp_abs: i64 = 0;
        for &b in &bytes[exp_start..idx] {
            exp_abs = exp_abs.checked_mul(10)?.checked_add(i64::from(b - b'0'))?;
        }
        if exp_neg {
            exp_abs.checked_neg()?
        } else {
            exp_abs
        }
    } else {
        0
    };

    if idx != bytes.len() {
        return None;
    }

    let mut digits = String::with_capacity(int_part.len() + frac_part.len());
    digits.push_str(int_part);
    digits.push_str(frac_part);

    let trimmed_leading = digits.trim_start_matches('0');
    if trimmed_leading.is_empty() {
        return Some(CanonicalDecimal::Zero);
    }
    let trimmed = trimmed_leading.trim_end_matches('0');
    let trailing_zeros = trimmed_leading.len() - trimmed.len();

    let frac_len = i64::try_from(frac_part.len()).ok()?;
    let trailing_zeros = i64::try_from(trailing_zeros).ok()?;
    let exponent = exp_val.checked_sub(frac_len)?.checked_add(trailing_zeros)?;

    Some(CanonicalDecimal::NonZero {
        negative,
        digits: trimmed.to_string(),
        exponent,
    })
}

/// Parse a raw JSON number lexeme into a finite `f64` only when its decimal value
/// round-trips identically through `serde_json::Number::from_f64`.
pub(crate) fn parse_exact_f64_lexeme(raw: &str) -> Option<f64> {
    let expected = parse_canonical_decimal(raw)?;
    let value: f64 = serde_json::from_str(raw).ok()?;
    if !value.is_finite() {
        return None;
    }
    let round_tripped = serde_json::Number::from_f64(value)?.to_string();
    let actual = parse_canonical_decimal(&round_tripped)?;
    (expected == actual).then_some(value)
}

fn exact_f64_from_value(value: &Value) -> Option<f64> {
    let number = value.as_number()?;
    parse_exact_f64_lexeme(&number.to_string())
}

/// Deterministic v1 argument constraint types.
#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ArgumentConstraint {
    /// Argument value must exactly match one of the listed JSON values.
    AllowedValues { values: Vec<Value> },
    /// Argument must be a JSON string starting with `prefix`.
    Prefix { prefix: String },
    /// Argument must be a finite JSON number `<= max`.
    MaxNumber { max: f64 },
}

impl<'de> Deserialize<'de> for ArgumentConstraint {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        #[derive(Deserialize)]
        struct ConstraintTag {
            #[serde(rename = "type")]
            kind: String,
        }
        #[derive(Deserialize)]
        struct AllowedValuesWire {
            values: Vec<Value>,
        }
        #[derive(Deserialize)]
        struct PrefixWire {
            prefix: String,
        }
        #[derive(Deserialize)]
        struct MaxNumberWire {
            max: Box<RawValue>,
        }

        let raw = Box::<RawValue>::deserialize(deserializer)?;
        let tag: ConstraintTag =
            serde_json::from_str(raw.get()).map_err(serde::de::Error::custom)?;
        match tag.kind.as_str() {
            "allowed_values" => {
                let wire: AllowedValuesWire =
                    serde_json::from_str(raw.get()).map_err(serde::de::Error::custom)?;
                Ok(ArgumentConstraint::AllowedValues {
                    values: wire.values,
                })
            }
            "prefix" => {
                let wire: PrefixWire =
                    serde_json::from_str(raw.get()).map_err(serde::de::Error::custom)?;
                Ok(ArgumentConstraint::Prefix {
                    prefix: wire.prefix,
                })
            }
            "max_number" => {
                let wire: MaxNumberWire =
                    serde_json::from_str(raw.get()).map_err(serde::de::Error::custom)?;
                let max = parse_exact_f64_lexeme(wire.max.get()).ok_or_else(|| {
                    serde::de::Error::custom("max_number bound must be a finite exact JSON number")
                })?;
                Ok(ArgumentConstraint::MaxNumber { max })
            }
            other => Err(serde::de::Error::custom(format!(
                "unknown argument constraint type `{other}`"
            ))),
        }
    }
}

impl ArgumentConstraint {
    /// Evaluate whether `value` satisfies this constraint. Missing values fail closed.
    pub fn matches(&self, value: Option<&Value>) -> bool {
        self.matches_with_wire_lexeme(value, None)
    }

    /// Evaluate whether `value` satisfies this constraint in wire mode, requiring an exact
    /// raw JSON lexeme for `MaxNumber` that matches the `f64` carried by `value`.
    pub fn matches_with_raw(&self, value: Option<&Value>, raw_lexeme: Option<&str>) -> bool {
        self.matches_with_wire_lexeme(value, Some(raw_lexeme))
    }

    fn matches_with_wire_lexeme(
        &self,
        value: Option<&Value>,
        wire_lexeme: Option<Option<&str>>,
    ) -> bool {
        let Some(val) = value else {
            return false;
        };
        match self {
            ArgumentConstraint::AllowedValues { values } => {
                !values.is_empty() && values.iter().any(|allowed| allowed == val)
            }
            ArgumentConstraint::Prefix { prefix } => {
                val.as_str().is_some_and(|s| s.starts_with(prefix.as_str()))
            }
            ArgumentConstraint::MaxNumber { max } => {
                if !max.is_finite() || !val.is_number() {
                    return false;
                }
                let parsed = match wire_lexeme {
                    Some(Some(raw)) => {
                        let Some(raw_f64) = parse_exact_f64_lexeme(raw) else {
                            return false;
                        };
                        let Some(val_f64) = exact_f64_from_value(val) else {
                            return false;
                        };
                        if val_f64 != raw_f64 {
                            return false;
                        }
                        Some(raw_f64)
                    }
                    Some(None) => None,
                    None => exact_f64_from_value(val),
                };
                parsed.is_some_and(|n| n.is_finite() && n <= *max)
            }
        }
    }

    /// Returns `true` if `self` is at least as restrictive as `parent` (strict inclusion).
    pub fn is_subset_of(&self, parent: &ArgumentConstraint) -> bool {
        match (self, parent) {
            (
                ArgumentConstraint::AllowedValues { values: child },
                ArgumentConstraint::AllowedValues {
                    values: parent_vals,
                },
            ) => !child.is_empty() && child.iter().all(|c| parent_vals.contains(c)),
            (
                ArgumentConstraint::Prefix { prefix: child },
                ArgumentConstraint::Prefix { prefix: parent_pfx },
            ) => child.starts_with(parent_pfx.as_str()),
            (
                ArgumentConstraint::MaxNumber { max: child },
                ArgumentConstraint::MaxNumber { max: parent_max },
            ) => child.is_finite() && parent_max.is_finite() && child <= parent_max,
            _ => false,
        }
    }
}

/// Role policy definition inside a signed role artifact.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct RolePolicySpec {
    /// Explicit allow-list of MCP tools this role may invoke (deny by default).
    #[serde(default)]
    pub allowed_tools: HashSet<String>,
    /// Per-tool deterministic argument constraints: `tool_name -> arg_name -> constraint`.
    #[serde(default)]
    pub argument_constraints: HashMap<String, HashMap<String, ArgumentConstraint>>,
}

/// Verified in-memory role policy snapshot for one tenant.
#[derive(Debug, Clone)]
pub struct VerifiedRolePolicy {
    pub tenant_id: String,
    pub tenant_uuid: Uuid,
    pub version: u64,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub content_sha256: String,
    pub roles: HashMap<String, RolePolicySpec>,
}

/// Persisted anti-rollback version floor stored at `<floor_dir>/<tenant_id>.floor.json` (`0600`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct PersistedVersionFloor {
    tenant_uuid: Uuid,
    version: u64,
    content_sha256: String,
}

/// Errors returned during signed role policy verification, persistence, or evaluation.
#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum RolePolicyError {
    #[error("role policy trust store is not loaded")]
    TrustSetNotLoaded,
    #[error("invalid tenant identifier")]
    InvalidTenant,
    #[error("role policy artifact missing or unreadable")]
    ArtifactMissing,
    #[error("role policy artifact is malformed")]
    Malformed,
    #[error("role policy header must contain exactly alg, typ and kid")]
    HeaderParams,
    #[error("role policy alg must be EdDSA")]
    Algorithm,
    #[error("role policy typ must be {ROLE_POLICY_ARTIFACT_TYP}")]
    Type,
    #[error("role policy kid format is invalid")]
    KidFormat,
    #[error("role policy kid is not in pinned trust set")]
    UnknownKid,
    #[error("role policy signature verification failed")]
    Signature,
    #[error("role policy issuer mismatch")]
    Issuer,
    #[error("role policy audience mismatch")]
    Audience,
    #[error("role policy tenant mismatch")]
    TenantMismatch,
    #[error("role policy validity expired or exceeds 15-minute maximum")]
    ValidityInvalid,
    #[error("role policy version rollback or conflicting content at same version")]
    VersionRollback,
    #[error("persisted anti-rollback floor is unreadable or corrupted")]
    FloorCorrupted,
    #[error("failed to persist anti-rollback floor atomically")]
    FloorPersistFailed,
    #[error("tool call denied by role policy")]
    DeniedByRole,
    #[error("tool call denied by argument constraint")]
    DeniedByConstraint,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct FileFingerprint {
    modified: SystemTime,
    len: u64,
    #[cfg(unix)]
    ino: u64,
    #[cfg(unix)]
    ctime: i64,
    #[cfg(unix)]
    ctime_nsec: i64,
    #[cfg(unix)]
    mode: u32,
    #[cfg(not(unix))]
    created: Option<SystemTime>,
}

#[derive(Debug, Clone)]
struct TenantSnapshot {
    result: Result<Arc<VerifiedRolePolicy>, RolePolicyError>,
    fingerprint: Option<FileFingerprint>,
    generation: u64,
}

#[derive(Debug, Default)]
struct TenantPolicyState {
    current_version: u64,
    /// Ordered history of activated verified versions (bounded to `MAX_VERSION_HISTORY`).
    history: BTreeMap<u64, Arc<VerifiedRolePolicy>>,
    /// Monotonic counter incremented each time a snapshot is stored for this tenant.
    snapshot_generation: u64,
    /// Latest loaded snapshot (or load error) plus pre-read file fingerprint.
    snapshot: Option<TenantSnapshot>,
}

/// Typed inputs for evaluating a single tool call against the signed role policy.
pub struct RoleEvalInput<'a> {
    pub tenant_id: &'a str,
    pub role: &'a str,
    pub tool_name: &'a str,
    pub args: &'a Value,
    pub issued_policy_version: u64,
    pub token_allowed_tools: Option<&'a [String]>,
    pub token_constraints: Option<&'a HashMap<String, ArgumentConstraint>>,
}

/// Store loading, verifying, persisting floors for, and evaluating signed local role policies.
#[derive(Clone)]
pub struct RolePolicyStore {
    artifacts_dir: PathBuf,
    floor_dir: PathBuf,
    issuer: String,
    audience: String,
    trust: Option<Arc<PolicyTrustStore>>,
    allowed_tenants: Option<Arc<HashSet<String>>>,
    max_tracked_tenants: usize,
    tenants: Arc<RwLock<HashMap<String, TenantPolicyState>>>,
    refresh_locks: Arc<RwLock<HashMap<String, Arc<tokio::sync::Mutex<()>>>>>,
    #[cfg(test)]
    reload_count: Arc<std::sync::atomic::AtomicUsize>,
}

impl RolePolicyStore {
    pub fn new(
        artifacts_dir: impl Into<PathBuf>,
        floor_dir: impl Into<PathBuf>,
        issuer: impl Into<String>,
        audience: impl Into<String>,
        trust: Option<Arc<PolicyTrustStore>>,
    ) -> Self {
        Self {
            artifacts_dir: artifacts_dir.into(),
            floor_dir: floor_dir.into(),
            issuer: issuer.into(),
            audience: audience.into(),
            trust,
            allowed_tenants: None,
            max_tracked_tenants: MAX_TRACKED_TENANTS,
            tenants: Arc::new(RwLock::new(HashMap::new())),
            refresh_locks: Arc::new(RwLock::new(HashMap::new())),
            #[cfg(test)]
            reload_count: Arc::new(std::sync::atomic::AtomicUsize::new(0)),
        }
    }

    /// Restrict tracked tenants to an explicit allowlist when non-empty (e.g. `policy_boot_tenants`).
    ///
    /// An empty iterator leaves the store bounded by on-disk artifacts and [`MAX_TRACKED_TENANTS`].
    pub fn with_allowed_tenants<I, S>(mut self, tenants: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<String>,
    {
        let set: HashSet<String> = tenants
            .into_iter()
            .map(Into::into)
            .filter(|tenant| !tenant.trim().is_empty())
            .collect();
        self.allowed_tenants = (!set.is_empty()).then(|| Arc::new(set));
        self
    }

    #[cfg(test)]
    fn with_max_tracked_tenants(mut self, max: usize) -> Self {
        self.max_tracked_tenants = max;
        self
    }

    #[cfg(test)]
    pub(crate) fn reload_count(&self) -> usize {
        self.reload_count.load(std::sync::atomic::Ordering::SeqCst)
    }

    fn ensure_tenant_allowed(&self, tenant_id: &str) -> Result<(), RolePolicyError> {
        if self
            .allowed_tenants
            .as_ref()
            .is_some_and(|allowed| !allowed.contains(tenant_id))
        {
            return Err(RolePolicyError::ArtifactMissing);
        }
        Ok(())
    }

    /// Verify the in-memory snapshot for `tenant_id` against the current on-disk artifact.
    ///
    /// Serializes per-tenant checks and runs `stat` (+ conditional [`Self::reload_tenant`])
    /// inside `tokio::task::spawn_blocking` on every call so policy reductions apply on the
    /// very next request without blocking async runtime worker threads.
    pub async fn refresh_tenant(&self, tenant_id: &str) -> Result<(), RolePolicyError> {
        validate_tenant_filename(tenant_id)?;
        self.ensure_tenant_allowed(tenant_id)?;

        let lock = self.resolve_tenant_refresh_lock(tenant_id).await?;
        let _guard = lock.lock().await;

        let store = self.clone();
        let tenant = tenant_id.to_string();
        tokio::task::spawn_blocking(move || store.refresh_tenant_blocking(&tenant))
            .await
            .map_err(|err| {
                warn!(
                    tenant_id = %tenant_id,
                    cancelled = err.is_cancelled(),
                    panicked = err.is_panic(),
                    "Role policy refresh blocking task failed"
                );
                RolePolicyError::ArtifactMissing
            })?
    }

    fn require_trust_loaded(&self) -> Result<(), RolePolicyError> {
        if self.trust.as_ref().and_then(|t| t.current()).is_none() {
            return Err(RolePolicyError::TrustSetNotLoaded);
        }
        Ok(())
    }

    async fn resolve_tenant_refresh_lock(
        &self,
        tenant_id: &str,
    ) -> Result<Arc<tokio::sync::Mutex<()>>, RolePolicyError> {
        if let Some(lock) = self.refresh_locks.read().get(tenant_id) {
            return Ok(Arc::clone(lock));
        }

        let already_tracked = self.tenants.read().contains_key(tenant_id);
        if !already_tracked {
            if self.tenants.read().len() >= self.max_tracked_tenants
                || self.refresh_locks.read().len() >= self.max_tracked_tenants
            {
                return Err(RolePolicyError::ArtifactMissing);
            }

            let artifact_path = self.artifacts_dir.join(format!("{tenant_id}.roles.jws"));
            let exists_and_readable = tokio::task::spawn_blocking(move || {
                File::open(&artifact_path)
                    .and_then(|file| file.metadata())
                    .is_ok_and(|meta| meta.is_file())
            })
            .await
            .map_err(|_| RolePolicyError::ArtifactMissing)?;
            if !exists_and_readable {
                return Err(RolePolicyError::ArtifactMissing);
            }
        }

        let mut locks = self.refresh_locks.write();
        if let Some(lock) = locks.get(tenant_id) {
            return Ok(Arc::clone(lock));
        }
        if locks.len() >= self.max_tracked_tenants {
            return Err(RolePolicyError::ArtifactMissing);
        }
        let lock = Arc::new(tokio::sync::Mutex::new(()));
        locks.insert(tenant_id.to_string(), Arc::clone(&lock));
        Ok(lock)
    }

    fn refresh_tenant_blocking(&self, tenant_id: &str) -> Result<(), RolePolicyError> {
        let artifact_path = self.artifacts_dir.join(format!("{tenant_id}.roles.jws"));
        let current_fp = file_fingerprint(&artifact_path);

        if current_fp.is_some() && self.require_trust_loaded().is_ok() {
            let map = self.tenants.read();
            let unchanged = map
                .get(tenant_id)
                .and_then(|state| state.snapshot.as_ref())
                .is_some_and(|snapshot| {
                    matches!(
                        &snapshot.result,
                        Ok(policy)
                            if snapshot.fingerprint == current_fp
                                && Utc::now() < policy.expires_at
                    )
                });
            if unchanged {
                return Ok(());
            }
        }

        self.reload_tenant(tenant_id).map(|_| ())
    }

    /// Reload, verify, persist floor atomically (0600), and activate the signed role
    /// artifact `<artifacts_dir>/<tenant_id>.roles.jws`.
    pub fn reload_tenant(&self, tenant_id: &str) -> Result<VerifiedRolePolicy, RolePolicyError> {
        validate_tenant_filename(tenant_id)?;
        self.ensure_tenant_allowed(tenant_id)?;

        let (already_tracked, start_generation) = {
            let map = self.tenants.read();
            match map.get(tenant_id) {
                Some(state) => (true, state.snapshot_generation),
                None => {
                    if map.len() >= self.max_tracked_tenants {
                        return Err(RolePolicyError::ArtifactMissing);
                    }
                    (false, 0)
                }
            }
        };

        #[cfg(test)]
        self.reload_count
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst);

        let artifact_path = self.artifacts_dir.join(format!("{tenant_id}.roles.jws"));
        let Some(fingerprint) = file_fingerprint(&artifact_path) else {
            if already_tracked {
                self.record_error_snapshot(
                    tenant_id,
                    &RolePolicyError::ArtifactMissing,
                    None,
                    start_generation,
                );
            }
            return Err(RolePolicyError::ArtifactMissing);
        };
        let result = self
            .load_verified_tenant(tenant_id, &artifact_path)
            .and_then(|verified| {
                self.activate_verified_policy_with_fp(
                    tenant_id,
                    verified,
                    Some(fingerprint),
                    start_generation,
                )
            });

        if let Err(ref err) = result {
            self.record_error_snapshot(tenant_id, err, Some(fingerprint), start_generation);
        }

        result
    }

    fn record_error_snapshot(
        &self,
        tenant_id: &str,
        err: &RolePolicyError,
        fingerprint: Option<FileFingerprint>,
        start_generation: u64,
    ) {
        let mut map = self.tenants.write();
        if !map.contains_key(tenant_id)
            && (matches!(
                err,
                RolePolicyError::ArtifactMissing | RolePolicyError::InvalidTenant
            ) || map.len() >= self.max_tracked_tenants)
        {
            return;
        }
        let state = map.entry(tenant_id.to_string()).or_default();
        let newer_snapshot_present = state
            .snapshot
            .as_ref()
            .is_some_and(|snapshot| snapshot.generation > start_generation);
        if newer_snapshot_present {
            return;
        }
        state.snapshot_generation += 1;
        let generation = state.snapshot_generation;
        state.snapshot = Some(TenantSnapshot {
            result: Err(err.clone()),
            fingerprint,
            generation,
        });
    }

    fn load_verified_tenant(
        &self,
        tenant_id: &str,
        artifact_path: &Path,
    ) -> Result<VerifiedRolePolicy, RolePolicyError> {
        let trust = self
            .trust
            .as_ref()
            .and_then(|t| t.current())
            .ok_or(RolePolicyError::TrustSetNotLoaded)?;

        let bytes = fs::read(artifact_path).map_err(|_| RolePolicyError::ArtifactMissing)?;
        if bytes.len() > MAX_ROLE_POLICY_BYTES {
            return Err(RolePolicyError::Malformed);
        }
        let jws = String::from_utf8(bytes)
            .map_err(|_| RolePolicyError::Malformed)?
            .trim()
            .to_string();

        self.verify_jws(&trust, tenant_id, &jws)
    }

    #[cfg(test)]
    fn activate_verified_policy(
        &self,
        tenant_id: &str,
        verified: VerifiedRolePolicy,
    ) -> Result<VerifiedRolePolicy, RolePolicyError> {
        let start_generation = self
            .tenants
            .read()
            .get(tenant_id)
            .map_or(0, |state| state.snapshot_generation);
        self.activate_verified_policy_with_fp(tenant_id, verified, None, start_generation)
    }

    fn activate_verified_policy_with_fp(
        &self,
        tenant_id: &str,
        verified: VerifiedRolePolicy,
        fingerprint: Option<FileFingerprint>,
        start_generation: u64,
    ) -> Result<VerifiedRolePolicy, RolePolicyError> {
        let _floor_lock = lock_floor(&self.floor_dir, tenant_id)?;
        if Utc::now() >= verified.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
        }

        #[cfg_attr(not(unix), allow(unused_variables))]
        let prev_version = {
            let map = self.tenants.read();
            if let Some(state) = map.get(tenant_id) {
                if let Some(newer_err) = newer_error_snapshot(state, start_generation) {
                    return Err(newer_err);
                }
                if verified.version < state.current_version {
                    return Err(RolePolicyError::VersionRollback);
                }
                if verified.version == state.current_version
                    && state
                        .history
                        .get(&verified.version)
                        .is_some_and(|prev| prev.content_sha256 != verified.content_sha256)
                {
                    return Err(RolePolicyError::VersionRollback);
                }
                state.current_version
            } else if map.len() >= self.max_tracked_tenants {
                return Err(RolePolicyError::ArtifactMissing);
            } else {
                0
            }
        };

        // Check persisted floor and persist atomically BEFORE activating in memory,
        // without holding `self.tenants` write lock across disk I/O.
        let floor_path = self.floor_dir.join(format!("{tenant_id}.floor.json"));
        let existing_floor = read_persisted_floor(&floor_path)?;
        let next_floor = PersistedVersionFloor {
            tenant_uuid: verified.tenant_uuid,
            version: verified.version,
            content_sha256: verified.content_sha256.clone(),
        };

        let must_persist = match existing_floor {
            None => true,
            Some(ref prev) => {
                if prev.tenant_uuid != next_floor.tenant_uuid {
                    return Err(RolePolicyError::TenantMismatch);
                }
                if next_floor.version < prev.version {
                    return Err(RolePolicyError::VersionRollback);
                }
                if next_floor.version == prev.version {
                    if next_floor.content_sha256 != prev.content_sha256 {
                        return Err(RolePolicyError::VersionRollback);
                    }
                    false
                } else {
                    true
                }
            }
        };

        if must_persist {
            persist_floor_atomic_0600(&self.floor_dir, &floor_path, &next_floor)?;
        }
        #[cfg(unix)]
        if must_persist || prev_version != verified.version {
            fs::File::open(&self.floor_dir)
                .and_then(|dir| dir.sync_all())
                .map_err(|_| RolePolicyError::FloorPersistFailed)?;
        }

        let verified_arc = Arc::new(verified.clone());
        let mut map = self.tenants.write();
        if !map.contains_key(tenant_id) && map.len() >= self.max_tracked_tenants {
            return Err(RolePolicyError::ArtifactMissing);
        }
        let state = map.entry(tenant_id.to_string()).or_default();
        if let Some(newer_err) = newer_error_snapshot(state, start_generation) {
            return Err(newer_err);
        }
        if verified.version < state.current_version {
            return Err(RolePolicyError::VersionRollback);
        }
        if verified.version == state.current_version
            && state
                .history
                .get(&verified.version)
                .is_some_and(|prev| prev.content_sha256 != verified.content_sha256)
        {
            return Err(RolePolicyError::VersionRollback);
        }

        let stale_same_version = verified.version == state.current_version
            && state
                .snapshot
                .as_ref()
                .is_some_and(|snapshot| snapshot.generation > start_generation);

        state.current_version = verified.version;
        state
            .history
            .insert(verified.version, Arc::clone(&verified_arc));
        while state.history.len() > MAX_VERSION_HISTORY {
            if let Some(&oldest) = state.history.keys().next() {
                state.history.remove(&oldest);
            }
        }
        if !stale_same_version {
            state.snapshot_generation += 1;
            let generation = state.snapshot_generation;
            state.snapshot = Some(TenantSnapshot {
                result: Ok(verified_arc),
                fingerprint,
                generation,
            });
        }

        Ok(verified)
    }

    /// Snapshot the current verified policy version and role permissions for `tenant_id`
    /// from memory (no file I/O; callers on async paths should await [`Self::refresh_tenant`] first).
    pub fn current_role_snapshot(
        &self,
        tenant_id: &str,
        role: &str,
    ) -> Result<(u64, RolePolicySpec), RolePolicyError> {
        validate_tenant_filename(tenant_id)?;
        self.ensure_tenant_allowed(tenant_id)?;
        self.require_trust_loaded()?;
        let map = self.tenants.read();
        let state = map.get(tenant_id).ok_or(RolePolicyError::ArtifactMissing)?;
        let current = state
            .snapshot
            .as_ref()
            .ok_or(RolePolicyError::ArtifactMissing)?
            .result
            .as_ref()
            .map_err(Clone::clone)?;
        if Utc::now() >= current.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
        }
        let spec = current
            .roles
            .get(role)
            .cloned()
            .ok_or(RolePolicyError::DeniedByRole)?;
        Ok((current.version, spec))
    }

    /// Evaluate the monotonic intersection across every policy version activated since
    /// `issued_policy_version`, plus any delegated tool-set and argument-constraint narrowing
    /// carried in the token, using the in-memory snapshot (no file I/O).
    pub fn evaluate_call(&self, input: &RoleEvalInput<'_>) -> Result<(), RolePolicyError> {
        self.evaluate_call_internal(input, None)
    }

    /// Evaluate a tool call with captured wire JSON number lexemes (fail-closed for any
    /// `MaxNumber` argument missing a raw lexeme), using the in-memory snapshot (no file I/O).
    pub(crate) fn evaluate_call_with_raw(
        &self,
        input: &RoleEvalInput<'_>,
        raw_number_args: &HashMap<String, String>,
    ) -> Result<(), RolePolicyError> {
        self.evaluate_call_internal(input, Some(raw_number_args))
    }

    fn evaluate_call_internal(
        &self,
        input: &RoleEvalInput<'_>,
        raw_number_args: Option<&HashMap<String, String>>,
    ) -> Result<(), RolePolicyError> {
        let RoleEvalInput {
            tenant_id,
            role,
            tool_name,
            args,
            issued_policy_version,
            token_allowed_tools,
            token_constraints,
        } = *input;
        validate_tenant_filename(tenant_id)?;
        self.ensure_tenant_allowed(tenant_id)?;
        self.require_trust_loaded()?;

        let map = self.tenants.read();
        let state = map.get(tenant_id).ok_or(RolePolicyError::ArtifactMissing)?;
        let current = state
            .snapshot
            .as_ref()
            .ok_or(RolePolicyError::ArtifactMissing)?
            .result
            .as_ref()
            .map_err(Clone::clone)?;
        if Utc::now() >= current.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
        }
        if issued_policy_version == 0 || issued_policy_version > current.version {
            return Err(RolePolicyError::DeniedByRole);
        }

        // Token-level explicit tool allow-list (strict narrowing for delegated tokens).
        if let Some(allowed) = token_allowed_tools {
            if !allowed.iter().any(|t| t == tool_name) {
                return Err(RolePolicyError::DeniedByRole);
            }
        }

        // Intersect EVERY activated policy version from `issued_policy_version..=current.version`.
        // Guarantees:
        // - Widening added after token issuance is denied (absent in `issued_policy_version`).
        // - Reduction takes effect immediately once refreshed (absent in `current.version`).
        // - Withdrawal in v(k) followed by restoration in v(k+1) under the same token stays denied
        //   because v(k) is in `issued_policy_version..=current.version`.
        if !state.history.contains_key(&issued_policy_version) {
            return Err(RolePolicyError::DeniedByRole);
        }

        let args_obj = args.as_object();
        let validate = |constraints: &HashMap<String, ArgumentConstraint>| {
            for (arg_name, constraint) in constraints {
                let wire_lexeme =
                    raw_number_args.map(|raw_map| raw_map.get(arg_name).map(String::as_str));
                if !constraint
                    .matches_with_wire_lexeme(args_obj.and_then(|o| o.get(arg_name)), wire_lexeme)
                {
                    return Err(RolePolicyError::DeniedByConstraint);
                }
            }
            Ok(())
        };

        for (&ver, policy) in state.history.range(issued_policy_version..=current.version) {
            if Utc::now() >= policy.expires_at && ver == current.version {
                return Err(RolePolicyError::ValidityInvalid);
            }
            let Some(role_spec) = policy.roles.get(role) else {
                return Err(RolePolicyError::DeniedByRole);
            };
            if !role_spec.allowed_tools.contains(tool_name) {
                return Err(RolePolicyError::DeniedByRole);
            }
            if let Some(constraints) = role_spec.argument_constraints.get(tool_name) {
                validate(constraints)?;
            }
        }

        // Apply any additional delegated argument constraints from the token.
        if let Some(extra_constraints) = token_constraints {
            validate(extra_constraints)?;
        }

        Ok(())
    }

    /// Return `(current_version, allowed_tools, active_role_spec)` intersected monotonically
    /// across every policy version activated since `issued_policy_version` and any token-level
    /// tool allow-list, reading only the in-memory snapshot (no file I/O).
    pub(crate) fn effective_allowed_tools(
        &self,
        tenant_id: &str,
        role: &str,
        issued_policy_version: u64,
        token_allowed_tools: Option<&[String]>,
    ) -> Result<(u64, HashSet<String>, RolePolicySpec), RolePolicyError> {
        validate_tenant_filename(tenant_id)?;
        self.ensure_tenant_allowed(tenant_id)?;
        self.require_trust_loaded()?;

        let map = self.tenants.read();
        let state = map.get(tenant_id).ok_or(RolePolicyError::ArtifactMissing)?;
        let current = state
            .snapshot
            .as_ref()
            .ok_or(RolePolicyError::ArtifactMissing)?
            .result
            .as_ref()
            .map_err(Clone::clone)?;
        if Utc::now() >= current.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
        }
        if issued_policy_version == 0
            || issued_policy_version > current.version
            || !state.history.contains_key(&issued_policy_version)
        {
            return Err(RolePolicyError::DeniedByRole);
        }
        let active_role = current
            .roles
            .get(role)
            .ok_or(RolePolicyError::DeniedByRole)?;
        let history: Option<Vec<_>> = state
            .history
            .range(issued_policy_version..=current.version)
            .map(|(_, policy)| policy.roles.get(role))
            .collect();
        let mut allowed_tools = HashSet::new();
        if let Some(history) = history {
            for tool in &active_role.allowed_tools {
                if token_allowed_tools.is_some_and(|allowed| !allowed.contains(tool))
                    || history
                        .iter()
                        .any(|spec| !spec.allowed_tools.contains(tool))
                {
                    continue;
                }
                allowed_tools.insert(tool.clone());
            }
        }
        Ok((current.version, allowed_tools, active_role.clone()))
    }

    fn verify_jws(
        &self,
        trust: &super::policy_trust::PolicyTrustSet,
        tenant_id: &str,
        jws: &str,
    ) -> Result<VerifiedRolePolicy, RolePolicyError> {
        let header = jws
            .split('.')
            .next()
            .filter(|_| jws.matches('.').count() == 2)
            .and_then(|seg| URL_SAFE_NO_PAD.decode(seg).ok())
            .and_then(|bytes| serde_json::from_slice::<Map<String, Value>>(&bytes).ok())
            .ok_or(RolePolicyError::Malformed)?;

        let param = |name: &str| header.get(name).and_then(Value::as_str);
        if header.len() != 3
            || ["alg", "typ", "kid"]
                .iter()
                .any(|k| !header.contains_key(*k))
        {
            return Err(RolePolicyError::HeaderParams);
        }
        if param("alg") != Some("EdDSA") {
            return Err(RolePolicyError::Algorithm);
        }
        if param("typ") != Some(ROLE_POLICY_ARTIFACT_TYP) {
            return Err(RolePolicyError::Type);
        }
        let kid = param("kid")
            .filter(|k| KID_FORMAT.is_match(k))
            .ok_or(RolePolicyError::KidFormat)?;
        let key = trust.key(kid).ok_or(RolePolicyError::UnknownKid)?;

        let mut validation = Validation::new(Algorithm::EdDSA);
        validation.validate_exp = false;
        validation.validate_aud = false;
        validation.required_spec_claims.clear();

        let claims: BTreeMap<String, Box<RawValue>> = jsonwebtoken::decode(jws, key, &validation)
            .map_err(|_| RolePolicyError::Signature)?
            .claims;

        let string_claim = |name: &str| {
            claims
                .get(name)
                .and_then(|raw| serde_json::from_str::<String>(raw.get()).ok())
        };
        if string_claim("iss").as_deref() != Some(self.issuer.as_str()) {
            return Err(RolePolicyError::Issuer);
        }
        if string_claim("aud").as_deref() != Some(self.audience.as_str()) {
            return Err(RolePolicyError::Audience);
        }
        if string_claim("tenant_id").as_deref() != Some(tenant_id) {
            return Err(RolePolicyError::TenantMismatch);
        }
        let tenant_uuid = string_claim("tenant_uuid")
            .and_then(|raw| Uuid::parse_str(&raw).ok())
            .ok_or(RolePolicyError::TenantMismatch)?;

        let version = claims
            .get("version")
            .and_then(|raw| serde_json::from_str::<u64>(raw.get()).ok())
            .filter(|&v| v > 0)
            .ok_or(RolePolicyError::Malformed)?;

        let issued_at = string_claim("issued_at")
            .and_then(|raw| DateTime::parse_from_rfc3339(&raw).ok())
            .map(|dt| dt.with_timezone(&Utc))
            .ok_or(RolePolicyError::ValidityInvalid)?;
        let expires_at = string_claim("expires_at")
            .and_then(|raw| DateTime::parse_from_rfc3339(&raw).ok())
            .map(|dt| dt.with_timezone(&Utc))
            .ok_or(RolePolicyError::ValidityInvalid)?;

        let now = Utc::now();
        let validity = (expires_at - issued_at)
            .to_std()
            .map_err(|_| RolePolicyError::ValidityInvalid)?;
        if validity.is_zero()
            || validity > MAX_ROLE_POLICY_VALIDITY
            || issued_at > now + chrono::Duration::seconds(MAX_CLOCK_SKEW_SECS)
            || expires_at <= now
        {
            return Err(RolePolicyError::ValidityInvalid);
        }

        let roles_raw = claims.get("roles").ok_or(RolePolicyError::Malformed)?;
        let roles: HashMap<String, RolePolicySpec> =
            serde_json::from_str(roles_raw.get()).map_err(|_| RolePolicyError::Malformed)?;

        let content_sha256 = compute_roles_digest(&roles)?;

        Ok(VerifiedRolePolicy {
            tenant_id: tenant_id.to_string(),
            tenant_uuid,
            version,
            issued_at,
            expires_at,
            content_sha256,
            roles,
        })
    }
}

fn newer_error_snapshot(
    state: &TenantPolicyState,
    start_generation: u64,
) -> Option<RolePolicyError> {
    match state.snapshot.as_ref() {
        Some(TenantSnapshot {
            result: Err(err),
            generation,
            ..
        }) if *generation > start_generation => Some(err.clone()),
        _ => None,
    }
}

fn file_fingerprint(path: &Path) -> Option<FileFingerprint> {
    let meta = fs::metadata(path).ok()?;
    if !meta.is_file() {
        return None;
    }
    let modified = meta.modified().ok()?;
    #[cfg(unix)]
    let (ino, ctime, ctime_nsec, mode) = {
        use std::os::unix::fs::MetadataExt;
        (meta.ino(), meta.ctime(), meta.ctime_nsec(), meta.mode())
    };
    #[cfg(not(unix))]
    let created = meta.created().ok();
    Some(FileFingerprint {
        modified,
        len: meta.len(),
        #[cfg(unix)]
        ino,
        #[cfg(unix)]
        ctime,
        #[cfg(unix)]
        ctime_nsec,
        #[cfg(unix)]
        mode,
        #[cfg(not(unix))]
        created,
    })
}

fn validate_tenant_filename(tenant_id: &str) -> Result<(), RolePolicyError> {
    if crate::telemetry::validated_tenant(Some(tenant_id)).is_none()
        || tenant_id.contains('/')
        || tenant_id.contains('\\')
        || tenant_id.contains("..")
    {
        return Err(RolePolicyError::InvalidTenant);
    }
    Ok(())
}

fn digest_serializable<T: Serialize>(value: &T) -> Result<String, RolePolicyError> {
    let bytes = serde_json::to_vec(value).map_err(|_| RolePolicyError::Malformed)?;
    let hash = Sha256::digest(&bytes);
    Ok(hash.iter().map(|b| format!("{b:02x}")).collect())
}

/// Deterministic SHA-256 digest of role rules (canonicalized key order).
fn compute_roles_digest(
    roles: &HashMap<String, RolePolicySpec>,
) -> Result<String, RolePolicyError> {
    let mut canonical: BTreeMap<&str, Value> = BTreeMap::new();
    for (role_name, spec) in roles {
        let mut tools: Vec<&String> = spec.allowed_tools.iter().collect();
        tools.sort();
        let mut tool_constraints: BTreeMap<&str, BTreeMap<&str, &ArgumentConstraint>> =
            BTreeMap::new();
        for (tool_name, arg_map) in &spec.argument_constraints {
            let mut sorted_args = BTreeMap::new();
            for (arg_name, c) in arg_map {
                if matches!(c, ArgumentConstraint::MaxNumber { max } if !max.is_finite()) {
                    return Err(RolePolicyError::Malformed);
                }
                sorted_args.insert(arg_name.as_str(), c);
            }
            tool_constraints.insert(tool_name.as_str(), sorted_args);
        }
        let mut entry = Map::new();
        entry.insert(
            "allowed_tools".to_string(),
            serde_json::to_value(&tools).map_err(|_| RolePolicyError::Malformed)?,
        );
        entry.insert(
            "argument_constraints".to_string(),
            serde_json::to_value(&tool_constraints).map_err(|_| RolePolicyError::Malformed)?,
        );
        canonical.insert(role_name.as_str(), Value::Object(entry));
    }
    digest_serializable(&canonical)
}

fn lock_floor(floor_dir: &Path, tenant_id: &str) -> Result<File, RolePolicyError> {
    fs::create_dir_all(floor_dir).map_err(|_| RolePolicyError::FloorPersistFailed)?;

    // The lock file stays in place while successive snapshots replace the JSON file.
    let mut options = OpenOptions::new();
    options.read(true).write(true).create(true).truncate(false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600).custom_flags(libc::O_NOFOLLOW);
    }
    let file = options
        .open(floor_dir.join(format!("{tenant_id}.floor.lock")))
        .map_err(|_| RolePolicyError::FloorPersistFailed)?;
    if !file
        .metadata()
        .map_err(|_| RolePolicyError::FloorPersistFailed)?
        .is_file()
    {
        return Err(RolePolicyError::FloorPersistFailed);
    }
    file.lock()
        .map_err(|_| RolePolicyError::FloorPersistFailed)?;
    Ok(file)
}

fn read_persisted_floor(path: &Path) -> Result<Option<PersistedVersionFloor>, RolePolicyError> {
    match fs::read_to_string(path) {
        Ok(raw) => {
            let parsed: PersistedVersionFloor = serde_json::from_str(&raw).map_err(|_| {
                warn!(path = %path.display(), "Persisted role policy floor corrupted");
                RolePolicyError::FloorCorrupted
            })?;
            if parsed.version == 0 || parsed.content_sha256.len() != 64 {
                return Err(RolePolicyError::FloorCorrupted);
            }
            Ok(Some(parsed))
        }
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(_) => Err(RolePolicyError::FloorCorrupted),
    }
}

fn persist_floor_atomic_0600(
    floor_dir: &Path,
    target_path: &Path,
    floor: &PersistedVersionFloor,
) -> Result<(), RolePolicyError> {
    let tmp_path = stage_floor(floor_dir, floor)?;
    fs::rename(&tmp_path, target_path).map_err(|_| {
        let _ = fs::remove_file(&tmp_path);
        RolePolicyError::FloorPersistFailed
    })
}

fn stage_floor(
    floor_dir: &Path,
    floor: &PersistedVersionFloor,
) -> Result<PathBuf, RolePolicyError> {
    let tmp_path = floor_dir.join(format!(".floor-{}.tmp", Uuid::new_v4()));
    let serialized = serde_json::to_vec(floor).map_err(|_| RolePolicyError::FloorPersistFailed)?;

    let mut opts = OpenOptions::new();
    opts.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        opts.mode(0o600);
    }

    let mut file = opts
        .open(&tmp_path)
        .map_err(|_| RolePolicyError::FloorPersistFailed)?;
    let result = file.write_all(&serialized).and_then(|()| {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(fs::Permissions::from_mode(0o600))?;
        }
        file.sync_all()
    });
    drop(file);
    if result.is_err() {
        let _ = fs::remove_file(&tmp_path);
        return Err(RolePolicyError::FloorPersistFailed);
    }
    Ok(tmp_path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use aws_lc_rs::signature::{Ed25519KeyPair, KeyPair as _};
    use serde_json::json;

    struct RoleSigner {
        kp: Ed25519KeyPair,
        kid: String,
        tenant_uuid: Uuid,
    }

    impl RoleSigner {
        fn new() -> Self {
            let pkcs8 =
                Ed25519KeyPair::generate_pkcs8(&aws_lc_rs::rand::SystemRandom::new()).unwrap();
            let kp = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
            Self {
                kp,
                kid: "cp-policy-202611-1".to_string(),
                tenant_uuid: Uuid::new_v4(),
            }
        }

        fn trust_jwks(&self) -> String {
            let x = URL_SAFE_NO_PAD.encode(self.kp.public_key().as_ref());
            serde_json::to_string(&json!({
                "keys": [{
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "alg": "EdDSA",
                    "use": "sig",
                    "kid": self.kid,
                    "x": x
                }]
            }))
            .unwrap()
        }

        fn sign(&self, tenant: &str, version: u64, ttl_secs: i64, roles: Value) -> String {
            let now = Utc::now();
            let header = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "alg": "EdDSA",
                    "typ": ROLE_POLICY_ARTIFACT_TYP,
                    "kid": self.kid
                }))
                .unwrap(),
            );
            let payload = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "iss": "stoa-poc-policy",
                    "aud": "stoa-gateway",
                    "tenant_id": tenant,
                    "tenant_uuid": self.tenant_uuid.to_string(),
                    "version": version,
                    "issued_at": now.to_rfc3339(),
                    "expires_at": (now + chrono::Duration::seconds(ttl_secs)).to_rfc3339(),
                    "roles": roles
                }))
                .unwrap(),
            );
            let input = format!("{header}.{payload}");
            let sig = self.kp.sign(input.as_bytes());
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        }

        fn sign_raw_roles(
            &self,
            tenant: &str,
            version: u64,
            ttl_secs: i64,
            roles_json: &str,
        ) -> String {
            let now = Utc::now();
            let header = URL_SAFE_NO_PAD.encode(
                serde_json::to_vec(&json!({
                    "alg": "EdDSA",
                    "typ": ROLE_POLICY_ARTIFACT_TYP,
                    "kid": self.kid
                }))
                .unwrap(),
            );
            let payload_json = format!(
                r#"{{"iss":"stoa-poc-policy","aud":"stoa-gateway","tenant_id":{tenant},"tenant_uuid":{tenant_uuid},"version":{version},"issued_at":{issued_at},"expires_at":{expires_at},"roles":{roles_json}}}"#,
                tenant = serde_json::to_string(tenant).unwrap(),
                tenant_uuid = serde_json::to_string(&self.tenant_uuid.to_string()).unwrap(),
                issued_at = serde_json::to_string(&now.to_rfc3339()).unwrap(),
                expires_at = serde_json::to_string(
                    &(now + chrono::Duration::seconds(ttl_secs)).to_rfc3339()
                )
                .unwrap(),
            );
            let payload = URL_SAFE_NO_PAD.encode(payload_json.as_bytes());
            let input = format!("{header}.{payload}");
            let sig = self.kp.sign(input.as_bytes());
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        }
    }

    #[test]
    fn argument_constraints_v1_and_delegation_subset_rules() {
        let allow = ArgumentConstraint::AllowedValues {
            values: vec![json!("EUR"), json!("USD")],
        };
        assert!(allow.matches(Some(&json!("EUR"))));
        assert!(!allow.matches(Some(&json!("BTC"))));
        assert!(!allow.matches(None));

        let allow_narrow = ArgumentConstraint::AllowedValues {
            values: vec![json!("EUR")],
        };
        let allow_wide = ArgumentConstraint::AllowedValues {
            values: vec![json!("EUR"), json!("GBP")],
        };
        assert!(allow_narrow.is_subset_of(&allow));
        assert!(!allow_wide.is_subset_of(&allow));

        let pfx = ArgumentConstraint::Prefix {
            prefix: "acct-".to_string(),
        };
        assert!(pfx.matches(Some(&json!("acct-42"))));
        assert!(!pfx.matches(Some(&json!("other-42"))));
        assert!(!pfx.matches(Some(&json!(123))));
        assert!(ArgumentConstraint::Prefix {
            prefix: "acct-eu-".to_string()
        }
        .is_subset_of(&pfx));
        assert!(!ArgumentConstraint::Prefix {
            prefix: "ac".to_string()
        }
        .is_subset_of(&pfx));

        let cap = ArgumentConstraint::MaxNumber { max: 100.0 };
        assert!(cap.matches(Some(&json!(100))));
        assert!(cap.matches(Some(&json!(42.5))));
        assert!(!cap.matches(Some(&json!(100.01))));
        assert!(!cap.matches(Some(&json!("50"))));
        assert!(ArgumentConstraint::MaxNumber { max: 50.0 }.is_subset_of(&cap));
        assert!(!ArgumentConstraint::MaxNumber { max: 150.0 }.is_subset_of(&cap));
    }

    #[test]
    fn anti_rollback_persisted_0600_and_15_minute_max_validity() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        let roles_v2 = json!({
            "reader": {
                "allowed_tools": ["payments_list"],
                "argument_constraints": {
                    "payments_list": {
                        "currency": { "type": "allowed_values", "values": ["EUR"] },
                        "account": { "type": "prefix", "prefix": "acct-" },
                        "limit": { "type": "max_number", "max": 50.0 }
                    }
                }
            }
        });

        // Validity > 15 min (901s) is rejected BEFORE persisting floor.
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign("acme", 2, 901, roles_v2.clone()),
        )
        .unwrap();
        assert_eq!(
            store.reload_tenant("acme").unwrap_err(),
            RolePolicyError::ValidityInvalid
        );
        assert!(!floor_dir.join("acme.floor.json").exists());

        // Valid 10-min v2 loads and persists floor with 0600 permissions.
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign("acme", 2, 600, roles_v2.clone()),
        )
        .unwrap();
        let loaded = store.reload_tenant("acme").expect("v2 loads");
        assert_eq!(loaded.version, 2);
        let floor_file = floor_dir.join("acme.floor.json");
        assert!(floor_file.exists());
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = fs::metadata(&floor_file).unwrap().permissions().mode() & 0o777;
            assert_eq!(mode, 0o600);
        }

        // Same version with different content is rejected.
        let altered_v2 = json!({
            "reader": { "allowed_tools": ["payments_list", "payments_delete"] }
        });
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign("acme", 2, 600, altered_v2),
        )
        .unwrap();
        assert_eq!(
            store.reload_tenant("acme").unwrap_err(),
            RolePolicyError::VersionRollback
        );

        // Fresh store instance (simulating restart) STILL rejects rollback to v1!
        let restarted_store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign("acme", 1, 600, roles_v2),
        )
        .unwrap();
        assert_eq!(
            restarted_store.reload_tenant("acme").unwrap_err(),
            RolePolicyError::VersionRollback
        );

        // Corrupted floor file fails closed.
        fs::write(&floor_file, "{not-valid-json").unwrap();
        assert_eq!(
            restarted_store.reload_tenant("acme").unwrap_err(),
            RolePolicyError::FloorCorrupted
        );
    }

    #[test]
    fn parallel_role_activations_keep_the_latest_version() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let trust = PolicyTrustStore::open(&trust_path);
        let floor_dir = tmp.path().join("floors");
        let store = RolePolicyStore::new(
            tmp.path(),
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(trust.clone()),
        );
        let trust = trust.current().unwrap();
        let barrier = std::sync::Barrier::new(16);
        let roles = json!({"reader": {"allowed_tools": ["payments_list"]}});
        std::thread::scope(|scope| {
            let tasks: Vec<_> = (1..=16)
                .map(|version| {
                    let policy = store
                        .verify_jws(
                            &trust,
                            "acme",
                            &signer.sign("acme", version, 60, roles.clone()),
                        )
                        .unwrap();
                    let barrier = &barrier;
                    let store = &store;
                    scope.spawn(move || {
                        barrier.wait();
                        store.activate_verified_policy("acme", policy)
                    })
                })
                .collect();
            for task in tasks {
                assert!(matches!(
                    task.join().unwrap(),
                    Ok(_) | Err(RolePolicyError::VersionRollback)
                ));
            }
        });
        assert_eq!(store.tenants.read()["acme"].current_version, 16);
        let floor = read_persisted_floor(&floor_dir.join("acme.floor.json"))
            .unwrap()
            .unwrap();
        assert_eq!(floor.version, 16);
    }

    fn process_floor_fixture() -> tempfile::TempDir {
        let root = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        fs::write(root.path().join("trust.json"), signer.trust_jwks()).unwrap();
        for version in [1, 2] {
            let artifacts = root.path().join(format!("v{version}"));
            fs::create_dir(&artifacts).unwrap();
            let roles = json!({"reader": {"allowed_tools": ["payments_list"]}});
            fs::write(
                artifacts.join("acme.roles.jws"),
                signer.sign("acme", version, 120, roles),
            )
            .unwrap();
        }
        root
    }

    fn fixture_floor_store(root: &Path, version: &str) -> RolePolicyStore {
        RolePolicyStore::new(
            root.join(version),
            root.join("floors"),
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(root.join("trust.json"))),
        )
    }

    fn wait_for_test_marker(path: &Path) {
        let deadline = std::time::Instant::now() + Duration::from_secs(10);
        while !path.is_file() {
            assert!(std::time::Instant::now() < deadline, "missing {path:?}");
            std::thread::sleep(Duration::from_millis(10));
        }
    }

    struct FloorWorker(std::process::Child);

    impl FloorWorker {
        fn start(root: &Path, mode: &str) -> Self {
            Self(
                std::process::Command::new(std::env::current_exe().unwrap())
                    .args([
                        "--exact",
                        "control_plane::role_policy::tests::role_floor_worker_process",
                    ])
                    .env("STOA_TEST_FLOOR_ROOT", root)
                    .env("STOA_TEST_FLOOR_MODE", mode)
                    .stdout(std::process::Stdio::null())
                    .spawn()
                    .unwrap(),
            )
        }

        fn wait(&mut self) -> std::process::ExitStatus {
            let deadline = std::time::Instant::now() + Duration::from_secs(10);
            loop {
                if let Some(status) = self.0.try_wait().unwrap() {
                    return status;
                }
                assert!(
                    std::time::Instant::now() < deadline,
                    "floor worker did not exit"
                );
                std::thread::sleep(Duration::from_millis(10));
            }
        }
    }

    impl Drop for FloorWorker {
        fn drop(&mut self) {
            if matches!(self.0.try_wait(), Ok(None)) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
    }

    #[test]
    fn role_floor_worker_process() {
        let Some(root) = std::env::var_os("STOA_TEST_FLOOR_ROOT") else {
            return;
        };
        let root = PathBuf::from(root);
        let mode = std::env::var("STOA_TEST_FLOOR_MODE").unwrap();
        if mode == "stage" {
            let floor_dir = root.join("floors");
            let _guard = lock_floor(&floor_dir, "acme").unwrap();
            let mut next = read_persisted_floor(&floor_dir.join("acme.floor.json"))
                .unwrap()
                .unwrap();
            next.version = 2;
            let staged = stage_floor(&floor_dir, &next).unwrap();
            fs::write(
                root.join("staged.tmp"),
                staged.file_name().unwrap().as_encoded_bytes(),
            )
            .unwrap();
            fs::rename(root.join("staged.tmp"), root.join("staged")).unwrap();
            std::thread::sleep(Duration::from_secs(15));
            panic!("floor worker was not interrupted");
        }

        let store = fixture_floor_store(&root, &mode);
        fs::write(root.join(format!("{mode}.ready")), "").unwrap();
        wait_for_test_marker(&root.join("start"));
        let result = store.reload_tenant("acme");
        match mode.as_str() {
            "v1" => assert!(matches!(
                result,
                Ok(VerifiedRolePolicy { version: 1, .. }) | Err(RolePolicyError::VersionRollback)
            )),
            "v2" => assert_eq!(result.unwrap().version, 2),
            _ => panic!("unexpected floor worker mode"),
        }
    }

    #[test]
    fn role_floor_is_monotone_across_writer_processes() {
        let fixture = process_floor_fixture();
        let root = fixture.path();
        let mut older = FloorWorker::start(root, "v1");
        let mut newer = FloorWorker::start(root, "v2");
        wait_for_test_marker(&root.join("v1.ready"));
        wait_for_test_marker(&root.join("v2.ready"));
        fs::write(root.join("start"), "").unwrap();
        assert!(older.wait().success());
        assert!(newer.wait().success());
        let floor = read_persisted_floor(&root.join("floors/acme.floor.json"))
            .unwrap()
            .unwrap();
        assert_eq!(floor.version, 2);
        assert_eq!(
            fixture_floor_store(root, "v1")
                .reload_tenant("acme")
                .unwrap_err(),
            RolePolicyError::VersionRollback
        );
    }

    #[test]
    fn role_floor_remains_active_after_interrupted_write() {
        let fixture = process_floor_fixture();
        let root = fixture.path();
        assert_eq!(
            fixture_floor_store(root, "v1")
                .reload_tenant("acme")
                .unwrap()
                .version,
            1
        );
        let floor_dir = root.join("floors");
        let floor_path = floor_dir.join("acme.floor.json");
        let mut interrupted = FloorWorker::start(root, "stage");
        let marker = root.join("staged");
        wait_for_test_marker(&marker);

        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .open(floor_dir.join("acme.floor.lock"))
            .unwrap();
        assert!(matches!(lock.try_lock(), Err(fs::TryLockError::WouldBlock)));
        let staged = floor_dir.join(fs::read_to_string(marker).unwrap());
        assert_eq!(read_persisted_floor(&staged).unwrap().unwrap().version, 2);
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            1
        );

        interrupted.0.kill().unwrap();
        assert!(!interrupted.wait().success());
        lock.try_lock().unwrap();
        drop(lock);
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            1
        );

        fs::write(root.join("start"), "").unwrap();
        let mut resumed = FloorWorker::start(root, "v2");
        assert!(resumed.wait().success());
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            2
        );
    }

    #[test]
    fn role_floor_unreadable_state_prevents_activation() {
        let fixture = process_floor_fixture();
        let root = fixture.path();
        let store = fixture_floor_store(root, "v1");
        assert_eq!(store.reload_tenant("acme").unwrap().version, 1);

        let floor_path = root.join("floors/acme.floor.json");
        let floor_bytes = fs::read(&floor_path).unwrap();
        fs::remove_file(&floor_path).unwrap();
        fs::create_dir(&floor_path).unwrap();
        fs::copy(
            root.join("v2/acme.roles.jws"),
            root.join("v1/acme.roles.jws"),
        )
        .unwrap();
        assert_eq!(
            store.reload_tenant("acme").unwrap_err(),
            RolePolicyError::FloorCorrupted
        );
        assert_eq!(store.tenants.read()["acme"].current_version, 1);
        fs::remove_dir(&floor_path).unwrap();
        fs::write(&floor_path, floor_bytes).unwrap();
        assert_eq!(store.reload_tenant("acme").unwrap().version, 2);
    }

    #[test]
    fn session_reduction_applies_on_next_call_and_widening_or_restore_refused_under_same_token() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        // v1 allows payments_list only.
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                1,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        )
        .unwrap();
        store.reload_tenant("acme").unwrap();
        let (v1, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert_eq!(v1, 1);
        let eval = |tool: &str, ver: u64| {
            store.evaluate_call(&RoleEvalInput {
                tenant_id: "acme",
                role: "reader",
                tool_name: tool,
                args: &json!({}),
                issued_policy_version: ver,
                token_allowed_tools: None,
                token_constraints: None,
            })
        };
        assert!(eval("payments_list", v1).is_ok());

        // v2 widens role to add payments_export -> token issued at v1 is STILL denied!
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                2,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list", "payments_export"] } }),
            ),
        )
        .unwrap();
        store.reload_tenant("acme").unwrap();
        assert_eq!(
            eval("payments_export", v1).unwrap_err(),
            RolePolicyError::DeniedByRole
        );

        // New token issued at v2 CAN call payments_export.
        let (v2, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert!(eval("payments_export", v2).is_ok());

        // v3 withdraws payments_export -> denied on next call for v2 token!
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                3,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        )
        .unwrap();
        store.reload_tenant("acme").unwrap();
        assert_eq!(
            eval("payments_export", v2).unwrap_err(),
            RolePolicyError::DeniedByRole
        );

        // v4 restores payments_export -> v2 token STILL denied (withdrawal occurred during session),
        // while a freshly issued v4 token is allowed!
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                4,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list", "payments_export"] } }),
            ),
        )
        .unwrap();
        store.reload_tenant("acme").unwrap();
        assert_eq!(
            eval("payments_export", v2).unwrap_err(),
            RolePolicyError::DeniedByRole
        );
        let (v4, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert!(eval("payments_export", v4).is_ok());
    }

    #[test]
    fn max_number_exact_domain_and_literal_lexemes() {
        // Exact bounds accepted.
        let safe_max: ArgumentConstraint =
            serde_json::from_str(r#"{"type":"max_number","max":9007199254740992}"#).unwrap();
        assert_eq!(
            safe_max,
            ArgumentConstraint::MaxNumber {
                max: 9_007_199_254_740_992.0
            }
        );

        let decimal: ArgumentConstraint =
            serde_json::from_str(r#"{"type":"max_number","max":50.01}"#).unwrap();
        let scientific: ArgumentConstraint =
            serde_json::from_str(r#"{"type":"max_number","max":5001e-2}"#).unwrap();
        let trailing: ArgumentConstraint =
            serde_json::from_str(r#"{"type":"max_number","max":50.0100}"#).unwrap();
        assert_eq!(decimal, ArgumentConstraint::MaxNumber { max: 50.01 });
        assert_eq!(scientific, decimal);
        assert_eq!(trailing, decimal);

        let negative: ArgumentConstraint =
            serde_json::from_str(r#"{"type":"max_number","max":-50.01}"#).unwrap();
        assert_eq!(negative, ArgumentConstraint::MaxNumber { max: -50.01 });
        assert!(serde_json::from_str::<ArgumentConstraint>(
            r#"{"type":"max_number","max":-9007199254740992}"#
        )
        .is_ok());
        assert!(
            serde_json::from_str::<ArgumentConstraint>(r#"{"type":"max_number","max":0}"#).is_ok()
        );
        assert!(
            serde_json::from_str::<ArgumentConstraint>(r#"{"type":"max_number","max":-0.0}"#)
                .is_ok()
        );

        // Imprecise, underflowing, or malformed bounds rejected at decode time.
        for bad in [
            r#"{"type":"max_number","max":9007199254740993}"#,
            r#"{"type":"max_number","max":-9007199254740993}"#,
            r#"{"type":"max_number","max":50.0100000000000000001}"#,
            r#"{"type":"max_number","max":-50.0100000000000000001}"#,
            r#"{"type":"max_number","max":1e-400}"#,
            r#"{"type":"max_number","max":1e-325}"#,
            r#"{"type":"max_number","max":-1e-400}"#,
            r#"{"type":"max_number","max":"50.01"}"#,
            r#"{"type":"max_number"}"#,
            r#"{"type":"prefix"}"#,
            r#"{"type":"allowed_values"}"#,
        ] {
            assert!(
                serde_json::from_str::<ArgumentConstraint>(bad).is_err(),
                "expected decode rejection for {bad}"
            );
        }

        // Historical variants still decode normally.
        assert_eq!(
            serde_json::from_str::<ArgumentConstraint>(
                r#"{"type":"allowed_values","values":["EUR","USD"]}"#
            )
            .unwrap(),
            ArgumentConstraint::AllowedValues {
                values: vec![json!("EUR"), json!("USD")]
            }
        );
        assert_eq!(
            serde_json::from_str::<ArgumentConstraint>(r#"{"type":"prefix","prefix":"acct-"}"#)
                .unwrap(),
            ArgumentConstraint::Prefix {
                prefix: "acct-".to_string()
            }
        );

        // Internal Values > 2^53 and imprecise raw lexemes are rejected.
        assert!(safe_max.matches(Some(&json!(9_007_199_254_740_992_u64))));
        assert!(!safe_max.matches(Some(&json!(9_007_199_254_740_993_u64))));
        assert!(safe_max.matches_with_raw(
            Some(&json!(9_007_199_254_740_992_u64)),
            Some("9007199254740992")
        ));
        assert!(!safe_max.matches_with_raw(
            Some(&json!(9_007_199_254_740_992_u64)),
            Some("9007199254740993")
        ));

        assert!(decimal.matches_with_raw(Some(&json!(50.01)), Some("50.01")));
        assert!(decimal.matches_with_raw(Some(&json!(50.01)), Some("5001e-2")));
        assert!(decimal.matches_with_raw(Some(&json!(50.01)), Some("50.0100")));
        assert!(decimal.matches_with_raw(Some(&json!(-50.01)), Some("-50.01")));
        assert!(!decimal.matches_with_raw(Some(&json!(50.01)), Some("50.0100000000000000001")));
        assert!(!decimal.matches_with_raw(Some(&json!(-50.01)), Some("-50.0100000000000000001")));
        assert!(!decimal.matches_with_raw(Some(&json!(0.0)), Some("1e-400")));
        assert!(!decimal.matches_with_raw(Some(&json!(50.01)), None));
        assert!(!decimal.matches_with_raw(Some(&json!(10.0)), Some("50.01")));

        // Positive underflow must never round down to 0.0 and satisfy max = 0.0.
        let zero_cap = ArgumentConstraint::MaxNumber { max: 0.0 };
        assert!(zero_cap.matches_with_raw(Some(&json!(0)), Some("0")));
        assert!(zero_cap.matches_with_raw(Some(&json!(0.0)), Some("-0.0")));
        assert!(!zero_cap.matches_with_raw(Some(&json!(0.0)), Some("1e-400")));
    }

    #[test]
    fn signed_role_policy_rejects_imprecise_max_number_and_enforces_historical_and_token_lexemes() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        let v1_roles = r#"{
            "reader": {
                "allowed_tools": ["refund_create"],
                "argument_constraints": {
                    "refund_create": {
                        "amount": { "type": "max_number", "max": 50.01 }
                    }
                }
            }
        }"#;
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign_raw_roles("acme", 1, 600, v1_roles),
        )
        .unwrap();
        let loaded_v1 = store.reload_tenant("acme").expect("conforming v1 loads");
        assert_eq!(loaded_v1.version, 1);
        assert_eq!(
            loaded_v1.content_sha256,
            compute_roles_digest(&loaded_v1.roles).unwrap()
        );
        let floor_path = floor_dir.join("acme.floor.json");
        let floor_v1 = read_persisted_floor(&floor_path).unwrap().unwrap();
        assert_eq!(floor_v1.version, 1);
        assert_eq!(floor_v1.content_sha256, loaded_v1.content_sha256);

        // Equivalent decimal spelling produces the exact same digest and activates against the existing floor.
        let v1_equiv = r#"{
            "reader": {
                "allowed_tools": ["refund_create"],
                "argument_constraints": {
                    "refund_create": {
                        "amount": { "type": "max_number", "max": 5001e-2 }
                    }
                }
            }
        }"#;
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign_raw_roles("acme", 1, 600, v1_equiv),
        )
        .unwrap();
        let reloaded_v1 = store
            .reload_tenant("acme")
            .expect("equivalent v1 matches existing floor digest");
        assert_eq!(reloaded_v1.content_sha256, loaded_v1.content_sha256);

        // Signed role artifacts with non-representable max_number bounds are rejected without advancing floor.
        for bad_max in ["50.0100000000000000001", "9007199254740993", "1e-400"] {
            let bad_roles = format!(
                r#"{{
                    "reader": {{
                        "allowed_tools": ["refund_create"],
                        "argument_constraints": {{
                            "refund_create": {{
                                "amount": {{ "type": "max_number", "max": {bad_max} }}
                            }}
                        }}
                    }}
                }}"#
            );
            fs::write(
                artifacts_dir.join("acme.roles.jws"),
                signer.sign_raw_roles("acme", 2, 600, &bad_roles),
            )
            .unwrap();
            assert_eq!(
                store.reload_tenant("acme").unwrap_err(),
                RolePolicyError::Malformed,
                "expected Malformed for signed max {bad_max}"
            );
            assert_eq!(
                read_persisted_floor(&floor_path).unwrap().unwrap().version,
                1
            );
        }

        // Activate v2 without the amount cap; a token issued at v1 must STILL enforce the
        // historical v1 max_number lexeme check while ignoring unbounded numeric arguments.
        let v2_roles = r#"{
            "reader": {
                "allowed_tools": ["refund_create"],
                "argument_constraints": {}
            }
        }"#;
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign_raw_roles("acme", 2, 600, v2_roles),
        )
        .unwrap();
        assert_eq!(store.reload_tenant("acme").unwrap().version, 2);

        let ok_raw = HashMap::from([
            ("amount".to_string(), "5001e-2".to_string()),
            ("unbounded_id".to_string(), "9007199254740993".to_string()),
        ]);
        assert!(store
            .evaluate_call_with_raw(
                &RoleEvalInput {
                    tenant_id: "acme",
                    role: "reader",
                    tool_name: "refund_create",
                    args: &json!({"amount": 50.01, "unbounded_id": 9_007_199_254_740_993_u64}),
                    issued_policy_version: 1,
                    token_allowed_tools: None,
                    token_constraints: None,
                },
                &ok_raw,
            )
            .is_ok());

        let bad_raw = HashMap::from([("amount".to_string(), "50.0100000000000000001".to_string())]);
        assert_eq!(
            store
                .evaluate_call_with_raw(
                    &RoleEvalInput {
                        tenant_id: "acme",
                        role: "reader",
                        tool_name: "refund_create",
                        args: &json!({"amount": 50.01}),
                        issued_policy_version: 1,
                        token_allowed_tools: None,
                        token_constraints: None,
                    },
                    &bad_raw,
                )
                .unwrap_err(),
            RolePolicyError::DeniedByConstraint
        );

        // Missing raw lexeme in wire mode fails closed instead of reconstructing from Value.
        let empty_raw = HashMap::new();
        assert_eq!(
            store
                .evaluate_call_with_raw(
                    &RoleEvalInput {
                        tenant_id: "acme",
                        role: "reader",
                        tool_name: "refund_create",
                        args: &json!({"amount": 50.01}),
                        issued_policy_version: 1,
                        token_allowed_tools: None,
                        token_constraints: None,
                    },
                    &empty_raw,
                )
                .unwrap_err(),
            RolePolicyError::DeniedByConstraint
        );

        // Mismatch between Value f64 and raw lexeme f64 also fails closed.
        let mismatched_raw = HashMap::from([("amount".to_string(), "50.01".to_string())]);
        assert_eq!(
            store
                .evaluate_call_with_raw(
                    &RoleEvalInput {
                        tenant_id: "acme",
                        role: "reader",
                        tool_name: "refund_create",
                        args: &json!({"amount": 10.0}),
                        issued_policy_version: 1,
                        token_allowed_tools: None,
                        token_constraints: None,
                    },
                    &mismatched_raw,
                )
                .unwrap_err(),
            RolePolicyError::DeniedByConstraint
        );

        // Token-carried delegated ceiling also enforces raw lexeme precision on v2 tokens.
        let token_caps = HashMap::from([(
            "amount".to_string(),
            ArgumentConstraint::MaxNumber { max: 25.0 },
        )]);
        let tok_ok_raw = HashMap::from([("amount".to_string(), "2500e-2".to_string())]);
        assert!(store
            .evaluate_call_with_raw(
                &RoleEvalInput {
                    tenant_id: "acme",
                    role: "reader",
                    tool_name: "refund_create",
                    args: &json!({"amount": 25.0}),
                    issued_policy_version: 2,
                    token_allowed_tools: None,
                    token_constraints: Some(&token_caps),
                },
                &tok_ok_raw,
            )
            .is_ok());
        let tok_bad_raw =
            HashMap::from([("amount".to_string(), "25.000000000000000001".to_string())]);
        assert_eq!(
            store
                .evaluate_call_with_raw(
                    &RoleEvalInput {
                        tenant_id: "acme",
                        role: "reader",
                        tool_name: "refund_create",
                        args: &json!({"amount": 25.0}),
                        issued_policy_version: 2,
                        token_allowed_tools: None,
                        token_constraints: Some(&token_caps),
                    },
                    &tok_bad_raw,
                )
                .unwrap_err(),
            RolePolicyError::DeniedByConstraint
        );
    }

    fn replace_file_atomic(target: &Path, content: &str) {
        let tmp_path = target.with_extension(format!("tmp-{}", Uuid::new_v4()));
        fs::write(&tmp_path, content).unwrap();
        fs::rename(&tmp_path, target).unwrap();
    }

    #[tokio::test]
    async fn reduction_takes_effect_on_next_call_without_sleep() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let role_path = artifacts_dir.join("acme.roles.jws");
        fs::write(
            &role_path,
            signer.sign(
                "acme",
                1,
                600,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list", "payments_export"],
                        "argument_constraints": {
                            "payments_list": {
                                "limit": { "type": "max_number", "max": 100.0 }
                            }
                        }
                    }
                }),
            ),
        )
        .unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.reload_count(), 1);
        let (v1, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert_eq!(v1, 1);

        let eval = |tool: &str, args: &Value| {
            store.evaluate_call(&RoleEvalInput {
                tenant_id: "acme",
                role: "reader",
                tool_name: tool,
                args,
                issued_policy_version: v1,
                token_allowed_tools: None,
                token_constraints: None,
            })
        };
        assert!(eval("payments_export", &json!({})).is_ok());
        assert!(eval("payments_list", &json!({"limit": 80})).is_ok());

        // Overwrite with v2 removing payments_export (no sleep): refused on the very next call.
        replace_file_atomic(
            &role_path,
            &signer.sign(
                "acme",
                2,
                600,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list"],
                        "argument_constraints": {
                            "payments_list": {
                                "limit": { "type": "max_number", "max": 100.0 }
                            }
                        }
                    }
                }),
            ),
        );
        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.reload_count(), 2);
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 2);
        assert_eq!(
            eval("payments_export", &json!({})).unwrap_err(),
            RolePolicyError::DeniedByRole
        );
        let (_, effective_tools, _) = store
            .effective_allowed_tools("acme", "reader", v1, None)
            .unwrap();
        assert!(!effective_tools.contains("payments_export"));
        assert!(effective_tools.contains("payments_list"));
        assert!(eval("payments_list", &json!({"limit": 80})).is_ok());

        // Overwrite with v3 tightening the limit constraint (no sleep): refused on the very next call.
        replace_file_atomic(
            &role_path,
            &signer.sign(
                "acme",
                3,
                600,
                json!({
                    "reader": {
                        "allowed_tools": ["payments_list"],
                        "argument_constraints": {
                            "payments_list": {
                                "limit": { "type": "max_number", "max": 25.0 }
                            }
                        }
                    }
                }),
            ),
        );
        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.reload_count(), 3);
        assert_eq!(
            eval("payments_list", &json!({"limit": 80})).unwrap_err(),
            RolePolicyError::DeniedByConstraint
        );
        assert!(eval("payments_list", &json!({"limit": 20})).is_ok());
    }

    #[tokio::test]
    async fn unchanged_policy_file_reuses_snapshot_without_reload() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                1,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        )
        .unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.reload_count(), 1);

        for _ in 0..10 {
            store.refresh_tenant("acme").await.unwrap();
        }
        assert_eq!(store.reload_count(), 1);
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 1);
    }

    #[tokio::test]
    async fn snapshot_refresh_refuses_rollback_fails_closed_and_keeps_floor() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let role_path = artifacts_dir.join("acme.roles.jws");
        fs::write(
            &role_path,
            signer.sign(
                "acme",
                2,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list", "payments_export"] } }),
            ),
        )
        .unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.reload_count(), 1);
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 2);
        let floor_path = floor_dir.join("acme.floor.json");
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            2
        );

        // Immediately write rollback v1 (no sleep): fails closed on the very next call.
        replace_file_atomic(
            &role_path,
            &signer.sign(
                "acme",
                1,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        );

        assert_eq!(
            store.refresh_tenant("acme").await.unwrap_err(),
            RolePolicyError::VersionRollback
        );
        assert_eq!(store.reload_count(), 2);

        // All sync evaluators fail closed with VersionRollback.
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::VersionRollback
        );
        assert_eq!(
            store
                .evaluate_call(&RoleEvalInput {
                    tenant_id: "acme",
                    role: "reader",
                    tool_name: "payments_list",
                    args: &json!({}),
                    issued_policy_version: 2,
                    token_allowed_tools: None,
                    token_constraints: None,
                })
                .unwrap_err(),
            RolePolicyError::VersionRollback
        );
        assert_eq!(
            store
                .effective_allowed_tools("acme", "reader", 2, None)
                .unwrap_err(),
            RolePolicyError::VersionRollback
        );

        // Neither the persisted floor nor the in-memory version floor is lowered.
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            2
        );
        assert_eq!(store.tenants.read()["acme"].current_version, 2);
    }

    #[tokio::test]
    async fn stat_or_read_error_fails_closed_immediately() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let role_path = artifacts_dir.join("acme.roles.jws");
        let v1_jws = signer.sign(
            "acme",
            1,
            600,
            json!({ "reader": { "allowed_tools": ["payments_list"] } }),
        );
        fs::write(&role_path, &v1_jws).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 1);

        // Deleting the artifact causes stat to fail and immediately puts the tenant fail-closed.
        fs::remove_file(&role_path).unwrap();
        assert_eq!(
            store.refresh_tenant("acme").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store
                .evaluate_call(&RoleEvalInput {
                    tenant_id: "acme",
                    role: "reader",
                    tool_name: "payments_list",
                    args: &json!({}),
                    issued_policy_version: 1,
                    token_allowed_tools: None,
                    token_constraints: None,
                })
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store
                .effective_allowed_tools("acme", "reader", 1, None)
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );

        // Replacing the artifact path with a directory (unreadable as a file) stays fail-closed.
        fs::create_dir(&role_path).unwrap();
        assert_eq!(
            store.refresh_tenant("acme").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );

        // Restoring the signed artifact recovers cleanly.
        fs::remove_dir(&role_path).unwrap();
        fs::write(&role_path, &v1_jws).unwrap();
        store.refresh_tenant("acme").await.unwrap();
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 1);
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn concurrent_refreshes_coalesce_to_single_load() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();
        fs::write(
            artifacts_dir.join("acme.roles.jws"),
            signer.sign(
                "acme",
                1,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        )
        .unwrap();

        let store = Arc::new(RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        ));

        let barrier = Arc::new(tokio::sync::Barrier::new(32));
        let mut handles = Vec::with_capacity(32);
        for _ in 0..32 {
            let store = Arc::clone(&store);
            let barrier = Arc::clone(&barrier);
            handles.push(tokio::spawn(async move {
                barrier.wait().await;
                store.refresh_tenant("acme").await
            }));
        }
        for handle in handles {
            handle.await.unwrap().expect("coalesced refresh succeeds");
        }

        assert_eq!(store.reload_count(), 1);
        let (ver, spec) = store.current_role_snapshot("acme", "reader").unwrap();
        assert_eq!(ver, 1);
        assert!(spec.allowed_tools.contains("payments_list"));
    }

    #[tokio::test]
    async fn unknown_tenant_fails_closed() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        );

        // Before any refresh, sync evaluators fail closed with ArtifactMissing.
        assert_eq!(
            store
                .current_role_snapshot("unknown", "reader")
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store
                .evaluate_call(&RoleEvalInput {
                    tenant_id: "unknown",
                    role: "reader",
                    tool_name: "payments_list",
                    args: &json!({}),
                    issued_policy_version: 1,
                    token_allowed_tools: None,
                    token_constraints: None,
                })
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store
                .effective_allowed_tools("unknown", "reader", 1, None)
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );

        // Refreshing an unknown tenant fails closed and leaves sync evaluators failing closed.
        assert_eq!(
            store.refresh_tenant("unknown").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store
                .current_role_snapshot("unknown", "reader")
                .unwrap_err(),
            RolePolicyError::ArtifactMissing
        );

        // Invalid tenant identifiers are refused without touching disk or state.
        assert_eq!(
            store.refresh_tenant("../escape").await.unwrap_err(),
            RolePolicyError::InvalidTenant
        );
        assert_eq!(
            store
                .current_role_snapshot("../escape", "reader")
                .unwrap_err(),
            RolePolicyError::InvalidTenant
        );
        assert!(store.tenants.read().is_empty());
        assert!(store.refresh_locks.read().is_empty());
    }

    #[tokio::test]
    async fn tenant_maps_are_bounded_by_allowlist_existence_and_hard_cap() {
        assert_eq!(MAX_TRACKED_TENANTS, 1024);

        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let roles = json!({ "reader": { "allowed_tools": ["payments_list"] } });
        for tenant in ["acme", "other", "t1", "t2", "t3"] {
            fs::write(
                artifacts_dir.join(format!("{tenant}.roles.jws")),
                signer.sign(tenant, 1, 600, roles.clone()),
            )
            .unwrap();
        }

        // Allowlist (policy_boot_tenants non-empty): rejects tenants outside the allowlist without insertion.
        let allowlisted = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        )
        .with_allowed_tenants(["acme"]);

        allowlisted.refresh_tenant("acme").await.unwrap();
        assert_eq!(allowlisted.tenants.read().len(), 1);
        assert_eq!(allowlisted.refresh_locks.read().len(), 1);

        assert_eq!(
            allowlisted.refresh_tenant("other").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            allowlisted.reload_tenant("other").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert!(!allowlisted.tenants.read().contains_key("other"));
        assert!(!allowlisted.refresh_locks.read().contains_key("other"));

        // Hard cap & ArtifactMissing / InvalidTenant leave no map entry.
        let capped = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(PolicyTrustStore::open(&trust_path)),
        )
        .with_max_tracked_tenants(2);

        assert_eq!(
            capped.refresh_tenant("ghost").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            capped.reload_tenant("ghost").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            capped.refresh_tenant("../escape").await.unwrap_err(),
            RolePolicyError::InvalidTenant
        );
        assert_eq!(
            capped.reload_tenant("../escape").unwrap_err(),
            RolePolicyError::InvalidTenant
        );
        assert!(capped.tenants.read().is_empty());
        assert!(capped.refresh_locks.read().is_empty());

        capped.refresh_tenant("t1").await.unwrap();
        capped.refresh_tenant("t2").await.unwrap();
        assert_eq!(capped.tenants.read().len(), 2);
        assert_eq!(capped.refresh_locks.read().len(), 2);

        // Tenant beyond the hard cap fails closed without insertion.
        assert_eq!(
            capped.refresh_tenant("t3").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            capped.reload_tenant("t3").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(capped.tenants.read().len(), 2);
        assert_eq!(capped.refresh_locks.read().len(), 2);
        assert!(!capped.tenants.read().contains_key("t3"));
        assert!(!capped.refresh_locks.read().contains_key("t3"));

        // Already-tracked tenants continue refreshing normally.
        capped.refresh_tenant("t1").await.unwrap();
        assert_eq!(capped.current_role_snapshot("t1", "reader").unwrap().0, 1);
    }

    #[test]
    fn compute_roles_digest_propagates_malformed_error() {
        struct FailingSerialize;
        impl Serialize for FailingSerialize {
            fn serialize<S>(&self, _serializer: S) -> Result<S::Ok, S::Error>
            where
                S: serde::Serializer,
            {
                Err(serde::ser::Error::custom("serialization error"))
            }
        }

        assert_eq!(
            digest_serializable(&FailingSerialize).unwrap_err(),
            RolePolicyError::Malformed
        );

        let mut bad_roles = HashMap::new();
        bad_roles.insert(
            "reader".to_string(),
            RolePolicySpec {
                allowed_tools: HashSet::from(["payments_list".to_string()]),
                argument_constraints: HashMap::from([(
                    "payments_list".to_string(),
                    HashMap::from([(
                        "limit".to_string(),
                        ArgumentConstraint::MaxNumber { max: f64::NAN },
                    )]),
                )]),
            },
        );
        assert_eq!(
            compute_roles_digest(&bad_roles).unwrap_err(),
            RolePolicyError::Malformed
        );

        let mut valid_roles = HashMap::new();
        valid_roles.insert(
            "reader".to_string(),
            RolePolicySpec {
                allowed_tools: HashSet::from(["payments_list".to_string()]),
                argument_constraints: HashMap::new(),
            },
        );
        let digest = compute_roles_digest(&valid_roles).expect("valid roles digest");
        assert_eq!(digest.len(), 64);
        let empty_digest: String = Sha256::digest(b"")
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_ne!(digest, empty_digest);
    }

    #[test]
    fn file_fingerprint_distinguishes_ctime_changes() {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("acme.roles.jws");
        fs::write(&path, "payload").unwrap();

        let fp = file_fingerprint(&path).expect("fingerprint for existing file");
        assert_eq!(fp.len, 7);

        #[cfg(unix)]
        {
            let mut other_sec = fp;
            other_sec.ctime = other_sec.ctime.wrapping_add(1);
            assert_ne!(fp, other_sec);

            let mut other_nsec = fp;
            other_nsec.ctime_nsec = other_nsec.ctime_nsec.wrapping_add(1);
            assert_ne!(fp, other_nsec);
        }
    }

    #[tokio::test]
    async fn snapshot_generation_guards_stale_activation_and_stale_error() {
        let tmp = tempfile::tempdir().unwrap();
        let signer = RoleSigner::new();
        let trust_path = tmp.path().join("trust.json");
        fs::write(&trust_path, signer.trust_jwks()).unwrap();
        let trust_store = PolicyTrustStore::open(&trust_path);
        let artifacts_dir = tmp.path().join("roles");
        let floor_dir = tmp.path().join("floors");
        fs::create_dir_all(&artifacts_dir).unwrap();

        let store = RolePolicyStore::new(
            &artifacts_dir,
            &floor_dir,
            "stoa-poc-policy",
            "stoa-gateway",
            Some(trust_store.clone()),
        );

        let role_path = artifacts_dir.join("acme.roles.jws");
        fs::write(
            &role_path,
            signer.sign(
                "acme",
                1,
                600,
                json!({ "reader": { "allowed_tools": ["payments_list"] } }),
            ),
        )
        .unwrap();
        store.refresh_tenant("acme").await.unwrap();
        let gen_after_v1 = store.tenants.read()["acme"].snapshot_generation;

        let trust = trust_store.current().unwrap();
        let v2_jws = signer.sign(
            "acme",
            2,
            600,
            json!({ "reader": { "allowed_tools": ["payments_list", "payments_export"] } }),
        );
        let verified_v2 = store.verify_jws(&trust, "acme", &v2_jws).unwrap();

        // A newer error snapshot is recorded after `gen_after_v1`.
        store.record_error_snapshot("acme", &RolePolicyError::Signature, None, gen_after_v1);
        let gen_after_err = store.tenants.read()["acme"].snapshot_generation;
        assert!(gen_after_err > gen_after_v1);
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::Signature
        );

        // An older valid activation started at `gen_after_v1` must NOT overwrite the newer error
        // snapshot or advance the persisted floor.
        assert_eq!(
            store
                .activate_verified_policy_with_fp("acme", verified_v2.clone(), None, gen_after_v1)
                .unwrap_err(),
            RolePolicyError::Signature
        );
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::Signature
        );
        let floor_path = floor_dir.join("acme.floor.json");
        assert_eq!(
            read_persisted_floor(&floor_path).unwrap().unwrap().version,
            1
        );

        // A valid activation started at `gen_after_err` succeeds and replaces the error snapshot.
        let activated = store
            .activate_verified_policy_with_fp("acme", verified_v2, None, gen_after_err)
            .unwrap();
        assert_eq!(activated.version, 2);
        let gen_after_v2 = store.tenants.read()["acme"].snapshot_generation;
        assert!(gen_after_v2 > gen_after_err);
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 2);

        // Conversely, an older error started at `gen_after_err` must NOT overwrite the newer valid v2 snapshot.
        store.record_error_snapshot(
            "acme",
            &RolePolicyError::ArtifactMissing,
            None,
            gen_after_err,
        );
        assert_eq!(store.current_role_snapshot("acme", "reader").unwrap().0, 2);

        // Genuine errors after v2 still fail closed on refresh: bad signature...
        let (header_payload, sig) = v2_jws.rsplit_once('.').unwrap();
        let flipped = if sig.starts_with('A') { 'B' } else { 'A' };
        let tampered = format!("{header_payload}.{flipped}{}", &sig[1..]);
        replace_file_atomic(&role_path, &tampered);
        assert_eq!(
            store.refresh_tenant("acme").await.unwrap_err(),
            RolePolicyError::Signature
        );
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::Signature
        );

        // ...and missing artifact.
        fs::remove_file(&role_path).unwrap();
        assert_eq!(
            store.refresh_tenant("acme").await.unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
        assert_eq!(
            store.current_role_snapshot("acme", "reader").unwrap_err(),
            RolePolicyError::ArtifactMissing
        );
    }
}
