//! API Classifications
//!
//! CAB-912: H/VH/VVH classification definitions with required policies and rate limits.
//!
//! Classification Levels:
//! - H (High): Standard APIs, auto-approved, 50 requests/hour
//! - VH (Very High): Sensitive APIs, requires review, 10 requests/hour
//! - VVH (Very Very High): Critical APIs, requires review, 2 requests/hour

use serde::{Deserialize, Serialize};
use std::collections::HashSet;

// =============================================================================
// Classification Enum
// =============================================================================

/// API classification level determining approval workflow and rate limits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum Classification {
    /// High - Standard APIs
    H,
    /// Very High - Sensitive APIs
    VH,
    /// Very Very High - Critical APIs
    VVH,
}

impl Classification {
    /// Parse classification from string (case-insensitive).
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_uppercase().as_str() {
            "H" => Some(Classification::H),
            "VH" => Some(Classification::VH),
            "VVH" => Some(Classification::VVH),
            _ => None,
        }
    }

    /// Whether this classification auto-approves (no human review needed).
    pub fn auto_approve(&self) -> bool {
        match self {
            Classification::H => true,
            Classification::VH => false,
            Classification::VVH => false,
        }
    }

    /// Rate limit per hour for this classification.
    pub fn rate_limit_per_hour(&self) -> u32 {
        match self {
            Classification::H => 50,
            Classification::VH => 10,
            Classification::VVH => 2,
        }
    }

    /// Required policies for this classification.
    pub fn required_policies(&self) -> HashSet<&'static str> {
        let mut policies = HashSet::new();

        // H base policies (required for all)
        policies.insert("rate-limit");
        policies.insert("auth-jwt");

        match self {
            Classification::H => {}
            Classification::VH => {
                // VH adds mTLS and audit logging
                policies.insert("mtls");
                policies.insert("audit-logging");
            }
            Classification::VVH => {
                // VVH includes VH policies plus encryption and geo-restriction
                policies.insert("mtls");
                policies.insert("audit-logging");
                policies.insert("data-encryption");
                policies.insert("geo-restriction");
            }
        }

        policies
    }

    /// Check if provided policies satisfy requirements for this classification.
    ///
    /// Returns Ok(()) if all required policies are present, or Err with missing policies.
    pub fn validate_policies(&self, provided: &[String]) -> Result<(), Vec<String>> {
        let required = self.required_policies();
        let provided_set: HashSet<&str> = provided.iter().map(|s| s.as_str()).collect();

        let missing: Vec<String> = required
            .iter()
            .filter(|p| !provided_set.contains(*p))
            .map(|s| s.to_string())
            .collect();

        if missing.is_empty() {
            Ok(())
        } else {
            Err(missing)
        }
    }

    /// Human-readable description of this classification.
    pub fn description(&self) -> &'static str {
        match self {
            Classification::H => "High - Standard APIs with basic security",
            Classification::VH => "Very High - Sensitive APIs requiring mTLS and audit logging",
            Classification::VVH => {
                "Very Very High - Critical APIs with encryption and geo-restriction"
            }
        }
    }
}

impl std::fmt::Display for Classification {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Classification::H => write!(f, "H"),
            Classification::VH => write!(f, "VH"),
            Classification::VVH => write!(f, "VVH"),
        }
    }
}

impl Default for Classification {
    fn default() -> Self {
        Classification::H
    }
}

// =============================================================================
// Classification Config
// =============================================================================

/// Configuration for classification rate limits (can be overridden by env).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassificationConfig {
    /// Rate limit per hour for H classification
    pub h_rate_limit: u32,
    /// Rate limit per hour for VH classification
    pub vh_rate_limit: u32,
    /// Rate limit per hour for VVH classification
    pub vvh_rate_limit: u32,
    /// Global rate limit per tenant per minute
    pub tenant_rate_limit: u32,
}

impl Default for ClassificationConfig {
    fn default() -> Self {
        Self {
            h_rate_limit: 50,
            vh_rate_limit: 10,
            vvh_rate_limit: 2,
            tenant_rate_limit: 10,
        }
    }
}

impl ClassificationConfig {
    /// Get rate limit for a specific classification.
    pub fn rate_limit_for(&self, classification: Classification) -> u32 {
        match classification {
            Classification::H => self.h_rate_limit,
            Classification::VH => self.vh_rate_limit,
            Classification::VVH => self.vvh_rate_limit,
        }
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_classification_from_str() {
        assert_eq!(Classification::from_str("H"), Some(Classification::H));
        assert_eq!(Classification::from_str("h"), Some(Classification::H));
        assert_eq!(Classification::from_str("VH"), Some(Classification::VH));
        assert_eq!(Classification::from_str("vh"), Some(Classification::VH));
        assert_eq!(Classification::from_str("VVH"), Some(Classification::VVH));
        assert_eq!(Classification::from_str("vvh"), Some(Classification::VVH));
        assert_eq!(Classification::from_str("invalid"), None);
    }

    #[test]
    fn test_auto_approve() {
        assert!(Classification::H.auto_approve());
        assert!(!Classification::VH.auto_approve());
        assert!(!Classification::VVH.auto_approve());
    }

    #[test]
    fn test_rate_limits() {
        assert_eq!(Classification::H.rate_limit_per_hour(), 50);
        assert_eq!(Classification::VH.rate_limit_per_hour(), 10);
        assert_eq!(Classification::VVH.rate_limit_per_hour(), 2);
    }

    #[test]
    fn test_required_policies_h() {
        let policies = Classification::H.required_policies();
        assert!(policies.contains("rate-limit"));
        assert!(policies.contains("auth-jwt"));
        assert_eq!(policies.len(), 2);
    }

    #[test]
    fn test_required_policies_vh() {
        let policies = Classification::VH.required_policies();
        assert!(policies.contains("rate-limit"));
        assert!(policies.contains("auth-jwt"));
        assert!(policies.contains("mtls"));
        assert!(policies.contains("audit-logging"));
        assert_eq!(policies.len(), 4);
    }

    #[test]
    fn test_required_policies_vvh() {
        let policies = Classification::VVH.required_policies();
        assert!(policies.contains("rate-limit"));
        assert!(policies.contains("auth-jwt"));
        assert!(policies.contains("mtls"));
        assert!(policies.contains("audit-logging"));
        assert!(policies.contains("data-encryption"));
        assert!(policies.contains("geo-restriction"));
        assert_eq!(policies.len(), 6);
    }

    #[test]
    fn test_validate_policies_h_success() {
        let provided = vec!["rate-limit".to_string(), "auth-jwt".to_string()];
        assert!(Classification::H.validate_policies(&provided).is_ok());
    }

    #[test]
    fn test_validate_policies_h_missing() {
        let provided = vec!["rate-limit".to_string()];
        let result = Classification::H.validate_policies(&provided);
        assert!(result.is_err());
        let missing = result.unwrap_err();
        assert!(missing.contains(&"auth-jwt".to_string()));
    }

    #[test]
    fn test_validate_policies_vvh_success() {
        let provided = vec![
            "rate-limit".to_string(),
            "auth-jwt".to_string(),
            "mtls".to_string(),
            "audit-logging".to_string(),
            "data-encryption".to_string(),
            "geo-restriction".to_string(),
        ];
        assert!(Classification::VVH.validate_policies(&provided).is_ok());
    }

    #[test]
    fn test_classification_display() {
        assert_eq!(format!("{}", Classification::H), "H");
        assert_eq!(format!("{}", Classification::VH), "VH");
        assert_eq!(format!("{}", Classification::VVH), "VVH");
    }

    #[test]
    fn test_classification_config() {
        let config = ClassificationConfig::default();
        assert_eq!(config.rate_limit_for(Classification::H), 50);
        assert_eq!(config.rate_limit_for(Classification::VH), 10);
        assert_eq!(config.rate_limit_for(Classification::VVH), 2);
    }
}
