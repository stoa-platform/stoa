//! DPoP (Demonstrating Proof-of-Possession) — RFC 9449
//!
//! Validates DPoP proofs to bind access tokens to a specific client key pair.
//! Complements mTLS (RFC 8705) for environments where certificate-based binding
//! is not feasible (e.g., browser-based clients, mobile apps).
//!
//! Validation steps (RFC 9449 Section 4.3):
//! 1. Parse DPoP header as JWT
//! 2. Verify `typ` header is "dpop+jwt"
//! 3. Verify `alg` is asymmetric (ES256, RS256, EdDSA — not HS*)
//! 4. Verify `jwk` header contains a public key (no private key material)
//! 5. Verify signature using the embedded JWK
//! 6. Verify `htm` matches the HTTP method
//! 7. Verify `htu` matches the request URI
//! 8. Verify `iat` is within acceptable time window
//! 9. Validate `jti` presence and length bound
//! 10. If access token bound, verify `ath` = SHA-256(access_token) and `cnf.jkt`
//! 11. Record `(jkt, jti)` in the per-process replay table (after all binding checks)

use axum::http::Uri;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};
use subtle::ConstantTimeEq;
use thiserror::Error;
use tracing::{debug, warn};

use crate::auth::claims::CnfClaim;
use crate::metrics;

/// Maximum permitted `jti` claim length in bytes.
pub const MAX_JTI_LEN: usize = 128;

/// Upper bound on active replay entries tracked per DPoP key thumbprint (`jkt`).
const DEFAULT_MAX_JTI_PER_KEY: usize = 4_096;

// =============================================================================
// Configuration
// =============================================================================

/// DPoP configuration.
///
/// All fields are configurable via `STOA_DPOP__*` environment variables
/// (note the **double underscore** between the prefix and the field — required
/// by the nested-struct env-var mapping installed in `src/config/loader.rs`).
/// Single-underscore forms (`STOA_DPOP_ENABLED`) are silently ignored.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DpopConfig {
    /// Enable DPoP validation (default: false — opt-in).
    /// Env: STOA_DPOP__ENABLED
    #[serde(default)]
    pub enabled: bool,

    /// Require DPoP proof on all token-authenticated requests.
    /// When false, DPoP is optional (opportunistic binding).
    /// Env: STOA_DPOP__REQUIRED
    #[serde(default)]
    pub required: bool,

    /// Maximum age of DPoP proof in seconds (default: 300 = 5 min).
    /// Proofs with `iat` older than this are rejected.
    /// Env: STOA_DPOP__MAX_AGE_SECS
    #[serde(default = "default_max_age_secs")]
    pub max_age_secs: u64,

    /// Maximum clock skew tolerance in seconds (default: 30).
    /// Env: STOA_DPOP__CLOCK_SKEW_SECS
    #[serde(default = "default_clock_skew_secs")]
    pub clock_skew_secs: u64,

    /// JTI cache TTL in seconds (for replay prevention). Default: 600 = 10 min.
    /// Should be >= 2 * max_age_secs to catch all replays.
    /// Env: STOA_DPOP__JTI_CACHE_TTL_SECS
    #[serde(default = "default_jti_cache_ttl_secs")]
    pub jti_cache_ttl_secs: u64,

    /// Maximum JTI cache entries (default: 100_000).
    /// Env: STOA_DPOP__JTI_CACHE_MAX
    #[serde(default = "default_jti_cache_max")]
    pub jti_cache_max: u64,
}

fn default_max_age_secs() -> u64 {
    300
}
fn default_clock_skew_secs() -> u64 {
    30
}
fn default_jti_cache_ttl_secs() -> u64 {
    600
}
fn default_jti_cache_max() -> u64 {
    100_000
}

impl Default for DpopConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            required: false,
            max_age_secs: default_max_age_secs(),
            clock_skew_secs: default_clock_skew_secs(),
            jti_cache_ttl_secs: default_jti_cache_ttl_secs(),
            jti_cache_max: default_jti_cache_max(),
        }
    }
}

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum DpopError {
    #[error("missing DPoP header")]
    MissingHeader,

    #[error("invalid DPoP proof: failed to decode JWT header")]
    InvalidJwtHeader,

    #[error("invalid DPoP proof: typ must be 'dpop+jwt', got '{0}'")]
    InvalidTyp(String),

    #[error("invalid DPoP proof: algorithm '{0}' is not allowed (must be asymmetric)")]
    DisallowedAlgorithm(String),

    #[error("invalid DPoP proof: missing 'jwk' in JWT header")]
    MissingJwk,

    #[error("invalid DPoP proof: JWK contains private key material")]
    PrivateKeyInJwk,

    #[error("invalid DPoP proof: unsupported JWK key type '{0}'")]
    UnsupportedKeyType(String),

    #[error("invalid DPoP proof: failed to construct decoding key from JWK")]
    DecodingKeyError,

    #[error("invalid DPoP proof: signature verification failed")]
    SignatureInvalid,

    #[error("invalid DPoP proof: htm mismatch (expected '{expected}', got '{got}')")]
    HtmMismatch { expected: String, got: String },

    #[error("invalid DPoP proof: htu mismatch (expected '{expected}', got '{got}')")]
    HtuMismatch { expected: String, got: String },

    #[error("invalid DPoP proof: missing 'iat' claim")]
    MissingIat,

    #[error("invalid DPoP proof: iat is too old ({age_secs}s > {max_secs}s)")]
    ProofTooOld { age_secs: u64, max_secs: u64 },

    #[error("invalid DPoP proof: iat is in the future ({skew_secs}s ahead > {max_skew}s)")]
    ProofInFuture { skew_secs: u64, max_skew: u64 },

    #[error("invalid DPoP proof: missing 'jti' claim")]
    MissingJti,

    #[error("invalid DPoP proof: 'jti' exceeds maximum length")]
    JtiTooLong,

    #[error("DPoP proof replay detected")]
    ReplayDetected(String),

    #[error("invalid DPoP proof: ath mismatch (access token hash does not match)")]
    AthMismatch,

    #[error("invalid DPoP proof: missing 'ath' claim for token binding")]
    MissingAth,

    #[error("DPoP cnf.jkt binding mismatch: token jkt does not match proof JWK thumbprint")]
    JktMismatch,
}

// =============================================================================
// DPoP Claims (JWT payload)
// =============================================================================

/// Claims inside a DPoP proof JWT (RFC 9449 Section 4.2).
#[derive(Debug, Deserialize)]
pub struct DpopClaims {
    /// Unique identifier for the proof (replay prevention)
    pub jti: Option<String>,

    /// HTTP method (e.g., "POST")
    pub htm: Option<String>,

    /// HTTP target URI (scheme + authority + path, no query/fragment)
    pub htu: Option<String>,

    /// Issued-at timestamp (seconds since epoch)
    pub iat: Option<i64>,

    /// Access token hash (SHA-256, base64url-encoded, no padding)
    pub ath: Option<String>,
}

// =============================================================================
// JWK types for header parsing
// =============================================================================

/// Minimal JWK representation from the DPoP proof header.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DpopJwk {
    pub kty: String,
    #[serde(default)]
    pub crv: Option<String>,
    #[serde(default)]
    pub x: Option<String>,
    #[serde(default)]
    pub y: Option<String>,
    #[serde(default)]
    pub n: Option<String>,
    #[serde(default)]
    pub e: Option<String>,
    // Private key fields — MUST NOT be present
    #[serde(default)]
    pub d: Option<String>,
    #[serde(default)]
    pub p: Option<String>,
    #[serde(default)]
    pub q: Option<String>,
}

impl DpopJwk {
    /// Check that no private key material is present.
    pub fn has_private_key(&self) -> bool {
        self.d.is_some() || self.p.is_some() || self.q.is_some()
    }
}

// =============================================================================
// DPoP Validator
// =============================================================================

/// Per-process in-memory replay table with O(1) amortized FIFO expiry eviction and per-key cap.
///
/// State is local to the current process: entries are not persisted across restarts
/// and are not replicated across instances.
#[derive(Default)]
struct JtiReplayTable {
    /// `SHA-256(jkt || 0x00 || jti) -> expiry instant`.
    entries: HashMap<[u8; 32], Instant>,
    /// FIFO expiration queue (`(expires_at, entry_hash, jkt_hash)`).
    /// Monotonically ordered because all entries share the validator's fixed effective TTL.
    expiry_queue: VecDeque<(Instant, [u8; 32], [u8; 32])>,
    /// Active entry count per `SHA-256(jkt)` so no single key can exhaust global capacity.
    per_key_counts: HashMap<[u8; 32], usize>,
}

impl JtiReplayTable {
    fn evict_expired(&mut self, now: Instant) {
        while let Some(&(expires_at, _, _)) = self.expiry_queue.front() {
            if expires_at > now {
                break;
            }
            let Some((_, entry_hash, jkt_hash)) = self.expiry_queue.pop_front() else {
                break;
            };
            if self.entries.get(&entry_hash).copied() == Some(expires_at) {
                self.entries.remove(&entry_hash);
                if let Some(count) = self.per_key_counts.get_mut(&jkt_hash) {
                    *count = count.saturating_sub(1);
                    if *count == 0 {
                        self.per_key_counts.remove(&jkt_hash);
                    }
                }
            }
        }
    }
}

fn hash_jkt(jkt: &str) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(jkt.as_bytes());
    hasher.finalize().into()
}

fn hash_scoped_jti(jkt: &str, jti: &str) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(jkt.as_bytes());
    hasher.update([0u8]);
    hasher.update(jti.as_bytes());
    hasher.finalize().into()
}

/// DPoP proof validator with a per-process in-memory replay table.
///
/// The replay table is scoped to the current process (not shared across replicas
/// and cleared on process restart).
#[derive(Clone)]
pub struct DpopValidator {
    config: DpopConfig,
    /// Maximum active entries allowed per DPoP key thumbprint (`jkt`).
    max_entries_per_key: usize,
    /// Atomic, bounded per-process JTI replay table.
    jti_cache: Arc<Mutex<JtiReplayTable>>,
}

impl DpopValidator {
    /// Create a new DPoP validator with the given config.
    pub fn new(config: DpopConfig) -> Self {
        let global_max = config.jti_cache_max as usize;
        let max_entries_per_key = if global_max == 0 {
            0
        } else {
            (global_max / 16)
                .clamp(1, DEFAULT_MAX_JTI_PER_KEY)
                .min(global_max)
        };
        Self {
            config,
            max_entries_per_key,
            jti_cache: Arc::new(Mutex::new(JtiReplayTable::default())),
        }
    }

    /// Override the per-key entry cap (clamped to global `jti_cache_max`).
    pub fn with_max_entries_per_key(mut self, cap: usize) -> Self {
        self.max_entries_per_key = cap.min(self.config.jti_cache_max as usize);
        self
    }

    /// Effective replay retention TTL in seconds: always at least `max_age_secs + clock_skew_secs`.
    pub fn effective_jti_ttl_secs(&self) -> u64 {
        let min_ttl = self
            .config
            .max_age_secs
            .saturating_add(self.config.clock_skew_secs);
        self.config.jti_cache_ttl_secs.max(min_ttl)
    }

    /// Validate a DPoP proof.
    ///
    /// # Arguments
    /// - `dpop_header`: The raw DPoP proof JWT from the `DPoP` HTTP header
    /// - `http_method`: The HTTP method of the current request (e.g., "POST")
    /// - `http_uri`: The HTTP target URI (scheme + authority + path)
    /// - `access_token`: Optional access token for `ath` binding verification
    /// - `token_cnf`: Optional `cnf` claim from the access token for `jkt` binding
    pub fn validate(
        &self,
        dpop_header: &str,
        http_method: &str,
        http_uri: &str,
        access_token: Option<&str>,
        token_cnf: Option<&CnfClaim>,
    ) -> Result<DpopJwk, DpopError> {
        // Step 1: Parse JWT header
        let header = decode_header(dpop_header).map_err(|e| {
            debug!("DPoP header decode failed: {e}");
            DpopError::InvalidJwtHeader
        })?;

        // Step 2: Verify typ = "dpop+jwt"
        let typ = header.typ.as_deref().unwrap_or("");
        if !typ.eq_ignore_ascii_case("dpop+jwt") {
            return Err(DpopError::InvalidTyp(typ.to_string()));
        }

        // Step 3: Verify asymmetric algorithm
        let alg = header.alg;
        if !is_allowed_algorithm(alg) {
            return Err(DpopError::DisallowedAlgorithm(format!("{alg:?}")));
        }

        // Step 4: Extract and validate JWK from header
        let jwk_raw = header.jwk.ok_or(DpopError::MissingJwk)?;
        // jsonwebtoken::Jwk → serde_json::Value → DpopJwk
        let jwk_value = serde_json::to_value(&jwk_raw).map_err(|_| DpopError::MissingJwk)?;
        let jwk: DpopJwk = serde_json::from_value(jwk_value).map_err(|_| DpopError::MissingJwk)?;

        if jwk.has_private_key() {
            return Err(DpopError::PrivateKeyInJwk);
        }

        // Step 5: Construct decoding key from JWK and verify signature
        let decoding_key = build_decoding_key(&jwk, alg)?;

        let mut validation = Validation::new(alg);
        validation.validate_exp = false; // DPoP proofs don't have `exp`
        validation.required_spec_claims.clear(); // Only custom claims
        validation.validate_aud = false;

        let token_data =
            decode::<DpopClaims>(dpop_header, &decoding_key, &validation).map_err(|e| {
                debug!("DPoP signature verification failed: {e}");
                DpopError::SignatureInvalid
            })?;

        let claims = token_data.claims;

        // Step 6: Verify htm (HTTP method)
        let htm = claims.htm.as_deref().ok_or(DpopError::HtmMismatch {
            expected: http_method.to_string(),
            got: "(missing)".to_string(),
        })?;
        if !htm.eq_ignore_ascii_case(http_method) {
            return Err(DpopError::HtmMismatch {
                expected: http_method.to_string(),
                got: htm.to_string(),
            });
        }

        // Step 7: Verify htu (HTTP target URI)
        let htu = claims.htu.as_deref().ok_or(DpopError::HtuMismatch {
            expected: http_uri.to_string(),
            got: "(missing)".to_string(),
        })?;
        if !htu_matches(htu, http_uri) {
            return Err(DpopError::HtuMismatch {
                expected: http_uri.to_string(),
                got: htu.to_string(),
            });
        }

        // Step 8: Verify iat (issued-at timestamp)
        let iat = claims.iat.ok_or(DpopError::MissingIat)?;
        self.validate_iat(iat)?;

        // Step 9: Validate jti presence and length bound (before any state mutation)
        let jti = claims.jti.as_deref().ok_or(DpopError::MissingJti)?;
        if jti.is_empty() {
            return Err(DpopError::MissingJti);
        }
        if jti.len() > MAX_JTI_LEN {
            return Err(DpopError::JtiTooLong);
        }

        // Step 10: Verify ath (access token hash) if access_token provided
        if let Some(token) = access_token {
            let expected_ath = compute_ath(token);
            let proof_ath = claims.ath.as_deref().ok_or(DpopError::MissingAth)?;
            if proof_ath != expected_ath {
                metrics::record_dpop_validation("ath_mismatch");
                return Err(DpopError::AthMismatch);
            }
        }

        // Step 11: Verify cnf.jkt binding (RFC 9449 Section 6.1)
        // If the access token has a cnf.jkt claim, verify it matches the DPoP proof JWK thumbprint
        if let Some(cnf) = token_cnf {
            Self::verify_cnf_binding(&jwk, cnf)?;
        }

        // Step 12: Record (jkt, jti) atomically ONLY after ath and cnf.jkt checks succeed
        let proof_jkt = compute_jwk_thumbprint(&jwk);
        self.check_replay(&proof_jkt, jti)?;

        metrics::record_dpop_validation("success");
        debug!("DPoP proof validated successfully");
        Ok(jwk)
    }

    /// Validate the `iat` timestamp against configured bounds.
    fn validate_iat(&self, iat: i64) -> Result<(), DpopError> {
        let now = chrono::Utc::now().timestamp();
        let age = now.saturating_sub(iat);
        let max_age = self.config.max_age_secs as i64;
        let max_skew = self.config.clock_skew_secs as i64;

        if age > max_age {
            return Err(DpopError::ProofTooOld {
                age_secs: age as u64,
                max_secs: self.config.max_age_secs,
            });
        }

        if age < -max_skew {
            return Err(DpopError::ProofInFuture {
                skew_secs: (-age) as u64,
                max_skew: self.config.clock_skew_secs,
            });
        }

        Ok(())
    }

    /// Check and record `(jkt, jti)` atomically with O(1) FIFO expiry eviction,
    /// per-key quota, and fail-closed global capacity bound.
    fn check_replay(&self, jkt: &str, jti: &str) -> Result<(), DpopError> {
        if jti.is_empty() {
            return Err(DpopError::MissingJti);
        }
        if jti.len() > MAX_JTI_LEN {
            return Err(DpopError::JtiTooLong);
        }

        let now = Instant::now();
        let ttl = Duration::from_secs(self.effective_jti_ttl_secs());
        let max_entries = self.config.jti_cache_max as usize;
        let entry_hash = hash_scoped_jti(jkt, jti);
        let jkt_hash = hash_jkt(jkt);

        let mut table = self.jti_cache.lock();
        table.evict_expired(now);

        if let Some(&expires_at) = table.entries.get(&entry_hash) {
            if expires_at > now {
                warn!("DPoP replay detected");
                metrics::record_dpop_validation("replay");
                return Err(DpopError::ReplayDetected(String::new()));
            }
        }

        let key_count = table.per_key_counts.get(&jkt_hash).copied().unwrap_or(0);
        if key_count >= self.max_entries_per_key {
            warn!(
                max_per_key = self.max_entries_per_key,
                "DPoP per-key replay quota reached; failing closed"
            );
            metrics::record_dpop_validation("replay_key_quota");
            return Err(DpopError::ReplayDetected(String::new()));
        }

        if table.entries.len() >= max_entries {
            warn!(max_entries, "DPoP replay cache saturated; failing closed");
            metrics::record_dpop_validation("replay_cache_full");
            return Err(DpopError::ReplayDetected(String::new()));
        }

        let expires_at = now + ttl;
        table.entries.insert(entry_hash, expires_at);
        table
            .expiry_queue
            .push_back((expires_at, entry_hash, jkt_hash));
        *table.per_key_counts.entry(jkt_hash).or_insert(0) += 1;
        Ok(())
    }

    /// Verify that the DPoP proof JWK thumbprint matches the `cnf.jkt` in the access token.
    ///
    /// Uses timing-safe comparison to prevent side-channel attacks.
    fn verify_cnf_binding(jwk: &DpopJwk, cnf: &CnfClaim) -> Result<(), DpopError> {
        if let Some(expected_jkt) = &cnf.jkt {
            let proof_jkt = compute_jwk_thumbprint(jwk);
            if proof_jkt.as_bytes().ct_eq(expected_jkt.as_bytes()).into() {
                debug!("DPoP cnf.jkt binding verified");
                Ok(())
            } else {
                warn!("DPoP cnf.jkt binding mismatch");
                metrics::record_dpop_validation("jkt_mismatch");
                Err(DpopError::JktMismatch)
            }
        } else {
            // No jkt in cnf — DPoP binding not required by token
            Ok(())
        }
    }

    /// Returns true if DPoP is enabled.
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Returns true if DPoP is required.
    pub fn is_required(&self) -> bool {
        self.config.required
    }
}

// =============================================================================
// Helper Functions
// =============================================================================

/// Allowed asymmetric algorithms for DPoP proofs (RFC 9449 Section 4.3).
fn is_allowed_algorithm(alg: Algorithm) -> bool {
    matches!(
        alg,
        Algorithm::ES256
            | Algorithm::ES384
            | Algorithm::RS256
            | Algorithm::RS384
            | Algorithm::RS512
            | Algorithm::PS256
            | Algorithm::PS384
            | Algorithm::PS512
            | Algorithm::EdDSA
    )
}

/// Build a `DecodingKey` from a DPoP JWK and algorithm.
fn build_decoding_key(jwk: &DpopJwk, alg: Algorithm) -> Result<DecodingKey, DpopError> {
    match jwk.kty.as_str() {
        "EC" => {
            let x = jwk.x.as_deref().ok_or(DpopError::DecodingKeyError)?;
            let y = jwk.y.as_deref().ok_or(DpopError::DecodingKeyError)?;
            DecodingKey::from_ec_components(x, y).map_err(|_| DpopError::DecodingKeyError)
        }
        "RSA" => {
            let n = jwk.n.as_deref().ok_or(DpopError::DecodingKeyError)?;
            let e = jwk.e.as_deref().ok_or(DpopError::DecodingKeyError)?;
            DecodingKey::from_rsa_components(n, e).map_err(|_| DpopError::DecodingKeyError)
        }
        "OKP" if matches!(alg, Algorithm::EdDSA) => {
            let x = jwk.x.as_deref().ok_or(DpopError::DecodingKeyError)?;
            DecodingKey::from_ed_components(x).map_err(|_| DpopError::DecodingKeyError)
        }
        other => Err(DpopError::UnsupportedKeyType(other.to_string())),
    }
}

/// Validate that a path adheres strictly to RFC 3986 path characters:
/// segment = *( pchar / "/" )
/// pchar   = unreserved / pct-encoded / sub-delims / ":" / "@"
/// pct-encoded = "%" HEXDIG HEXDIG
fn is_valid_rfc3986_path(path: &str) -> bool {
    let bytes = path.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        let b = bytes[i];
        match b {
            // unreserved = ALPHA / DIGIT / "-" / "." / "_" / "~"
            b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                i += 1;
            }
            // sub-delims = "!" / "$" / "&" / "'" / "(" / ")" / "*" / "+" / "," / ";" / "="
            b'!' | b'$' | b'&' | b'\'' | b'(' | b')' | b'*' | b'+' | b',' | b';' | b'=' => {
                i += 1;
            }
            // ":" / "@" / "/"
            b':' | b'@' | b'/' => {
                i += 1;
            }
            // pct-encoded = "%" HEXDIG HEXDIG
            b'%' => {
                if i + 2 >= bytes.len() {
                    return false;
                }
                let h1 = bytes[i + 1];
                let h2 = bytes[i + 2];
                if !h1.is_ascii_hexdigit() || !h2.is_ascii_hexdigit() {
                    return false;
                }
                i += 3;
            }
            _ => return false,
        }
    }
    true
}

/// Extract validated HTU components for RFC 9449 comparison.
///
/// Returns `(scheme, host, port, path)` borrowing slices from the parsed `Uri`.
/// Rejects relative URIs, non-HTTP(S) schemes, empty hosts, invalid/zero ports,
/// authorities containing userinfo (`@`), and raw paths with non-RFC 3986 characters
/// (e.g. backslashes, malformed percent-encodings).
fn extract_htu_parts(uri: &Uri) -> Option<(&str, &str, u16, &str)> {
    let scheme = uri.scheme_str()?;
    let default_port = if scheme.eq_ignore_ascii_case("http") {
        80
    } else if scheme.eq_ignore_ascii_case("https") {
        443
    } else {
        return None;
    };

    let authority = uri.authority()?;
    if authority.as_str().contains('@') {
        return None;
    }

    let host = authority.host();
    if host.is_empty() {
        return None;
    }

    let port_suffix = authority.as_str().strip_prefix(host)?;
    let port = if port_suffix.is_empty() {
        default_port
    } else {
        let port_str = port_suffix.strip_prefix(':')?;
        if port_str.is_empty() || !port_str.chars().all(|c| c.is_ascii_digit()) {
            return None;
        }
        let parsed: u16 = port_str.parse().ok()?;
        if parsed == 0 {
            return None;
        }
        parsed
    };

    let raw_path = uri.path();
    let path = if raw_path.is_empty() { "/" } else { raw_path };

    if !is_valid_rfc3986_path(path) {
        return None;
    }

    Some((scheme, host, port, path))
}

/// Compare `htu` from the proof with the actual request URI.
///
/// Per RFC 9449 Section 4.3 and RFC 3986 Section 6.2.2.1:
/// - query and fragment components are ignored,
/// - scheme and host are compared ASCII case-insensitively,
/// - omitted ports match the scheme default (`80` for `http`, `443` for `https`),
/// - path comparison is exact and case-sensitive,
/// - invalid ports (including 0, non-numeric, or out of range) and relative URIs are rejected.
fn htu_matches(htu: &str, request_uri: &str) -> bool {
    let Ok(uri_a) = strip_query_fragment(htu).parse::<Uri>() else {
        return false;
    };
    let Ok(uri_b) = strip_query_fragment(request_uri).parse::<Uri>() else {
        return false;
    };

    let Some((scheme_a, host_a, port_a, path_a)) = extract_htu_parts(&uri_a) else {
        return false;
    };
    let Some((scheme_b, host_b, port_b, path_b)) = extract_htu_parts(&uri_b) else {
        return false;
    };

    scheme_a.eq_ignore_ascii_case(scheme_b)
        && host_a.eq_ignore_ascii_case(host_b)
        && port_a == port_b
        && path_a == path_b
}

/// Strip query string and fragment from a URI.
fn strip_query_fragment(s: &str) -> &str {
    let s = s.split('#').next().unwrap_or(s);
    s.split('?').next().unwrap_or(s)
}

/// Compute the access token hash (ath) per RFC 9449 Section 6.1:
/// `base64url(sha256(ascii(access_token)))` with no padding.
pub fn compute_ath(access_token: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(access_token.as_bytes());
    let hash = hasher.finalize();
    URL_SAFE_NO_PAD.encode(hash)
}

/// Compute the JWK thumbprint (RFC 7638) for a DPoP JWK.
/// Used for `jkt` confirmation in access tokens (RFC 9449 Section 6.1).
pub fn compute_jwk_thumbprint(jwk: &DpopJwk) -> String {
    // RFC 7638: lexicographically sorted, required members only
    let json = match jwk.kty.as_str() {
        "EC" => {
            format!(
                r#"{{"crv":"{}","kty":"EC","x":"{}","y":"{}"}}"#,
                jwk.crv.as_deref().unwrap_or(""),
                jwk.x.as_deref().unwrap_or(""),
                jwk.y.as_deref().unwrap_or("")
            )
        }
        "RSA" => {
            format!(
                r#"{{"e":"{}","kty":"RSA","n":"{}"}}"#,
                jwk.e.as_deref().unwrap_or(""),
                jwk.n.as_deref().unwrap_or("")
            )
        }
        "OKP" => {
            format!(
                r#"{{"crv":"{}","kty":"OKP","x":"{}"}}"#,
                jwk.crv.as_deref().unwrap_or(""),
                jwk.x.as_deref().unwrap_or("")
            )
        }
        _ => return String::new(),
    };

    let mut hasher = Sha256::new();
    hasher.update(json.as_bytes());
    let hash = hasher.finalize();
    URL_SAFE_NO_PAD.encode(hash)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> DpopConfig {
        DpopConfig {
            enabled: true,
            required: true,
            max_age_secs: 300,
            clock_skew_secs: 30,
            jti_cache_ttl_secs: 600,
            jti_cache_max: 1000,
        }
    }

    #[test]
    fn test_allowed_algorithms() {
        assert!(is_allowed_algorithm(Algorithm::ES256));
        assert!(is_allowed_algorithm(Algorithm::RS256));
        assert!(is_allowed_algorithm(Algorithm::PS256));
        assert!(is_allowed_algorithm(Algorithm::EdDSA));
        assert!(!is_allowed_algorithm(Algorithm::HS256));
        assert!(!is_allowed_algorithm(Algorithm::HS384));
        assert!(!is_allowed_algorithm(Algorithm::HS512));
    }

    #[test]
    fn test_htu_matches_exact() {
        let cases = [
            (
                "https://mcp.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            ("https://mcp.gostoa.dev", "https://mcp.gostoa.dev/"),
            (
                "https://mcp.gostoa.dev/mcp/tools%2Fcall",
                "https://mcp.gostoa.dev/mcp/tools%2Fcall",
            ),
            (
                "https://mcp.gostoa.dev/users/@alice/tools",
                "https://mcp.gostoa.dev/users/@alice/tools",
            ),
        ];
        for (a, b) in cases {
            assert!(htu_matches(a, b), "expected match between '{a}' and '{b}'");
        }
    }

    #[test]
    fn test_htu_matches_ignores_query() {
        let cases = [
            (
                "https://mcp.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call?foo=bar",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools/call?a=1&b=2",
                "https://mcp.gostoa.dev/mcp/tools/call?c=3",
            ),
        ];
        for (a, b) in cases {
            assert!(htu_matches(a, b), "query should be ignored: '{a}' vs '{b}'");
        }
    }

    #[test]
    fn test_htu_matches_ignores_fragment() {
        let cases = [
            (
                "https://mcp.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call#section",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools/call?a=1#frag1",
                "https://mcp.gostoa.dev/mcp/tools/call?b=2#frag2",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools/call#frag?notquery",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
        ];
        for (a, b) in cases {
            assert!(
                htu_matches(a, b),
                "fragment/query should be ignored: '{a}' vs '{b}'"
            );
        }
    }

    #[test]
    fn test_htu_matches_case_insensitive() {
        let matching_cases = [
            (
                "HTTPS://MCP.GOSTOA.DEV/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "Http://McP.GoStOa.DeV/mcp/tools/call",
                "http://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://[2001:DB8::1]/mcp/tools/call",
                "https://[2001:db8::1]/mcp/tools/call",
            ),
            (
                "https://[2001:DB8::1]:443/mcp/tools/call",
                "https://[2001:db8::1]/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev:443/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev:443/mcp/tools/call",
            ),
            (
                "http://mcp.gostoa.dev:80/mcp/tools/call",
                "http://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "http://mcp.gostoa.dev/mcp/tools/call",
                "http://mcp.gostoa.dev:80/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev:8443/mcp/tools/call",
                "https://mcp.gostoa.dev:8443/mcp/tools/call",
            ),
        ];
        for (a, b) in matching_cases {
            assert!(htu_matches(a, b), "expected match between '{a}' and '{b}'");
        }
    }

    #[test]
    fn test_htu_mismatch_different_path() {
        let mismatches = [
            (
                "https://mcp.gostoa.dev/mcp/tools/list",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/MCP/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/Tools/Call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools%2Fcall",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools%2fcall",
                "https://mcp.gostoa.dev/mcp/tools%2Fcall",
            ),
            (
                "https://mcp.gostoa.dev/mcp/./tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/other/../tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp//tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev/mcp/tools/call/",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://other.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "http://mcp.gostoa.dev/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev:8443/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev:8443/mcp/tools/call",
                "https://mcp.gostoa.dev:9443/mcp/tools/call",
            ),
            (
                "http://mcp.gostoa.dev:8080/mcp/tools/call",
                "http://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "https://mcp.gostoa.dev:80/mcp/tools/call",
                "https://mcp.gostoa.dev/mcp/tools/call",
            ),
            (
                "http://mcp.gostoa.dev:443/mcp/tools/call",
                "http://mcp.gostoa.dev/mcp/tools/call",
            ),
        ];
        for (a, b) in mismatches {
            assert!(
                !htu_matches(a, b),
                "expected mismatch between '{a}' and '{b}'"
            );
        }

        let valid = "https://mcp.gostoa.dev/mcp/tools/call";
        let invalid_uris = [
            "",
            "/mcp/tools/call",
            "mcp/tools/call",
            "//mcp.gostoa.dev/mcp/tools/call",
            "not a uri",
            "https://",
            "https:///mcp/tools/call",
            "https://:443/mcp/tools/call",
            "https://mcp.gostoa.dev:/mcp/tools/call",
            "https://mcp.gostoa.dev:0/mcp/tools/call",
            "https://mcp.gostoa.dev:0000/mcp/tools/call",
            "https://mcp.gostoa.dev:+443/mcp/tools/call",
            "https://mcp.gostoa.dev:99999/mcp/tools/call",
            "https://mcp.gostoa.dev:abc/mcp/tools/call",
            "https://mcp.gostoa.dev/bad path",
            "https://mcp.gostoa.dev/mcp\\tools",
            "ftp://mcp.gostoa.dev/mcp/tools/call",
            "https://user@mcp.gostoa.dev/mcp/tools/call",
            "https://user:pass@mcp.gostoa.dev/mcp/tools/call",
            "https://@mcp.gostoa.dev/mcp/tools/call",
            "https://example.com/foo\\bar",
            "https://example.com/foo%zzbar",
            "https://example.com/foo%",
            "https://example.com/foo%2",
            "https://example.com/foo%2g",
            "https://example.com/path with spaces",
            "https://example.com/foo^bar",
            "https://example.com/foo{bar}",
            "https://example.com/foo|bar",
        ];
        for bad in invalid_uris {
            assert!(!htu_matches(bad, bad), "expected rejection for '{bad}'");
            assert!(!htu_matches(bad, valid), "expected rejection for '{bad}'");
            assert!(!htu_matches(valid, bad), "expected rejection for '{bad}'");
        }
    }

    #[test]
    fn test_compute_ath() {
        let ath = compute_ath("test-token");
        assert!(!ath.is_empty());
        assert!(!ath.contains('='));
        assert!(!ath.contains('+'));
        assert!(!ath.contains('/'));
    }

    #[test]
    fn test_compute_ath_deterministic() {
        let ath1 = compute_ath("my-access-token");
        let ath2 = compute_ath("my-access-token");
        assert_eq!(ath1, ath2);
    }

    #[test]
    fn test_compute_ath_different_tokens() {
        let ath1 = compute_ath("token-a");
        let ath2 = compute_ath("token-b");
        assert_ne!(ath1, ath2);
    }

    #[test]
    fn test_jwk_has_private_key() {
        let public_only = DpopJwk {
            kty: "EC".to_string(),
            crv: Some("P-256".to_string()),
            x: Some("x-coord".to_string()),
            y: Some("y-coord".to_string()),
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        };
        assert!(!public_only.has_private_key());

        let with_private = DpopJwk {
            d: Some("private-d".to_string()),
            ..public_only
        };
        assert!(with_private.has_private_key());
    }

    #[test]
    fn test_jti_replay_detection() {
        let validator = DpopValidator::new(test_config());
        assert!(validator.check_replay("jkt-a", "unique-jti-1").is_ok());
        let err = validator.check_replay("jkt-a", "unique-jti-1").unwrap_err();
        assert!(matches!(err, DpopError::ReplayDetected(_)));
        // Same jti under a different key thumbprint is allowed (jti is scoped by jkt).
        assert!(validator.check_replay("jkt-b", "unique-jti-1").is_ok());
        assert!(validator.check_replay("jkt-a", "unique-jti-2").is_ok());
    }

    #[test]
    fn test_validate_iat_valid() {
        let validator = DpopValidator::new(test_config());
        let now = chrono::Utc::now().timestamp();
        assert!(validator.validate_iat(now).is_ok());
        assert!(validator.validate_iat(now - 60).is_ok());
        assert!(validator.validate_iat(now - 299).is_ok());
    }

    #[test]
    fn test_validate_iat_too_old() {
        let validator = DpopValidator::new(test_config());
        let now = chrono::Utc::now().timestamp();
        let err = validator.validate_iat(now - 301).unwrap_err();
        assert!(matches!(err, DpopError::ProofTooOld { .. }));
    }

    #[test]
    fn test_validate_iat_future() {
        let validator = DpopValidator::new(test_config());
        let now = chrono::Utc::now().timestamp();
        let err = validator.validate_iat(now + 31).unwrap_err();
        assert!(matches!(err, DpopError::ProofInFuture { .. }));
    }

    #[test]
    fn test_jwk_thumbprint_ec() {
        let jwk = DpopJwk {
            kty: "EC".to_string(),
            crv: Some("P-256".to_string()),
            x: Some("test-x".to_string()),
            y: Some("test-y".to_string()),
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        };
        let thumbprint = compute_jwk_thumbprint(&jwk);
        assert!(!thumbprint.is_empty());
        assert_eq!(thumbprint, compute_jwk_thumbprint(&jwk));
    }

    #[test]
    fn test_jwk_thumbprint_rsa() {
        let jwk = DpopJwk {
            kty: "RSA".to_string(),
            crv: None,
            x: None,
            y: None,
            n: Some("test-n".to_string()),
            e: Some("AQAB".to_string()),
            d: None,
            p: None,
            q: None,
        };
        let thumbprint = compute_jwk_thumbprint(&jwk);
        assert!(!thumbprint.is_empty());
    }

    #[test]
    fn test_default_config() {
        let config = DpopConfig::default();
        assert!(!config.enabled);
        assert!(!config.required);
        assert_eq!(config.max_age_secs, 300);
        assert_eq!(config.clock_skew_secs, 30);
        assert_eq!(config.jti_cache_ttl_secs, 600);
        assert_eq!(config.jti_cache_max, 100_000);
    }

    #[test]
    fn test_dpop_validator_creation() {
        let config = test_config();
        let validator = DpopValidator::new(config);
        assert!(validator.is_enabled());
        assert!(validator.is_required());
    }

    #[test]
    fn test_build_decoding_key_unsupported_kty() {
        let jwk = DpopJwk {
            kty: "oct".to_string(),
            crv: None,
            x: None,
            y: None,
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        };
        let result = build_decoding_key(&jwk, Algorithm::HS256);
        assert!(result.is_err());
        let err = result.err().unwrap();
        assert!(matches!(err, DpopError::UnsupportedKeyType(_)));
    }

    // =========================================================================
    // cnf.jkt binding tests (CAB-1605)
    // =========================================================================

    fn ec_test_jwk() -> DpopJwk {
        DpopJwk {
            kty: "EC".to_string(),
            crv: Some("P-256".to_string()),
            x: Some("test-x-coord".to_string()),
            y: Some("test-y-coord".to_string()),
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        }
    }

    #[test]
    fn test_cnf_jkt_binding_valid() {
        let jwk = ec_test_jwk();
        let expected_jkt = compute_jwk_thumbprint(&jwk);
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some(expected_jkt),
        };
        let result = DpopValidator::verify_cnf_binding(&jwk, &cnf);
        assert!(result.is_ok());
    }

    #[test]
    fn test_cnf_jkt_binding_mismatch() {
        let jwk = ec_test_jwk();
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some("wrong-thumbprint-value".to_string()),
        };
        let result = DpopValidator::verify_cnf_binding(&jwk, &cnf);
        assert!(result.is_err());
        assert!(matches!(result.unwrap_err(), DpopError::JktMismatch));
    }

    #[test]
    fn test_cnf_jkt_binding_missing_jkt() {
        // When cnf exists but has no jkt field, binding is not enforced
        let jwk = ec_test_jwk();
        let cnf = CnfClaim {
            x5t_s256: Some("cert-thumbprint".to_string()),
            jkt: None,
        };
        let result = DpopValidator::verify_cnf_binding(&jwk, &cnf);
        assert!(result.is_ok());
    }

    #[test]
    fn test_cnf_jkt_binding_rsa_key() {
        let jwk = DpopJwk {
            kty: "RSA".to_string(),
            crv: None,
            x: None,
            y: None,
            n: Some("test-modulus".to_string()),
            e: Some("AQAB".to_string()),
            d: None,
            p: None,
            q: None,
        };
        let expected_jkt = compute_jwk_thumbprint(&jwk);
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some(expected_jkt),
        };
        assert!(DpopValidator::verify_cnf_binding(&jwk, &cnf).is_ok());
    }

    #[test]
    fn test_cnf_jkt_binding_timing_safe() {
        // Verify that even similar thumbprints fail (no prefix bypass)
        let jwk = ec_test_jwk();
        let mut wrong_jkt = compute_jwk_thumbprint(&jwk);
        // Flip the last character
        let last = wrong_jkt.pop().unwrap_or('A');
        wrong_jkt.push(if last == 'A' { 'B' } else { 'A' });
        let cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some(wrong_jkt),
        };
        assert!(matches!(
            DpopValidator::verify_cnf_binding(&jwk, &cnf).unwrap_err(),
            DpopError::JktMismatch
        ));
    }

    #[test]
    fn test_replay_detection_is_atomic_under_concurrency() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        use std::sync::Barrier;

        let validator = Arc::new(DpopValidator::new(test_config()));
        let workers = 32;
        let barrier = Arc::new(Barrier::new(workers));
        let admitted = Arc::new(AtomicUsize::new(0));
        let rejected = Arc::new(AtomicUsize::new(0));

        let mut handles = Vec::with_capacity(workers);
        for _ in 0..workers {
            let v = Arc::clone(&validator);
            let b = Arc::clone(&barrier);
            let ok = Arc::clone(&admitted);
            let err = Arc::clone(&rejected);
            handles.push(std::thread::spawn(move || {
                b.wait();
                match v.check_replay("jkt-concurrent", "concurrent-jti-1") {
                    Ok(()) => {
                        ok.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(DpopError::ReplayDetected(_)) => {
                        err.fetch_add(1, Ordering::SeqCst);
                    }
                    Err(other) => panic!("unexpected error: {other}"),
                }
            }));
        }

        for h in handles {
            h.join().expect("worker thread panicked");
        }

        assert_eq!(admitted.load(Ordering::SeqCst), 1);
        assert_eq!(rejected.load(Ordering::SeqCst), workers - 1);
    }

    #[test]
    fn test_replay_bounds_per_key_cap_length_and_effective_ttl() {
        let cfg = DpopConfig {
            enabled: true,
            required: true,
            max_age_secs: 300,
            clock_skew_secs: 30,
            // Configured below max_age + skew; must clamp to >= 330s.
            jti_cache_ttl_secs: 10,
            jti_cache_max: 100,
        };
        let validator = DpopValidator::new(cfg).with_max_entries_per_key(2);
        assert_eq!(validator.effective_jti_ttl_secs(), 330);

        // Overlong jti (> 128 bytes) rejected without mutating table.
        let long_jti = "x".repeat(MAX_JTI_LEN + 1);
        assert!(matches!(
            validator.check_replay("jkt-a", &long_jti),
            Err(DpopError::JtiTooLong)
        ));

        // Key A hits its per-key cap of 2 and fails closed; Key B remains unaffected.
        assert!(validator.check_replay("jkt-a", "j1").is_ok());
        assert!(validator.check_replay("jkt-a", "j2").is_ok());
        assert!(matches!(
            validator.check_replay("jkt-a", "j3"),
            Err(DpopError::ReplayDetected(_))
        ));
        assert!(validator.check_replay("jkt-b", "j1").is_ok());
        assert!(validator.check_replay("jkt-b", "j2").is_ok());
    }

    #[test]
    fn test_jti_not_recorded_when_ath_or_cnf_binding_fails() {
        use aws_lc_rs::signature::{EcdsaKeyPair, KeyPair, ECDSA_P256_SHA256_FIXED_SIGNING};

        let pkcs8 = EcdsaKeyPair::generate_pkcs8(
            &ECDSA_P256_SHA256_FIXED_SIGNING,
            &aws_lc_rs::rand::SystemRandom::new(),
        )
        .unwrap();
        let kp =
            EcdsaKeyPair::from_pkcs8(&ECDSA_P256_SHA256_FIXED_SIGNING, pkcs8.as_ref()).unwrap();
        let pub_bytes = kp.public_key().as_ref();
        let jwk = DpopJwk {
            kty: "EC".to_string(),
            crv: Some("P-256".to_string()),
            x: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[1..33])),
            y: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[33..65])),
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        };
        let jkt = compute_jwk_thumbprint(&jwk);

        let sign_proof = |jti: &str, ath: Option<String>| -> String {
            let header = serde_json::json!({
                "typ": "dpop+jwt",
                "alg": "ES256",
                "jwk": {
                    "kty": jwk.kty,
                    "crv": jwk.crv,
                    "x": jwk.x,
                    "y": jwk.y,
                }
            });
            let mut payload = serde_json::json!({
                "jti": jti,
                "htm": "POST",
                "htu": "https://gw.example/mcp",
                "iat": chrono::Utc::now().timestamp(),
            });
            if let Some(a) = ath {
                payload["ath"] = serde_json::Value::String(a);
            }
            let input = format!(
                "{}.{}",
                URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header).unwrap()),
                URL_SAFE_NO_PAD.encode(serde_json::to_vec(&payload).unwrap()),
            );
            let sig = kp
                .sign(&aws_lc_rs::rand::SystemRandom::new(), input.as_bytes())
                .unwrap();
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        };

        let validator = DpopValidator::new(test_config());
        let access_token = "tok-abc";
        let good_cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some(jkt),
        };
        let bad_cnf = CnfClaim {
            x5t_s256: None,
            jkt: Some("wrong-thumbprint".to_string()),
        };

        // 1. Failing ath must NOT record jti.
        let bad_ath_proof = sign_proof("same-jti-1", Some("wrong-ath".to_string()));
        assert!(matches!(
            validator.validate(
                &bad_ath_proof,
                "POST",
                "https://gw.example/mcp",
                Some(access_token),
                Some(&good_cnf)
            ),
            Err(DpopError::AthMismatch)
        ));

        // 2. Failing cnf.jkt must NOT record jti.
        let valid_proof = sign_proof("same-jti-1", Some(compute_ath(access_token)));
        assert!(matches!(
            validator.validate(
                &valid_proof,
                "POST",
                "https://gw.example/mcp",
                Some(access_token),
                Some(&bad_cnf)
            ),
            Err(DpopError::JktMismatch)
        ));

        // 3. Same jti now succeeds once both ath and cnf.jkt match, then replays are blocked.
        assert!(validator
            .validate(
                &valid_proof,
                "POST",
                "https://gw.example/mcp",
                Some(access_token),
                Some(&good_cnf)
            )
            .is_ok());
        assert!(matches!(
            validator.validate(
                &valid_proof,
                "POST",
                "https://gw.example/mcp",
                Some(access_token),
                Some(&good_cnf)
            ),
            Err(DpopError::ReplayDetected(_))
        ));
    }

    #[test]
    fn test_validate_htu_comparison_rules() {
        use aws_lc_rs::signature::{EcdsaKeyPair, KeyPair, ECDSA_P256_SHA256_FIXED_SIGNING};

        let pkcs8 = EcdsaKeyPair::generate_pkcs8(
            &ECDSA_P256_SHA256_FIXED_SIGNING,
            &aws_lc_rs::rand::SystemRandom::new(),
        )
        .unwrap();
        let kp =
            EcdsaKeyPair::from_pkcs8(&ECDSA_P256_SHA256_FIXED_SIGNING, pkcs8.as_ref()).unwrap();
        let pub_bytes = kp.public_key().as_ref();
        let jwk = DpopJwk {
            kty: "EC".to_string(),
            crv: Some("P-256".to_string()),
            x: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[1..33])),
            y: Some(URL_SAFE_NO_PAD.encode(&pub_bytes[33..65])),
            n: None,
            e: None,
            d: None,
            p: None,
            q: None,
        };

        let sign_proof = |jti: &str, htu: &str| -> String {
            let header = serde_json::json!({
                "typ": "dpop+jwt",
                "alg": "ES256",
                "jwk": {
                    "kty": jwk.kty,
                    "crv": jwk.crv,
                    "x": jwk.x,
                    "y": jwk.y,
                }
            });
            let payload = serde_json::json!({
                "jti": jti,
                "htm": "POST",
                "htu": htu,
                "iat": chrono::Utc::now().timestamp(),
            });
            let input = format!(
                "{}.{}",
                URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header).unwrap()),
                URL_SAFE_NO_PAD.encode(serde_json::to_vec(&payload).unwrap()),
            );
            let sig = kp
                .sign(&aws_lc_rs::rand::SystemRandom::new(), input.as_bytes())
                .unwrap();
            format!("{input}.{}", URL_SAFE_NO_PAD.encode(sig.as_ref()))
        };

        let validator = DpopValidator::new(test_config());
        let req_uri = "https://gw.example/mcp/Tools";
        let req_with_qf = "https://gw.example/mcp/Tools?foo=bar#frag";

        // Scheme/host case-insensitivity and default port equivalence succeed.
        let accepted = sign_proof("htu-ok-1", "HTTPS://GW.EXAMPLE:443/mcp/Tools");
        let res = validator.validate(&accepted, "POST", req_with_qf, None, None);
        assert!(res.is_ok());

        // Path case mismatch, non-equivalent port, userinfo, and relative URI fail.
        let rejected_htus = [
            "https://gw.example/mcp/tools",
            "https://gw.example:8443/mcp/Tools",
            "https://user@gw.example/mcp/Tools",
            "/mcp/Tools",
        ];
        for (idx, bad_htu) in rejected_htus.into_iter().enumerate() {
            let jti = format!("htu-bad-{idx}");
            let proof = sign_proof(&jti, bad_htu);
            let res = validator.validate(&proof, "POST", req_uri, None, None);
            assert!(matches!(res, Err(DpopError::HtuMismatch { .. })));
        }
    }
}
