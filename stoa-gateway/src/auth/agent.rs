//! Agent Identity Extraction (CAB-1710)
//!
//! Extracts HEGEMON agent identity from JWT claims. Service accounts for
//! HEGEMON workers carry custom claims that identify the agent type, worker ID,
//! and capabilities. This module provides the `AgentIdentity` struct and
//! extraction logic on top of the existing `Claims` infrastructure.
//!
//! Detection heuristic (in priority order):
//! 1. Explicit `hegemon:agent` scope in JWT
//! 2. `azp` matching `hegemon-worker-*` pattern (Keycloak service account client ID)
//! 3. Realm role `hegemon-agent` present

use serde::{Deserialize, Serialize};

use super::claims::Claims;

/// Agent type for HEGEMON workers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentType {
    /// Implementation worker (code changes, PRs)
    Worker,
    /// Orchestrator (dispatches work, monitors)
    Orchestrator,
    /// Review agent (read-only code review)
    Reviewer,
    /// Council validator (ticket/plan scoring)
    Council,
}

impl AgentType {
    /// Parse from string.
    pub fn parse(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "worker" => Some(Self::Worker),
            "orchestrator" => Some(Self::Orchestrator),
            "reviewer" => Some(Self::Reviewer),
            "council" => Some(Self::Council),
            _ => None,
        }
    }

    /// String representation.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Worker => "worker",
            Self::Orchestrator => "orchestrator",
            Self::Reviewer => "reviewer",
            Self::Council => "council",
        }
    }
}

/// HEGEMON agent identity extracted from JWT claims.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentIdentity {
    /// Keycloak subject (service account user ID)
    pub subject: String,

    /// Agent type (worker, orchestrator, reviewer, council)
    pub agent_type: AgentType,

    /// Worker identifier (e.g., "1", "nuremberg-3")
    pub worker_id: Option<String>,

    /// Keycloak client ID (azp claim)
    pub client_id: String,

    /// Tenant scope (if agent is tenant-scoped)
    pub tenant_id: Option<String>,

    /// Agent capabilities derived from scopes
    pub capabilities: Vec<String>,
}

impl AgentIdentity {
    /// Check if this agent has a specific capability.
    pub fn has_capability(&self, cap: &str) -> bool {
        self.capabilities.iter().any(|c| c == cap)
    }

    /// Check if this agent can write (create PRs, modify code).
    pub fn can_write(&self) -> bool {
        matches!(self.agent_type, AgentType::Worker | AgentType::Orchestrator)
    }

    /// Check if this agent is read-only.
    pub fn is_read_only(&self) -> bool {
        matches!(self.agent_type, AgentType::Reviewer | AgentType::Council)
    }
}

// Keycloak service account client ID prefix for HEGEMON workers
const HEGEMON_CLIENT_PREFIX: &str = "hegemon-worker-";
const HEGEMON_AGENT_ROLE: &str = "hegemon-agent";

impl Claims {
    /// Extract agent identity from JWT claims.
    ///
    /// Returns `Some(AgentIdentity)` if the token belongs to a HEGEMON agent
    /// (detected via custom claims, azp pattern, or realm role).
    /// Returns `None` for regular user tokens.
    pub fn agent_identity(&self) -> Option<AgentIdentity> {
        let has_agent_scope = self.has_scope("hegemon:agent");
        let azp = self.azp.as_deref().unwrap_or("");
        let azp_match = azp.starts_with(HEGEMON_CLIENT_PREFIX);
        let has_agent_role = self.has_realm_role(HEGEMON_AGENT_ROLE);

        if !has_agent_scope && !azp_match && !has_agent_role {
            return None;
        }

        let agent_type = self.detect_agent_type(azp);

        let worker_id = if azp_match {
            Some(azp.strip_prefix(HEGEMON_CLIENT_PREFIX)?.to_string())
        } else {
            None
        };

        let capabilities = self
            .scopes()
            .into_iter()
            .filter(|s| s.starts_with("hegemon:"))
            .map(|s| s.to_string())
            .collect();

        Some(AgentIdentity {
            subject: self.sub.clone(),
            agent_type,
            worker_id,
            client_id: azp.to_string(),
            tenant_id: self.tenant_id().map(|s| s.to_string()),
            capabilities,
        })
    }

    /// Detect agent type from claims context.
    fn detect_agent_type(&self, azp: &str) -> AgentType {
        if self.has_scope("hegemon:orchestrator") {
            return AgentType::Orchestrator;
        }
        if self.has_scope("hegemon:reviewer") {
            return AgentType::Reviewer;
        }
        if self.has_scope("hegemon:council") {
            return AgentType::Council;
        }
        if azp.contains("orchestrator") {
            return AgentType::Orchestrator;
        }
        if azp.contains("reviewer") {
            return AgentType::Reviewer;
        }
        if azp.contains("council") {
            return AgentType::Council;
        }
        AgentType::Worker
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::claims::{Audience, RealmAccess};

    fn base_claims() -> Claims {
        Claims {
            sub: "sa-hegemon-worker-1".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("hegemon-worker-1".to_string()),
            preferred_username: Some("service-account-hegemon-worker-1".to_string()),
            email: None,
            email_verified: None,
            name: None,
            given_name: None,
            family_name: None,
            tenant: None,
            realm_access: Some(RealmAccess {
                roles: vec!["hegemon-agent".to_string()],
            }),
            resource_access: None,
            sid: None,
            typ: Some("Bearer".to_string()),
            scope: Some("openid hegemon:agent hegemon:write".to_string()),
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: None,
            worker_roles: None,
            supervision_tier: None,
        }
    }

    fn user_claims() -> Claims {
        Claims {
            sub: "user-123".to_string(),
            exp: chrono::Utc::now().timestamp() + 3600,
            iat: chrono::Utc::now().timestamp(),
            iss: "https://auth.gostoa.dev/realms/stoa".to_string(),
            aud: Audience::Single("stoa-mcp".to_string()),
            azp: Some("stoa-mcp".to_string()),
            preferred_username: Some("john.doe".to_string()),
            email: Some("john@example.com".to_string()),
            email_verified: Some(true),
            name: Some("John Doe".to_string()),
            given_name: Some("John".to_string()),
            family_name: Some("Doe".to_string()),
            tenant: Some("acme".to_string()),
            realm_access: Some(RealmAccess {
                roles: vec!["tenant-admin".to_string()],
            }),
            resource_access: None,
            sid: None,
            typ: Some("Bearer".to_string()),
            scope: Some("openid profile email stoa:write".to_string()),
            cnf: None,
            sub_account_id: None,
            master_account_id: None,
            worker_name: None,
            worker_roles: None,
            supervision_tier: None,
        }
    }

    #[test]
    fn test_agent_identity_from_worker_token() {
        let claims = base_claims();
        let identity = claims.agent_identity();
        assert!(identity.is_some());
        let id = identity.unwrap();
        assert_eq!(id.agent_type, AgentType::Worker);
        assert_eq!(id.worker_id.as_deref(), Some("1"));
        assert_eq!(id.client_id, "hegemon-worker-1");
        assert!(id.has_capability("hegemon:agent"));
        assert!(id.has_capability("hegemon:write"));
        assert!(id.can_write());
        assert!(!id.is_read_only());
    }

    #[test]
    fn test_regular_user_returns_none() {
        let claims = user_claims();
        assert!(claims.agent_identity().is_none());
    }

    #[test]
    fn test_orchestrator_from_scope() {
        let mut claims = base_claims();
        claims.scope = Some("openid hegemon:agent hegemon:orchestrator".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.agent_type, AgentType::Orchestrator);
        assert!(id.can_write());
    }

    #[test]
    fn test_reviewer_from_scope() {
        let mut claims = base_claims();
        claims.scope = Some("openid hegemon:agent hegemon:reviewer".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.agent_type, AgentType::Reviewer);
        assert!(id.is_read_only());
        assert!(!id.can_write());
    }

    #[test]
    fn test_council_from_scope() {
        let mut claims = base_claims();
        claims.scope = Some("openid hegemon:agent hegemon:council".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.agent_type, AgentType::Council);
        assert!(id.is_read_only());
    }

    #[test]
    fn test_orchestrator_from_azp_name() {
        let mut claims = base_claims();
        claims.azp = Some("hegemon-worker-orchestrator-1".to_string());
        claims.scope = Some("openid hegemon:agent".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.agent_type, AgentType::Orchestrator);
    }

    #[test]
    fn test_detection_via_role_only() {
        let mut claims = base_claims();
        claims.azp = Some("custom-client".to_string());
        claims.scope = Some("openid".to_string());
        let id = claims.agent_identity();
        assert!(id.is_some());
        let id = id.unwrap();
        assert_eq!(id.agent_type, AgentType::Worker);
        assert!(id.worker_id.is_none());
        assert_eq!(id.client_id, "custom-client");
    }

    #[test]
    fn test_detection_via_scope_only() {
        let mut claims = base_claims();
        claims.azp = Some("custom-client".to_string());
        claims.realm_access = Some(RealmAccess { roles: vec![] });
        claims.scope = Some("openid hegemon:agent".to_string());
        let id = claims.agent_identity();
        assert!(id.is_some());
    }

    #[test]
    fn test_no_detection_without_signals() {
        let mut claims = base_claims();
        claims.azp = Some("custom-client".to_string());
        claims.realm_access = Some(RealmAccess { roles: vec![] });
        claims.scope = Some("openid profile".to_string());
        assert!(claims.agent_identity().is_none());
    }

    #[test]
    fn test_capabilities_extracted_from_scopes() {
        let mut claims = base_claims();
        claims.scope =
            Some("openid hegemon:agent hegemon:write hegemon:dispatch stoa:read".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.capabilities.len(), 3);
        assert!(id.has_capability("hegemon:agent"));
        assert!(id.has_capability("hegemon:write"));
        assert!(id.has_capability("hegemon:dispatch"));
        assert!(!id.has_capability("stoa:read"));
    }

    #[test]
    fn test_tenant_scoped_agent() {
        let mut claims = base_claims();
        claims.tenant = Some("acme".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.tenant_id.as_deref(), Some("acme"));
    }

    #[test]
    fn test_agent_type_parse() {
        assert_eq!(AgentType::parse("worker"), Some(AgentType::Worker));
        assert_eq!(
            AgentType::parse("orchestrator"),
            Some(AgentType::Orchestrator)
        );
        assert_eq!(AgentType::parse("reviewer"), Some(AgentType::Reviewer));
        assert_eq!(AgentType::parse("council"), Some(AgentType::Council));
        assert_eq!(AgentType::parse("WORKER"), Some(AgentType::Worker));
        assert_eq!(AgentType::parse("unknown"), None);
    }

    #[test]
    fn test_agent_type_as_str() {
        assert_eq!(AgentType::Worker.as_str(), "worker");
        assert_eq!(AgentType::Orchestrator.as_str(), "orchestrator");
        assert_eq!(AgentType::Reviewer.as_str(), "reviewer");
        assert_eq!(AgentType::Council.as_str(), "council");
    }

    #[test]
    fn test_agent_identity_serialization() {
        let id = AgentIdentity {
            subject: "sa-1".to_string(),
            agent_type: AgentType::Worker,
            worker_id: Some("1".to_string()),
            client_id: "hegemon-worker-1".to_string(),
            tenant_id: None,
            capabilities: vec!["hegemon:agent".to_string()],
        };
        let json = serde_json::to_string(&id).unwrap();
        assert!(json.contains("\"agent_type\":\"worker\""));
        let deserialized: AgentIdentity = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.agent_type, AgentType::Worker);
    }

    #[test]
    fn test_worker_id_extraction_multi_segment() {
        let mut claims = base_claims();
        claims.azp = Some("hegemon-worker-nuremberg-3".to_string());
        let id = claims.agent_identity().unwrap();
        assert_eq!(id.worker_id.as_deref(), Some("nuremberg-3"));
    }

    #[test]
    fn test_empty_azp() {
        let mut claims = base_claims();
        claims.azp = None;
        let id = claims.agent_identity();
        assert!(id.is_some());
        let id = id.unwrap();
        assert_eq!(id.client_id, "");
    }
}
