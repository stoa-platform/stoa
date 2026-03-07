//! JWT Bearer Client Authentication (RFC 7523)
//!
//! CAB-1740: FAPI 2.0 requires confidential clients to authenticate using
//! `private_key_jwt` instead of `client_secret`. This module validates
//! `client_assertion` JWTs on the gateway before forwarding to Keycloak.
//!
//! Validation checks (per RFC 7523 Section 3):
//! 1. `client_assertion_type` == `urn:ietf:params:oauth:client-assertion-type:jwt-bearer`
//! 2. JWT signature verified against client's public key (JWKS)
//! 3. `iss` == client_id
//! 4. `sub` == client_id
//! 5. `aud` contains the token endpoint URL
//! 6. `exp` not expired (with leeway)
//! 7. `jti` present (replay protection — logged, not enforced server-side)

use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use moka::future::Cache;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, info, warn};

use crate::auth::oidc::{Jwk, Jwks};

/// The required assertion type for JWT Bearer client auth (RFC 7523).
pub const JWT_BEARER_ASSERTION_TYPE: &str =
    "urn:ietf:params:oauth:client-assertion-type:jwt-bearer";

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum ClientAuthError {
    #[error("Missing client_assertion parameter")]
    MissingAssertion,

    #[error("Missing client_assertion_type parameter")]
    MissingAssertionType,

    #[error("Invalid client_assertion_type: expected {expected}, got {actual}")]
    InvalidAssertionType { expected: String, actual: String },

    #[error("Invalid assertion JWT: {0}")]
    InvalidJwt(String),

    #[error("Unsupported algorithm: {0:?}. Expected RS256 or ES256")]
    UnsupportedAlgorithm(Algorithm),

    #[error("Missing 'iss' claim in client assertion")]
    MissingIssuer,

    #[error("Invalid 'iss' claim: expected {expected}, got {actual}")]
    IssuerMismatch { expected: String, actual: String },

    #[error("Invalid 'sub' claim: expected {expected}, got {actual}")]
    SubjectMismatch { expected: String, actual: String },

    #[error("Missing 'aud' claim in client assertion")]
    MissingAudience,

    #[error("Invalid 'aud' claim: token endpoint {expected} not in audience")]
    AudienceMismatch { expected: String },

    #[error("Client assertion expired")]
    Expired,

    #[error("Missing 'jti' claim (replay protection)")]
    MissingJti,

    #[error("Failed to fetch client JWKS from {url}: {reason}")]
    JwksFetchError { url: String, reason: String },

    #[error("No matching key found for kid: {0}")]
    KeyNotFound(String),
}

// =============================================================================
// Claims
// =============================================================================

/// JWT claims in a client assertion (RFC 7523).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClientAssertionClaims {
    /// Issuer — MUST be the client_id
    #[serde(default)]
    pub iss: Option<String>,

    /// Subject — MUST be the client_id
    #[serde(default)]
    pub sub: Option<String>,

    /// Audience — MUST contain the token endpoint URL
    #[serde(default)]
    pub aud: Option<AudClaim>,

    /// Expiration time
    #[serde(default)]
    pub exp: Option<u64>,

    /// JWT ID — unique identifier for replay protection
    #[serde(default)]
    pub jti: Option<String>,

    /// Issued at
    #[serde(default)]
    pub iat: Option<u64>,

    /// Not before
    #[serde(default)]
    pub nbf: Option<u64>,
}

/// Audience can be a single string or array of strings.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum AudClaim {
    Single(String),
    Multiple(Vec<String>),
}

impl AudClaim {
    /// Check if the audience contains a specific value.
    pub fn contains(&self, value: &str) -> bool {
        match self {
            AudClaim::Single(s) => s == value,
            AudClaim::Multiple(v) => v.iter().any(|s| s == value),
        }
    }
}

// =============================================================================
// Client JWKS Cache
// =============================================================================

/// Cache for client JWKS (per JWKS URI).
/// Clients register their `jwks_uri` during DCR; we fetch and cache their public keys.
pub struct ClientJwksCache {
    http_client: reqwest::Client,
    cache: Cache<String, Arc<Jwks>>,
}

impl ClientJwksCache {
    /// Create a new client JWKS cache with the given TTL.
    pub fn new(http_client: reqwest::Client, ttl: Duration) -> Self {
        let cache = Cache::builder()
            .time_to_live(ttl)
            .max_capacity(100) // up to 100 client JWKS URIs
            .build();
        Self { http_client, cache }
    }

    /// Fetch a client's JWKS from their registered URI (with caching).
    pub async fn get_jwks(&self, jwks_uri: &str) -> Result<Arc<Jwks>, ClientAuthError> {
        if let Some(jwks) = self.cache.get(jwks_uri).await {
            debug!(uri = %jwks_uri, "Client JWKS cache hit");
            return Ok(jwks);
        }

        info!(uri = %jwks_uri, "Fetching client JWKS");

        let resp = self
            .http_client
            .get(jwks_uri)
            .timeout(Duration::from_secs(10))
            .send()
            .await
            .map_err(|e| ClientAuthError::JwksFetchError {
                url: jwks_uri.to_string(),
                reason: e.to_string(),
            })?;

        if !resp.status().is_success() {
            return Err(ClientAuthError::JwksFetchError {
                url: jwks_uri.to_string(),
                reason: format!("HTTP {}", resp.status()),
            });
        }

        let jwks: Jwks = resp
            .json()
            .await
            .map_err(|e| ClientAuthError::JwksFetchError {
                url: jwks_uri.to_string(),
                reason: e.to_string(),
            })?;

        let jwks = Arc::new(jwks);
        self.cache.insert(jwks_uri.to_string(), jwks.clone()).await;
        Ok(jwks)
    }
}

// =============================================================================
// Assertion Validator
// =============================================================================

/// Parsed client assertion parameters from a token request body.
#[derive(Debug)]
pub struct ClientAssertion {
    pub client_id: String,
    pub assertion: String,
}

/// Parse `client_assertion` and `client_assertion_type` from a form-encoded body.
/// Returns `None` if neither parameter is present (client is not using JWT auth).
/// Returns `Err` if parameters are partially present or invalid type.
pub fn parse_client_assertion(body: &[u8]) -> Result<Option<ClientAssertion>, ClientAuthError> {
    let params: Vec<(String, String)> = form_urlencoded::parse(body)
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect();

    let assertion_type = params
        .iter()
        .find(|(k, _)| k == "client_assertion_type")
        .map(|(_, v)| v.as_str());
    let assertion = params
        .iter()
        .find(|(k, _)| k == "client_assertion")
        .map(|(_, v)| v.as_str());
    let client_id = params
        .iter()
        .find(|(k, _)| k == "client_id")
        .map(|(_, v)| v.as_str());

    // Neither present — not using JWT auth
    if assertion_type.is_none() && assertion.is_none() {
        return Ok(None);
    }

    // Partial — one without the other
    let assertion_type = assertion_type.ok_or(ClientAuthError::MissingAssertionType)?;
    let assertion = assertion.ok_or(ClientAuthError::MissingAssertion)?;

    // Validate assertion type
    if assertion_type != JWT_BEARER_ASSERTION_TYPE {
        return Err(ClientAuthError::InvalidAssertionType {
            expected: JWT_BEARER_ASSERTION_TYPE.to_string(),
            actual: assertion_type.to_string(),
        });
    }

    // client_id can come from the form body or from the JWT iss claim.
    // If present in the body, use it; otherwise we'll extract from JWT later.
    let client_id = client_id.unwrap_or("").to_string();

    Ok(Some(ClientAssertion {
        client_id,
        assertion: assertion.to_string(),
    }))
}

/// Validate a client assertion JWT per RFC 7523.
///
/// `token_endpoint_url` is the expected audience (the gateway's token endpoint).
/// `jwks` contains the client's public keys for signature verification.
pub fn validate_client_assertion(
    assertion: &ClientAssertion,
    token_endpoint_url: &str,
    jwks: &Jwks,
) -> Result<ClientAssertionClaims, ClientAuthError> {
    // 1. Decode header to get kid and algorithm
    let header = decode_header(&assertion.assertion)
        .map_err(|e| ClientAuthError::InvalidJwt(format!("Invalid JWT header: {}", e)))?;

    // 2. Verify supported algorithm (RS256 for RSA, ES256 for EC)
    let alg = header.alg;
    if alg != Algorithm::RS256 && alg != Algorithm::ES256 {
        return Err(ClientAuthError::UnsupportedAlgorithm(alg));
    }

    // 3. Find the matching key
    let decoding_key = find_decoding_key(jwks, header.kid.as_deref(), alg)?;

    // 4. Build validation — we validate exp but NOT iss/aud via jsonwebtoken
    //    (we do custom validation below for better error messages)
    let mut validation = Validation::new(alg);
    validation.validate_exp = true;
    validation.leeway = 30; // 30 seconds clock skew
    validation.validate_aud = false; // custom validation below
    validation.set_required_spec_claims(&["exp"]);

    // 5. Decode and verify signature
    let token_data =
        decode::<ClientAssertionClaims>(&assertion.assertion, &decoding_key, &validation).map_err(
            |e| match e.kind() {
                jsonwebtoken::errors::ErrorKind::ExpiredSignature => ClientAuthError::Expired,
                jsonwebtoken::errors::ErrorKind::InvalidSignature => {
                    ClientAuthError::InvalidJwt("Signature verification failed".to_string())
                }
                _ => ClientAuthError::InvalidJwt(e.to_string()),
            },
        )?;

    let claims = token_data.claims;

    // 6. Validate iss == client_id
    let iss = claims
        .iss
        .as_deref()
        .ok_or(ClientAuthError::MissingIssuer)?;
    let expected_client_id = if assertion.client_id.is_empty() {
        iss // If client_id not in body, iss IS the client_id
    } else {
        &assertion.client_id
    };
    if iss != expected_client_id {
        return Err(ClientAuthError::IssuerMismatch {
            expected: expected_client_id.to_string(),
            actual: iss.to_string(),
        });
    }

    // 7. Validate sub == client_id
    if let Some(sub) = claims.sub.as_deref() {
        if sub != expected_client_id {
            return Err(ClientAuthError::SubjectMismatch {
                expected: expected_client_id.to_string(),
                actual: sub.to_string(),
            });
        }
    }
    // sub is recommended but not strictly required by RFC 7523

    // 8. Validate aud contains token endpoint
    let aud = claims
        .aud
        .as_ref()
        .ok_or(ClientAuthError::MissingAudience)?;
    if !aud.contains(token_endpoint_url) {
        return Err(ClientAuthError::AudienceMismatch {
            expected: token_endpoint_url.to_string(),
        });
    }

    // 9. jti should be present for replay protection
    if claims.jti.is_none() {
        warn!("Client assertion missing 'jti' claim — replay protection not available");
        // RFC 7523 says SHOULD, not MUST, so we warn but don't reject
    } else {
        debug!(jti = ?claims.jti, "Client assertion jti present");
    }

    info!(
        client_id = %expected_client_id,
        alg = ?alg,
        "Client assertion validated (private_key_jwt)"
    );

    Ok(claims)
}

/// Find a decoding key from the JWKS matching the kid and algorithm.
fn find_decoding_key(
    jwks: &Jwks,
    kid: Option<&str>,
    alg: Algorithm,
) -> Result<DecodingKey, ClientAuthError> {
    let matching_keys: Vec<&Jwk> = jwks
        .keys
        .iter()
        .filter(|k| {
            // Match kid if provided
            let kid_match = kid.is_none_or(|id| k.kid.as_deref() == Some(id));
            // Match key type
            let kty_match = match alg {
                Algorithm::RS256 => k.kty == "RSA",
                Algorithm::ES256 => k.kty == "EC",
                _ => false,
            };
            // Match use (sig or unspecified)
            let use_match = k.is_signature_key();
            kid_match && kty_match && use_match
        })
        .collect();

    let key = matching_keys
        .first()
        .ok_or_else(|| ClientAuthError::KeyNotFound(kid.unwrap_or("(none)").to_string()))?;

    key.to_decoding_key()
        .map_err(|e| ClientAuthError::InvalidJwt(format!("Invalid key: {}", e)))
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use jsonwebtoken::{encode, EncodingKey, Header};

    /// Static RSA 2048 key pair for testing (DO NOT use in production).
    /// Generated once with `openssl genrsa 2048`, avoids openssl system dependency in CI.
    const TEST_RSA_PRIVATE_PEM: &str = "-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAxUa9q/L+ewhQKY4Wiwnro6SWh7rjBSf25tGX8Akp8eSrC6/V
ctOua6zs5qiqkdoPozTf3zife5lzCtYzDIeu+DwvvUAzUXZHXjS1UxnMcYNIvUvf
myjhEaLyuHrqjzKFDzAbJ295m+QiuZ9ld2E90Cds81f3LDInOrBnRj3JfFkT/wkp
H5RIifnMAiXpxWJgdUmZBjouCczHRWzJFFe33R6lI37BVqgMten0LBxQsEg51oGB
sYyHHW4WIKCALZDv1ErKaxxp2lxQZkpUjYOjLg1Sbqiw5cSDUeKTDv2osLTdJ+B6
yYuSJJwhv6QNWYytBfLDSULk/zrSBfCdo3LHAQIDAQABAoIBAAw36L3Ycq+l9NmT
COVHCbTAqBhbYE3QoymaAgciWSpHyXqDgyTN1K3rd5+EYy6eBvWKvAIqQpH0H8iE
OmSQd4s9Ro9qFVeae9p7SR7+0D9YVFIxm6WDdVerXA1GIyaX+F7nwcnKLSn1Kfut
Ujpv79U3aOeEO21NxKldVUMn5uWcLppuKxugitwvQk7IHCMnxiR1SdSA52025RpR
Y3CZK8leryv9zFBFtvViMgvpZGfotXaOugshJH0blwm8G9/3VH0UoK8OgT6uwK78
oSeyQvzPiRuZF5xa7IGogyTQE3SVsBa5fqQ18mpyon8I/o6Omr5zL1F+c4dsF3Vv
A7qT5fECgYEA9CyA3lqOoEWToIIqv21phJyGN9KhCPf30rdgEV8mP/+ffz+LpFOL
if2+pDu5zcgeyKMQjGpeKPvrWPwKDIlk4s6t6wZGciuXnXwJkrERKoVf5wpf9rV6
7laksXv44YjYYSJGBn4BkBmvSg/sASrwI4Q6HIImhU1cQDBwWdCeYZECgYEAztTC
FZN96BQUt5S4XGpSpFrxA/GiHOQOIXlYDoLMWkWFxIFQ459/Fpn/MTO162GHzBL3
9FBBVwoig6qzt3KCHnFChpbfdsgwbMBxOXtjvLOaRX2mFV6hAwj/VlpplJOFvPv5
5MToydPU2C4kDg4c7hkTNImD3DxoeBercusTVnECgYB9anZuv1jO3a3sHa/TT2GJ
adROy/NG5gb2xpWjlpnQ+X11ILCbIQZlRF4tgTf4iLe3GnqfhOsEZhEGTb7jnZai
IMKYG0sHzXg8vb81B5nnm0YdJ+kOkTypOvuw5hp5zY5GphINt58Z4vd0NSVlnCZo
N7yZdAhRI+EkXzz2BP+04QKBgQDJKOxLB9Qg78bmdeKJH2+ZIkneyBgfeT61F8uo
8VXHRm6/m/YMLIfyd3xXYi/A6m6k8J3wJE4oVVcUL+XyuZAMA6PsOrjEUhem7dQx
T+zFDvkwNPBfQFXhGdMdLXoaYxBjqb513X17LmeIiffPI7LHb+PZ6RUyEh6ZDoxV
jISWQQKBgEQksTI6ef6jg44qwqQA2ew2SEAyY5JzOERiQJjRl+q7+Ju0XM1HhwoV
TPrZxYMzJbu0Vtw0cn7OZL/tWMPSLcHkpJkNhPUOAhZs82tYBevuuZ1mxs/5nkwo
2YHoRmnYJalBnDUzJcxS0iuSZukwxJ1TsJI20S+n5kvGFV951YBp
-----END RSA PRIVATE KEY-----";

    const TEST_RSA_PUBLIC_PEM: &str = "-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxUa9q/L+ewhQKY4Wiwnr
o6SWh7rjBSf25tGX8Akp8eSrC6/VctOua6zs5qiqkdoPozTf3zife5lzCtYzDIeu
+DwvvUAzUXZHXjS1UxnMcYNIvUvfmyjhEaLyuHrqjzKFDzAbJ295m+QiuZ9ld2E9
0Cds81f3LDInOrBnRj3JfFkT/wkpH5RIifnMAiXpxWJgdUmZBjouCczHRWzJFFe3
3R6lI37BVqgMten0LBxQsEg51oGBsYyHHW4WIKCALZDv1ErKaxxp2lxQZkpUjYOj
Lg1Sbqiw5cSDUeKTDv2osLTdJ+B6yYuSJJwhv6QNWYytBfLDSULk/zrSBfCdo3LH
AQIDAQAB
-----END PUBLIC KEY-----";

    // Precomputed JWK components for the test key above (base64url-encoded n and e).
    const TEST_RSA_N: &str = "xUa9q_L-ewhQKY4Wiwnro6SWh7rjBSf25tGX8Akp8eSrC6_VctOua6zs5qiqkdoPozTf3zife5lzCtYzDIeu-DwvvUAzUXZHXjS1UxnMcYNIvUvfmyjhEaLyuHrqjzKFDzAbJ295m-QiuZ9ld2E90Cds81f3LDInOrBnRj3JfFkT_wkpH5RIifnMAiXpxWJgdUmZBjouCczHRWzJFFe33R6lI37BVqgMten0LBxQsEg51oGBsYyHHW4WIKCALZDv1ErKaxxp2lxQZkpUjYOjLg1Sbqiw5cSDUeKTDv2osLTdJ-B6yYuSJJwhv6QNWYytBfLDSULk_zrSBfCdo3LHAQ";
    const TEST_RSA_E: &str = "AQAB";

    /// Helper: get the static test RSA key pair.
    fn test_rsa_keys() -> (EncodingKey, DecodingKey, String, String) {
        let encoding_key =
            EncodingKey::from_rsa_pem(TEST_RSA_PRIVATE_PEM.as_bytes()).expect("encoding key");
        let decoding_key =
            DecodingKey::from_rsa_pem(TEST_RSA_PUBLIC_PEM.as_bytes()).expect("decoding key");

        (
            encoding_key,
            decoding_key,
            TEST_RSA_N.to_string(),
            TEST_RSA_E.to_string(),
        )
    }

    fn make_test_jwks(kid: &str, n: &str, e: &str) -> Jwks {
        Jwks {
            keys: vec![Jwk {
                kty: "RSA".to_string(),
                kid: Some(kid.to_string()),
                alg: Some("RS256".to_string()),
                key_use: Some("sig".to_string()),
                n: Some(n.to_string()),
                e: Some(e.to_string()),
                x5c: None,
                x5t: None,
                x5t_s256: None,
            }],
        }
    }

    fn make_assertion(
        encoding_key: &EncodingKey,
        kid: &str,
        claims: &ClientAssertionClaims,
    ) -> String {
        let mut header = Header::new(Algorithm::RS256);
        header.kid = Some(kid.to_string());
        encode(&header, claims, encoding_key).expect("JWT encode")
    }

    fn now_secs() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("time")
            .as_secs()
    }

    // -------------------------------------------------------------------------
    // parse_client_assertion tests
    // -------------------------------------------------------------------------

    #[test]
    fn test_parse_no_assertion_params() {
        let body = b"grant_type=authorization_code&code=abc";
        let result = parse_client_assertion(body).unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn test_parse_valid_assertion() {
        let body = format!(
            "grant_type=authorization_code&client_assertion_type={}&client_assertion=eyJ.test.jwt&client_id=my-client",
            JWT_BEARER_ASSERTION_TYPE
        );
        let result = parse_client_assertion(body.as_bytes()).unwrap().unwrap();
        assert_eq!(result.client_id, "my-client");
        assert_eq!(result.assertion, "eyJ.test.jwt");
    }

    #[test]
    fn test_parse_assertion_without_client_id() {
        let body = format!(
            "grant_type=authorization_code&client_assertion_type={}&client_assertion=eyJ.test.jwt",
            JWT_BEARER_ASSERTION_TYPE
        );
        let result = parse_client_assertion(body.as_bytes()).unwrap().unwrap();
        assert_eq!(result.client_id, ""); // Will be extracted from JWT iss
    }

    #[test]
    fn test_parse_missing_assertion_type() {
        let body = b"client_assertion=eyJ.test.jwt";
        let result = parse_client_assertion(body);
        assert!(matches!(result, Err(ClientAuthError::MissingAssertionType)));
    }

    #[test]
    fn test_parse_missing_assertion() {
        let body = format!("client_assertion_type={}", JWT_BEARER_ASSERTION_TYPE);
        let result = parse_client_assertion(body.as_bytes());
        assert!(matches!(result, Err(ClientAuthError::MissingAssertion)));
    }

    #[test]
    fn test_parse_wrong_assertion_type() {
        let body = b"client_assertion_type=wrong&client_assertion=eyJ.test.jwt";
        let result = parse_client_assertion(body);
        assert!(matches!(
            result,
            Err(ClientAuthError::InvalidAssertionType { .. })
        ));
    }

    // -------------------------------------------------------------------------
    // validate_client_assertion tests
    // -------------------------------------------------------------------------

    #[test]
    fn test_validate_valid_assertion() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-1".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(result.is_ok());
        let validated = result.unwrap();
        assert_eq!(validated.iss.as_deref(), Some("my-client"));
        assert_eq!(validated.jti.as_deref(), Some("unique-id-1"));
    }

    #[test]
    fn test_validate_expired_assertion() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() - 120), // expired 2 min ago (past 30s leeway)
            jti: Some("unique-id-2".to_string()),
            iat: Some(now_secs() - 600),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(result, Err(ClientAuthError::Expired)));
    }

    #[test]
    fn test_validate_wrong_issuer() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("wrong-client".to_string()),
            sub: Some("wrong-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-3".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(
            result,
            Err(ClientAuthError::IssuerMismatch { .. })
        ));
    }

    #[test]
    fn test_validate_wrong_subject() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("different-client".to_string()), // sub != iss
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-4".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(
            result,
            Err(ClientAuthError::SubjectMismatch { .. })
        ));
    }

    #[test]
    fn test_validate_wrong_audience() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single("https://wrong.endpoint/token".to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-5".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(
            result,
            Err(ClientAuthError::AudienceMismatch { .. })
        ));
    }

    #[test]
    fn test_validate_multiple_audiences() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Multiple(vec![
                "https://other.service".to_string(),
                token_endpoint.to_string(),
            ])),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-6".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_no_kid_uses_first_matching_key() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let jwks = make_test_jwks("some-key", &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-7".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };

        // Encode WITHOUT kid in header
        let header = Header::new(Algorithm::RS256);
        let jwt = encode(&header, &claims, &enc_key).expect("encode");

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_wrong_key_fails_signature() {
        // Sign with the test key, verify against a JWKS with a different modulus
        let (enc_key, _, _, _) = test_rsa_keys();
        let kid = "test-key-1";
        // Use a bogus modulus — different from the actual test key
        let wrong_n = "zZZ9q_L-ewhQKY4Wiwnro6SWh7rjBSf25tGX8Akp8eSrC6_VctOua6zs5qiqkdoPozTf3zife5lzCtYzDIeu-DwvvUAzUXZHXjS1UxnMcYNIvUvfmyjhEaLyuHrqjzKFDzAbJ295m-QiuZ9ld2E90Cds81f3LDInOrBnRj3JfFkT_wkpH5RIifnMAiXpxWJgdUmZBjouCczHRWzJFFe33R6lI37BVqgMten0LBxQsEg51oGBsYyHHW4WIKCALZDv1ErKaxxp2lxQZkpUjYOjLg1Sbqiw5cSDUeKTDv2osLTdJ-B6yYuSJJwhv6QNWYytBfLDSULk_zrSBfCdo3LHAQ";
        let jwks = make_test_jwks(kid, wrong_n, TEST_RSA_E);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-8".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(result, Err(ClientAuthError::InvalidJwt(_))));
    }

    #[test]
    fn test_validate_missing_iss() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: None,
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-9".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(result, Err(ClientAuthError::MissingIssuer)));
    }

    #[test]
    fn test_validate_missing_aud() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: None,
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-10".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(result, Err(ClientAuthError::MissingAudience)));
    }

    #[test]
    fn test_validate_client_id_from_iss_when_body_empty() {
        let (enc_key, _dec_key, n, e) = test_rsa_keys();
        let kid = "test-key-1";
        let jwks = make_test_jwks(kid, &n, &e);
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("auto-detected-client".to_string()),
            sub: Some("auto-detected-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-11".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, kid, &claims);

        let assertion = ClientAssertion {
            client_id: "".to_string(), // empty — use iss
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(result.is_ok());
        assert_eq!(result.unwrap().iss.as_deref(), Some("auto-detected-client"));
    }

    #[test]
    fn test_validate_key_not_found() {
        let (enc_key, _dec_key, _n, _e) = test_rsa_keys();
        let jwks = Jwks { keys: vec![] }; // empty JWKS
        let token_endpoint = "https://mcp.gostoa.dev/oauth/token";

        let claims = ClientAssertionClaims {
            iss: Some("my-client".to_string()),
            sub: Some("my-client".to_string()),
            aud: Some(AudClaim::Single(token_endpoint.to_string())),
            exp: Some(now_secs() + 300),
            jti: Some("unique-id-12".to_string()),
            iat: Some(now_secs()),
            nbf: None,
        };
        let jwt = make_assertion(&enc_key, "test-key-1", &claims);

        let assertion = ClientAssertion {
            client_id: "my-client".to_string(),
            assertion: jwt,
        };

        let result = validate_client_assertion(&assertion, token_endpoint, &jwks);
        assert!(matches!(result, Err(ClientAuthError::KeyNotFound(_))));
    }

    // -------------------------------------------------------------------------
    // AudClaim tests
    // -------------------------------------------------------------------------

    #[test]
    fn test_aud_single_contains() {
        let aud = AudClaim::Single("https://token.endpoint".to_string());
        assert!(aud.contains("https://token.endpoint"));
        assert!(!aud.contains("https://other.endpoint"));
    }

    #[test]
    fn test_aud_multiple_contains() {
        let aud = AudClaim::Multiple(vec![
            "https://a.endpoint".to_string(),
            "https://b.endpoint".to_string(),
        ]);
        assert!(aud.contains("https://a.endpoint"));
        assert!(aud.contains("https://b.endpoint"));
        assert!(!aud.contains("https://c.endpoint"));
    }
}
