// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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

use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use std::sync::Arc;
use thiserror::Error;
use tracing::{debug, error, info, warn};

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

        // Set audience validation
        if self.config.validate_audience {
            validation.set_audience(&[self.oidc_provider.audience()]);
        }

        // Decode and validate
        let token_data =
            decode::<Claims>(token, &decoding_key, &validation).map_err(|e| match e.kind() {
                jsonwebtoken::errors::ErrorKind::ExpiredSignature => JwtError::Expired,
                jsonwebtoken::errors::ErrorKind::InvalidIssuer => JwtError::InvalidIssuer {
                    expected: self.oidc_provider.issuer_url().to_string(),
                },
                jsonwebtoken::errors::ErrorKind::InvalidAudience => JwtError::InvalidAudience {
                    expected: self.oidc_provider.audience().to_string(),
                },
                jsonwebtoken::errors::ErrorKind::InvalidSignature => JwtError::InvalidSignature,
                _ => JwtError::DecodeError(e.to_string()),
            })?;

        let claims = token_data.claims;

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
mod tests {
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
}
