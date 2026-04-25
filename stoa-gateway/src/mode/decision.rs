//! Shared authorization decision pipeline for gateway adapters.
//!
//! Protocol adapters such as sidecar ext_authz, future micro-gateway proxying,
//! or mesh integration should translate their request shape into `DecisionInput`
//! and delegate policy/quota/scope checks here.

use crate::quota::ConsumerRateLimiter;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{debug, info, instrument, warn};

/// Gateway-neutral authorization request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionInput {
    /// HTTP method.
    pub method: String,
    /// Request path.
    pub path: String,
    /// Selected request headers.
    #[serde(default)]
    pub headers: HashMap<String, String>,
    /// Source IP address.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_ip: Option<String>,
    /// Pre-validated principal.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub principal: Option<DecisionPrincipal>,
    /// Tenant ID resolved by the adapter.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,
    /// Adapter-specific metadata.
    #[serde(default)]
    pub context: serde_json::Value,
}

/// Gateway-neutral principal resolved before policy evaluation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionPrincipal {
    /// Stable subject identifier.
    pub id: String,
    /// Principal email.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub email: Option<String>,
    /// Principal roles.
    #[serde(default)]
    pub roles: Vec<String>,
    /// OAuth scopes.
    #[serde(default)]
    pub scopes: Vec<String>,
    /// Additional claims.
    #[serde(default)]
    pub claims: HashMap<String, serde_json::Value>,
}

/// Gateway-neutral authorization decision.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decision {
    /// Whether the request is allowed.
    pub allowed: bool,
    /// Status code to return if denied.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status_code: Option<u16>,
    /// Headers to add to the upstream request.
    #[serde(default)]
    pub headers_to_add: HashMap<String, String>,
    /// Headers to remove from the upstream request.
    #[serde(default)]
    pub headers_to_remove: Vec<String>,
    /// Denial reason.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub denial_reason: Option<String>,
    /// Policy that caused denial.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub denied_by_policy: Option<String>,
    /// Decision metadata for observability.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<DecisionMetadata>,
}

/// Decision metadata for observability and metering.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionMetadata {
    /// Unique request ID.
    pub request_id: String,
    /// Evaluated policy stages.
    pub policies_evaluated: Vec<String>,
    /// Evaluation time in microseconds.
    pub evaluation_time_us: u64,
    /// Rate limit state.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rate_limit: Option<DecisionRateLimitState>,
}

/// Rate limit state exposed to protocol adapters.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DecisionRateLimitState {
    /// Current request count.
    pub current: u64,
    /// Maximum allowed.
    pub limit: u64,
    /// Window reset time (Unix timestamp).
    pub reset_at: u64,
    /// Remaining requests in window.
    pub remaining: u64,
}

impl Decision {
    /// Create an allow response.
    pub fn allow() -> Self {
        Self {
            allowed: true,
            status_code: None,
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: None,
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create a deny response.
    pub fn deny(reason: impl Into<String>) -> Self {
        Self {
            allowed: false,
            status_code: Some(403),
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: Some(reason.into()),
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create an unauthorized response.
    pub fn unauthorized(reason: impl Into<String>) -> Self {
        Self {
            allowed: false,
            status_code: Some(401),
            headers_to_add: HashMap::new(),
            headers_to_remove: Vec::new(),
            denial_reason: Some(reason.into()),
            denied_by_policy: None,
            metadata: None,
        }
    }

    /// Create a rate limited response.
    pub fn rate_limited(state: DecisionRateLimitState) -> Self {
        Self {
            allowed: false,
            status_code: Some(429),
            headers_to_add: [
                ("X-RateLimit-Limit".to_string(), state.limit.to_string()),
                (
                    "X-RateLimit-Remaining".to_string(),
                    state.remaining.to_string(),
                ),
                ("X-RateLimit-Reset".to_string(), state.reset_at.to_string()),
            ]
            .into_iter()
            .collect(),
            headers_to_remove: Vec::new(),
            denial_reason: Some("Rate limit exceeded".to_string()),
            denied_by_policy: Some("rate_limit".to_string()),
            metadata: Some(DecisionMetadata {
                request_id: uuid::Uuid::new_v4().to_string(),
                policies_evaluated: vec!["rate_limit".to_string()],
                evaluation_time_us: 0,
                rate_limit: Some(state),
            }),
        }
    }

    /// Add a header to the allowed request.
    pub fn with_header(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers_to_add.insert(name.into(), value.into());
        self
    }

    /// Set the denied-by policy.
    pub fn with_policy(mut self, policy: impl Into<String>) -> Self {
        self.denied_by_policy = Some(policy.into());
        self
    }

    /// Set metadata.
    pub fn with_metadata(mut self, metadata: DecisionMetadata) -> Self {
        self.metadata = Some(metadata);
        self
    }
}

/// Shared decision engine used by gateway protocol adapters.
#[derive(Clone, Default)]
pub struct DecisionEngine {
    rate_limiter: Option<Arc<ConsumerRateLimiter>>,
    required_scopes: Vec<String>,
}

impl DecisionEngine {
    /// Create a decision engine with no optional services wired.
    pub fn new() -> Self {
        Self::default()
    }

    /// Attach a consumer rate limiter.
    pub fn with_rate_limiter(mut self, limiter: Arc<ConsumerRateLimiter>) -> Self {
        self.rate_limiter = Some(limiter);
        self
    }

    /// Set required scopes for authorization.
    pub fn with_required_scopes(mut self, scopes: Vec<String>) -> Self {
        self.required_scopes = scopes;
        self
    }

    /// Evaluate a gateway-neutral authorization decision.
    #[instrument(skip(self, input))]
    pub fn decide(&self, input: DecisionInput) -> Decision {
        let start = std::time::Instant::now();
        let request_id = uuid::Uuid::new_v4().to_string();

        debug!(
            request_id = %request_id,
            method = %input.method,
            path = %input.path,
            "Processing authorization decision"
        );

        let principal = match &input.principal {
            Some(principal) => principal,
            None => {
                warn!(request_id = %request_id, "No principal in decision input");
                return Decision::unauthorized("Missing user information");
            }
        };

        let tenant_id = match &input.tenant_id {
            Some(tenant_id) => tenant_id,
            None => {
                warn!(request_id = %request_id, "No tenant ID in decision input");
                return Decision::deny("Missing tenant ID");
            }
        };

        let mut policies_evaluated = vec!["identity".to_string(), "tenant".to_string()];

        if let Some(ref limiter) = self.rate_limiter {
            policies_evaluated.push("consumer_rate_limit".to_string());
            let consumer_key = format!("{}:{}", tenant_id, principal.id);
            if let Err(error) = limiter.check_rate_limit(&consumer_key) {
                let state = limiter.get_rate_limit_info(&consumer_key);
                warn!(
                    request_id = %request_id,
                    consumer = %consumer_key,
                    error = %error,
                    "Rate limit exceeded"
                );
                return Decision::rate_limited(DecisionRateLimitState {
                    current: u64::from(state.limit.saturating_sub(state.remaining)),
                    limit: u64::from(state.limit),
                    reset_at: state.reset_epoch.max(0) as u64,
                    remaining: u64::from(state.remaining),
                })
                .with_policy("consumer_rate_limit");
            }
        }

        if !self.required_scopes.is_empty() {
            policies_evaluated.push("scope_enforcement".to_string());
            let has_scope = self
                .required_scopes
                .iter()
                .any(|scope| principal.scopes.contains(scope));
            if !has_scope {
                warn!(
                    request_id = %request_id,
                    user_scopes = ?principal.scopes,
                    required = ?self.required_scopes,
                    "Insufficient scopes"
                );
                return Decision::deny(format!(
                    "Insufficient scopes: requires one of [{}]",
                    self.required_scopes.join(", ")
                ))
                .with_policy("scope_enforcement");
            }
        }

        let evaluation_time_us = start.elapsed().as_micros() as u64;
        let mut decision = Decision::allow()
            .with_header("X-User-ID", &principal.id)
            .with_header("X-Tenant-ID", tenant_id)
            .with_header("X-Request-ID", &request_id);

        if !principal.scopes.is_empty() {
            decision = decision.with_header("X-User-Scopes", principal.scopes.join(","));
        }

        if !principal.roles.is_empty() {
            decision = decision.with_header("X-User-Roles", principal.roles.join(","));
        }

        decision = decision.with_metadata(DecisionMetadata {
            request_id,
            policies_evaluated,
            evaluation_time_us,
            rate_limit: None,
        });

        info!(
            evaluation_time_us = evaluation_time_us,
            "Authorization allowed"
        );

        decision
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::quota::{PlanQuota, RateLimiterConfig};

    fn input(principal: Option<DecisionPrincipal>, tenant_id: Option<&str>) -> DecisionInput {
        DecisionInput {
            method: "GET".to_string(),
            path: "/api/v1/users".to_string(),
            headers: HashMap::new(),
            source_ip: None,
            principal,
            tenant_id: tenant_id.map(ToString::to_string),
            context: serde_json::Value::Null,
        }
    }

    fn principal(scopes: Vec<&str>) -> DecisionPrincipal {
        DecisionPrincipal {
            id: "user-456".to_string(),
            email: Some("user@example.com".to_string()),
            roles: vec!["admin".to_string()],
            scopes: scopes.into_iter().map(ToString::to_string).collect(),
            claims: HashMap::new(),
        }
    }

    #[test]
    fn decide_rejects_missing_principal() {
        let decision = DecisionEngine::new().decide(input(None, Some("acme")));

        assert!(!decision.allowed);
        assert_eq!(decision.status_code, Some(401));
    }

    #[test]
    fn decide_rejects_missing_tenant() {
        let decision = DecisionEngine::new().decide(input(Some(principal(vec!["read"])), None));

        assert!(!decision.allowed);
        assert_eq!(decision.status_code, Some(403));
        assert_eq!(
            decision.denial_reason,
            Some("Missing tenant ID".to_string())
        );
    }

    #[test]
    fn decide_allows_and_enriches_headers() {
        let decision = DecisionEngine::new()
            .decide(input(Some(principal(vec!["read", "write"])), Some("acme")));

        assert!(decision.allowed);
        assert_eq!(
            decision.headers_to_add.get("X-User-ID"),
            Some(&"user-456".to_string())
        );
        assert_eq!(
            decision.headers_to_add.get("X-Tenant-ID"),
            Some(&"acme".to_string())
        );
        assert_eq!(
            decision.headers_to_add.get("X-User-Scopes"),
            Some(&"read,write".to_string())
        );
        assert!(decision.metadata.is_some());
    }

    #[test]
    fn decide_enforces_required_scopes() {
        let decision = DecisionEngine::new()
            .with_required_scopes(vec!["stoa:admin".to_string()])
            .decide(input(Some(principal(vec!["stoa:read"])), Some("acme")));

        assert!(!decision.allowed);
        assert_eq!(decision.status_code, Some(403));
        assert_eq!(
            decision.denied_by_policy,
            Some("scope_enforcement".to_string())
        );
    }

    #[test]
    fn decide_enforces_consumer_rate_limit() {
        let limiter = Arc::new(ConsumerRateLimiter::new(RateLimiterConfig {
            default_rate_per_minute: 1,
            ..Default::default()
        }));
        limiter.set_plan_quota(
            "acme:user-456",
            PlanQuota {
                rate_limit_per_minute: 1,
                ..Default::default()
            },
        );
        let engine = DecisionEngine::new().with_rate_limiter(limiter);

        let allowed = engine.decide(input(Some(principal(vec!["read"])), Some("acme")));
        assert!(allowed.allowed);

        let limited = engine.decide(input(Some(principal(vec!["read"])), Some("acme")));
        assert!(!limited.allowed);
        assert_eq!(limited.status_code, Some(429));
        assert_eq!(
            limited.denied_by_policy,
            Some("consumer_rate_limit".to_string())
        );
    }
}
