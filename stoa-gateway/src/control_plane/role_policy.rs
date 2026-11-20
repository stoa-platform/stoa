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
use std::time::Duration;

use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use chrono::{DateTime, Utc};
use jsonwebtoken::{Algorithm, Validation};
use once_cell::sync::Lazy;
use parking_lot::RwLock;
use regex::Regex;
use serde::{Deserialize, Serialize};
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

static KID_FORMAT: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^cp-policy-[0-9]{4}(0[1-9]|1[0-2])-[1-9][0-9]*$").expect("kid regex")
});

/// Deterministic v1 argument constraint types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ArgumentConstraint {
    /// Argument value must exactly match one of the listed JSON values.
    AllowedValues { values: Vec<Value> },
    /// Argument must be a JSON string starting with `prefix`.
    Prefix { prefix: String },
    /// Argument must be a finite JSON number `<= max`.
    MaxNumber { max: f64 },
}

impl ArgumentConstraint {
    /// Evaluate whether `value` satisfies this constraint. Missing values fail closed.
    pub fn matches(&self, value: Option<&Value>) -> bool {
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
                max.is_finite() && val.as_f64().is_some_and(|n| n.is_finite() && n <= *max)
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

#[derive(Debug, Default)]
struct TenantPolicyState {
    current_version: u64,
    /// Ordered history of activated verified versions (bounded to `MAX_VERSION_HISTORY`).
    history: BTreeMap<u64, VerifiedRolePolicy>,
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
    tenants: Arc<RwLock<HashMap<String, TenantPolicyState>>>,
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
            tenants: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Reload, verify, persist floor atomically (0600), and activate the signed role
    /// artifact `<artifacts_dir>/<tenant_id>.roles.jws`.
    pub fn reload_tenant(&self, tenant_id: &str) -> Result<VerifiedRolePolicy, RolePolicyError> {
        validate_tenant_filename(tenant_id)?;
        let trust = self
            .trust
            .as_ref()
            .and_then(|t| t.current())
            .ok_or(RolePolicyError::TrustSetNotLoaded)?;

        let artifact_path = self.artifacts_dir.join(format!("{tenant_id}.roles.jws"));
        let bytes = fs::read(&artifact_path).map_err(|_| RolePolicyError::ArtifactMissing)?;
        if bytes.len() > MAX_ROLE_POLICY_BYTES {
            return Err(RolePolicyError::Malformed);
        }
        let jws = String::from_utf8(bytes)
            .map_err(|_| RolePolicyError::Malformed)?
            .trim()
            .to_string();

        let verified = self.verify_jws(&trust, tenant_id, &jws)?;
        self.activate_verified_policy(tenant_id, verified)
    }

    fn activate_verified_policy(
        &self,
        tenant_id: &str,
        verified: VerifiedRolePolicy,
    ) -> Result<VerifiedRolePolicy, RolePolicyError> {
        let _floor_lock = lock_floor(&self.floor_dir, tenant_id)?;
        let mut map = self.tenants.write();
        if Utc::now() >= verified.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
        }
        let state = map.entry(tenant_id.to_string()).or_default();
        if verified.version < state.current_version {
            return Err(RolePolicyError::VersionRollback);
        }
        if verified.version == state.current_version {
            if let Some(prev) = state.history.get(&verified.version) {
                if prev.content_sha256 != verified.content_sha256 {
                    return Err(RolePolicyError::VersionRollback);
                }
            }
        }

        // Check persisted floor and persist atomically BEFORE activating in memory.
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
        if must_persist || state.current_version != verified.version {
            fs::File::open(&self.floor_dir)
                .and_then(|dir| dir.sync_all())
                .map_err(|_| RolePolicyError::FloorPersistFailed)?;
        }

        state.current_version = verified.version;
        state.history.insert(verified.version, verified.clone());
        while state.history.len() > MAX_VERSION_HISTORY {
            if let Some(&oldest) = state.history.keys().next() {
                state.history.remove(&oldest);
            }
        }

        Ok(verified)
    }

    /// Snapshot the current verified policy version and role permissions for `tenant_id`
    /// (used at token issuance to anchor the monotonic session ceiling).
    pub fn current_role_snapshot(
        &self,
        tenant_id: &str,
        role: &str,
    ) -> Result<(u64, RolePolicySpec), RolePolicyError> {
        let verified = self.reload_tenant(tenant_id)?;
        let spec = verified
            .roles
            .get(role)
            .cloned()
            .ok_or(RolePolicyError::DeniedByRole)?;
        Ok((verified.version, spec))
    }

    /// Re-verify the active signed role artifact and evaluate the monotonic intersection
    /// across every policy version activated since `issued_policy_version`, plus any
    /// delegated tool-set and argument-constraint narrowing carried in the token.
    pub fn evaluate_call(&self, input: &RoleEvalInput<'_>) -> Result<(), RolePolicyError> {
        let RoleEvalInput {
            tenant_id,
            role,
            tool_name,
            args,
            issued_policy_version,
            token_allowed_tools,
            token_constraints,
        } = *input;
        // Always reload/re-verify the signed artifact on disk so any policy reduction
        // takes effect immediately on the very next call.
        let current = self.reload_tenant(tenant_id)?;
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
        // - Reduction takes effect immediately (absent in `current.version`).
        // - Withdrawal in v(k) followed by restoration in v(k+1) under the same token stays denied
        //   because v(k) is in `issued_policy_version..=current.version`.
        let map = self.tenants.read();
        let state = map.get(tenant_id).ok_or(RolePolicyError::ArtifactMissing)?;
        if !state.history.contains_key(&issued_policy_version) {
            return Err(RolePolicyError::DeniedByRole);
        }

        let args_obj = args.as_object();
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
                for (arg_name, constraint) in constraints {
                    let arg_val = args_obj.and_then(|o| o.get(arg_name));
                    if !constraint.matches(arg_val) {
                        return Err(RolePolicyError::DeniedByConstraint);
                    }
                }
            }
        }

        // Apply any additional delegated argument constraints from the token.
        if let Some(extra_constraints) = token_constraints {
            for (arg_name, constraint) in extra_constraints {
                let arg_val = args_obj.and_then(|o| o.get(arg_name));
                if !constraint.matches(arg_val) {
                    return Err(RolePolicyError::DeniedByConstraint);
                }
            }
        }

        Ok(())
    }

    /// Return `(current_version, allowed_tools, active_role_spec)` intersected monotonically
    /// across every policy version activated since `issued_policy_version` and any token-level
    /// tool allow-list.
    pub(crate) fn effective_allowed_tools(
        &self,
        tenant_id: &str,
        role: &str,
        issued_policy_version: u64,
        token_allowed_tools: Option<&[String]>,
    ) -> Result<(u64, HashSet<String>, RolePolicySpec), RolePolicyError> {
        self.reload_tenant(tenant_id)?;
        let map = self.tenants.read();
        let state = map.get(tenant_id).ok_or(RolePolicyError::ArtifactMissing)?;
        let current = state
            .history
            .get(&state.current_version)
            .ok_or(RolePolicyError::ArtifactMissing)?;
        if issued_policy_version == 0
            || issued_policy_version > current.version
            || !state.history.contains_key(&issued_policy_version)
        {
            return Err(RolePolicyError::DeniedByRole);
        }
        if Utc::now() >= current.expires_at {
            return Err(RolePolicyError::ValidityInvalid);
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

        let claims: Map<String, Value> = jsonwebtoken::decode(jws, key, &validation)
            .map_err(|_| RolePolicyError::Signature)?
            .claims;

        let string_claim = |name: &str| claims.get(name).and_then(Value::as_str);
        if string_claim("iss") != Some(self.issuer.as_str()) {
            return Err(RolePolicyError::Issuer);
        }
        if string_claim("aud") != Some(self.audience.as_str()) {
            return Err(RolePolicyError::Audience);
        }
        if string_claim("tenant_id") != Some(tenant_id) {
            return Err(RolePolicyError::TenantMismatch);
        }
        let tenant_uuid = string_claim("tenant_uuid")
            .and_then(|raw| Uuid::parse_str(raw).ok())
            .ok_or(RolePolicyError::TenantMismatch)?;

        let version = claims
            .get("version")
            .and_then(Value::as_u64)
            .filter(|&v| v > 0)
            .ok_or(RolePolicyError::Malformed)?;

        let issued_at = string_claim("issued_at")
            .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
            .map(|dt| dt.with_timezone(&Utc))
            .ok_or(RolePolicyError::ValidityInvalid)?;
        let expires_at = string_claim("expires_at")
            .and_then(|raw| DateTime::parse_from_rfc3339(raw).ok())
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

        let roles_val = claims
            .get("roles")
            .cloned()
            .ok_or(RolePolicyError::Malformed)?;
        let roles: HashMap<String, RolePolicySpec> =
            serde_json::from_value(roles_val).map_err(|_| RolePolicyError::Malformed)?;

        let content_sha256 = compute_roles_digest(&roles);

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

/// Deterministic SHA-256 digest of role rules (canonicalized key order).
fn compute_roles_digest(roles: &HashMap<String, RolePolicySpec>) -> String {
    let mut canonical: BTreeMap<&str, Value> = BTreeMap::new();
    for (role_name, spec) in roles {
        let mut tools: Vec<&String> = spec.allowed_tools.iter().collect();
        tools.sort();
        let mut tool_constraints: BTreeMap<&str, BTreeMap<&str, &ArgumentConstraint>> =
            BTreeMap::new();
        for (tool_name, arg_map) in &spec.argument_constraints {
            let mut sorted_args = BTreeMap::new();
            for (arg_name, c) in arg_map {
                sorted_args.insert(arg_name.as_str(), c);
            }
            tool_constraints.insert(tool_name.as_str(), sorted_args);
        }
        canonical.insert(
            role_name.as_str(),
            serde_json::json!({
                "allowed_tools": tools,
                "argument_constraints": tool_constraints,
            }),
        );
    }
    let bytes = serde_json::to_vec(&canonical).unwrap_or_default();
    let hash = Sha256::digest(&bytes);
    hash.iter().map(|b| format!("{b:02x}")).collect()
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
    fn session_reduction_immediate_and_widening_or_restore_refused_under_same_token() {
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
        assert_eq!(
            eval("payments_export", v1).unwrap_err(),
            RolePolicyError::DeniedByRole
        );

        // New token issued at v2 CAN call payments_export.
        let (v2, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert!(eval("payments_export", v2).is_ok());

        // v3 withdraws payments_export -> immediate deny on next call for v2 token!
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
        assert_eq!(
            eval("payments_export", v2).unwrap_err(),
            RolePolicyError::DeniedByRole
        );
        let (v4, _) = store.current_role_snapshot("acme", "reader").unwrap();
        assert!(eval("payments_export", v4).is_ok());
    }
}
