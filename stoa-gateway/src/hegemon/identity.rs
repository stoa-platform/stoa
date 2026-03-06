//! HEGEMON Agent Identity — Extract agent identity from JWT claims.
//!
//! Workers authenticate via Keycloak service accounts. Their JWTs contain
//! custom claims (`worker_name`, `worker_roles`) set by protocol mappers.
//!
//! The `AgentIdentity` is injected into axum request extensions, following
//! the same pattern as `AuthenticatedUser` in the auth module.

use crate::auth::claims::Claims;
use crate::supervision::SupervisionTier;
use serde::{Deserialize, Serialize};

/// Identity of an authenticated HEGEMON worker agent.
///
/// Extracted from JWT custom claims and optionally enriched with
/// supervision tier from the `X-Hegemon-Supervision` header.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentIdentity {
    /// Worker name (e.g., "hegemon-worker-backend").
    /// Source: `worker_name` JWT claim.
    pub worker_name: String,

    /// Worker roles (e.g., ["backend", "api"]).
    /// Source: `worker_roles` JWT claim.
    pub worker_roles: Vec<String>,

    /// Keycloak subject ID (user/service account UUID).
    pub subject: String,

    /// Supervision tier for this request.
    /// Source: JWT `supervision_tier` claim, overridden by `X-Hegemon-Supervision` header.
    pub supervision_tier: SupervisionTier,
}

impl AgentIdentity {
    /// Extract agent identity from validated JWT claims.
    ///
    /// Returns `None` if the `worker_name` claim is absent (not a HEGEMON agent).
    /// The supervision tier defaults to `Autopilot` unless overridden.
    pub fn from_claims(claims: &Claims) -> Option<Self> {
        let worker_name = claims.worker_name.as_ref()?;

        Some(Self {
            worker_name: worker_name.clone(),
            worker_roles: claims.worker_roles.clone().unwrap_or_default(),
            subject: claims.sub.clone(),
            supervision_tier: claims
                .supervision_tier
                .as_deref()
                .and_then(SupervisionTier::from_header)
                .unwrap_or(SupervisionTier::Autopilot),
        })
    }

    /// Apply header override for supervision tier.
    ///
    /// The `X-Hegemon-Supervision` header takes precedence over the JWT claim,
    /// allowing per-request tier escalation.
    pub fn with_tier_override(mut self, header_value: Option<&str>) -> Self {
        if let Some(tier) = header_value.and_then(SupervisionTier::from_header) {
            self.supervision_tier = tier;
        }
        self
    }

    /// Check if this agent has a specific role.
    pub fn has_role(&self, role: &str) -> bool {
        self.worker_roles.iter().any(|r| r == role)
    }

    /// Check if this agent has the `hegemon:execute` role (required for dispatch).
    pub fn can_execute(&self) -> bool {
        self.has_role("hegemon:execute")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, Claims};

    fn make_claims(
        worker_name: Option<&str>,
        worker_roles: Option<Vec<&str>>,
        supervision_tier: Option<&str>,
    ) -> Claims {
        Claims {
            sub: "service-account-worker-1".to_string(),
            exp: 9999999999,
            iat: 1700000000,
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp-gateway".to_string()),
            azp: Some("hegemon-worker-backend".to_string()),
            preferred_username: Some("service-account-worker-1".to_string()),
            email: None,
            email_verified: None,
            name: None,
            given_name: None,
            family_name: None,
            tenant: None,
            realm_access: None,
            resource_access: None,
            sid: None,
            typ: Some("Bearer".to_string()),
            scope: Some("openid profile".to_string()),
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: worker_name.map(|s| s.to_string()),
            worker_roles: worker_roles
                .map(|roles| roles.into_iter().map(|r| r.to_string()).collect()),
            supervision_tier: supervision_tier.map(|s| s.to_string()),
        }
    }

    #[test]
    fn test_from_claims_with_worker_name() {
        let claims = make_claims(
            Some("hegemon-worker-backend"),
            Some(vec!["backend", "hegemon:execute"]),
            None,
        );
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert_eq!(identity.worker_name, "hegemon-worker-backend");
        assert_eq!(identity.worker_roles, vec!["backend", "hegemon:execute"]);
        assert_eq!(identity.subject, "service-account-worker-1");
        assert_eq!(identity.supervision_tier, SupervisionTier::Autopilot);
    }

    #[test]
    fn test_from_claims_without_worker_name_returns_none() {
        let claims = make_claims(None, None, None);
        assert!(AgentIdentity::from_claims(&claims).is_none());
    }

    #[test]
    fn test_from_claims_with_empty_roles() {
        let claims = make_claims(Some("worker-1"), None, None);
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert!(identity.worker_roles.is_empty());
    }

    #[test]
    fn test_from_claims_with_supervision_tier() {
        let claims = make_claims(Some("worker-1"), None, Some("copilot"));
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert_eq!(identity.supervision_tier, SupervisionTier::CoPilot);
    }

    #[test]
    fn test_from_claims_with_command_tier() {
        let claims = make_claims(Some("worker-1"), None, Some("command"));
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert_eq!(identity.supervision_tier, SupervisionTier::Command);
    }

    #[test]
    fn test_from_claims_with_invalid_tier_defaults_to_autopilot() {
        let claims = make_claims(Some("worker-1"), None, Some("invalid-tier"));
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert_eq!(identity.supervision_tier, SupervisionTier::Autopilot);
    }

    #[test]
    fn test_tier_header_override() {
        let claims = make_claims(Some("worker-1"), None, Some("autopilot"));
        let identity = AgentIdentity::from_claims(&claims)
            .unwrap()
            .with_tier_override(Some("command"));
        assert_eq!(identity.supervision_tier, SupervisionTier::Command);
    }

    #[test]
    fn test_tier_header_override_none_keeps_original() {
        let claims = make_claims(Some("worker-1"), None, Some("copilot"));
        let identity = AgentIdentity::from_claims(&claims)
            .unwrap()
            .with_tier_override(None);
        assert_eq!(identity.supervision_tier, SupervisionTier::CoPilot);
    }

    #[test]
    fn test_tier_header_override_invalid_keeps_original() {
        let claims = make_claims(Some("worker-1"), None, Some("copilot"));
        let identity = AgentIdentity::from_claims(&claims)
            .unwrap()
            .with_tier_override(Some("bogus"));
        assert_eq!(identity.supervision_tier, SupervisionTier::CoPilot);
    }

    #[test]
    fn test_has_role() {
        let claims = make_claims(
            Some("worker-1"),
            Some(vec!["backend", "hegemon:execute"]),
            None,
        );
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert!(identity.has_role("backend"));
        assert!(identity.has_role("hegemon:execute"));
        assert!(!identity.has_role("frontend"));
    }

    #[test]
    fn test_can_execute() {
        let claims_with = make_claims(
            Some("worker-1"),
            Some(vec!["backend", "hegemon:execute"]),
            None,
        );
        let claims_without = make_claims(Some("worker-2"), Some(vec!["qa"]), None);
        assert!(AgentIdentity::from_claims(&claims_with)
            .unwrap()
            .can_execute());
        assert!(!AgentIdentity::from_claims(&claims_without)
            .unwrap()
            .can_execute());
    }

    #[test]
    fn test_can_execute_empty_roles() {
        let claims = make_claims(Some("worker-1"), None, None);
        assert!(!AgentIdentity::from_claims(&claims).unwrap().can_execute());
    }

    #[test]
    fn test_subject_preserved() {
        let claims = make_claims(Some("worker-1"), None, None);
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        assert_eq!(identity.subject, "service-account-worker-1");
    }

    #[test]
    fn test_serialization_roundtrip() {
        let claims = make_claims(
            Some("worker-backend"),
            Some(vec!["backend", "hegemon:execute"]),
            Some("copilot"),
        );
        let identity = AgentIdentity::from_claims(&claims).unwrap();
        let json = serde_json::to_string(&identity).unwrap();
        let deserialized: AgentIdentity = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.worker_name, "worker-backend");
        assert_eq!(deserialized.worker_roles.len(), 2);
    }
}
