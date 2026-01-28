// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Safe Mode Fallback
//!
//! CAB-912: DenyAll/ForceReview fallback when Git or policy service unavailable.
//!
//! Safe modes:
//! - DenyAll: Reject all requests (most secure, may cause outages)
//! - ForceReview: Allow but require human review (balanced)
//! - AllowCached: Allow if we have valid cached policies (risk of stale)

use serde::{Deserialize, Serialize};

// =============================================================================
// Safe Mode Enum
// =============================================================================

/// Safe mode behavior when policy service is unavailable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum SafeMode {
    /// Deny all requests (fail-closed)
    ///
    /// Most secure option. Use when data integrity is critical.
    /// Risk: May cause service outages during Git/policy issues.
    DenyAll,

    /// Allow requests but force human review (default)
    ///
    /// Balanced option. APIs can be created but won't go live
    /// until policies are verified and human review completes.
    #[default]
    ForceReview,

    /// Allow if cached policies are still valid
    ///
    /// Least disruptive but carries risk of using stale policies.
    /// Only use if you have strong cache invalidation.
    AllowCached,
}

impl SafeMode {
    /// Parse safe mode from string.
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "deny_all" | "deny-all" | "denyall" => Some(SafeMode::DenyAll),
            "force_review" | "force-review" | "forcereview" => Some(SafeMode::ForceReview),
            "allow_cached" | "allow-cached" | "allowcached" => Some(SafeMode::AllowCached),
            _ => None,
        }
    }

    /// Human-readable description.
    pub fn description(&self) -> &'static str {
        match self {
            SafeMode::DenyAll => "Deny all requests when policy service unavailable",
            SafeMode::ForceReview => {
                "Allow but require human review when policy service unavailable"
            }
            SafeMode::AllowCached => "Allow if cached policies are valid",
        }
    }

    /// Whether this mode allows requests to proceed (possibly with review).
    pub fn allows_requests(&self) -> bool {
        match self {
            SafeMode::DenyAll => false,
            SafeMode::ForceReview => true,
            SafeMode::AllowCached => true,
        }
    }

    /// Whether this mode requires human review.
    pub fn requires_review(&self) -> bool {
        match self {
            SafeMode::DenyAll => false, // Not applicable, requests denied
            SafeMode::ForceReview => true,
            SafeMode::AllowCached => false, // Uses cached, no extra review
        }
    }
}

impl std::fmt::Display for SafeMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SafeMode::DenyAll => write!(f, "deny_all"),
            SafeMode::ForceReview => write!(f, "force_review"),
            SafeMode::AllowCached => write!(f, "allow_cached"),
        }
    }
}

// =============================================================================
// Safe Mode Config
// =============================================================================

/// Configuration for safe mode behavior.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafeModeConfig {
    /// Which safe mode to use
    pub mode: SafeMode,

    /// Maximum age of cached policies in safe mode (seconds)
    /// Only relevant for AllowCached mode
    pub max_cache_age_seconds: u64,

    /// Whether to send alerts when entering safe mode
    pub alert_on_safe_mode: bool,

    /// Message to include in denial responses
    pub denial_message: String,
}

impl Default for SafeModeConfig {
    fn default() -> Self {
        Self {
            mode: SafeMode::ForceReview,
            max_cache_age_seconds: 300, // 5 minutes
            alert_on_safe_mode: true,
            denial_message: "Policy service temporarily unavailable. Please retry later.".into(),
        }
    }
}

impl SafeModeConfig {
    /// Create config for deny-all mode.
    pub fn deny_all() -> Self {
        Self {
            mode: SafeMode::DenyAll,
            ..Default::default()
        }
    }

    /// Create config for force-review mode.
    pub fn force_review() -> Self {
        Self {
            mode: SafeMode::ForceReview,
            ..Default::default()
        }
    }

    /// Create config for allow-cached mode.
    pub fn allow_cached(max_age_seconds: u64) -> Self {
        Self {
            mode: SafeMode::AllowCached,
            max_cache_age_seconds: max_age_seconds,
            ..Default::default()
        }
    }
}

// =============================================================================
// Safe Mode Trigger
// =============================================================================

/// Reasons for entering safe mode.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SafeModeTrigger {
    /// Git service is unavailable
    GitUnavailable { error: String },

    /// Policy service is unavailable
    PolicyServiceUnavailable { error: String },

    /// Policy version check failed
    VersionCheckFailed { expected: String, actual: String },

    /// Circuit breaker is open
    CircuitBreakerOpen { failures: u32 },

    /// Manual override
    ManualOverride { reason: String },
}

impl SafeModeTrigger {
    /// Human-readable description of the trigger.
    pub fn message(&self) -> String {
        match self {
            SafeModeTrigger::GitUnavailable { error } => {
                format!("Git service unavailable: {}", error)
            }
            SafeModeTrigger::PolicyServiceUnavailable { error } => {
                format!("Policy service unavailable: {}", error)
            }
            SafeModeTrigger::VersionCheckFailed { expected, actual } => {
                format!(
                    "Policy version mismatch: expected {}, got {}",
                    expected, actual
                )
            }
            SafeModeTrigger::CircuitBreakerOpen { failures } => {
                format!("Circuit breaker open after {} failures", failures)
            }
            SafeModeTrigger::ManualOverride { reason } => {
                format!("Manual safe mode override: {}", reason)
            }
        }
    }

    /// Whether this trigger is retriable.
    pub fn is_retriable(&self) -> bool {
        match self {
            SafeModeTrigger::ManualOverride { .. } => false,
            _ => true,
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
    fn test_safe_mode_from_str() {
        assert_eq!(SafeMode::from_str("deny_all"), Some(SafeMode::DenyAll));
        assert_eq!(SafeMode::from_str("deny-all"), Some(SafeMode::DenyAll));
        assert_eq!(
            SafeMode::from_str("force_review"),
            Some(SafeMode::ForceReview)
        );
        assert_eq!(
            SafeMode::from_str("allow_cached"),
            Some(SafeMode::AllowCached)
        );
        assert_eq!(SafeMode::from_str("invalid"), None);
    }

    #[test]
    fn test_safe_mode_default() {
        assert_eq!(SafeMode::default(), SafeMode::ForceReview);
    }

    #[test]
    fn test_safe_mode_allows_requests() {
        assert!(!SafeMode::DenyAll.allows_requests());
        assert!(SafeMode::ForceReview.allows_requests());
        assert!(SafeMode::AllowCached.allows_requests());
    }

    #[test]
    fn test_safe_mode_requires_review() {
        assert!(!SafeMode::DenyAll.requires_review());
        assert!(SafeMode::ForceReview.requires_review());
        assert!(!SafeMode::AllowCached.requires_review());
    }

    #[test]
    fn test_safe_mode_display() {
        assert_eq!(format!("{}", SafeMode::DenyAll), "deny_all");
        assert_eq!(format!("{}", SafeMode::ForceReview), "force_review");
        assert_eq!(format!("{}", SafeMode::AllowCached), "allow_cached");
    }

    #[test]
    fn test_config_defaults() {
        let config = SafeModeConfig::default();
        assert_eq!(config.mode, SafeMode::ForceReview);
        assert_eq!(config.max_cache_age_seconds, 300);
        assert!(config.alert_on_safe_mode);
    }

    #[test]
    fn test_trigger_message() {
        let trigger = SafeModeTrigger::GitUnavailable {
            error: "connection refused".into(),
        };
        assert!(trigger.message().contains("connection refused"));
        assert!(trigger.is_retriable());

        let trigger = SafeModeTrigger::ManualOverride {
            reason: "maintenance".into(),
        };
        assert!(!trigger.is_retriable());
    }
}
