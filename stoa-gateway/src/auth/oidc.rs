// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! OIDC Discovery
//!
//! CAB-912 P2: OIDC discovery with JWKS caching for Keycloak.
//!
//! Features:
//! - Automatic OIDC configuration discovery
//! - JWKS fetching and caching (moka cache)
//! - Key rotation support
//! - TTL-based cache invalidation (5 minutes)

use moka::future::Cache;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, error, info, warn};

// =============================================================================
// Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum OidcError {
    #[error("Failed to fetch OIDC configuration: {0}")]
    ConfigFetchError(String),

    #[error("Failed to fetch JWKS: {0}")]
    JwksFetchError(String),

    #[error("Key not found: {kid}")]
    KeyNotFound { kid: String },

    #[error("Invalid issuer: expected {expected}, got {actual}")]
    InvalidIssuer { expected: String, actual: String },

    #[error("HTTP error: {0}")]
    HttpError(#[from] reqwest::Error),
}

// =============================================================================
// OIDC Configuration
// =============================================================================

/// OIDC Discovery configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OidcConfig {
    /// Issuer URL
    pub issuer: String,

    /// Authorization endpoint
    pub authorization_endpoint: String,

    /// Token endpoint
    pub token_endpoint: String,

    /// UserInfo endpoint
    #[serde(default)]
    pub userinfo_endpoint: Option<String>,

    /// JWKS URI for public keys
    pub jwks_uri: String,

    /// End session endpoint
    #[serde(default)]
    pub end_session_endpoint: Option<String>,

    /// Supported response types
    #[serde(default)]
    pub response_types_supported: Vec<String>,

    /// Supported grant types
    #[serde(default)]
    pub grant_types_supported: Vec<String>,

    /// Supported subject types
    #[serde(default)]
    pub subject_types_supported: Vec<String>,

    /// Supported signing algorithms
    #[serde(default)]
    pub id_token_signing_alg_values_supported: Vec<String>,

    /// Supported scopes
    #[serde(default)]
    pub scopes_supported: Vec<String>,

    /// Supported claims
    #[serde(default)]
    pub claims_supported: Vec<String>,
}

// =============================================================================
// JWKS (JSON Web Key Set)
// =============================================================================

/// JSON Web Key Set.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Jwks {
    /// List of keys
    pub keys: Vec<Jwk>,
}

/// JSON Web Key.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Jwk {
    /// Key type (e.g., "RSA")
    pub kty: String,

    /// Key ID
    #[serde(default)]
    pub kid: Option<String>,

    /// Algorithm (e.g., "RS256")
    #[serde(default)]
    pub alg: Option<String>,

    /// Key use (e.g., "sig" for signature)
    #[serde(rename = "use", default)]
    pub key_use: Option<String>,

    /// RSA modulus (for RSA keys)
    #[serde(default)]
    pub n: Option<String>,

    /// RSA exponent (for RSA keys)
    #[serde(default)]
    pub e: Option<String>,

    /// X.509 certificate chain
    #[serde(default)]
    pub x5c: Option<Vec<String>>,

    /// X.509 certificate thumbprint (SHA-1)
    #[serde(default)]
    pub x5t: Option<String>,

    /// X.509 certificate thumbprint (SHA-256)
    #[serde(rename = "x5t#S256", default)]
    pub x5t_s256: Option<String>,
}

impl Jwk {
    /// Get the key ID.
    pub fn key_id(&self) -> Option<&str> {
        self.kid.as_deref()
    }

    /// Check if this is an RSA key.
    pub fn is_rsa(&self) -> bool {
        self.kty == "RSA"
    }

    /// Check if this key is used for signatures.
    pub fn is_signature_key(&self) -> bool {
        self.key_use.as_deref() == Some("sig") || self.key_use.is_none()
    }

    /// Convert to jsonwebtoken DecodingKey.
    pub fn to_decoding_key(&self) -> Result<jsonwebtoken::DecodingKey, OidcError> {
        if !self.is_rsa() {
            return Err(OidcError::JwksFetchError(format!(
                "Unsupported key type: {}",
                self.kty
            )));
        }

        let n = self
            .n
            .as_ref()
            .ok_or_else(|| OidcError::JwksFetchError("Missing RSA modulus (n)".to_string()))?;
        let e = self
            .e
            .as_ref()
            .ok_or_else(|| OidcError::JwksFetchError("Missing RSA exponent (e)".to_string()))?;

        jsonwebtoken::DecodingKey::from_rsa_components(n, e)
            .map_err(|e| OidcError::JwksFetchError(format!("Invalid RSA key: {}", e)))
    }
}

// =============================================================================
// OIDC Provider
// =============================================================================

/// OIDC Provider configuration.
#[derive(Debug, Clone)]
pub struct OidcProviderConfig {
    /// Issuer URL (e.g., https://auth.gostoa.dev/realms/stoa)
    pub issuer_url: String,

    /// Expected audience (client ID)
    pub audience: String,

    /// JWKS cache TTL
    pub jwks_cache_ttl: Duration,

    /// HTTP timeout for discovery
    pub http_timeout: Duration,
}

impl Default for OidcProviderConfig {
    fn default() -> Self {
        Self {
            issuer_url: "https://auth.gostoa.dev/realms/stoa".to_string(),
            audience: "stoa-mcp".to_string(),
            jwks_cache_ttl: Duration::from_secs(300), // 5 minutes
            http_timeout: Duration::from_secs(10),
        }
    }
}

/// OIDC Provider with caching.
pub struct OidcProvider {
    config: OidcProviderConfig,
    client: Client,
    oidc_config_cache: Cache<String, Arc<OidcConfig>>,
    jwks_cache: Cache<String, Arc<Jwks>>,
}

impl OidcProvider {
    /// Create a new OIDC provider.
    pub fn new(config: OidcProviderConfig) -> Self {
        let client = Client::builder()
            .timeout(config.http_timeout)
            .build()
            .expect("Failed to create HTTP client");

        let oidc_config_cache = Cache::builder()
            .time_to_live(config.jwks_cache_ttl)
            .max_capacity(10)
            .build();

        let jwks_cache = Cache::builder()
            .time_to_live(config.jwks_cache_ttl)
            .max_capacity(10)
            .build();

        Self {
            config,
            client,
            oidc_config_cache,
            jwks_cache,
        }
    }

    /// Get the issuer URL.
    pub fn issuer_url(&self) -> &str {
        &self.config.issuer_url
    }

    /// Get the expected audience.
    pub fn audience(&self) -> &str {
        &self.config.audience
    }

    /// Fetch OIDC configuration (with caching).
    pub async fn get_config(&self) -> Result<Arc<OidcConfig>, OidcError> {
        let cache_key = self.config.issuer_url.clone();

        // Try cache first
        if let Some(config) = self.oidc_config_cache.get(&cache_key).await {
            debug!("OIDC config cache hit");
            return Ok(config);
        }

        // Fetch from discovery endpoint
        let discovery_url = format!(
            "{}/.well-known/openid-configuration",
            self.config.issuer_url.trim_end_matches('/')
        );

        info!(url = %discovery_url, "Fetching OIDC configuration");

        let response = self
            .client
            .get(&discovery_url)
            .send()
            .await
            .map_err(|e| OidcError::ConfigFetchError(e.to_string()))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            error!(status = %status, body = %body, "Failed to fetch OIDC config");
            return Err(OidcError::ConfigFetchError(format!(
                "HTTP {}: {}",
                status, body
            )));
        }

        let config: OidcConfig = response
            .json()
            .await
            .map_err(|e| OidcError::ConfigFetchError(e.to_string()))?;

        // Validate issuer
        if config.issuer != self.config.issuer_url {
            warn!(
                expected = %self.config.issuer_url,
                actual = %config.issuer,
                "Issuer mismatch in OIDC config"
            );
        }

        let config = Arc::new(config);
        self.oidc_config_cache
            .insert(cache_key, config.clone())
            .await;

        info!("OIDC configuration cached");
        Ok(config)
    }

    /// Fetch JWKS (with caching).
    pub async fn get_jwks(&self) -> Result<Arc<Jwks>, OidcError> {
        // First, get the OIDC config to find JWKS URI
        let oidc_config = self.get_config().await?;
        let jwks_uri = &oidc_config.jwks_uri;

        // Try cache first
        if let Some(jwks) = self.jwks_cache.get(jwks_uri).await {
            debug!("JWKS cache hit");
            return Ok(jwks);
        }

        info!(url = %jwks_uri, "Fetching JWKS");

        let response = self
            .client
            .get(jwks_uri)
            .send()
            .await
            .map_err(|e| OidcError::JwksFetchError(e.to_string()))?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            error!(status = %status, body = %body, "Failed to fetch JWKS");
            return Err(OidcError::JwksFetchError(format!(
                "HTTP {}: {}",
                status, body
            )));
        }

        let jwks: Jwks = response
            .json()
            .await
            .map_err(|e| OidcError::JwksFetchError(e.to_string()))?;

        info!(key_count = jwks.keys.len(), "JWKS fetched and cached");

        let jwks = Arc::new(jwks);
        self.jwks_cache.insert(jwks_uri.clone(), jwks.clone()).await;

        Ok(jwks)
    }

    /// Get a specific key by ID.
    pub async fn get_key(&self, kid: &str) -> Result<Jwk, OidcError> {
        let jwks = self.get_jwks().await?;

        jwks.keys
            .iter()
            .find(|k| k.kid.as_deref() == Some(kid) && k.is_signature_key())
            .cloned()
            .ok_or_else(|| OidcError::KeyNotFound {
                kid: kid.to_string(),
            })
    }

    /// Get any valid signing key (when kid is not specified).
    pub async fn get_default_key(&self) -> Result<Jwk, OidcError> {
        let jwks = self.get_jwks().await?;

        jwks.keys
            .iter()
            .find(|k| k.is_rsa() && k.is_signature_key())
            .cloned()
            .ok_or_else(|| OidcError::JwksFetchError("No valid signing key found".to_string()))
    }

    /// Invalidate all caches (for testing or key rotation).
    pub async fn invalidate_cache(&self) {
        self.oidc_config_cache.invalidate_all();
        self.jwks_cache.invalidate_all();
        info!("OIDC caches invalidated");
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jwk_is_rsa() {
        let jwk = Jwk {
            kty: "RSA".to_string(),
            kid: Some("key-1".to_string()),
            alg: Some("RS256".to_string()),
            key_use: Some("sig".to_string()),
            n: Some("modulus".to_string()),
            e: Some("AQAB".to_string()),
            x5c: None,
            x5t: None,
            x5t_s256: None,
        };
        assert!(jwk.is_rsa());
        assert!(jwk.is_signature_key());
    }

    #[test]
    fn test_jwk_non_signature() {
        let jwk = Jwk {
            kty: "RSA".to_string(),
            kid: Some("enc-key".to_string()),
            alg: Some("RSA-OAEP".to_string()),
            key_use: Some("enc".to_string()),
            n: Some("modulus".to_string()),
            e: Some("AQAB".to_string()),
            x5c: None,
            x5t: None,
            x5t_s256: None,
        };
        assert!(!jwk.is_signature_key());
    }

    #[test]
    fn test_oidc_config_parse() {
        let json = r#"{
            "issuer": "https://auth.gostoa.dev/realms/stoa",
            "authorization_endpoint": "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/auth",
            "token_endpoint": "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token",
            "jwks_uri": "https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/certs",
            "response_types_supported": ["code", "token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"]
        }"#;

        let config: OidcConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.issuer, "https://auth.gostoa.dev/realms/stoa");
        assert!(config
            .id_token_signing_alg_values_supported
            .contains(&"RS256".to_string()));
    }

    #[test]
    fn test_jwks_parse() {
        let json = r#"{
            "keys": [
                {
                    "kty": "RSA",
                    "kid": "key-1",
                    "use": "sig",
                    "alg": "RS256",
                    "n": "sXchDaQebSXKcvLx",
                    "e": "AQAB"
                }
            ]
        }"#;

        let jwks: Jwks = serde_json::from_str(json).unwrap();
        assert_eq!(jwks.keys.len(), 1);
        assert_eq!(jwks.keys[0].kid, Some("key-1".to_string()));
    }

    #[test]
    fn test_provider_config_default() {
        let config = OidcProviderConfig::default();
        assert_eq!(config.audience, "stoa-mcp");
        assert_eq!(config.jwks_cache_ttl, Duration::from_secs(300));
    }
}
