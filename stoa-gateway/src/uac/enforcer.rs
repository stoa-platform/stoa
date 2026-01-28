// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! UAC Enforcer
//!
//! CAB-912: Policy enforcement with Git version checking.
//!
//! The enforcer ensures:
//! 1. Classification requirements are met (H/VH/VVH)
//! 2. All required policies are present
//! 3. Policy version is logged for audit trail
//! 4. Safe mode fallback when policies unavailable

use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{info, warn};

use super::cache::VersionedPolicyCache;
use super::classifications::Classification;
use super::safe_mode::{SafeMode, SafeModeConfig};
use crate::mcp::protocol::ApiState;

// =============================================================================
// Enforcement Context
// =============================================================================

/// Context for policy enforcement decisions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnforcementContext {
    /// Tenant identifier
    pub tenant_id: String,

    /// User identifier (from JWT)
    pub user_id: String,

    /// User's roles
    #[serde(default)]
    pub roles: Vec<String>,

    /// Request ID for tracing
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_id: Option<String>,
}

impl EnforcementContext {
    /// Create a new enforcement context.
    pub fn new(tenant_id: impl Into<String>, user_id: impl Into<String>) -> Self {
        Self {
            tenant_id: tenant_id.into(),
            user_id: user_id.into(),
            roles: vec![],
            request_id: None,
        }
    }

    /// Add roles to the context.
    pub fn with_roles(mut self, roles: Vec<String>) -> Self {
        self.roles = roles;
        self
    }

    /// Add request ID for tracing.
    pub fn with_request_id(mut self, request_id: impl Into<String>) -> Self {
        self.request_id = Some(request_id.into());
        self
    }

    /// Check if user has admin role.
    pub fn is_admin(&self) -> bool {
        self.roles.iter().any(|r| r == "admin" || r == "cpi-admin")
    }
}

// =============================================================================
// Enforcement Decision
// =============================================================================

/// Result of policy enforcement check.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "decision", rename_all = "lowercase")]
pub enum EnforcementDecision {
    /// Request is allowed to proceed
    Allow {
        /// Resulting API state (active or pending_review)
        state: ApiState,
        /// Policy version used for this decision (for audit)
        policy_version: String,
    },

    /// Request is denied
    Deny {
        /// Reason for denial
        reason: String,
        /// Missing policies (if any)
        missing_policies: Vec<String>,
        /// Whether the request can be retried
        retriable: bool,
    },
}

impl EnforcementDecision {
    /// Create an Allow decision with auto-approve (H classification).
    pub fn allow_active(policy_version: String) -> Self {
        Self::Allow {
            state: ApiState::Active,
            policy_version,
        }
    }

    /// Create an Allow decision with pending review (VH/VVH classification).
    pub fn allow_pending_review(policy_version: String) -> Self {
        Self::Allow {
            state: ApiState::PendingReview,
            policy_version,
        }
    }

    /// Create a Deny decision for missing policies.
    pub fn deny_missing_policies(missing: Vec<String>) -> Self {
        Self::Deny {
            reason: format!("Missing required policies: {}", missing.join(", ")),
            missing_policies: missing,
            retriable: true,
        }
    }

    /// Create a Deny decision for policy unavailable (safe mode).
    pub fn deny_safe_mode(reason: impl Into<String>) -> Self {
        Self::Deny {
            reason: reason.into(),
            missing_policies: vec![],
            retriable: true,
        }
    }

    /// Create a Deny decision for rate limit.
    pub fn deny_rate_limit(classification: Classification) -> Self {
        Self::Deny {
            reason: format!(
                "Rate limit exceeded for {} classification: max {} per hour",
                classification,
                classification.rate_limit_per_hour()
            ),
            missing_policies: vec![],
            retriable: true,
        }
    }

    /// Check if this is an Allow decision.
    pub fn is_allowed(&self) -> bool {
        matches!(self, EnforcementDecision::Allow { .. })
    }

    /// Get the policy version if allowed.
    pub fn policy_version(&self) -> Option<&str> {
        match self {
            EnforcementDecision::Allow { policy_version, .. } => Some(policy_version),
            EnforcementDecision::Deny { .. } => None,
        }
    }
}

// =============================================================================
// UAC Enforcer
// =============================================================================

/// UAC (Unified Access Control) Enforcer.
///
/// Enforces policies based on classification and validates requirements.
pub struct UacEnforcer {
    /// Policy cache with version checking
    cache: Arc<VersionedPolicyCache>,

    /// Safe mode configuration
    safe_mode: SafeModeConfig,
}

impl UacEnforcer {
    /// Create a new enforcer with the given cache.
    pub fn new(cache: Arc<VersionedPolicyCache>) -> Self {
        Self {
            cache,
            safe_mode: SafeModeConfig::default(),
        }
    }

    /// Create an enforcer with custom safe mode config.
    pub fn with_safe_mode(mut self, config: SafeModeConfig) -> Self {
        self.safe_mode = config;
        self
    }

    /// Enforce policies for an API creation request.
    ///
    /// # Arguments
    /// * `classification` - API classification (H/VH/VVH)
    /// * `provided_policies` - Policies provided in the request
    /// * `ctx` - Enforcement context with tenant/user info
    ///
    /// # Returns
    /// * `EnforcementDecision` - Allow or Deny with details
    pub fn enforce(
        &self,
        classification: Classification,
        provided_policies: &[String],
        ctx: &EnforcementContext,
    ) -> EnforcementDecision {
        // Get current policy version
        let policy_version = self.cache.get_version();

        // If no version available, check safe mode
        if policy_version.is_empty() {
            warn!(
                tenant = %ctx.tenant_id,
                user = %ctx.user_id,
                "No policy version available - entering safe mode"
            );
            return self.apply_safe_mode(classification, ctx);
        }

        // Validate required policies
        if let Err(missing) = classification.validate_policies(provided_policies) {
            info!(
                tenant = %ctx.tenant_id,
                user = %ctx.user_id,
                classification = %classification,
                missing = ?missing,
                "Missing required policies"
            );
            return EnforcementDecision::deny_missing_policies(missing);
        }

        // All policies present - determine state based on classification
        let state = if classification.auto_approve() {
            ApiState::Active
        } else {
            ApiState::PendingReview
        };

        info!(
            tenant = %ctx.tenant_id,
            user = %ctx.user_id,
            classification = %classification,
            state = %state,
            policy_version = %policy_version,
            "Enforcement decision: ALLOW"
        );

        EnforcementDecision::Allow {
            state,
            policy_version,
        }
    }

    /// Apply safe mode when policies are unavailable.
    fn apply_safe_mode(
        &self,
        classification: Classification,
        ctx: &EnforcementContext,
    ) -> EnforcementDecision {
        match self.safe_mode.mode {
            SafeMode::DenyAll => {
                warn!(
                    tenant = %ctx.tenant_id,
                    user = %ctx.user_id,
                    "Safe mode: DenyAll"
                );
                EnforcementDecision::deny_safe_mode(
                    "Policy service unavailable - all requests denied (safe mode)",
                )
            }
            SafeMode::ForceReview => {
                warn!(
                    tenant = %ctx.tenant_id,
                    user = %ctx.user_id,
                    classification = %classification,
                    "Safe mode: ForceReview"
                );
                // Allow but require human review regardless of classification
                EnforcementDecision::Allow {
                    state: ApiState::PendingReview,
                    policy_version: "safe-mode".to_string(),
                }
            }
            SafeMode::AllowCached => {
                // This mode would check if we have valid cached policies
                // For now, fall back to ForceReview
                EnforcementDecision::Allow {
                    state: ApiState::PendingReview,
                    policy_version: "safe-mode-cached".to_string(),
                }
            }
        }
    }

    /// Get the current policy version.
    pub fn policy_version(&self) -> String {
        self.cache.get_version()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_enforcer() -> UacEnforcer {
        let cache = Arc::new(VersionedPolicyCache::new(3600));
        cache.set_version("test-version-123".to_string());
        UacEnforcer::new(cache)
    }

    fn make_context() -> EnforcementContext {
        EnforcementContext::new("tenant-acme", "user-123")
    }

    #[test]
    fn test_enforce_h_with_all_policies() {
        let enforcer = make_enforcer();
        let ctx = make_context();

        let policies = vec!["rate-limit".to_string(), "auth-jwt".to_string()];

        let decision = enforcer.enforce(Classification::H, &policies, &ctx);

        assert!(decision.is_allowed());
        match decision {
            EnforcementDecision::Allow {
                state,
                policy_version,
            } => {
                assert_eq!(state, ApiState::Active);
                assert_eq!(policy_version, "test-version-123");
            }
            _ => panic!("Expected Allow"),
        }
    }

    #[test]
    fn test_enforce_h_missing_policy() {
        let enforcer = make_enforcer();
        let ctx = make_context();

        let policies = vec!["rate-limit".to_string()]; // missing auth-jwt

        let decision = enforcer.enforce(Classification::H, &policies, &ctx);

        assert!(!decision.is_allowed());
        match decision {
            EnforcementDecision::Deny {
                missing_policies, ..
            } => {
                assert!(missing_policies.contains(&"auth-jwt".to_string()));
            }
            _ => panic!("Expected Deny"),
        }
    }

    #[test]
    fn test_enforce_vh_pending_review() {
        let enforcer = make_enforcer();
        let ctx = make_context();

        let policies = vec![
            "rate-limit".to_string(),
            "auth-jwt".to_string(),
            "mtls".to_string(),
            "audit-logging".to_string(),
        ];

        let decision = enforcer.enforce(Classification::VH, &policies, &ctx);

        assert!(decision.is_allowed());
        match decision {
            EnforcementDecision::Allow { state, .. } => {
                assert_eq!(state, ApiState::PendingReview);
            }
            _ => panic!("Expected Allow"),
        }
    }

    #[test]
    fn test_enforce_vvh_pending_review() {
        let enforcer = make_enforcer();
        let ctx = make_context();

        let policies = vec![
            "rate-limit".to_string(),
            "auth-jwt".to_string(),
            "mtls".to_string(),
            "audit-logging".to_string(),
            "data-encryption".to_string(),
            "geo-restriction".to_string(),
        ];

        let decision = enforcer.enforce(Classification::VVH, &policies, &ctx);

        assert!(decision.is_allowed());
        match decision {
            EnforcementDecision::Allow { state, .. } => {
                assert_eq!(state, ApiState::PendingReview);
            }
            _ => panic!("Expected Allow"),
        }
    }

    #[test]
    fn test_safe_mode_deny_all() {
        let cache = Arc::new(VersionedPolicyCache::new(3600));
        // Don't set version - simulates unavailable policy service

        let enforcer = UacEnforcer::new(cache).with_safe_mode(SafeModeConfig {
            mode: SafeMode::DenyAll,
            ..Default::default()
        });

        let ctx = make_context();
        let policies = vec!["rate-limit".to_string(), "auth-jwt".to_string()];

        let decision = enforcer.enforce(Classification::H, &policies, &ctx);

        assert!(!decision.is_allowed());
    }

    #[test]
    fn test_safe_mode_force_review() {
        let cache = Arc::new(VersionedPolicyCache::new(3600));
        // Don't set version

        let enforcer = UacEnforcer::new(cache).with_safe_mode(SafeModeConfig {
            mode: SafeMode::ForceReview,
            ..Default::default()
        });

        let ctx = make_context();
        let policies = vec!["rate-limit".to_string(), "auth-jwt".to_string()];

        let decision = enforcer.enforce(Classification::H, &policies, &ctx);

        assert!(decision.is_allowed());
        match decision {
            EnforcementDecision::Allow { state, .. } => {
                assert_eq!(state, ApiState::PendingReview);
            }
            _ => panic!("Expected Allow with PendingReview"),
        }
    }

    #[test]
    fn test_context_is_admin() {
        let ctx = EnforcementContext::new("tenant", "user").with_roles(vec!["cpi-admin".into()]);
        assert!(ctx.is_admin());

        let ctx = EnforcementContext::new("tenant", "user").with_roles(vec!["viewer".into()]);
        assert!(!ctx.is_admin());
    }
}
