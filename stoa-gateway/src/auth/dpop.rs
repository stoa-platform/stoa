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
//! 9. Verify `jti` is unique (replay prevention)
//! 10. If access token bound, verify `ath` = SHA-256(access_token)

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use moka::sync::Cache;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::sync::Arc;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, warn};

use crate::metrics;

// =============================================================================
// Configuration
// =============================================================================

/// DPoP configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DpopConfig {
    /// Enable DPoP validation (default: false — opt-in)
    #[serde(default)]
    pub enabled: bool,

    /// Require DPoP proof on all token-authenticated requests.
    /// When false, DPoP is optional (opportunistic binding).
    #[serde(default)]
    pub required: bool,

    /// Maximum age of DPoP proof in seconds (default: 300 = 5 min).
    /// Proofs with `iat` older than this are rejected.
    #[serde(default = "default_max_age_secs")]
    pub max_age_secs: u64,

    /// Maximum clock skew tolerance in seconds (default: 30).
    #[serde(default = "default_clock_skew_secs")]
    pub clock_skew_secs: u64,

    /// JTI cache TTL in seconds (for replay prevention). Default: 600 = 10 min.
    /// Should be >= 2 * max_age_secs to catch all replays.
    #[serde(default = "default_jti_cache_ttl_secs")]
    pub jti_cache_ttl_secs: u64,

    /// Maximum JTI cache entries (default: 100_000).
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

    #[error("DPoP proof replay detected (jti: '{0}')")]
    ReplayDetected(String),

    #[error("invalid DPoP proof: ath mismatch (access token hash does not match)")]
    AthMismatch,

    #[error("invalid DPoP proof: missing 'ath' claim for token binding")]
    MissingAth,
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

/// DPoP proof validator with JTI replay cache.
#[derive(Clone)]
pub struct DpopValidator {
    config: DpopConfig,
    /// JTI replay cache: maps jti → () with TTL expiry.
    jti_cache: Arc<Cache<String, ()>>,
}

impl DpopValidator {
    /// Create a new DPoP validator with the given config.
    pub fn new(config: DpopConfig) -> Self {
        let jti_cache = Cache::builder()
            .max_capacity(config.jti_cache_max)
            .time_to_live(Duration::from_secs(config.jti_cache_ttl_secs))
            .build();

        Self {
            config,
            jti_cache: Arc::new(jti_cache),
        }
    }

    /// Validate a DPoP proof.
    ///
    /// # Arguments
    /// - `dpop_header`: The raw DPoP proof JWT from the `DPoP` HTTP header
    /// - `http_method`: The HTTP method of the current request (e.g., "POST")
    /// - `http_uri`: The HTTP target URI (scheme + authority + path)
    /// - `access_token`: Optional access token for `ath` binding verification
    pub fn validate(
        &self,
        dpop_header: &str,
        http_method: &str,
        http_uri: &str,
        access_token: Option<&str>,
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

        // Step 9: Verify jti (replay prevention)
        let jti = claims.jti.as_deref().ok_or(DpopError::MissingJti)?;
        if jti.is_empty() {
            return Err(DpopError::MissingJti);
        }
        self.check_replay(jti)?;

        // Step 10: Verify ath (access token hash) if access_token provided
        if let Some(token) = access_token {
            let expected_ath = compute_ath(token);
            let proof_ath = claims.ath.as_deref().ok_or(DpopError::MissingAth)?;
            if proof_ath != expected_ath {
                metrics::record_dpop_validation("ath_mismatch");
                return Err(DpopError::AthMismatch);
            }
        }

        metrics::record_dpop_validation("success");
        debug!("DPoP proof validated successfully (jti={jti})");
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

    /// Check JTI for replay. Returns Err if already seen.
    fn check_replay(&self, jti: &str) -> Result<(), DpopError> {
        if self.jti_cache.get(jti).is_some() {
            warn!("DPoP replay detected: jti={jti}");
            metrics::record_dpop_validation("replay");
            return Err(DpopError::ReplayDetected(jti.to_string()));
        }
        self.jti_cache.insert(jti.to_string(), ());
        Ok(())
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

/// Compare `htu` from the proof with the actual request URI.
/// Per RFC 9449 Section 4.3: comparison is case-insensitive for scheme/host,
/// and query/fragment components of the URI are ignored.
fn htu_matches(htu: &str, request_uri: &str) -> bool {
    let htu_clean = strip_query_fragment(htu);
    let uri_clean = strip_query_fragment(request_uri);
    htu_clean.eq_ignore_ascii_case(&uri_clean)
}

/// Strip query string and fragment from a URI.
fn strip_query_fragment(s: &str) -> String {
    let without_fragment = s.split('#').next().unwrap_or(s);
    without_fragment
        .split('?')
        .next()
        .unwrap_or(without_fragment)
        .to_string()
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
        assert!(htu_matches(
            "https://mcp.gostoa.dev/mcp/tools/call",
            "https://mcp.gostoa.dev/mcp/tools/call"
        ));
    }

    #[test]
    fn test_htu_matches_ignores_query() {
        assert!(htu_matches(
            "https://mcp.gostoa.dev/mcp/tools/call",
            "https://mcp.gostoa.dev/mcp/tools/call?foo=bar"
        ));
    }

    #[test]
    fn test_htu_matches_ignores_fragment() {
        assert!(htu_matches(
            "https://mcp.gostoa.dev/mcp/tools/call",
            "https://mcp.gostoa.dev/mcp/tools/call#section"
        ));
    }

    #[test]
    fn test_htu_matches_case_insensitive() {
        assert!(htu_matches(
            "HTTPS://MCP.GOSTOA.DEV/mcp/tools/call",
            "https://mcp.gostoa.dev/mcp/tools/call"
        ));
    }

    #[test]
    fn test_htu_mismatch_different_path() {
        assert!(!htu_matches(
            "https://mcp.gostoa.dev/mcp/tools/list",
            "https://mcp.gostoa.dev/mcp/tools/call"
        ));
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
        assert!(validator.check_replay("unique-jti-1").is_ok());
        let err = validator.check_replay("unique-jti-1").unwrap_err();
        assert!(matches!(err, DpopError::ReplayDetected(_)));
        assert!(validator.check_replay("unique-jti-2").is_ok());
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
}
