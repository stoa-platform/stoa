//! JWT Validation
//!
//! CAB-912 P2: JWT token validation with RS256 signature verification.
//!
//! Features:
//! - RS256 signature verification using JWKS
//! - Expiration check
//! - Issuer validation
//! - Audience validation
//! - Claims extraction
use jsonwebtoken::{decode, decode_header, Algorithm, Validation};
use std::sync::Arc;
use thiserror::Error;
use tracing::{debug, warn};

use super::claims::Claims;
use super::oidc::{OidcError, OidcProvider};

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum JwtError {
    #[error("Missing Authorization header")]
    MissingHeader,

    #[error("Invalid Authorization header format (expected 'Bearer <token>')")]
    InvalidHeaderFormat,

    #[error("Token expired")]
    Expired,

    #[error("Invalid issuer: expected {expected}")]
    InvalidIssuer { expected: String },

    #[error("Invalid audience: expected {expected}")]
    InvalidAudience { expected: String },

    #[error("Invalid signature")]
    InvalidSignature,

    #[error("Token decode error: {0}")]
    DecodeError(String),

    #[error("Key not found for kid: {0}")]
    KeyNotFound(String),

    #[error("OIDC error: {0}")]
    OidcError(#[from] OidcError),

    #[error("Missing required claim: {0}")]
    MissingClaim(String),
}

// =============================================================================
// JWT Validator
// =============================================================================

/// JWT Validator configuration.
#[derive(Debug, Clone)]
pub struct JwtValidatorConfig {
    /// Whether to validate the issuer
    pub validate_issuer: bool,

    /// Whether to validate the audience
    pub validate_audience: bool,

    /// Audiences accepted when `validate_audience` is set.
    /// Empty falls back to the OIDC provider audience.
    pub audiences: Vec<String>,

    /// Whether to validate expiration
    pub validate_exp: bool,

    /// Clock skew tolerance in seconds
    pub leeway_seconds: u64,

    /// Required scopes (if any)
    pub required_scopes: Vec<String>,
}

impl Default for JwtValidatorConfig {
    fn default() -> Self {
        Self {
            validate_issuer: true,
            validate_audience: true,
            audiences: Vec::new(),
            validate_exp: true,
            leeway_seconds: 30,
            required_scopes: vec![],
        }
    }
}

/// JWT Validator using OIDC provider for key fetching.
pub struct JwtValidator {
    oidc_provider: Arc<OidcProvider>,
    config: JwtValidatorConfig,
}

impl JwtValidator {
    /// Create a new JWT validator.
    pub fn new(oidc_provider: Arc<OidcProvider>) -> Self {
        Self {
            oidc_provider,
            config: JwtValidatorConfig::default(),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(oidc_provider: Arc<OidcProvider>, config: JwtValidatorConfig) -> Self {
        Self {
            oidc_provider,
            config,
        }
    }

    /// True when this validator rejects a token whose `aud` is missing or wrong.
    pub fn enforces_audience(&self) -> bool {
        self.config.validate_audience
    }

    /// Same keys and issuer, but `aud` must contain one of `audiences`.
    ///
    /// Used by the REST proxy when a published policy carries `config.audience`.
    /// The process-wide validator can leave audience checks off; the policy
    /// still fail-closes that route.
    pub fn with_audience_override(&self, audiences: &[String]) -> Self {
        Self {
            oidc_provider: Arc::clone(&self.oidc_provider),
            config: JwtValidatorConfig {
                validate_audience: true,
                audiences: audiences.to_vec(),
                ..self.config.clone()
            },
        }
    }

    /// Validate a JWT token and extract claims.
    pub async fn validate(&self, token: &str) -> Result<Claims, JwtError> {
        // Decode header to get kid
        let header = decode_header(token)
            .map_err(|e| JwtError::DecodeError(format!("Invalid token header: {}", e)))?;

        debug!(
            alg = ?header.alg,
            kid = ?header.kid,
            "Decoding JWT header"
        );

        // Only support RS256
        if header.alg != Algorithm::RS256 {
            return Err(JwtError::DecodeError(format!(
                "Unsupported algorithm: {:?}. Only RS256 is supported.",
                header.alg
            )));
        }

        // Get the signing key
        let jwk = if let Some(kid) = &header.kid {
            self.oidc_provider.get_key(kid).await?
        } else {
            warn!("No kid in token header, using default key");
            self.oidc_provider.get_default_key().await?
        };

        // Convert to decoding key
        let decoding_key = jwk.to_decoding_key()?;

        // Build validation
        let mut validation = Validation::new(Algorithm::RS256);
        validation.validate_exp = self.config.validate_exp;
        validation.leeway = self.config.leeway_seconds;

        // Set issuer validation
        if self.config.validate_issuer {
            validation.set_issuer(&[self.oidc_provider.issuer_url()]);
        }

        // Set audience validation. STOA_JWT_AUDIENCE overrides the OIDC client id.
        // jsonwebtoken accepts a token that omits `aud` even after set_audience,
        // so the claim is checked again on the decoded Claims.
        let required_audiences: Vec<String> = if self.config.validate_audience {
            if self.config.audiences.is_empty() {
                vec![self.oidc_provider.audience().to_string()]
            } else {
                self.config.audiences.clone()
            }
        } else {
            Vec::new()
        };
        if required_audiences.is_empty() {
            validation.validate_aud = false;
        } else {
            let refs: Vec<&str> = required_audiences.iter().map(String::as_str).collect();
            validation.set_audience(&refs);
        }

        // Decode and validate
        let token_data =
            decode::<Claims>(token, &decoding_key, &validation).map_err(|e| match e.kind() {
                jsonwebtoken::errors::ErrorKind::ExpiredSignature => JwtError::Expired,
                jsonwebtoken::errors::ErrorKind::InvalidIssuer => JwtError::InvalidIssuer {
                    expected: self.oidc_provider.issuer_url().to_string(),
                },
                jsonwebtoken::errors::ErrorKind::InvalidAudience => JwtError::InvalidAudience {
                    expected: required_audiences.join(","),
                },
                jsonwebtoken::errors::ErrorKind::InvalidSignature => JwtError::InvalidSignature,
                _ => JwtError::DecodeError(e.to_string()),
            })?;

        let claims = token_data.claims;
        if !required_audiences.is_empty()
            && !required_audiences
                .iter()
                .any(|aud| claims.aud.contains(aud))
        {
            return Err(JwtError::InvalidAudience {
                expected: required_audiences.join(","),
            });
        }

        // Check required scopes
        if !self.config.required_scopes.is_empty() {
            for scope in &self.config.required_scopes {
                if !claims.has_scope(scope) {
                    return Err(JwtError::MissingClaim(format!("scope:{}", scope)));
                }
            }
        }

        debug!(
            sub = %claims.sub,
            tenant = ?claims.tenant_id(),
            "JWT validated successfully"
        );

        Ok(claims)
    }

    /// Extract a token from an Authorization header value.
    pub fn extract_token(auth_header: &str) -> Result<&str, JwtError> {
        let parts: Vec<&str> = auth_header.splitn(2, ' ').collect();

        if parts.len() != 2 {
            return Err(JwtError::InvalidHeaderFormat);
        }

        if parts[0].to_lowercase() != "bearer" {
            return Err(JwtError::InvalidHeaderFormat);
        }

        Ok(parts[1].trim())
    }

    /// Get the OIDC provider.
    pub fn oidc_provider(&self) -> &Arc<OidcProvider> {
        &self.oidc_provider
    }
}

// =============================================================================
// Token Extraction Helper
// =============================================================================

/// Extract token from various sources (header, cookie, query).
pub struct TokenExtractor;

impl TokenExtractor {
    /// Extract token from Authorization header.
    pub fn from_header(value: &str) -> Result<String, JwtError> {
        JwtValidator::extract_token(value).map(|s| s.to_string())
    }

    /// Extract token from cookie value.
    pub fn from_cookie(cookies: &str, cookie_name: &str) -> Option<String> {
        for cookie in cookies.split(';') {
            let parts: Vec<&str> = cookie.trim().splitn(2, '=').collect();
            if parts.len() == 2 && parts[0] == cookie_name {
                return Some(parts[1].to_string());
            }
        }
        None
    }
}

// =============================================================================
// Validated Token
// =============================================================================

/// A validated token with claims.
#[derive(Debug, Clone)]
pub struct ValidatedToken {
    /// The original token string
    pub raw_token: String,

    /// The validated claims
    pub claims: Claims,
}

impl ValidatedToken {
    /// Create a new validated token.
    pub fn new(raw_token: String, claims: Claims) -> Self {
        Self { raw_token, claims }
    }

    /// Get the user ID.
    pub fn user_id(&self) -> &str {
        self.claims.user_id()
    }

    /// Get the tenant ID.
    pub fn tenant_id(&self) -> Option<&str> {
        self.claims.tenant_id()
    }

    /// Get the username.
    pub fn username(&self) -> Option<&str> {
        self.claims.username()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    #[test]
    fn test_extract_token_bearer() {
        let token =
            JwtValidator::extract_token("Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9").unwrap();
        assert_eq!(token, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
    }

    #[test]
    fn test_extract_token_lowercase_bearer() {
        let token =
            JwtValidator::extract_token("bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9").unwrap();
        assert_eq!(token, "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
    }

    #[test]
    fn test_extract_token_missing_bearer() {
        let result = JwtValidator::extract_token("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9");
        assert!(matches!(result, Err(JwtError::InvalidHeaderFormat)));
    }

    #[test]
    fn test_extract_token_wrong_scheme() {
        let result = JwtValidator::extract_token("Basic dXNlcjpwYXNz");
        assert!(matches!(result, Err(JwtError::InvalidHeaderFormat)));
    }

    #[test]
    fn test_token_from_cookie() {
        let cookies = "session=abc123; token=eyJhbGci.xxx.yyy; other=value";
        let token = TokenExtractor::from_cookie(cookies, "token");
        assert_eq!(token, Some("eyJhbGci.xxx.yyy".to_string()));
    }

    #[test]
    fn test_token_from_cookie_not_found() {
        let cookies = "session=abc123; other=value";
        let token = TokenExtractor::from_cookie(cookies, "token");
        assert!(token.is_none());
    }

    #[test]
    fn test_validator_config_default() {
        let config = JwtValidatorConfig::default();
        assert!(config.validate_issuer);
        assert!(config.validate_audience);
        assert!(config.validate_exp);
        assert_eq!(config.leeway_seconds, 30);
    }

    const TEST_PEM: &str = "-----BEGIN PRIVATE KEY-----\n\
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDFWYM6hI+Dz8n4\n\
Oi2U3iGFmmGHAM6Qp2Ytpt8yQM3boJc6Ia9w6jA+78HdT1AkhMjlopB6xstrT36W\n\
LAzLDp5v0FD4uCD+li5qSAY/y3Gx6k4WbRCKglMu96qg+9zpaGslyg2omfE3KmFS\n\
DmMyWvarEI7zZ7/U7fsUOMDcxvICGRUQQAJ793kgFmTAAmBy3uiN8EmWiej5+NVn\n\
FuscveweyBK25yA85ng/4XSjbexKO7Kx2sWNygQu3eHQcFqtefceDhM/diNIz51b\n\
l1kTqxv2NFAgArwGsX+T5xiLCVvLIhXWceNKwoLM1iCmoQfwC8ihR5S0+CusnpUZ\n\
PZfsX69/AgMBAAECggEACE4aDa5ic8Oc1ktse6VVd8/lZs8L4l6JGEa7gdvkTefW\n\
NWYRggj4+s0QNYYO81p7Md7Dgcc37E4uH5e++hSlakM0BSOKj+w2C9b4HFstb7VS\n\
j/MLDSkq4wEdNyUiSNhSGgcEyCGiWxX3foKIfigB1XUe7vNgyU8yj8lLpH7i1F+y\n\
1StLfI3Ab4BzgOEQmVXFARE+5f3ZOoAW+hsq8eHyWyyzSN+fE5wYtB7e3uhnstVB\n\
R+DOZHSv+P13L/oTze7B4V/88sDe/w5S7L5RD9JuFhF4C5fw7Pi94o4B1o2r2/7F\n\
HIOYEBB9SzeWae1kjyVRGII+5LO5LZGLEhwQFtUoQQKBgQD4yEMLerI/oM89/Bb3\n\
L29QNW3ia2hl1qvumB9X+bAM4nWIa7zDLXNpzrorLUUCJLoENswHXX0Od1rYOsoi\n\
Dlu5ucIFz5uYdu6OhBeyxjpYTloI2G30TQHrn2rhoD2nuOl00BTDYL0juoCTrw/v\n\
UmrGEwyYMp0mwWLRuB9EXnN0TwKBgQDLE0EI1zNPqGh5QJ47jvU5xsHlSj/YISLP\n\
Nro3JZIG2+BT8KyAxmIiSRgocBnSRPonCuwAt4iC1aNSl/H7uumI74pl61J9dd0p\n\
Shwp6N6sN/OzaP9521FgyH+FBTPPZDdplZ0eFuUhGDFigAgMILQb0a30QMRKCxjN\n\
nzQHLCjV0QKBgF6hxqb6MA11/P8GAjJab8wh1r+WvapnQxVJ9jo/txDfn3eaC75u\n\
boVj5nsACEztbXim42s1y5kSG5M+oZ7cuVVnbH9LXlNbghjh9CXDs3Pdse/Fa+XO\n\
2Rkolb5ndqxy8RLHB+7dwHRzv+7tW3Fcd1MK8fJ+5jpUu2Ms12/pQZ+PAoGBAIB4\n\
9NrX8mFBxJ55D+HUBjYAFSiu+YcNJ416LQK4ZRKrxda02x045FqWbY8fpGZPNwa+\n\
NSIa+mTzLTkSYYeE7zuvd5oU7wHqL/lwJjMpXL4NQ8LL+VwpMOmOzoXkDav11cyZ\n\
V2XyzBBM0uli4DRz+B3lYCy3ULcbIBztzCeBe3ARAoGBAKIgOvCYnz0wnHBFA+zq\n\
oRIvaIdbNosKoN+oT1jnnmfczLJ6pj+2Aa5n6j2kxwf5FTDqFlPI2tbmHmTQ7YsK\n\
p9F8dBQBt/cb1sBl3ammY8HSmaAq+k/vDAR5BTSi6lxo7z+D6Inf65nCqHAygbuN\n\
4H/ZaGW5OTrSMEsqHNuImeoC\n\
-----END PRIVATE KEY-----\n";

    const TEST_N: &str = "xVmDOoSPg8_J-DotlN4hhZphhwDOkKdmLabfMkDN26CXOiGvcOowPu_B3U9QJITI5aKQesbLa09-liwMyw6eb9BQ-Lgg_pYuakgGP8txsepOFm0QioJTLveqoPvc6WhrJcoNqJnxNyphUg5jMlr2qxCO82e_1O37FDjA3MbyAhkVEEACe_d5IBZkwAJgct7ojfBJlono-fjVZxbrHL3sHsgStucgPOZ4P-F0o23sSjuysdrFjcoELt3h0HBarXn3Hg4TP3YjSM-dW5dZE6sb9jRQIAK8BrF_k-cYiwlbyyIV1nHjSsKCzNYgpqEH8AvIoUeUtPgrrJ6VGT2X7F-vfw";

    #[derive(serde::Serialize)]
    struct MintedClaims {
        sub: &'static str,
        exp: i64,
        iat: i64,
        iss: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        aud: Option<String>,
    }

    pub(crate) async fn validator_against_test_key(
        config: JwtValidatorConfig,
    ) -> (JwtValidator, String) {
        use wiremock::matchers::{method, path};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let server = MockServer::start().await;
        let issuer = format!("{}/realms/stoa", server.uri());
        let jwks = format!("{}/jwks", server.uri());
        Mock::given(method("GET"))
            .and(path("/realms/stoa/.well-known/openid-configuration"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "issuer": issuer,
                "authorization_endpoint": format!("{issuer}/auth"),
                "token_endpoint": format!("{issuer}/token"),
                "jwks_uri": jwks,
            })))
            .mount(&server)
            .await;
        Mock::given(method("GET"))
            .and(path("/jwks"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "keys": [{
                    "kty": "RSA",
                    "kid": "test-key",
                    "use": "sig",
                    "alg": "RS256",
                    "n": TEST_N,
                    "e": "AQAB"
                }]
            })))
            .mount(&server)
            .await;

        let provider = Arc::new(crate::auth::oidc::OidcProvider::new(
            crate::auth::oidc::OidcProviderConfig {
                issuer_url: issuer.clone(),
                audience: "stoa-caller".into(),
                ..crate::auth::oidc::OidcProviderConfig::default()
            },
        ));
        let validator = JwtValidator::with_config(provider, config);
        (validator, issuer)
    }

    pub(crate) fn issuer_only() -> JwtValidatorConfig {
        JwtValidatorConfig {
            validate_audience: false,
            ..JwtValidatorConfig::default()
        }
    }

    pub(crate) fn mint(issuer: &str, exp: i64, aud: Option<&str>) -> String {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let mut header = jsonwebtoken::Header::new(jsonwebtoken::Algorithm::RS256);
        header.kid = Some("test-key".into());
        jsonwebtoken::encode(
            &header,
            &MintedClaims {
                sub: "svc",
                exp,
                iat: now,
                iss: issuer.to_string(),
                aud: aud.map(str::to_string),
            },
            &jsonwebtoken::EncodingKey::from_rsa_pem(TEST_PEM.as_bytes()).unwrap(),
        )
        .unwrap()
    }

    #[tokio::test]
    async fn rs256_accepts_keycloak_shaped_token_without_audience() {
        let (validator, issuer) = validator_against_test_key(issuer_only()).await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint(&issuer, now + 300, None);
        let claims = validator.validate(&token).await.expect("valid token");
        assert_eq!(claims.sub, "svc");
        assert_eq!(claims.iss, issuer);
    }

    #[tokio::test]
    async fn rs256_rejects_expired_token() {
        let (validator, issuer) = validator_against_test_key(issuer_only()).await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint(&issuer, now - 120, None);
        let error = validator.validate(&token).await.expect_err("expired");
        assert!(matches!(error, JwtError::Expired));
    }

    #[tokio::test]
    async fn rs256_rejects_wrong_issuer() {
        let (validator, _issuer) = validator_against_test_key(issuer_only()).await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let token = mint("http://evil.example/realms/stoa", now + 300, None);
        let error = validator.validate(&token).await.expect_err("wrong iss");
        assert!(matches!(error, JwtError::InvalidIssuer { .. }));
    }

    #[tokio::test]
    async fn rs256_checks_audience_only_when_configured() {
        let (validator, issuer) = validator_against_test_key(JwtValidatorConfig {
            validate_audience: true,
            audiences: vec!["stoa-gateway".into()],
            ..JwtValidatorConfig::default()
        })
        .await;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        let accepted = mint(&issuer, now + 300, Some("stoa-gateway"));
        let claims = validator.validate(&accepted).await.expect("aud matches");
        assert_eq!(claims.sub, "svc");

        let wrong = mint(&issuer, now + 300, Some("account"));
        let error = validator.validate(&wrong).await.expect_err("wrong aud");
        assert!(matches!(error, JwtError::InvalidAudience { .. }));

        let missing = mint(&issuer, now + 300, None);
        let error = validator.validate(&missing).await.expect_err("missing aud");
        assert!(matches!(error, JwtError::InvalidAudience { .. }));
    }
}
