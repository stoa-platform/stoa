//! eBPF Integration — UAC Policy Sync to Kernel (CAB-1848)
//!
//! Bridges stoa-gateway route/policy state to the eBPF daemon running on the
//! same host. When routes are reloaded (SIGHUP or admin API), policies are
//! translated to eBPF ApiPolicy structs and pushed to the daemon.
//!
//! The eBPF daemon exposes a localhost-only HTTP API on port 9192:
//! - `POST /policies` — bulk update BPF policy map
//! - `GET /status` — XDP/TC attachment status + metrics

use axum::http::StatusCode;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::info;

/// FNV-1a hash matching the eBPF TC classifier (stoa-tc-ebpf).
/// Must produce identical hashes for the same path.
fn fnv1a_hash(input: &str) -> u32 {
    let mut hash: u32 = 0x811c_9dc5;
    for byte in input.as_bytes() {
        hash ^= *byte as u32;
        hash = hash.wrapping_mul(0x0100_0193);
    }
    hash
}

/// Policy entry sent to the eBPF daemon.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EbpfApiPolicy {
    /// FNV-1a hash of the API path prefix.
    pub path_hash: u32,
    /// Original path (for logging/debugging).
    pub path: String,
    /// Max packets per second (0 = unlimited).
    pub max_pps: u64,
    /// Whether this API is blocked.
    pub blocked: bool,
}

/// Status response from the eBPF daemon.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EbpfStatus {
    pub xdp_attached: bool,
    pub tc_attached: bool,
    pub active_ips: u64,
    pub active_apis: u64,
    pub total_packets: u64,
    pub total_dropped: u64,
}

/// eBPF sync client — pushes policies to the local daemon.
pub struct EbpfSyncClient {
    daemon_url: String,
    http_client: reqwest::Client,
}

impl EbpfSyncClient {
    pub fn new(daemon_url: &str) -> Self {
        Self {
            daemon_url: daemon_url.trim_end_matches('/').to_string(),
            http_client: reqwest::Client::builder()
                .timeout(std::time::Duration::from_secs(5))
                .build()
                .unwrap_or_default(),
        }
    }

    /// Push policies to the eBPF daemon. Returns the number of policies synced.
    pub async fn sync_policies(&self, policies: &[EbpfApiPolicy]) -> Result<usize, String> {
        let url = format!("{}/policies", self.daemon_url);
        let count = policies.len();

        let resp = self
            .http_client
            .post(&url)
            .json(policies)
            .send()
            .await
            .map_err(|e| format!("eBPF daemon unreachable: {e}"))?;

        if resp.status().is_success() {
            info!(count, "eBPF policies synced");
            Ok(count)
        } else {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            Err(format!("eBPF daemon returned {status}: {body}"))
        }
    }

    /// Get status from the eBPF daemon.
    pub async fn status(&self) -> Result<EbpfStatus, String> {
        let url = format!("{}/status", self.daemon_url);
        let resp = self
            .http_client
            .get(&url)
            .send()
            .await
            .map_err(|e| format!("eBPF daemon unreachable: {e}"))?;

        if resp.status().is_success() {
            resp.json::<EbpfStatus>()
                .await
                .map_err(|e| format!("invalid status response: {e}"))
        } else {
            Err(format!("eBPF daemon returned {}", resp.status()))
        }
    }
}

/// Translate gateway routes + policies into eBPF policy entries.
///
/// For each active route with a rate_limit policy, creates an EbpfApiPolicy
/// with the FNV-1a hash of the path prefix (matching the TC classifier).
pub fn translate_routes_to_ebpf_policies(
    routes: &[Arc<crate::routes::registry::ApiRoute>],
    policies: &[crate::routes::policy::PolicyEntry],
) -> Vec<EbpfApiPolicy> {
    let mut result = Vec::new();

    for route in routes {
        if !route.activated {
            continue;
        }

        let path_hash = fnv1a_hash(&route.path_prefix);
        let mut max_pps: u64 = 0;
        let mut blocked = false;

        // Find rate_limit policies bound to this route
        for policy in policies {
            if policy.api_id != route.id {
                continue;
            }
            match policy.policy_type.as_str() {
                "rate_limit" => {
                    if let Some(limit) = policy.config.get("requests_per_second") {
                        max_pps = limit.as_u64().unwrap_or(0);
                    }
                }
                "block" => {
                    blocked = true;
                }
                _ => {}
            }
        }

        // Only push policies that have enforcement rules
        if max_pps > 0 || blocked {
            result.push(EbpfApiPolicy {
                path_hash,
                path: route.path_prefix.clone(),
                max_pps,
                blocked,
            });
        }
    }

    result
}

/// Sync current route state to the eBPF daemon.
/// Called after route reload (SIGHUP or admin API).
pub async fn sync_routes_to_ebpf(
    client: &EbpfSyncClient,
    route_registry: &crate::routes::registry::RouteRegistry,
    policy_registry: &crate::routes::policy::PolicyRegistry,
) -> Result<usize, String> {
    let routes = route_registry.list();
    let policies = policy_registry.list();

    let ebpf_policies = translate_routes_to_ebpf_policies(&routes, &policies);

    if ebpf_policies.is_empty() {
        info!("No eBPF-enforceable policies found (0 rate_limit/block rules)");
        return Ok(0);
    }

    client.sync_policies(&ebpf_policies).await
}

// ============================================================================
// Admin Handlers
// ============================================================================

/// POST /admin/ebpf/sync — manually trigger policy sync to eBPF daemon.
pub async fn ebpf_sync(
    axum::extract::State(state): axum::extract::State<crate::state::AppState>,
) -> impl axum::response::IntoResponse {
    let client = match &state.ebpf_client {
        Some(c) => c,
        None => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                axum::Json(serde_json::json!({
                    "status": "disabled",
                    "message": "eBPF integration not configured (STOA_EBPF_DAEMON_URL not set)"
                })),
            );
        }
    };

    match sync_routes_to_ebpf(client, &state.route_registry, &state.policy_registry).await {
        Ok(count) => (
            StatusCode::OK,
            axum::Json(serde_json::json!({
                "status": "ok",
                "policies_synced": count
            })),
        ),
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            axum::Json(serde_json::json!({
                "status": "error",
                "message": e
            })),
        ),
    }
}

/// GET /admin/ebpf/status — get eBPF daemon attachment status + metrics.
pub async fn ebpf_status(
    axum::extract::State(state): axum::extract::State<crate::state::AppState>,
) -> impl axum::response::IntoResponse {
    let client = match &state.ebpf_client {
        Some(c) => c,
        None => {
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                axum::Json(serde_json::json!({
                    "status": "disabled",
                    "message": "eBPF integration not configured"
                })),
            );
        }
    };

    match client.status().await {
        Ok(status) => (StatusCode::OK, axum::Json(serde_json::json!(status))),
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            axum::Json(serde_json::json!({
                "status": "error",
                "message": e
            })),
        ),
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::routes::policy::PolicyEntry;
    use crate::routes::registry::ApiRoute;

    fn make_route(id: &str, path: &str, activated: bool) -> ApiRoute {
        ApiRoute {
            id: id.to_string(),
            name: format!("Test API {id}"),
            tenant_id: "acme".to_string(),
            path_prefix: path.to_string(),
            backend_url: "http://backend:8080".to_string(),
            methods: vec![],
            spec_hash: String::new(),
            activated,
            classification: None,
            contract_key: None,
            upstream_http_version: Default::default(),
            upstreams: vec![],
            load_balancer: Default::default(),
            trusted_backend: false,
        }
    }

    fn make_policy(api_id: &str, policy_type: &str, config: serde_json::Value) -> PolicyEntry {
        PolicyEntry {
            id: format!("pol-{api_id}"),
            name: format!("Policy for {api_id}"),
            policy_type: policy_type.to_string(),
            config,
            priority: 0,
            api_id: api_id.to_string(),
        }
    }

    #[test]
    fn test_fnv1a_hash_consistency() {
        // Same input must always produce same hash (matching TC classifier)
        assert_eq!(fnv1a_hash("/api/v1/tools"), fnv1a_hash("/api/v1/tools"));
        assert_ne!(fnv1a_hash("/api/v1/tools"), fnv1a_hash("/api/v2/tools"));
    }

    #[test]
    fn test_fnv1a_known_values() {
        // Empty string
        assert_eq!(fnv1a_hash(""), 0x811c_9dc5);
        // "/" — single char
        let h = fnv1a_hash("/");
        assert_ne!(h, 0);
    }

    #[test]
    fn test_translate_rate_limit_policy() {
        let routes = vec![Arc::new(make_route("r1", "/api/v1/payments", true))];
        let policies = vec![make_policy(
            "r1",
            "rate_limit",
            serde_json::json!({"requests_per_second": 100}),
        )];

        let result = translate_routes_to_ebpf_policies(&routes, &policies);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "/api/v1/payments");
        assert_eq!(result[0].max_pps, 100);
        assert!(!result[0].blocked);
        assert_eq!(result[0].path_hash, fnv1a_hash("/api/v1/payments"));
    }

    #[test]
    fn test_translate_block_policy() {
        let routes = vec![Arc::new(make_route("r2", "/api/v1/deprecated", true))];
        let policies = vec![make_policy("r2", "block", serde_json::json!({}))];

        let result = translate_routes_to_ebpf_policies(&routes, &policies);
        assert_eq!(result.len(), 1);
        assert!(result[0].blocked);
    }

    #[test]
    fn test_translate_skips_inactive_routes() {
        let routes = vec![Arc::new(make_route("r3", "/api/v1/disabled", false))];
        let policies = vec![make_policy(
            "r3",
            "rate_limit",
            serde_json::json!({"requests_per_second": 50}),
        )];

        let result = translate_routes_to_ebpf_policies(&routes, &policies);
        assert!(result.is_empty());
    }

    #[test]
    fn test_translate_skips_routes_without_ebpf_policies() {
        let routes = vec![Arc::new(make_route("r4", "/api/v1/open", true))];
        let policies = vec![make_policy("r4", "cors", serde_json::json!({}))];

        let result = translate_routes_to_ebpf_policies(&routes, &policies);
        assert!(result.is_empty()); // cors has no eBPF enforcement
    }

    #[test]
    fn test_translate_multiple_routes() {
        let routes = vec![
            Arc::new(make_route("r5", "/api/v1/fast", true)),
            Arc::new(make_route("r6", "/api/v1/slow", true)),
            Arc::new(make_route("r7", "/api/v1/nopolicy", true)),
        ];
        let policies = vec![
            make_policy(
                "r5",
                "rate_limit",
                serde_json::json!({"requests_per_second": 1000}),
            ),
            make_policy("r6", "block", serde_json::json!({})),
        ];

        let result = translate_routes_to_ebpf_policies(&routes, &policies);
        assert_eq!(result.len(), 2); // r7 has no enforceable policy
    }
}
