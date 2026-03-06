//! OAuth2 Subscription Validation
//!
//! Validates that a JWT bearer (identified by `azp` claim) has an active subscription
//! for the target API. Uses moka cache to avoid per-request Control Plane API calls.
//!
//! Flow: JWT validated → extract `azp` → check subscription cache → call CP API if miss.

use moka::sync::Cache;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tracing::debug;

/// Cached subscription info returned by the Control Plane API.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubscriptionInfo {
    pub valid: bool,
    pub subscription_id: String,
    pub tenant_id: String,
    pub api_id: String,
    pub oauth_client_id: String,
    pub rate_limit: Option<u32>,
    /// Security profile for auth chain selection (CAB-1744).
    /// Values: "api_key", "oauth2_public", "oauth2_confidential",
    /// "fapi_baseline", "fapi_advanced". Defaults to "oauth2_public".
    pub security_profile: String,
}

/// Subscription validator with moka cache (5-min TTL, 10k entries).
///
/// Reuses the shared `reqwest::Client` from AppState (Council adjustment #6).
pub struct SubscriptionValidator {
    cache: Cache<String, SubscriptionInfo>,
    control_plane_url: String,
    http_client: reqwest::Client,
}

impl SubscriptionValidator {
    /// Create a new validator. `http_client` should be the shared pooled client from AppState.
    pub fn new(control_plane_url: String, http_client: reqwest::Client) -> Self {
        let cache = Cache::builder()
            .time_to_live(Duration::from_secs(300))
            .max_capacity(10_000)
            .build();

        Self {
            cache,
            control_plane_url,
            http_client,
        }
    }

    /// Validate that `oauth_client_id` has an active subscription for `api_id`.
    ///
    /// Returns cached result if available, otherwise calls the Control Plane API.
    pub async fn validate(
        &self,
        oauth_client_id: &str,
        api_id: &str,
    ) -> Result<SubscriptionInfo, SubscriptionError> {
        let cache_key = format!("{}:{}", oauth_client_id, api_id);

        // Check cache
        if let Some(info) = self.cache.get(&cache_key) {
            debug!(
                oauth_client_id = %oauth_client_id,
                api_id = %api_id,
                "Subscription cache hit"
            );
            if info.valid {
                return Ok(info);
            } else {
                return Err(SubscriptionError::NoActiveSubscription);
            }
        }

        // Call Control Plane
        let info = self
            .validate_with_control_plane(oauth_client_id, api_id)
            .await?;

        // Cache result (both valid and invalid to avoid repeated lookups)
        self.cache.insert(cache_key, info.clone());

        if info.valid {
            Ok(info)
        } else {
            Err(SubscriptionError::NoActiveSubscription)
        }
    }

    async fn validate_with_control_plane(
        &self,
        oauth_client_id: &str,
        api_id: &str,
    ) -> Result<SubscriptionInfo, SubscriptionError> {
        if self.control_plane_url.is_empty() {
            return Err(SubscriptionError::ConfigError(
                "Control Plane URL not configured".into(),
            ));
        }

        let url = format!(
            "{}/v1/subscriptions/validate-subscription",
            self.control_plane_url
        );

        let response = self
            .http_client
            .post(&url)
            .json(&serde_json::json!({
                "oauth_client_id": oauth_client_id,
                "api_id": api_id
            }))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|e| SubscriptionError::NetworkError(e.to_string()))?;

        let status = response.status();
        if status.is_success() {
            let cp_resp: serde_json::Value = response
                .json()
                .await
                .map_err(|e| SubscriptionError::ParseError(e.to_string()))?;

            Ok(SubscriptionInfo {
                valid: cp_resp
                    .get("valid")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
                subscription_id: cp_resp
                    .get("subscription_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                tenant_id: cp_resp
                    .get("tenant_id")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                api_id: api_id.to_string(),
                oauth_client_id: oauth_client_id.to_string(),
                rate_limit: cp_resp
                    .get("rate_limit")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as u32),
                security_profile: cp_resp
                    .get("security_profile")
                    .and_then(|v| v.as_str())
                    .unwrap_or("oauth2_public")
                    .to_string(),
            })
        } else if status.as_u16() == 403 || status.as_u16() == 404 {
            // No active subscription or expired — cache as invalid
            Ok(SubscriptionInfo {
                valid: false,
                subscription_id: String::new(),
                tenant_id: String::new(),
                api_id: api_id.to_string(),
                oauth_client_id: oauth_client_id.to_string(),
                rate_limit: None,
                security_profile: String::new(),
            })
        } else {
            Err(SubscriptionError::ControlPlaneError(format!(
                "Unexpected status: {}",
                status
            )))
        }
    }

    /// Invalidate cached subscription (call on subscription status change).
    pub fn invalidate(&self, oauth_client_id: &str, api_id: &str) {
        let cache_key = format!("{}:{}", oauth_client_id, api_id);
        self.cache.invalidate(&cache_key);
        debug!(
            oauth_client_id = %oauth_client_id,
            api_id = %api_id,
            "Subscription cache invalidated"
        );
    }

    /// Get cache stats for metrics.
    pub fn cache_size(&self) -> u64 {
        self.cache.entry_count()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum SubscriptionError {
    #[error("No active subscription")]
    NoActiveSubscription,

    #[error("Missing azp claim in JWT")]
    MissingAzpClaim,

    #[error("Network error: {0}")]
    NetworkError(String),

    #[error("Parse error: {0}")]
    ParseError(String),

    #[error("Control plane error: {0}")]
    ControlPlaneError(String),

    #[error("Configuration error: {0}")]
    ConfigError(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cache_creation() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());
        assert_eq!(validator.cache_size(), 0);
    }

    #[test]
    fn test_cache_key_format() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());
        let key = format!("{}:{}", "kc-client-123", "api-weather");
        assert_eq!(key, "kc-client-123:api-weather");
        assert_eq!(validator.cache_size(), 0);
    }

    #[test]
    fn test_cache_insert_and_get() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());

        let info = SubscriptionInfo {
            valid: true,
            subscription_id: "sub-1".into(),
            tenant_id: "acme".into(),
            api_id: "api-weather".into(),
            oauth_client_id: "kc-client-123".into(),
            rate_limit: Some(100),
            security_profile: "oauth2_public".into(),
        };

        let cache_key = "kc-client-123:api-weather".to_string();
        validator.cache.insert(cache_key.clone(), info.clone());
        validator.cache.run_pending_tasks();

        assert_eq!(validator.cache_size(), 1);
        let cached = validator.cache.get(&cache_key).expect("should be cached");
        assert!(cached.valid);
        assert_eq!(cached.subscription_id, "sub-1");
    }

    #[test]
    fn test_invalidate() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());

        let info = SubscriptionInfo {
            valid: true,
            subscription_id: "sub-1".into(),
            tenant_id: "acme".into(),
            api_id: "api-weather".into(),
            oauth_client_id: "kc-client-123".into(),
            rate_limit: None,
            security_profile: "oauth2_public".into(),
        };

        validator
            .cache
            .insert("kc-client-123:api-weather".into(), info);
        validator.cache.run_pending_tasks();
        assert_eq!(validator.cache_size(), 1);

        validator.invalidate("kc-client-123", "api-weather");
        // moka invalidation may not be immediate but get() should return None
        assert!(validator
            .cache
            .get(&"kc-client-123:api-weather".to_string())
            .is_none());
    }

    #[tokio::test]
    async fn test_validate_empty_cp_url() {
        let validator = SubscriptionValidator::new(String::new(), reqwest::Client::new());
        let result = validator.validate("kc-client-123", "api-weather").await;
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            matches!(err, SubscriptionError::ConfigError(_)),
            "expected ConfigError, got: {err}"
        );
    }

    #[tokio::test]
    async fn test_validate_network_error() {
        // Point to a non-existent host to trigger network error
        let validator = SubscriptionValidator::new(
            "http://127.0.0.1:1".into(), // port 1 — connection refused
            reqwest::Client::builder()
                .timeout(Duration::from_millis(100))
                .build()
                .unwrap_or_default(),
        );
        let result = validator.validate("kc-client-123", "api-weather").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_validate_cache_hit_valid() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());

        // Pre-populate cache with valid subscription
        let info = SubscriptionInfo {
            valid: true,
            subscription_id: "sub-1".into(),
            tenant_id: "acme".into(),
            api_id: "api-weather".into(),
            oauth_client_id: "kc-client-123".into(),
            rate_limit: Some(100),
            security_profile: "oauth2_confidential".into(),
        };
        validator
            .cache
            .insert("kc-client-123:api-weather".into(), info);

        // Should return from cache without hitting CP API
        let result = validator.validate("kc-client-123", "api-weather").await;
        assert!(result.is_ok());
        let info = result.expect("should be valid");
        assert_eq!(info.subscription_id, "sub-1");
        assert_eq!(info.rate_limit, Some(100));
    }

    #[tokio::test]
    async fn test_validate_cache_hit_invalid() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());

        // Pre-populate cache with invalid subscription
        let info = SubscriptionInfo {
            valid: false,
            subscription_id: String::new(),
            tenant_id: String::new(),
            api_id: "api-weather".into(),
            oauth_client_id: "unknown-client".into(),
            rate_limit: None,
            security_profile: String::new(),
        };
        validator
            .cache
            .insert("unknown-client:api-weather".into(), info);

        // Should return NoActiveSubscription from cache
        let result = validator.validate("unknown-client", "api-weather").await;
        assert!(result.is_err());
        assert!(matches!(
            result.unwrap_err(),
            SubscriptionError::NoActiveSubscription
        ));
    }

    #[tokio::test]
    async fn test_security_profile_from_cache() {
        let validator =
            SubscriptionValidator::new("http://localhost:8000".into(), reqwest::Client::new());

        let info = SubscriptionInfo {
            valid: true,
            subscription_id: "sub-fapi".into(),
            tenant_id: "acme".into(),
            api_id: "api-banking".into(),
            oauth_client_id: "kc-fapi-client".into(),
            rate_limit: None,
            security_profile: "fapi_advanced".into(),
        };
        validator
            .cache
            .insert("kc-fapi-client:api-banking".into(), info);

        let result = validator.validate("kc-fapi-client", "api-banking").await;
        assert!(result.is_ok());
        let info = result.expect("should be valid");
        assert_eq!(info.security_profile, "fapi_advanced");
    }

    #[test]
    fn test_security_profile_default() {
        // When security_profile is missing from CP API response, it defaults to "oauth2_public"
        let info = SubscriptionInfo {
            valid: true,
            subscription_id: "sub-1".into(),
            tenant_id: "acme".into(),
            api_id: "api-1".into(),
            oauth_client_id: "kc-1".into(),
            rate_limit: None,
            security_profile: "oauth2_public".into(),
        };
        assert_eq!(info.security_profile, "oauth2_public");
    }

    #[test]
    fn test_subscription_error_display() {
        let err = SubscriptionError::MissingAzpClaim;
        assert_eq!(err.to_string(), "Missing azp claim in JWT");

        let err = SubscriptionError::NoActiveSubscription;
        assert_eq!(err.to_string(), "No active subscription");
    }
}
