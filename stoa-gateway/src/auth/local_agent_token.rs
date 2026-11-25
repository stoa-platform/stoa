//! Dedicated local RS256 token issuer and validator for autonomous agent roles PoC.
//!
//! Architectural invariants enforced by this module:
//! - Strictly separated from the OIDC `JwtValidator` / `OidcProvider` (no shared keys).
//! - Mandatory `kid` header matched against the active in-memory key (no fallback key).
//! - Strict `RS256` algorithm enforcement.
//! - Ephemeral 2048-bit RSA keypair generated in memory at gateway startup and never exported;
//!   gateway restart invalidates all previously issued local tokens.
//! - Ephemeral tokens are never logged and redacted in `Debug`.
//! - Every PoC token is sender-constrained via `cnf.jkt` and validated with a DPoP proof
//!   (`htm`, `htu`, `ath`, `cnf.jkt`) using atomic replay detection.
//! - Child tokens carry their own `iss` (`stoa-poc-delegation`), canonical target resource `aud`
//!   (`mcp-tool:{tenant}:{tool}`, never the generic MCP audience), `act`, `chain_id`, `jti`,
//!   `depth` (`<= 3`), `parent_jti`, inherited non-empty `tenant_id`, and `exp <= parent.exp`.

use std::collections::{HashMap, HashSet};
use std::fmt;

use aws_lc_rs::encoding::{AsDer, Pkcs8V1Der};
use aws_lc_rs::rsa::{KeyPair, KeySize, PublicKeyComponents};
use aws_lc_rs::signature::KeyPair as _;
use axum::http::header::AUTHORIZATION;
use axum::http::HeaderMap;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use jsonwebtoken::{
    decode, decode_header, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use subtle::ConstantTimeEq;
use thiserror::Error;
use uuid::Uuid;

use crate::auth::claims::CnfClaim;
use crate::auth::dpop::{compute_jwk_thumbprint, DpopConfig, DpopError, DpopJwk, DpopValidator};
use crate::control_plane::role_policy::ArgumentConstraint;

/// Issuer for local parent agent tokens minted by the gateway in PoC mode.
pub const LOCAL_AGENT_ISSUER: &str = "stoa-poc-local";

/// Issuer for delegated child agent tokens minted by the gateway delegation endpoint.
pub const DELEGATION_ISSUER: &str = "stoa-poc-delegation";

/// Maximum permitted delegation depth (`0` = parent, `1..=3` = children).
pub const MAX_DELEGATION_DEPTH: u8 = 3;

/// Maximum permitted lifetime for a local ephemeral token (15 minutes).
pub const MAX_LOCAL_TOKEN_TTL_SECS: i64 = 900;

/// Generic MCP gateway audience that child tokens must never target.
pub const FORBIDDEN_CHILD_AUDIENCE: &str = "stoa-mcp-gateway";

/// Canonical resource audience for a tool-scoped delegated child token.
pub fn canonical_tool_audience(tenant_id: &str, tool_name: &str) -> String {
    format!("mcp-tool:{tenant_id}:{tool_name}")
}

/// Errors produced by local RS256 token issuance or verification.
#[derive(Debug, Error)]
pub enum LocalTokenError {
    #[error("key generation failed: {0}")]
    KeyGeneration(String),

    #[error("invalid token request: {0}")]
    InvalidRequest(&'static str),

    #[error("delegation denied: {0}")]
    DelegationDenied(&'static str),

    #[error("token signing failed")]
    SigningFailed,

    #[error("missing Authorization DPoP header")]
    MissingAuthorization,

    #[error("Authorization header must use the DPoP scheme")]
    InvalidAuthScheme,

    #[error("missing DPoP proof header")]
    MissingDpopHeader,

    #[error("invalid token header")]
    InvalidHeader,

    #[error("unsupported algorithm; only RS256 is accepted")]
    UnsupportedAlgorithm,

    #[error("missing kid header")]
    MissingKid,

    #[error("unknown kid")]
    UnknownKid,

    #[error("token validation failed")]
    InvalidToken,

    #[error("invalid claims: {0}")]
    InvalidClaims(&'static str),

    #[error("DPoP validation failed: {0}")]
    DpopFailed(#[from] DpopError),
}

/// Verified claims of a local RS256 agent token.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalAgentClaims {
    pub iss: String,
    pub sub: String,
    /// Exact target resource audience (always a single string).
    pub aud: String,
    pub tenant_id: String,
    pub role: String,
    pub chain_id: String,
    pub jti: String,
    pub depth: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parent_jti: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub act: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub policy_version: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub allowed_tools: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub arg_constraints: Option<HashMap<String, ArgumentConstraint>>,
    pub iat: i64,
    pub exp: i64,
    pub cnf: CnfClaim,
}

impl LocalAgentClaims {
    /// Return the stable root caller subject across a delegation chain.
    ///
    /// Walks nested RFC 8693 `act` claims to the originating depth-0 subject so delegated child
    /// tokens debit the same caller-level budget as their root caller.
    pub fn root_caller_sub(&self) -> &str {
        let mut cursor = self.act.as_ref();
        let mut root_sub: Option<&str> = None;
        while let Some(node) = cursor {
            if let Some(sub) = node.get("sub").and_then(Value::as_str) {
                if !sub.is_empty() {
                    root_sub = Some(sub);
                }
            }
            cursor = node.get("act");
        }
        root_sub.unwrap_or(self.sub.as_str())
    }
}

/// Request to mint an initial parent token (`depth = 0`) in autonomous PoC mode.
#[derive(Debug, Clone)]
pub struct IssueParentTokenRequest {
    pub sub: String,
    pub tenant_id: String,
    pub role: String,
    pub aud: String,
    pub cnf_jkt: String,
    pub ttl_secs: i64,
    pub policy_version: Option<u64>,
}

/// Request to mint a delegated child token (`depth = parent.depth + 1 <= 3`).
#[derive(Debug, Clone)]
pub struct DelegateChildTokenRequest {
    pub sub: String,
    pub target_tool: String,
    pub child_dpop_jwk: DpopJwk,
    pub allowed_tools: Vec<String>,
    pub arg_constraints: Option<HashMap<String, ArgumentConstraint>>,
    pub ttl_secs: Option<i64>,
}

/// Ephemeral token returned by local issuance; redacted in `Debug`.
#[derive(Clone)]
pub struct IssuedLocalToken {
    token: String,
    pub claims: LocalAgentClaims,
}

impl IssuedLocalToken {
    /// Access the compact JWS string for returning directly to the authenticated caller.
    pub fn as_str(&self) -> &str {
        &self.token
    }
}

impl fmt::Debug for IssuedLocalToken {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("IssuedLocalToken")
            .field("token", &"[REDACTED]")
            .field("claims", &self.claims)
            .finish()
    }
}

/// Dedicated local RS256 keypair, validator, and atomic DPoP verifier.
///
/// Never shares keys with `JwtValidator` / `OidcProvider` and never exports private key bytes.
pub struct LocalAgentAuth {
    kid: String,
    encoding_key: EncodingKey,
    decoding_key: DecodingKey,
    dpop: DpopValidator,
}

impl fmt::Debug for LocalAgentAuth {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("LocalAgentAuth")
            .field("kid", &self.kid)
            .field("encoding_key", &"[REDACTED]")
            .field("decoding_key", &"[REDACTED]")
            .finish()
    }
}

fn build_act_chain(parent: &LocalAgentClaims) -> Value {
    match &parent.act {
        Some(prev) => json!({ "sub": parent.sub, "act": prev }),
        None => json!({ "sub": parent.sub }),
    }
}

impl LocalAgentAuth {
    /// Generate a fresh ephemeral 2048-bit RS256 keypair in memory for this gateway boot.
    pub fn new() -> Result<Self, LocalTokenError> {
        let keypair = KeyPair::generate(KeySize::Rsa2048)
            .map_err(|_| LocalTokenError::KeyGeneration("RSA-2048 generation failed".into()))?;
        let der: Pkcs8V1Der<'_> = keypair
            .as_der()
            .map_err(|_| LocalTokenError::KeyGeneration("PKCS#8 encoding failed".into()))?;
        let pem = pem::encode(&pem::Pem::new("PRIVATE KEY", der.as_ref()));
        let encoding_key = EncodingKey::from_rsa_pem(pem.as_bytes())
            .map_err(|e| LocalTokenError::KeyGeneration(e.to_string()))?;
        drop(pem);

        let public = PublicKeyComponents::<Vec<u8>>::from(keypair.public_key());
        let n_b64 = URL_SAFE_NO_PAD.encode(&public.n);
        let e_b64 = URL_SAFE_NO_PAD.encode(&public.e);
        let decoding_key = DecodingKey::from_rsa_components(&n_b64, &e_b64)
            .map_err(|e| LocalTokenError::KeyGeneration(e.to_string()))?;

        let kid = format!("local-rs256-{}", Uuid::new_v4());
        let dpop = DpopValidator::new(DpopConfig {
            enabled: true,
            required: true,
            max_age_secs: 300,
            clock_skew_secs: 30,
            jti_cache_ttl_secs: 600,
            jti_cache_max: 100_000,
        });

        Ok(Self {
            kid,
            encoding_key,
            decoding_key,
            dpop,
        })
    }

    /// Public identifier of the active boot-ephemeral signing key.
    pub fn kid(&self) -> &str {
        &self.kid
    }

    /// Validate a bootstrap DPoP proof (before a token exists) and return its RFC 7638 JWK thumbprint.
    pub fn validate_bootstrap_dpop(
        &self,
        headers: &HeaderMap,
        http_method: &str,
        expected_htu: &str,
    ) -> Result<String, LocalTokenError> {
        let dpop_header = headers
            .get("DPoP")
            .and_then(|v| v.to_str().ok())
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .ok_or(LocalTokenError::MissingDpopHeader)?;

        let jwk = self
            .dpop
            .validate(dpop_header, http_method, expected_htu, None, None)?;
        let jkt = compute_jwk_thumbprint(&jwk);
        if jkt.is_empty() {
            return Err(LocalTokenError::InvalidClaims("empty DPoP JWK thumbprint"));
        }
        Ok(jkt)
    }

    /// Issue a short-lived parent token (`depth = 0`) bound to `req.cnf_jkt`.
    pub fn issue_parent_token(
        &self,
        req: IssueParentTokenRequest,
    ) -> Result<IssuedLocalToken, LocalTokenError> {
        if req.sub.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest("sub must not be empty"));
        }
        if crate::telemetry::validated_tenant(Some(req.tenant_id.as_str())).is_none() {
            return Err(LocalTokenError::InvalidRequest(
                "invalid or empty tenant_id",
            ));
        }
        if req.role.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest("role must not be empty"));
        }
        if req.aud.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest("aud must not be empty"));
        }
        if req.cnf_jkt.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest("cnf_jkt must not be empty"));
        }
        if req.ttl_secs <= 0 || req.ttl_secs > MAX_LOCAL_TOKEN_TTL_SECS {
            return Err(LocalTokenError::InvalidRequest(
                "ttl_secs must be between 1 and 900",
            ));
        }

        let now = chrono::Utc::now().timestamp();
        let claims = LocalAgentClaims {
            iss: LOCAL_AGENT_ISSUER.to_string(),
            sub: req.sub.trim().to_string(),
            aud: req.aud.trim().to_string(),
            tenant_id: req.tenant_id.trim().to_string(),
            role: req.role.trim().to_string(),
            chain_id: format!("chain-{}", Uuid::new_v4()),
            jti: format!("jti-{}", Uuid::new_v4()),
            depth: 0,
            parent_jti: None,
            act: None,
            policy_version: req.policy_version,
            allowed_tools: None,
            arg_constraints: None,
            iat: now,
            exp: now + req.ttl_secs,
            cnf: CnfClaim {
                x5t_s256: None,
                jkt: Some(req.cnf_jkt.trim().to_string()),
            },
        };

        self.sign_claims(claims)
    }

    /// Issue a delegated child token strictly included in `parent` (`depth = parent.depth + 1 <= 3`).
    pub fn issue_child_token(
        &self,
        parent: &LocalAgentClaims,
        parent_effective_tools: &HashSet<String>,
        parent_tool_constraints: Option<&HashMap<String, ArgumentConstraint>>,
        req: DelegateChildTokenRequest,
    ) -> Result<IssuedLocalToken, LocalTokenError> {
        if req.sub.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest("sub must not be empty"));
        }
        if crate::telemetry::validated_tenant(Some(parent.tenant_id.as_str())).is_none() {
            return Err(LocalTokenError::DelegationDenied(
                "parent tenant_id is empty or invalid",
            ));
        }
        let target_tool = req.target_tool.trim();
        if target_tool.is_empty() {
            return Err(LocalTokenError::InvalidRequest(
                "target_tool must not be empty",
            ));
        }
        if parent.depth >= MAX_DELEGATION_DEPTH {
            return Err(LocalTokenError::DelegationDenied(
                "delegation depth exceeds maximum of 3",
            ));
        }
        if req.child_dpop_jwk.has_private_key() {
            return Err(LocalTokenError::InvalidRequest(
                "child_dpop_jwk must be a public JWK",
            ));
        }
        let child_jkt = compute_jwk_thumbprint(&req.child_dpop_jwk);
        if child_jkt.is_empty() {
            return Err(LocalTokenError::InvalidRequest(
                "invalid child_dpop_jwk thumbprint",
            ));
        }

        // Strict tool inclusion: every delegated tool must be permitted for the parent.
        if req.allowed_tools.is_empty() {
            return Err(LocalTokenError::DelegationDenied(
                "allowed_tools must not be empty",
            ));
        }
        let mut deduped_tools = Vec::new();
        for tool in &req.allowed_tools {
            let trimmed = tool.trim();
            if trimmed.is_empty() || !parent_effective_tools.contains(trimmed) {
                return Err(LocalTokenError::DelegationDenied(
                    "requested tool is outside parent scope",
                ));
            }
            if let Some(ref parent_list) = parent.allowed_tools {
                if !parent_list.iter().any(|t| t == trimmed) {
                    return Err(LocalTokenError::DelegationDenied(
                        "requested tool is outside parent delegated scope",
                    ));
                }
            }
            if !deduped_tools.iter().any(|t| t == trimmed) {
                deduped_tools.push(trimmed.to_string());
            }
        }
        if !deduped_tools.iter().any(|t| t == target_tool) {
            return Err(LocalTokenError::DelegationDenied(
                "target_tool must be included in allowed_tools",
            ));
        }

        // Strict argument constraint inclusion: child may only narrow or add constraints.
        let mut effective_parent_constraints: HashMap<String, ArgumentConstraint> =
            parent_tool_constraints.cloned().unwrap_or_default();
        if let Some(ref parent_tok_constraints) = parent.arg_constraints {
            for (k, v) in parent_tok_constraints {
                effective_parent_constraints.insert(k.clone(), v.clone());
            }
        }
        let merged_constraints = if let Some(child_constraints) = req.arg_constraints {
            let mut merged = effective_parent_constraints.clone();
            for (arg_name, child_c) in child_constraints {
                if let Some(parent_c) = effective_parent_constraints.get(&arg_name) {
                    if !child_c.is_subset_of(parent_c) {
                        return Err(LocalTokenError::DelegationDenied(
                            "child argument constraint widens parent constraint",
                        ));
                    }
                }
                merged.insert(arg_name, child_c);
            }
            Some(merged)
        } else if !effective_parent_constraints.is_empty() {
            Some(effective_parent_constraints)
        } else {
            None
        };

        // Child exp must strictly be <= parent.exp and strictly in the future.
        let now = chrono::Utc::now().timestamp();
        let remaining_parent = parent.exp - now;
        if remaining_parent <= 0 {
            return Err(LocalTokenError::DelegationDenied("parent token expired"));
        }
        let child_ttl = match req.ttl_secs {
            Some(requested) => {
                if requested <= 0 || requested > MAX_LOCAL_TOKEN_TTL_SECS {
                    return Err(LocalTokenError::InvalidRequest(
                        "ttl_secs must be between 1 and 900",
                    ));
                }
                if requested > remaining_parent {
                    return Err(LocalTokenError::DelegationDenied(
                        "child exp must not exceed parent exp",
                    ));
                }
                requested
            }
            None => remaining_parent.min(120),
        };

        let aud = canonical_tool_audience(&parent.tenant_id, target_tool);
        if aud == FORBIDDEN_CHILD_AUDIENCE {
            return Err(LocalTokenError::DelegationDenied(
                "child audience cannot be generic MCP audience",
            ));
        }

        let claims = LocalAgentClaims {
            iss: DELEGATION_ISSUER.to_string(),
            sub: req.sub.trim().to_string(),
            aud,
            tenant_id: parent.tenant_id.clone(),
            role: parent.role.clone(),
            chain_id: parent.chain_id.clone(),
            jti: format!("jti-{}", Uuid::new_v4()),
            depth: parent.depth + 1,
            parent_jti: Some(parent.jti.clone()),
            act: Some(build_act_chain(parent)),
            policy_version: parent.policy_version,
            allowed_tools: Some(deduped_tools),
            arg_constraints: merged_constraints,
            iat: now,
            exp: now + child_ttl,
            cnf: CnfClaim {
                x5t_s256: None,
                jkt: Some(child_jkt),
            },
        };

        self.sign_claims(claims)
    }

    fn sign_claims(&self, claims: LocalAgentClaims) -> Result<IssuedLocalToken, LocalTokenError> {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(self.kid.clone());
        let token = encode(&header, &claims, &self.encoding_key)
            .map_err(|_| LocalTokenError::SigningFailed)?;
        Ok(IssuedLocalToken { token, claims })
    }

    #[cfg(test)]
    pub(crate) fn sign_claims_for_test(
        &self,
        claims: LocalAgentClaims,
    ) -> Result<IssuedLocalToken, LocalTokenError> {
        self.sign_claims(claims)
    }

    /// Decode and verify signature, `RS256`, mandatory matching `kid`, `exp`, `iss`, and
    /// structural claim invariants, then validate exact `aud` via `expected_aud_for`.
    pub fn validate_token_with_audience_fn<F>(
        &self,
        token: &str,
        expected_issuer: Option<&str>,
        expected_aud_for: F,
    ) -> Result<LocalAgentClaims, LocalTokenError>
    where
        F: FnOnce(&LocalAgentClaims) -> Result<String, LocalTokenError>,
    {
        let header = decode_header(token).map_err(|_| LocalTokenError::InvalidHeader)?;
        if header.alg != Algorithm::RS256 {
            return Err(LocalTokenError::UnsupportedAlgorithm);
        }

        let kid = header
            .kid
            .as_deref()
            .filter(|k| !k.trim().is_empty())
            .ok_or(LocalTokenError::MissingKid)?;
        if !bool::from(kid.as_bytes().ct_eq(self.kid.as_bytes())) {
            return Err(LocalTokenError::UnknownKid);
        }

        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = true;
        validation.validate_nbf = true;
        validation.validate_aud = false; // Checked strictly below via expected_aud_for.
        validation.leeway = 0;
        validation.set_required_spec_claims(&["exp", "iss", "aud", "sub"]);
        if let Some(iss) = expected_issuer {
            validation.set_issuer(&[iss]);
        } else {
            validation.set_issuer(&[LOCAL_AGENT_ISSUER, DELEGATION_ISSUER]);
        }

        let data = decode::<LocalAgentClaims>(token, &self.decoding_key, &validation)
            .map_err(|_| LocalTokenError::InvalidToken)?;
        let claims = data.claims;

        if claims.exp <= chrono::Utc::now().timestamp() {
            return Err(LocalTokenError::InvalidToken);
        }

        let expected_audience = expected_aud_for(&claims)?;
        if expected_audience.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest(
                "expected_audience must not be empty",
            ));
        }

        Self::validate_claims_invariants(&claims, &expected_audience)?;
        Ok(claims)
    }

    /// Validate a local RS256 token against a fixed expected audience.
    pub fn validate_token(
        &self,
        token: &str,
        expected_issuer: Option<&str>,
        expected_audience: &str,
    ) -> Result<LocalAgentClaims, LocalTokenError> {
        let aud = expected_audience.to_string();
        self.validate_token_with_audience_fn(token, expected_issuer, |_| Ok(aud))
    }

    fn validate_claims_invariants(
        claims: &LocalAgentClaims,
        expected_audience: &str,
    ) -> Result<(), LocalTokenError> {
        if claims.sub.trim().is_empty() {
            return Err(LocalTokenError::InvalidClaims("empty sub"));
        }
        if crate::telemetry::validated_tenant(Some(claims.tenant_id.as_str())).is_none() {
            return Err(LocalTokenError::InvalidClaims("invalid or empty tenant_id"));
        }
        if claims.role.trim().is_empty() {
            return Err(LocalTokenError::InvalidClaims("empty role"));
        }
        if claims.chain_id.trim().is_empty() {
            return Err(LocalTokenError::InvalidClaims("empty chain_id"));
        }
        if claims.jti.trim().is_empty() {
            return Err(LocalTokenError::InvalidClaims("empty jti"));
        }
        if claims.aud != expected_audience {
            return Err(LocalTokenError::InvalidClaims("audience mismatch"));
        }
        if claims.depth > MAX_DELEGATION_DEPTH {
            return Err(LocalTokenError::InvalidClaims("delegation depth exceeds 3"));
        }
        if claims
            .cnf
            .jkt
            .as_deref()
            .is_none_or(|jkt| jkt.trim().is_empty())
        {
            return Err(LocalTokenError::InvalidClaims("missing cnf.jkt binding"));
        }
        if claims.depth > 0 {
            if claims.iss != DELEGATION_ISSUER {
                return Err(LocalTokenError::InvalidClaims(
                    "child token must use delegation issuer",
                ));
            }
            if claims.aud == FORBIDDEN_CHILD_AUDIENCE {
                return Err(LocalTokenError::InvalidClaims(
                    "child token must not target generic MCP audience",
                ));
            }
            if claims
                .parent_jti
                .as_deref()
                .is_none_or(|p| p.trim().is_empty())
            {
                return Err(LocalTokenError::InvalidClaims("missing parent_jti"));
            }
            if claims.act.is_none() {
                return Err(LocalTokenError::InvalidClaims("missing act claim"));
            }
        } else if claims.iss != LOCAL_AGENT_ISSUER {
            return Err(LocalTokenError::InvalidClaims(
                "root token must use local issuer",
            ));
        }

        Ok(())
    }

    /// Validate an incoming HTTP/MCP request carrying `Authorization: DPoP <jwt>` + `DPoP: <proof>`,
    /// resolving the expected audience dynamically from the verified token's issuer/depth.
    pub fn validate_mcp_request_with_audience_fn<F>(
        &self,
        headers: &HeaderMap,
        http_method: &str,
        expected_htu: &str,
        expected_aud_for: F,
    ) -> Result<LocalAgentClaims, LocalTokenError>
    where
        F: FnOnce(&LocalAgentClaims) -> Result<String, LocalTokenError>,
    {
        let auth_header = headers
            .get(AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or(LocalTokenError::MissingAuthorization)?;

        let mut parts = auth_header.split_whitespace();
        let scheme = parts.next().ok_or(LocalTokenError::MissingAuthorization)?;
        let token = parts.next().ok_or(LocalTokenError::InvalidAuthScheme)?;
        if parts.next().is_some() || !scheme.eq_ignore_ascii_case("dpop") {
            return Err(LocalTokenError::InvalidAuthScheme);
        }

        let claims = self.validate_token_with_audience_fn(token, None, expected_aud_for)?;

        let dpop_header = headers
            .get("DPoP")
            .and_then(|v| v.to_str().ok())
            .map(str::trim)
            .filter(|v| !v.is_empty())
            .ok_or(LocalTokenError::MissingDpopHeader)?;

        self.dpop.validate(
            dpop_header,
            http_method,
            expected_htu,
            Some(token),
            Some(&claims.cnf),
        )?;

        Ok(claims)
    }

    /// Validate an incoming HTTP/MCP request carrying `Authorization: DPoP <jwt>` + `DPoP: <proof>`.
    pub fn validate_mcp_request(
        &self,
        headers: &HeaderMap,
        http_method: &str,
        expected_htu: &str,
        expected_audience: &str,
    ) -> Result<LocalAgentClaims, LocalTokenError> {
        let aud = expected_audience.to_string();
        self.validate_mcp_request_with_audience_fn(headers, http_method, expected_htu, |_| Ok(aud))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::dpop::compute_ath;
    use aws_lc_rs::signature::{EcdsaKeyPair, ECDSA_P256_SHA256_FIXED_SIGNING};
    use axum::http::HeaderValue;
    use serde_json::json;

    struct TestDpopKey {
        keypair: EcdsaKeyPair,
        jwk: DpopJwk,
        jkt: String,
    }

    impl TestDpopKey {
        fn generate() -> Self {
            let pkcs8 = EcdsaKeyPair::generate_pkcs8(
                &ECDSA_P256_SHA256_FIXED_SIGNING,
                &aws_lc_rs::rand::SystemRandom::new(),
            )
            .expect("generate EC P-256 key");
            let keypair =
                EcdsaKeyPair::from_pkcs8(&ECDSA_P256_SHA256_FIXED_SIGNING, pkcs8.as_ref())
                    .expect("parse EC key");
            let pub_bytes = keypair.public_key().as_ref();
            assert_eq!(pub_bytes.len(), 65);
            assert_eq!(pub_bytes[0], 0x04);
            let x = URL_SAFE_NO_PAD.encode(&pub_bytes[1..33]);
            let y = URL_SAFE_NO_PAD.encode(&pub_bytes[33..65]);
            let jwk = DpopJwk {
                kty: "EC".to_string(),
                crv: Some("P-256".to_string()),
                x: Some(x),
                y: Some(y),
                n: None,
                e: None,
                d: None,
                p: None,
                q: None,
            };
            let jkt = compute_jwk_thumbprint(&jwk);
            Self { keypair, jwk, jkt }
        }

        fn sign_proof(
            &self,
            htm: &str,
            htu: &str,
            jti: &str,
            access_token: Option<&str>,
        ) -> String {
            let header = json!({
                "typ": "dpop+jwt",
                "alg": "ES256",
                "jwk": {
                    "kty": self.jwk.kty,
                    "crv": self.jwk.crv,
                    "x": self.jwk.x,
                    "y": self.jwk.y,
                }
            });
            let mut claims = json!({
                "jti": jti,
                "htm": htm,
                "htu": htu,
                "iat": chrono::Utc::now().timestamp(),
            });
            if let Some(tok) = access_token {
                claims["ath"] = json!(compute_ath(tok));
            }
            let h_b64 = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&header).unwrap());
            let c_b64 = URL_SAFE_NO_PAD.encode(serde_json::to_vec(&claims).unwrap());
            let signing_input = format!("{h_b64}.{c_b64}");
            let rng = aws_lc_rs::rand::SystemRandom::new();
            let sig = self
                .keypair
                .sign(&rng, signing_input.as_bytes())
                .expect("sign DPoP proof");
            let s_b64 = URL_SAFE_NO_PAD.encode(sig.as_ref());
            format!("{signing_input}.{s_b64}")
        }
    }

    fn issue_sample_parent(auth: &LocalAgentAuth, dpop_key: &TestDpopKey) -> IssuedLocalToken {
        auth.issue_parent_token(IssueParentTokenRequest {
            sub: "agent-parent".to_string(),
            tenant_id: "acme".to_string(),
            role: "payments-reader".to_string(),
            aud: "http://stoa-gateway:8080/mcp/poc".to_string(),
            cnf_jkt: dpop_key.jkt.clone(),
            ttl_secs: 300,
            policy_version: Some(1),
        })
        .expect("issue parent token")
    }

    #[test]
    fn valid_parent_token_and_dpop_proof_pass() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&auth, &dpop_key);
        let htu = "http://stoa-gateway:8080/mcp/poc";
        let proof = dpop_key.sign_proof("POST", htu, "proof-1", Some(issued.as_str()));

        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("DPoP {}", issued.as_str())).unwrap(),
        );
        headers.insert("DPoP", HeaderValue::from_str(&proof).unwrap());

        let claims = auth
            .validate_mcp_request(&headers, "POST", htu, htu)
            .expect("valid request");
        assert_eq!(claims.tenant_id, "acme");
        assert_eq!(claims.role, "payments-reader");
        assert_eq!(claims.depth, 0);
        assert_eq!(claims.iss, LOCAL_AGENT_ISSUER);
    }

    #[test]
    fn missing_kid_is_rejected_without_fallback() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&auth, &dpop_key);

        let header = Header::new(Algorithm::RS256); // kid = None
        let token = encode(&header, &issued.claims, &auth.encoding_key).unwrap();
        let err = auth
            .validate_token(&token, None, "http://stoa-gateway:8080/mcp/poc")
            .unwrap_err();
        assert!(matches!(err, LocalTokenError::MissingKid));
    }

    #[test]
    fn non_rs256_algorithm_is_rejected() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&auth, &dpop_key);

        let mut header = Header::new(Algorithm::HS256);
        header.kid = Some(auth.kid().to_string());
        let token = encode(
            &header,
            &issued.claims,
            &EncodingKey::from_secret(b"not-an-rsa-key"),
        )
        .unwrap();

        let err = auth
            .validate_token(&token, None, "http://stoa-gateway:8080/mcp/poc")
            .unwrap_err();
        assert!(matches!(err, LocalTokenError::UnsupportedAlgorithm));
    }

    #[test]
    fn local_token_is_inactive_at_expiration() {
        let auth = LocalAgentAuth::new().unwrap();
        let key = TestDpopKey::generate();
        let mut claims = issue_sample_parent(&auth, &key).claims;
        let audience = claims.aud.clone();
        claims.exp = chrono::Utc::now().timestamp();
        let issued = auth.sign_claims(claims).unwrap();

        assert!(matches!(
            auth.validate_token(issued.as_str(), None, &audience),
            Err(LocalTokenError::InvalidToken)
        ));
    }

    #[test]
    fn token_from_previous_boot_or_external_key_is_rejected() {
        let boot1 = LocalAgentAuth::new().expect("boot1");
        let boot2 = LocalAgentAuth::new().expect("boot2");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&boot1, &dpop_key);

        let err = boot2
            .validate_token(issued.as_str(), None, "http://stoa-gateway:8080/mcp/poc")
            .unwrap_err();
        assert!(matches!(err, LocalTokenError::UnknownKid));

        let mut forged_header = Header::new(Algorithm::RS256);
        forged_header.kid = Some(boot2.kid().to_string());
        let forged = encode(&forged_header, &issued.claims, &boot1.encoding_key).unwrap();
        let err = boot2
            .validate_token(&forged, None, "http://stoa-gateway:8080/mcp/poc")
            .unwrap_err();
        assert!(matches!(err, LocalTokenError::InvalidToken));
    }

    #[test]
    fn dpop_replay_wrong_key_and_bearer_scheme_are_rejected() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let dpop_key = TestDpopKey::generate();
        let other_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&auth, &dpop_key);
        let htu = "http://stoa-gateway:8080/mcp/poc";

        let proof1 = dpop_key.sign_proof("POST", htu, "proof-bearer", Some(issued.as_str()));
        let mut bearer_headers = HeaderMap::new();
        bearer_headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("Bearer {}", issued.as_str())).unwrap(),
        );
        bearer_headers.insert("DPoP", HeaderValue::from_str(&proof1).unwrap());
        assert!(matches!(
            auth.validate_mcp_request(&bearer_headers, "POST", htu, htu)
                .unwrap_err(),
            LocalTokenError::InvalidAuthScheme
        ));

        let wrong_proof =
            other_key.sign_proof("POST", htu, "proof-wrong-key", Some(issued.as_str()));
        let mut wrong_headers = HeaderMap::new();
        wrong_headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("DPoP {}", issued.as_str())).unwrap(),
        );
        wrong_headers.insert("DPoP", HeaderValue::from_str(&wrong_proof).unwrap());
        assert!(matches!(
            auth.validate_mcp_request(&wrong_headers, "POST", htu, htu)
                .unwrap_err(),
            LocalTokenError::DpopFailed(DpopError::JktMismatch)
        ));

        let valid_proof = dpop_key.sign_proof("POST", htu, "proof-replay", Some(issued.as_str()));
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("DPoP {}", issued.as_str())).unwrap(),
        );
        headers.insert("DPoP", HeaderValue::from_str(&valid_proof).unwrap());
        assert!(auth
            .validate_mcp_request(&headers, "POST", htu, htu)
            .is_ok());
        assert!(matches!(
            auth.validate_mcp_request(&headers, "POST", htu, htu)
                .unwrap_err(),
            LocalTokenError::DpopFailed(DpopError::ReplayDetected(_))
        ));
    }

    #[test]
    fn child_delegation_enforces_claims_exp_depth_and_narrowing() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let parent_key = TestDpopKey::generate();
        let child_key = TestDpopKey::generate();
        let parent = issue_sample_parent(&auth, &parent_key);

        let parent_tools: HashSet<String> = ["payments_list".to_string()].into_iter().collect();
        let mut parent_constraints = HashMap::new();
        parent_constraints.insert(
            "limit".to_string(),
            ArgumentConstraint::MaxNumber { max: 100.0 },
        );

        // Requesting TTL exceeding parent's exp is rejected.
        let too_long = auth.issue_child_token(
            &parent.claims,
            &parent_tools,
            Some(&parent_constraints),
            DelegateChildTokenRequest {
                sub: "agent-child".to_string(),
                target_tool: "payments_list".to_string(),
                child_dpop_jwk: child_key.jwk.clone(),
                allowed_tools: vec!["payments_list".to_string()],
                arg_constraints: None,
                ttl_secs: Some(600),
            },
        );
        assert!(matches!(
            too_long,
            Err(LocalTokenError::DelegationDenied(_))
        ));

        // Widening parent constraint is rejected.
        let mut wider = HashMap::new();
        wider.insert(
            "limit".to_string(),
            ArgumentConstraint::MaxNumber { max: 200.0 },
        );
        let widened = auth.issue_child_token(
            &parent.claims,
            &parent_tools,
            Some(&parent_constraints),
            DelegateChildTokenRequest {
                sub: "agent-child".to_string(),
                target_tool: "payments_list".to_string(),
                child_dpop_jwk: child_key.jwk.clone(),
                allowed_tools: vec!["payments_list".to_string()],
                arg_constraints: Some(wider),
                ttl_secs: Some(60),
            },
        );
        assert!(matches!(widened, Err(LocalTokenError::DelegationDenied(_))));

        // Valid narrowed child token (depth 1 -> 2 -> 3 succeeds, 3 -> 4 rejected!).
        let mut narrower = HashMap::new();
        narrower.insert(
            "limit".to_string(),
            ArgumentConstraint::MaxNumber { max: 25.0 },
        );
        let c1 = auth
            .issue_child_token(
                &parent.claims,
                &parent_tools,
                Some(&parent_constraints),
                DelegateChildTokenRequest {
                    sub: "agent-child-1".to_string(),
                    target_tool: "payments_list".to_string(),
                    child_dpop_jwk: child_key.jwk.clone(),
                    allowed_tools: vec!["payments_list".to_string()],
                    arg_constraints: Some(narrower),
                    ttl_secs: Some(120),
                },
            )
            .expect("depth 1 child");
        assert_eq!(c1.claims.iss, DELEGATION_ISSUER);
        assert_eq!(c1.claims.aud, "mcp-tool:acme:payments_list");
        assert_eq!(c1.claims.tenant_id, "acme");
        assert_eq!(c1.claims.chain_id, parent.claims.chain_id);
        assert_eq!(
            c1.claims.parent_jti.as_deref(),
            Some(parent.claims.jti.as_str())
        );
        assert_eq!(c1.claims.depth, 1);
        assert!(c1.claims.exp <= parent.claims.exp);
        assert_eq!(c1.claims.act, Some(json!({ "sub": "agent-parent" })));

        let c2 = auth
            .issue_child_token(
                &c1.claims,
                &parent_tools,
                None,
                DelegateChildTokenRequest {
                    sub: "agent-child-2".to_string(),
                    target_tool: "payments_list".to_string(),
                    child_dpop_jwk: child_key.jwk.clone(),
                    allowed_tools: vec!["payments_list".to_string()],
                    arg_constraints: None,
                    ttl_secs: Some(90),
                },
            )
            .expect("depth 2 child");
        assert_eq!(c2.claims.depth, 2);

        let c3 = auth
            .issue_child_token(
                &c2.claims,
                &parent_tools,
                None,
                DelegateChildTokenRequest {
                    sub: "agent-child-3".to_string(),
                    target_tool: "payments_list".to_string(),
                    child_dpop_jwk: child_key.jwk.clone(),
                    allowed_tools: vec!["payments_list".to_string()],
                    arg_constraints: None,
                    ttl_secs: Some(60),
                },
            )
            .expect("depth 3 child");
        assert_eq!(c3.claims.depth, 3);

        // Depth 3 -> 4 MUST be rejected at issuance!
        let c4 = auth.issue_child_token(
            &c3.claims,
            &parent_tools,
            None,
            DelegateChildTokenRequest {
                sub: "agent-child-4".to_string(),
                target_tool: "payments_list".to_string(),
                child_dpop_jwk: child_key.jwk.clone(),
                allowed_tools: vec!["payments_list".to_string()],
                arg_constraints: None,
                ttl_secs: Some(30),
            },
        );
        assert!(matches!(c4, Err(LocalTokenError::DelegationDenied(_))));

        // Depth 4 crafted token MUST also be rejected at validation!
        let mut forged_c4 = c3.claims.clone();
        forged_c4.depth = 4;
        let forged_tok = auth.sign_claims(forged_c4).unwrap();
        assert!(matches!(
            auth.validate_token(forged_tok.as_str(), None, "mcp-tool:acme:payments_list")
                .unwrap_err(),
            LocalTokenError::InvalidClaims("delegation depth exceeds 3")
        ));
    }

    #[test]
    fn empty_and_whitespace_tenant_id_are_refused_on_issuance_validation_and_delegation() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let parent_key = TestDpopKey::generate();
        let child_key = TestDpopKey::generate();
        let audience = "http://stoa-gateway:8080/mcp/poc";

        for bad_tenant in ["", "   ", "\t\n"] {
            let err = auth
                .issue_parent_token(IssueParentTokenRequest {
                    sub: "agent-parent".to_string(),
                    tenant_id: bad_tenant.to_string(),
                    role: "payments-reader".to_string(),
                    aud: audience.to_string(),
                    cnf_jkt: parent_key.jkt.clone(),
                    ttl_secs: 300,
                    policy_version: Some(1),
                })
                .unwrap_err();
            assert!(matches!(
                err,
                LocalTokenError::InvalidRequest("invalid or empty tenant_id")
            ));
        }

        let parent = issue_sample_parent(&auth, &parent_key);
        let parent_tools: HashSet<String> = ["payments_list".to_string()].into_iter().collect();

        for bad_tenant in ["", "   "] {
            let mut empty_tenant_claims = parent.claims.clone();
            empty_tenant_claims.tenant_id = bad_tenant.to_string();
            let signed = auth.sign_claims(empty_tenant_claims.clone()).unwrap();
            let val_err = auth
                .validate_token(signed.as_str(), None, audience)
                .unwrap_err();
            assert!(matches!(
                val_err,
                LocalTokenError::InvalidClaims("invalid or empty tenant_id")
            ));

            let del_err = auth
                .issue_child_token(
                    &empty_tenant_claims,
                    &parent_tools,
                    None,
                    DelegateChildTokenRequest {
                        sub: "agent-child".to_string(),
                        target_tool: "payments_list".to_string(),
                        child_dpop_jwk: child_key.jwk.clone(),
                        allowed_tools: vec!["payments_list".to_string()],
                        arg_constraints: None,
                        ttl_secs: Some(60),
                    },
                )
                .unwrap_err();
            assert!(matches!(
                del_err,
                LocalTokenError::DelegationDenied("parent tenant_id is empty or invalid")
            ));
        }

        // A gateway-signed child token whose tenant_id is empty is also refused by validation.
        let valid_child = auth
            .issue_child_token(
                &parent.claims,
                &parent_tools,
                None,
                DelegateChildTokenRequest {
                    sub: "agent-child".to_string(),
                    target_tool: "payments_list".to_string(),
                    child_dpop_jwk: child_key.jwk,
                    allowed_tools: vec!["payments_list".to_string()],
                    arg_constraints: None,
                    ttl_secs: Some(60),
                },
            )
            .expect("issue valid child");
        let child_aud = valid_child.claims.aud.clone();
        let mut child_empty_tenant = valid_child.claims;
        child_empty_tenant.tenant_id = String::new();
        let signed_child = auth.sign_claims(child_empty_tenant).unwrap();
        let child_err = auth
            .validate_token(signed_child.as_str(), Some(DELEGATION_ISSUER), &child_aud)
            .unwrap_err();
        assert!(matches!(
            child_err,
            LocalTokenError::InvalidClaims("invalid or empty tenant_id")
        ));
    }

    #[test]
    fn child_tokens_strictly_inherit_parent_tenant_across_delegation_hops() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let parent_key = TestDpopKey::generate();
        let child_key = TestDpopKey::generate();
        let tenant = "tenant-beta";
        let parent = auth
            .issue_parent_token(IssueParentTokenRequest {
                sub: "agent-parent".to_string(),
                tenant_id: tenant.to_string(),
                role: "payments-reader".to_string(),
                aud: "http://stoa-gateway:8080/mcp/poc".to_string(),
                cnf_jkt: parent_key.jkt,
                ttl_secs: 300,
                policy_version: Some(1),
            })
            .expect("issue parent token");
        let parent_tools: HashSet<String> = ["payments_list".to_string()].into_iter().collect();
        let expected_aud = canonical_tool_audience(tenant, "payments_list");

        let mut current = parent.claims;
        for depth in 1..=MAX_DELEGATION_DEPTH {
            let child = auth
                .issue_child_token(
                    &current,
                    &parent_tools,
                    None,
                    DelegateChildTokenRequest {
                        sub: format!("agent-child-{depth}"),
                        target_tool: "payments_list".to_string(),
                        child_dpop_jwk: child_key.jwk.clone(),
                        allowed_tools: vec!["payments_list".to_string()],
                        arg_constraints: None,
                        ttl_secs: Some(60),
                    },
                )
                .expect("issue delegated child");
            assert_eq!(child.claims.depth, depth);
            assert_eq!(child.claims.tenant_id, tenant);
            assert_eq!(child.claims.aud, expected_aud);
            current = child.claims;
        }
    }

    #[test]
    fn child_token_cannot_target_or_be_validated_for_generic_mcp_audience() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let parent_key = TestDpopKey::generate();
        let child_key = TestDpopKey::generate();
        let parent = issue_sample_parent(&auth, &parent_key);
        let parent_tools: HashSet<String> = [
            "payments_list".to_string(),
            FORBIDDEN_CHILD_AUDIENCE.to_string(),
        ]
        .into_iter()
        .collect();

        // `issue_child_token` always emits a canonical tool audience, never the generic MCP aud.
        let child = auth
            .issue_child_token(
                &parent.claims,
                &parent_tools,
                None,
                DelegateChildTokenRequest {
                    sub: "agent-child".to_string(),
                    target_tool: "payments_list".to_string(),
                    child_dpop_jwk: child_key.jwk.clone(),
                    allowed_tools: vec!["payments_list".to_string()],
                    arg_constraints: None,
                    ttl_secs: Some(60),
                },
            )
            .expect("issue tool-scoped child");
        assert_ne!(child.claims.aud, FORBIDDEN_CHILD_AUDIENCE);
        assert_eq!(
            child.claims.aud,
            canonical_tool_audience("acme", "payments_list")
        );

        let edge_child = auth
            .issue_child_token(
                &parent.claims,
                &parent_tools,
                None,
                DelegateChildTokenRequest {
                    sub: "agent-child-edge".to_string(),
                    target_tool: FORBIDDEN_CHILD_AUDIENCE.to_string(),
                    child_dpop_jwk: child_key.jwk.clone(),
                    allowed_tools: vec![FORBIDDEN_CHILD_AUDIENCE.to_string()],
                    arg_constraints: None,
                    ttl_secs: Some(60),
                },
            )
            .expect("issue child for edge tool name");
        assert_ne!(edge_child.claims.aud, FORBIDDEN_CHILD_AUDIENCE);
        assert_eq!(
            edge_child.claims.aud,
            canonical_tool_audience("acme", FORBIDDEN_CHILD_AUDIENCE)
        );

        // Valid tool-scoped child passes for its canonical audience, fails against generic aud.
        assert!(auth
            .validate_token(child.as_str(), Some(DELEGATION_ISSUER), &child.claims.aud)
            .is_ok());
        let mismatch_err = auth
            .validate_token(
                child.as_str(),
                Some(DELEGATION_ISSUER),
                FORBIDDEN_CHILD_AUDIENCE,
            )
            .unwrap_err();
        assert!(matches!(
            mismatch_err,
            LocalTokenError::InvalidClaims("audience mismatch")
        ));
        let mismatch_any_iss = auth
            .validate_token(child.as_str(), None, FORBIDDEN_CHILD_AUDIENCE)
            .unwrap_err();
        assert!(matches!(
            mismatch_any_iss,
            LocalTokenError::InvalidClaims("audience mismatch")
        ));

        // Gateway-signed child token carrying FORBIDDEN_CHILD_AUDIENCE is refused even when the
        // validator's expected audience is FORBIDDEN_CHILD_AUDIENCE.
        let mut generic_claims = child.claims;
        generic_claims.aud = FORBIDDEN_CHILD_AUDIENCE.to_string();
        let forged = auth.sign_claims(generic_claims).unwrap();

        let err_delegation_iss = auth
            .validate_token(
                forged.as_str(),
                Some(DELEGATION_ISSUER),
                FORBIDDEN_CHILD_AUDIENCE,
            )
            .unwrap_err();
        assert!(matches!(
            err_delegation_iss,
            LocalTokenError::InvalidClaims("child token must not target generic MCP audience")
        ));

        let err_any_iss = auth
            .validate_token(forged.as_str(), None, FORBIDDEN_CHILD_AUDIENCE)
            .unwrap_err();
        assert!(matches!(
            err_any_iss,
            LocalTokenError::InvalidClaims("child token must not target generic MCP audience")
        ));

        let htu = "http://stoa-gateway:8080/mcp/poc";
        let proof = child_key.sign_proof("POST", htu, "proof-generic-aud", Some(forged.as_str()));
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_str(&format!("DPoP {}", forged.as_str())).unwrap(),
        );
        headers.insert("DPoP", HeaderValue::from_str(&proof).unwrap());
        let req_err = auth
            .validate_mcp_request(&headers, "POST", htu, FORBIDDEN_CHILD_AUDIENCE)
            .unwrap_err();
        assert!(matches!(
            req_err,
            LocalTokenError::InvalidClaims("child token must not target generic MCP audience")
        ));
    }

    #[test]
    fn debug_output_redacts_token_and_keys() {
        let auth = LocalAgentAuth::new().expect("init local auth");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&auth, &dpop_key);

        let auth_dbg = format!("{auth:?}");
        assert!(auth_dbg.contains("[REDACTED]"));
        assert!(auth_dbg.contains(auth.kid()));

        let tok_dbg = format!("{issued:?}");
        assert!(tok_dbg.contains("[REDACTED]"));
        assert!(!tok_dbg.contains(issued.as_str()));
    }
}
