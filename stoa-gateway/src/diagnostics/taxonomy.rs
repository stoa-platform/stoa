//! Error Classification Taxonomy (CAB-1316 Phase 1)
//!
//! 8 error categories covering all failure modes in gateway request processing.
//! Classification priority: explicit tag > message pattern > HTTP status code.

use serde::{Deserialize, Serialize};

/// Error categories for gateway request failures.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCategory {
    /// 401/403, token expired, OIDC failure
    Auth,
    /// Connection refused, timeout, DNS failure
    Network,
    /// 500/502/503 from upstream
    Backend,
    /// Gateway-level timeout exceeded
    Timeout,
    /// OPA deny, guardrail block
    Policy,
    /// 429 from token budget or rate limiter
    RateLimit,
    /// mTLS failure, cert expired, chain incomplete
    Certificate,
    /// Unclassifiable error
    Unknown,
}

impl ErrorCategory {
    /// Classify an error from HTTP status code and optional error message.
    ///
    /// Priority: message patterns (most specific) > status code (fallback).
    pub fn classify(status_code: Option<u16>, message: Option<&str>) -> Self {
        // Phase 1: message-pattern heuristics (highest priority for specificity)
        if let Some(msg) = message {
            let lower = msg.to_lowercase();
            if lower.contains("tls")
                || lower.contains("certificate")
                || lower.contains("ssl")
                || lower.contains("x509")
            {
                return Self::Certificate;
            }
            if lower.contains("policy")
                || lower.contains("guardrail")
                || lower.contains("opa")
                || lower.contains("denied by rule")
            {
                return Self::Policy;
            }
            if lower.contains("circuit") || lower.contains("circuit breaker") {
                return Self::Backend;
            }
            if lower.contains("dns")
                || lower.contains("connection refused")
                || lower.contains("connection reset")
                || lower.contains("no route to host")
            {
                return Self::Network;
            }
            if lower.contains("timeout") || lower.contains("timed out") {
                return Self::Timeout;
            }
            if lower.contains("rate limit") || lower.contains("quota") || lower.contains("throttl")
            {
                return Self::RateLimit;
            }
            if lower.contains("unauthorized")
                || lower.contains("forbidden")
                || lower.contains("token expired")
                || lower.contains("jwt")
                || lower.contains("invalid token")
            {
                return Self::Auth;
            }
        }

        // Phase 2: status-code fallback
        match status_code {
            Some(401 | 403) => Self::Auth,
            Some(429) => Self::RateLimit,
            Some(504) => Self::Timeout,
            Some(502 | 503) => Self::Backend,
            Some(s) if s >= 500 => Self::Backend,
            _ => Self::Unknown,
        }
    }

    /// Human-readable display name.
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Auth => "Authentication/Authorization",
            Self::Network => "Network Connectivity",
            Self::Backend => "Backend Service",
            Self::Timeout => "Timeout",
            Self::Policy => "Policy Engine",
            Self::RateLimit => "Rate Limit/Quota",
            Self::Certificate => "TLS/Certificate",
            Self::Unknown => "Unknown",
        }
    }

    /// Default suggested action for this error category.
    pub fn suggested_action(&self) -> &'static str {
        match self {
            Self::Auth => "Check JWT token validity, API key, or RBAC permissions",
            Self::Network => "Check DNS resolution, firewall rules, and network connectivity",
            Self::Backend => "Verify backend service is running and accessible from the gateway",
            Self::Timeout => {
                "Check network path between gateway and backend; consider increasing timeout"
            }
            Self::Policy => "Review gateway policies and guardrail rules for this API/tenant",
            Self::RateLimit => "Reduce request rate or increase quota allocation",
            Self::Certificate => "Check certificate validity, chain, and expiry dates",
            Self::Unknown => "Inspect gateway logs for more details",
        }
    }

    /// Default confidence score for classification by status code alone.
    pub fn default_confidence(&self) -> f64 {
        match self {
            Self::Auth => 0.85,
            Self::Network => 0.80,
            Self::Backend => 0.75,
            Self::Timeout => 0.80,
            Self::Policy => 0.85,
            Self::RateLimit => 0.90,
            Self::Certificate => 0.85,
            Self::Unknown => 0.10,
        }
    }
}

impl std::fmt::Display for ErrorCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.display_name())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_auth_by_status_401() {
        assert_eq!(
            ErrorCategory::classify(Some(401), None),
            ErrorCategory::Auth
        );
    }

    #[test]
    fn classify_auth_by_status_403() {
        assert_eq!(
            ErrorCategory::classify(Some(403), None),
            ErrorCategory::Auth
        );
    }

    #[test]
    fn classify_rate_limit_by_status_429() {
        assert_eq!(
            ErrorCategory::classify(Some(429), None),
            ErrorCategory::RateLimit
        );
    }

    #[test]
    fn classify_timeout_by_status_504() {
        assert_eq!(
            ErrorCategory::classify(Some(504), None),
            ErrorCategory::Timeout
        );
    }

    #[test]
    fn classify_backend_by_status_502() {
        assert_eq!(
            ErrorCategory::classify(Some(502), None),
            ErrorCategory::Backend
        );
    }

    #[test]
    fn classify_backend_by_status_503() {
        assert_eq!(
            ErrorCategory::classify(Some(503), None),
            ErrorCategory::Backend
        );
    }

    #[test]
    fn classify_backend_by_status_500() {
        assert_eq!(
            ErrorCategory::classify(Some(500), None),
            ErrorCategory::Backend
        );
    }

    #[test]
    fn classify_unknown_for_none() {
        assert_eq!(ErrorCategory::classify(None, None), ErrorCategory::Unknown);
    }

    #[test]
    fn classify_certificate_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(502), Some("TLS handshake failed")),
            ErrorCategory::Certificate
        );
    }

    #[test]
    fn classify_ssl_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(502), Some("SSL certificate verify failed")),
            ErrorCategory::Certificate
        );
    }

    #[test]
    fn classify_policy_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(403), Some("OPA policy denied")),
            ErrorCategory::Policy
        );
    }

    #[test]
    fn classify_guardrail_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(403), Some("guardrail blocked request")),
            ErrorCategory::Policy
        );
    }

    #[test]
    fn classify_network_dns_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(502), Some("DNS resolution failed")),
            ErrorCategory::Network
        );
    }

    #[test]
    fn classify_network_connection_refused() {
        assert_eq!(
            ErrorCategory::classify(Some(502), Some("connection refused")),
            ErrorCategory::Network
        );
    }

    #[test]
    fn classify_timeout_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(504), Some("request timed out after 30s")),
            ErrorCategory::Timeout
        );
    }

    #[test]
    fn classify_rate_limit_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(429), Some("rate limit exceeded")),
            ErrorCategory::RateLimit
        );
    }

    #[test]
    fn classify_quota_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(429), Some("consumer quota exhausted")),
            ErrorCategory::RateLimit
        );
    }

    #[test]
    fn classify_jwt_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(401), Some("JWT expired")),
            ErrorCategory::Auth
        );
    }

    #[test]
    fn classify_message_takes_priority_over_status() {
        // 403 normally = Auth, but "policy denied" message overrides to Policy
        assert_eq!(
            ErrorCategory::classify(Some(403), Some("policy denied access")),
            ErrorCategory::Policy
        );
    }

    #[test]
    fn classify_circuit_breaker_by_message() {
        assert_eq!(
            ErrorCategory::classify(Some(503), Some("circuit breaker open")),
            ErrorCategory::Backend
        );
    }

    #[test]
    fn display_name_all_variants() {
        // Ensure every variant has a non-empty display name
        for cat in [
            ErrorCategory::Auth,
            ErrorCategory::Network,
            ErrorCategory::Backend,
            ErrorCategory::Timeout,
            ErrorCategory::Policy,
            ErrorCategory::RateLimit,
            ErrorCategory::Certificate,
            ErrorCategory::Unknown,
        ] {
            assert!(!cat.display_name().is_empty());
            assert!(!cat.suggested_action().is_empty());
            assert!(cat.default_confidence() > 0.0);
            assert!(cat.default_confidence() <= 1.0);
        }
    }

    #[test]
    fn serde_roundtrip() {
        let cat = ErrorCategory::RateLimit;
        let json = serde_json::to_string(&cat).expect("serialize");
        assert_eq!(json, "\"rate_limit\"");
        let back: ErrorCategory = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back, cat);
    }

    #[test]
    fn x509_message_classified_as_certificate() {
        assert_eq!(
            ErrorCategory::classify(Some(502), Some("x509: certificate has expired")),
            ErrorCategory::Certificate
        );
    }
}
