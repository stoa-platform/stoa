//! API Key Authentication
//!
//! Validates API keys against Control Plane with moka cache.
//! WIP: Not yet instantiated in AppState. Remove `dead_code` when wired.
#![allow(dead_code)]

use axum::{
    extract::{Request, State},
    http::{header, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use moka::sync::Cache;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, warn};

use crate::config::Config;

/// Cached API key info
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiKeyInfo {
    pub key_id: String,
    pub tenant_id: String,
    pub subscription_id: String,
    pub scopes: Vec<String>,
    pub valid: bool,
}

/// API Key validator with caching
pub struct ApiKeyValidator {
    cache: Cache<String, ApiKeyInfo>,
    control_plane_url: String,
    http_client: reqwest::Client,
}

impl ApiKeyValidator {
    pub fn new(config: &Config) -> Self {
        // Cache with 5 min TTL, max 10k entries
        let cache = Cache::builder()
            .time_to_live(Duration::from_secs(300))
            .max_capacity(10_000)
            .build();

        Self {
            cache,
            control_plane_url: config.control_plane_url.clone().unwrap_or_default(),
            http_client: reqwest::Client::new(),
        }
    }

    /// Validate API key (cache first, then Control Plane)
    pub async fn validate(&self, api_key: &str) -> Result<ApiKeyInfo, ApiKeyError> {
        // Check cache
        if let Some(info) = self.cache.get(api_key) {
            debug!(key_id = %info.key_id, "API key cache hit");
            if info.valid {
                return Ok(info);
            } else {
                return Err(ApiKeyError::Invalid);
            }
        }

        // Call Control Plane
        let info = self.validate_with_control_plane(api_key).await?;

        // Cache result
        self.cache.insert(api_key.to_string(), info.clone());

        if info.valid {
            Ok(info)
        } else {
            Err(ApiKeyError::Invalid)
        }
    }

    async fn validate_with_control_plane(&self, api_key: &str) -> Result<ApiKeyInfo, ApiKeyError> {
        if self.control_plane_url.is_empty() {
            return Err(ApiKeyError::ConfigError(
                "Control Plane URL not configured".into(),
            ));
        }

        let url = format!("{}/api/v1/keys/validate", self.control_plane_url);

        let response = self
            .http_client
            .post(&url)
            .header("X-API-Key", api_key)
            .json(&serde_json::json!({ "key": api_key }))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| ApiKeyError::NetworkError(e.to_string()))?;

        let status = response.status();
        if status.is_success() {
            let info: ApiKeyInfo = response
                .json()
                .await
                .map_err(|e| ApiKeyError::ParseError(e.to_string()))?;
            Ok(info)
        } else if status.as_u16() == 401 || status.as_u16() == 403 {
            Ok(ApiKeyInfo {
                key_id: "unknown".into(),
                tenant_id: "".into(),
                subscription_id: "".into(),
                scopes: vec![],
                valid: false,
            })
        } else {
            Err(ApiKeyError::ControlPlaneError(format!(
                "Unexpected status: {}",
                status
            )))
        }
    }

    /// Invalidate cached key (call on key rotation)
    pub fn invalidate(&self, api_key: &str) {
        self.cache.invalidate(api_key);
        debug!("API key cache invalidated");
    }

    /// Get cache stats for metrics
    pub fn cache_size(&self) -> u64 {
        self.cache.entry_count()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ApiKeyError {
    #[error("Invalid API key")]
    Invalid,

    #[error("API key missing")]
    Missing,

    #[error("Network error: {0}")]
    NetworkError(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("Control plane error: {0}")]
    ControlPlaneError(String),

    #[error("Configuration error: {0}")]
    ConfigError(String),
}

/// Combined auth middleware: JWT first, fallback to API Key
pub async fn combined_auth_middleware(
    State(state): State<Arc<AppStateAuth>>,
    mut request: Request,
    next: Next,
) -> Response {
    // Try JWT first (from Authorization: Bearer header)
    if let Some(auth_header) = request.headers().get(header::AUTHORIZATION) {
        if let Ok(auth_str) = auth_header.to_str() {
            if auth_str.starts_with("Bearer ") {
                // JWT validation handled elsewhere
                return next.run(request).await;
            }
        }
    }

    // Fallback to API Key (from X-API-Key header)
    let api_key = request
        .headers()
        .get("X-API-Key")
        .and_then(|v| v.to_str().ok());

    match api_key {
        Some(key) => {
            match state.api_key_validator.validate(key).await {
                Ok(info) => {
                    // Inject tenant info into request extensions
                    request.extensions_mut().insert(info);
                    next.run(request).await
                }
                Err(e) => {
                    warn!(error = %e, "API key validation failed");
                    (StatusCode::UNAUTHORIZED, "Invalid API key").into_response()
                }
            }
        }
        None => {
            // No auth provided
            (StatusCode::UNAUTHORIZED, "Authentication required").into_response()
        }
    }
}

/// AppState subset for auth middleware
pub struct AppStateAuth {
    pub api_key_validator: ApiKeyValidator,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_creation() {
        let config = Config::default();
        let validator = ApiKeyValidator::new(&config);
        assert_eq!(validator.cache_size(), 0);
    }
}
