//! Secrets Detection Plugin — Block requests containing leaked credentials
//!
//! Scans request bodies for common secret patterns (API keys, JWTs, AWS keys,
//! GitHub PATs) using regex + Shannon entropy analysis. Always blocks — secrets
//! must never reach upstream backends.
//!
//! CAB-1936 Phase 3.

use async_trait::async_trait;
use axum::http::StatusCode;
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::Value;
use tracing::warn;

use super::super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};

// ============================================================================
// Secret Patterns
// ============================================================================

struct SecretPattern {
    name: &'static str,
    regex: &'static Lazy<Regex>,
    /// If true, also require Shannon entropy above the threshold.
    entropy_check: bool,
}

static AWS_ACCESS_KEY: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"AKIA[0-9A-Z]{16}").expect("AWS access key regex"));

static AWS_SECRET_KEY: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"(?:aws_secret_access_key|secret_access_key|AWS_SECRET)\s*[:=]\s*["']?([A-Za-z0-9/+=]{40})"#)
        .expect("AWS secret key regex")
});

static GENERIC_API_KEY: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"(?i)(?:api[_\-]?key|apikey|api[_\-]?token|api[_\-]?secret)\s*[:=]\s*["']?([A-Za-z0-9_\-]{20,})"#)
        .expect("generic API key regex")
});

static JWT_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_\-]+").expect("JWT regex")
});

static GITHUB_PAT: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"gh[ps]_[A-Za-z0-9_]{36,}").expect("GitHub PAT regex"));

// Allowlist: skip UUIDs and URLs before scanning
static UUID_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
        .expect("UUID regex")
});
static URL_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r#"https?://[^\s"']+"#).expect("URL regex"));

static PATTERNS: &[SecretPattern] = &[
    SecretPattern {
        name: "aws_access_key",
        regex: &AWS_ACCESS_KEY,
        entropy_check: false,
    },
    SecretPattern {
        name: "aws_secret_key",
        regex: &AWS_SECRET_KEY,
        entropy_check: true,
    },
    SecretPattern {
        name: "api_key",
        regex: &GENERIC_API_KEY,
        entropy_check: true,
    },
    SecretPattern {
        name: "jwt",
        regex: &JWT_PATTERN,
        entropy_check: false,
    },
    SecretPattern {
        name: "github_pat",
        regex: &GITHUB_PAT,
        entropy_check: false,
    },
];

// ============================================================================
// Entropy
// ============================================================================

/// Default Shannon entropy threshold for high-entropy secret detection.
const DEFAULT_ENTROPY_THRESHOLD: f64 = 4.0;

/// Compute Shannon entropy of a byte string.
fn shannon_entropy(s: &str) -> f64 {
    if s.is_empty() {
        return 0.0;
    }
    let mut freq = [0u32; 256];
    for &b in s.as_bytes() {
        freq[b as usize] += 1;
    }
    let len = s.len() as f64;
    freq.iter()
        .filter(|&&c| c > 0)
        .map(|&c| {
            let p = c as f64 / len;
            -p * p.log2()
        })
        .sum()
}

// ============================================================================
// Plugin
// ============================================================================

pub struct SecretsDetectionPlugin;

impl SecretsDetectionPlugin {
    pub fn new() -> Self {
        Self
    }

    fn entropy_threshold(config: &Value) -> f64 {
        config
            .get("entropy_threshold")
            .and_then(|v| v.as_f64())
            .unwrap_or(DEFAULT_ENTROPY_THRESHOLD)
    }

    /// Scan text for secret patterns. Returns the first matched pattern name, or None.
    fn detect(text: &str, config: &Value) -> Option<&'static str> {
        // Strip allowlisted content to reduce false positives
        let sanitized = URL_PATTERN.replace_all(text, "___URL___");
        let sanitized = UUID_PATTERN.replace_all(&sanitized, "___UUID___");

        let threshold = Self::entropy_threshold(config);

        for pattern in PATTERNS {
            if let Some(m) = pattern.regex.find(&sanitized) {
                if pattern.entropy_check {
                    // For patterns that capture a secret value, check entropy of the match
                    if shannon_entropy(m.as_str()) < threshold {
                        continue;
                    }
                }
                return Some(pattern.name);
            }
        }

        None
    }
}

impl Default for SecretsDetectionPlugin {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for SecretsDetectionPlugin {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "secrets-detection".to_string(),
            version: "1.0.0".to_string(),
            description: "Blocks requests containing leaked secrets (API keys, JWTs, AWS keys)"
                .to_string(),
            phases: vec![Phase::PreUpstream],
        }
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        if phase != Phase::PreUpstream {
            return PluginResult::Continue;
        }

        let body = match ctx.get_request_body_str() {
            Some(b) if !b.is_empty() => b,
            _ => return PluginResult::Continue,
        };

        if let Some(pattern_name) = Self::detect(body, &ctx.config) {
            warn!(
                plugin = "secrets-detection",
                tenant = %ctx.tenant_id,
                pattern = pattern_name,
                "Secret detected in request body — blocking"
            );

            return PluginResult::Terminate {
                status: StatusCode::UNPROCESSABLE_ENTITY,
                body: format!("Request blocked: potential secret detected ({pattern_name})"),
            };
        }

        PluginResult::Continue
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderMap;
    use serde_json::json;

    fn make_ctx(config: Value) -> PluginContext {
        let mut ctx = PluginContext::new(
            Phase::PreUpstream,
            "test-tenant".to_string(),
            "/api/test".to_string(),
            "POST".to_string(),
            HeaderMap::new(),
        );
        ctx.config = config;
        ctx
    }

    // --- Clean requests ---

    #[tokio::test]
    async fn test_clean_request_passes() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"hello world, no secrets here".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_no_body_passes() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- AWS Access Key ---

    #[tokio::test]
    async fn test_aws_access_key_blocked() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"key is AKIAIOSFODNN7EXAMPLE".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("aws_access_key"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- AWS Secret Key ---

    #[tokio::test]
    async fn test_aws_secret_key_blocked() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body =
            Some(b"aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("aws_secret_key"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- JWT ---

    #[tokio::test]
    async fn test_jwt_blocked() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        let jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U";
        ctx.request_body = Some(format!("token: {jwt}").into_bytes());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("jwt"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- GitHub PAT ---

    #[tokio::test]
    async fn test_github_pat_blocked() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijkl".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("github_pat"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- Generic API Key ---

    #[tokio::test]
    async fn test_generic_api_key_blocked() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"api_key=test_fake_key_aBcDeFgHiJkLmNoPqRsT".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        match result {
            PluginResult::Terminate { status, body } => {
                assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
                assert!(body.contains("api_key"));
            }
            _ => panic!("expected Terminate"),
        }
    }

    // --- Allowlisted content ---

    #[tokio::test]
    async fn test_url_not_flagged() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"endpoint: https://api.example.com/v1/resource".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    #[tokio::test]
    async fn test_uuid_not_flagged() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"id: 550e8400-e29b-41d4-a716-446655440000".to_vec());

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- Non-PreUpstream phase ---

    #[tokio::test]
    async fn test_post_upstream_skipped() {
        let plugin = SecretsDetectionPlugin::new();
        let mut ctx = make_ctx(json!({}));
        ctx.request_body = Some(b"AKIAIOSFODNN7EXAMPLE".to_vec());

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
    }

    // --- Entropy ---

    #[test]
    fn test_entropy_high_for_random_string() {
        // A random-looking string should have high entropy
        let e = shannon_entropy("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY");
        assert!(e > 4.0, "entropy {e} should be > 4.0");
    }

    #[test]
    fn test_entropy_low_for_repetitive_string() {
        let e = shannon_entropy("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        assert!(e < 1.0, "entropy {e} should be < 1.0");
    }

    // --- Metadata ---

    #[test]
    fn test_metadata() {
        let plugin = SecretsDetectionPlugin::new();
        let meta = plugin.metadata();
        assert_eq!(meta.name, "secrets-detection");
        assert_eq!(meta.phases, vec![Phase::PreUpstream]);
    }
}
