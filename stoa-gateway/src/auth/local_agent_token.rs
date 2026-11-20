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
use serde_json::Value;
use subtle::ConstantTimeEq;
use thiserror::Error;
use uuid::Uuid;

use crate::auth::claims::CnfClaim;
use crate::auth::dpop::{compute_jwk_thumbprint, DpopConfig, DpopError, DpopValidator};

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

/// Errors produced by local RS256 token issuance or verification.
#[derive(Debug, Error)]
pub enum LocalTokenError {
    #[error("key generation failed: {0}")]
    KeyGeneration(String),

    #[error("invalid token request: {0}")]
    InvalidRequest(&'static str),

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
    pub iat: i64,
    pub exp: i64,
    pub cnf: CnfClaim,
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
            iat: now,
            exp: now + req.ttl_secs,
            cnf: CnfClaim {
                x5t_s256: None,
                jkt: Some(req.cnf_jkt.trim().to_string()),
            },
        };

        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(self.kid.clone());
        let token = encode(&header, &claims, &self.encoding_key)
            .map_err(|_| LocalTokenError::SigningFailed)?;

        Ok(IssuedLocalToken { token, claims })
    }

    /// Validate a local RS256 token strictly: mandatory matching `kid`, no fallback, strict RS256.
    pub fn validate_token(
        &self,
        token: &str,
        expected_issuer: Option<&str>,
        expected_audience: &str,
    ) -> Result<LocalAgentClaims, LocalTokenError> {
        if expected_audience.trim().is_empty() {
            return Err(LocalTokenError::InvalidRequest(
                "expected_audience must not be empty",
            ));
        }

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
        validation.leeway = 5;
        validation.set_required_spec_claims(&["exp", "iss", "aud", "sub"]);
        validation.set_audience(&[expected_audience]);
        if let Some(iss) = expected_issuer {
            validation.set_issuer(&[iss]);
        } else {
            validation.set_issuer(&[LOCAL_AGENT_ISSUER, DELEGATION_ISSUER]);
        }

        let data = decode::<LocalAgentClaims>(token, &self.decoding_key, &validation)
            .map_err(|_| LocalTokenError::InvalidToken)?;
        let claims = data.claims;

        Self::validate_claims_invariants(&claims, expected_audience)?;
        Ok(claims)
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

    /// Validate an incoming HTTP/MCP request carrying `Authorization: DPoP <jwt>` + `DPoP: <proof>`.
    pub fn validate_mcp_request(
        &self,
        headers: &HeaderMap,
        http_method: &str,
        expected_htu: &str,
        expected_audience: &str,
    ) -> Result<LocalAgentClaims, LocalTokenError> {
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

        let claims = self.validate_token(token, None, expected_audience)?;

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
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::dpop::{compute_ath, DpopJwk};
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
    fn token_from_previous_boot_or_external_key_is_rejected() {
        let boot1 = LocalAgentAuth::new().expect("boot1");
        let boot2 = LocalAgentAuth::new().expect("boot2");
        let dpop_key = TestDpopKey::generate();
        let issued = issue_sample_parent(&boot1, &dpop_key);

        // Restart invalidates previous boot kid.
        let err = boot2
            .validate_token(issued.as_str(), None, "http://stoa-gateway:8080/mcp/poc")
            .unwrap_err();
        assert!(matches!(err, LocalTokenError::UnknownKid));

        // External RSA key forged with boot2's kid still fails signature verification.
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

        // Bearer scheme refused
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

        // Wrong DPoP key refused
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

        // Replay of the same DPoP proof is rejected
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
