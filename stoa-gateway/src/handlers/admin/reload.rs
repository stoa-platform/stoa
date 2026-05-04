//! Route hot-reload endpoint (CAB-1828).
//!
//! GW-1 P1-0: the admin response NEVER echoes reqwest/serde error details
//! back to the caller (would leak internal control-plane URLs, DNS names,
//! parser internals). Full errors are logged server-side with a
//! `request_id` for correlation; the HTTP body only carries a generic
//! message plus the id.

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use thiserror::Error;
use tracing::{error, warn};
use uuid::Uuid;

use crate::state::AppState;

/// Typed reload errors so both the admin handler (HTTP status mapping)
/// and background callers (tracing Display) can act on them.
#[derive(Error, Debug)]
pub enum ReloadError {
    #[error("STOA_CONTROL_PLANE_URL not configured")]
    NotConfigured,
    #[error("HTTP request to control plane failed")]
    CpUnreachable(#[source] reqwest::Error),
    #[error("Control plane returned non-success status {0}")]
    CpStatus(u16),
    #[error("Failed to parse control plane response")]
    ParseFailed(#[source] reqwest::Error),
    #[error("Route reload ack request to control plane failed")]
    AckUnreachable(#[source] reqwest::Error),
    #[error("Control plane route reload ack returned non-success status {0}")]
    AckStatus(u16),
}

impl ReloadError {
    /// HTTP status to surface on the admin endpoint.
    fn http_status(&self) -> StatusCode {
        match self {
            Self::NotConfigured => StatusCode::SERVICE_UNAVAILABLE,
            Self::CpUnreachable(_)
            | Self::CpStatus(_)
            | Self::ParseFailed(_)
            | Self::AckUnreachable(_)
            | Self::AckStatus(_) => StatusCode::BAD_GATEWAY,
        }
    }

    /// Generic, non-leaky client message.
    fn client_message(&self) -> &'static str {
        match self {
            Self::NotConfigured => "Route reload unavailable: control plane URL not configured",
            Self::CpUnreachable(_) => "Route reload failed: control plane unreachable",
            Self::CpStatus(_) => "Route reload failed: control plane returned an error",
            Self::ParseFailed(_) => "Route reload failed: control plane response malformed",
            Self::AckUnreachable(_) => "Route reload failed: control plane ack unreachable",
            Self::AckStatus(_) => "Route reload failed: control plane rejected route ack",
        }
    }
}

#[derive(Debug, Deserialize)]
struct ControlPlaneRoute {
    #[serde(flatten)]
    route: crate::routes::ApiRoute,
    #[serde(default)]
    deployment_id: String,
    #[serde(default)]
    gateway_instance_id: String,
    #[serde(default)]
    generation: Option<u64>,
}

#[derive(Debug, Serialize)]
struct RouteSyncAckPayload {
    synced_routes: Vec<RouteSyncAckResult>,
    sync_timestamp: String,
}

#[derive(Debug, Serialize)]
struct RouteSyncAckResult {
    deployment_id: String,
    status: &'static str,
    error: Option<String>,
    steps: Vec<RouteSyncAckStep>,
    generation: Option<u64>,
}

#[derive(Debug, Serialize)]
struct RouteSyncAckStep {
    name: &'static str,
    status: &'static str,
    detail: &'static str,
}

/// Trigger a route table reload from the Control Plane.
///
/// POST /admin/routes/reload
///
/// Fetches all published APIs from the CP and atomically swaps the
/// route table using `ArcSwap`. Readers never block during the swap.
/// Requires `STOA_ROUTE_RELOAD_ENABLED=true`.
pub async fn routes_reload(State(state): State<AppState>) -> impl IntoResponse {
    if !state.config.route_reload_enabled {
        return (
            StatusCode::CONFLICT,
            Json(serde_json::json!({
                "status": "error",
                "message": "Route reload is disabled (STOA_ROUTE_RELOAD_ENABLED=false)"
            })),
        );
    }

    match reload_routes_from_cp(&state).await {
        Ok(count) => (
            StatusCode::OK,
            Json(serde_json::json!({
                "status": "ok",
                "routes_loaded": count
            })),
        ),
        Err(e) => {
            // Log the full error server-side with a correlation id.
            // The HTTP body never carries `e`'s internals (GW-1 P1-0).
            let request_id = Uuid::new_v4();
            error!(
                request_id = %request_id,
                error = ?e,
                "Route reload failed",
            );
            (
                e.http_status(),
                Json(serde_json::json!({
                    "status": "error",
                    "message": e.client_message(),
                    "request_id": request_id.to_string(),
                })),
            )
        }
    }
}

/// Fetch routes from Control Plane and swap the route table.
///
/// Shared logic used by the admin endpoint, SIGHUP handler, and watch loop.
pub async fn reload_routes_from_cp(state: &AppState) -> Result<usize, ReloadError> {
    let cp_url = state
        .config
        .control_plane_url
        .as_deref()
        .ok_or(ReloadError::NotConfigured)?;

    let url = format!(
        "{}/v1/internal/gateways/routes",
        cp_url.trim_end_matches('/')
    );

    let mut request = state.http_client.get(&url);
    if let Some(gateway_name) = current_gateway_name(&state.config) {
        request = request.query(&[("gateway_name", gateway_name.as_str())]);
    } else {
        warn!("Route reload is unfiltered because the gateway name could not be derived");
    }

    if let Some(ref token) = state.config.control_plane_api_key {
        request = request.header("X-Gateway-Key", token.as_str());
    }

    let response = request.send().await.map_err(ReloadError::CpUnreachable)?;

    if !response.status().is_success() {
        return Err(ReloadError::CpStatus(response.status().as_u16()));
    }

    let control_plane_routes: Vec<ControlPlaneRoute> =
        response.json().await.map_err(ReloadError::ParseFailed)?;

    let acks = build_route_sync_acks(&control_plane_routes);
    let routes = control_plane_routes
        .into_iter()
        .map(|item| item.route)
        .collect();
    let count = state.route_registry.swap_all(routes);
    send_route_sync_acks(state, cp_url, acks).await?;
    Ok(count)
}

fn build_route_sync_acks(routes: &[ControlPlaneRoute]) -> HashMap<String, Vec<RouteSyncAckResult>> {
    let mut acks: HashMap<String, Vec<RouteSyncAckResult>> = HashMap::new();
    for route in routes {
        if route.deployment_id.is_empty() || route.gateway_instance_id.is_empty() {
            continue;
        }
        acks.entry(route.gateway_instance_id.clone())
            .or_default()
            .push(RouteSyncAckResult {
                deployment_id: route.deployment_id.clone(),
                status: "applied",
                error: None,
                steps: vec![
                    RouteSyncAckStep {
                        name: "gateway_routes_fetched",
                        status: "success",
                        detail: "route loaded from control plane",
                    },
                    RouteSyncAckStep {
                        name: "gateway_routes_applied",
                        status: "success",
                        detail: "route table swapped in stoa-gateway",
                    },
                ],
                generation: route.generation,
            });
    }
    acks
}

async fn send_route_sync_acks(
    state: &AppState,
    cp_url: &str,
    acks: HashMap<String, Vec<RouteSyncAckResult>>,
) -> Result<(), ReloadError> {
    if acks.is_empty() {
        return Ok(());
    }

    for (gateway_id, synced_routes) in acks {
        let url = format!(
            "{}/v1/internal/gateways/{}/route-sync-ack",
            cp_url.trim_end_matches('/'),
            gateway_id
        );
        let payload = RouteSyncAckPayload {
            synced_routes,
            sync_timestamp: Utc::now().to_rfc3339(),
        };
        let mut request = state.http_client.post(&url).json(&payload);
        if let Some(ref token) = state.config.control_plane_api_key {
            request = request.header("X-Gateway-Key", token.as_str());
        }
        let response = request.send().await.map_err(ReloadError::AckUnreachable)?;
        if !response.status().is_success() {
            return Err(ReloadError::AckStatus(response.status().as_u16()));
        }
    }

    Ok(())
}

fn current_gateway_name(config: &crate::config::Config) -> Option<String> {
    let hostname = std::env::var("STOA_INSTANCE_NAME")
        .ok()
        .filter(|name| !name.is_empty())
        .or_else(|| {
            hostname::get()
                .ok()
                .map(|hostname| hostname.to_string_lossy().to_string())
        })?;

    Some(derive_gateway_name(
        &hostname,
        &config.gateway_mode.to_string(),
        &config.environment.to_string(),
    ))
}

fn derive_gateway_name(hostname: &str, mode: &str, environment: &str) -> String {
    let mode_clean = mode.replace('_', "");
    format!("{hostname}-{mode_clean}-{environment}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use wiremock::matchers::{body_string_contains, header, method, path};
    use wiremock::{Mock, MockServer, ResponseTemplate};

    #[test]
    fn regression_route_reload_gateway_name_matches_control_plane_registration() {
        assert_eq!(
            derive_gateway_name("stoa-gateway", "edge-mcp", "prod"),
            "stoa-gateway-edge-mcp-prod"
        );
        assert_eq!(
            derive_gateway_name("wm-link", "edge_mcp", "dev"),
            "wm-link-edgemcp-dev"
        );
    }

    #[test]
    fn test_not_configured_maps_to_503_and_generic_message() {
        let err = ReloadError::NotConfigured;
        assert_eq!(err.http_status(), StatusCode::SERVICE_UNAVAILABLE);
        assert!(!err.client_message().contains("STOA_CONTROL_PLANE_URL"));
        // Display still carries the detail for server-side logs.
        assert!(err.to_string().contains("STOA_CONTROL_PLANE_URL"));
    }

    #[test]
    fn test_cp_status_maps_to_502_without_echoing_status_code_in_client_message() {
        let err = ReloadError::CpStatus(418);
        assert_eq!(err.http_status(), StatusCode::BAD_GATEWAY);
        assert!(!err.client_message().contains("418"));
    }

    #[tokio::test]
    async fn reload_routes_posts_route_sync_ack_for_loaded_deployments() {
        let mock_server = MockServer::start().await;
        let deployment_id = Uuid::new_v4();
        let gateway_id = Uuid::new_v4();

        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/routes"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!([
                {
                    "id": "route-1",
                    "api_id": "payments-api",
                    "deployment_id": deployment_id.to_string(),
                    "gateway_instance_id": gateway_id.to_string(),
                    "generation": 7,
                    "name": "Payments API",
                    "tenant_id": "acme",
                    "path_prefix": "/apis/acme/payments",
                    "backend_url": "https://backend.test",
                    "methods": ["GET"],
                    "spec_hash": "abc123",
                    "activated": true
                }
            ])))
            .mount(&mock_server)
            .await;

        Mock::given(method("POST"))
            .and(path(format!(
                "/v1/internal/gateways/{gateway_id}/route-sync-ack"
            )))
            .and(header("X-Gateway-Key", "test-key"))
            .and(body_string_contains(deployment_id.to_string()))
            .and(body_string_contains("\"status\":\"applied\""))
            .and(body_string_contains("\"generation\":7"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!({
                "processed": 1,
                "not_found": 0
            })))
            .expect(1)
            .mount(&mock_server)
            .await;

        let config = crate::config::Config {
            control_plane_url: Some(mock_server.uri()),
            control_plane_api_key: Some("test-key".to_string()),
            ..crate::config::Config::default()
        };
        let state = AppState::new(config);

        let count = reload_routes_from_cp(&state)
            .await
            .expect("reload succeeds");

        assert_eq!(count, 1);
        assert_eq!(state.route_registry.count(), 1);
    }

    #[tokio::test]
    async fn reload_routes_keeps_routes_without_deployment_metadata_but_skips_ack() {
        let mock_server = MockServer::start().await;

        Mock::given(method("GET"))
            .and(path("/v1/internal/gateways/routes"))
            .respond_with(ResponseTemplate::new(200).set_body_json(serde_json::json!([
                {
                    "id": "legacy-route",
                    "name": "Legacy API",
                    "tenant_id": "acme",
                    "path_prefix": "/legacy",
                    "backend_url": "https://legacy.test",
                    "methods": ["GET"],
                    "spec_hash": "abc123",
                    "activated": true
                }
            ])))
            .mount(&mock_server)
            .await;

        Mock::given(method("POST"))
            .and(path("/v1/internal/gateways/ignored/route-sync-ack"))
            .respond_with(ResponseTemplate::new(500))
            .expect(0)
            .mount(&mock_server)
            .await;

        let config = crate::config::Config {
            control_plane_url: Some(mock_server.uri()),
            control_plane_api_key: Some("test-key".to_string()),
            ..crate::config::Config::default()
        };
        let state = AppState::new(config);

        let count = reload_routes_from_cp(&state)
            .await
            .expect("reload succeeds");

        assert_eq!(count, 1);
        assert_eq!(state.route_registry.count(), 1);
    }

    #[test]
    fn regression_reload_client_messages_are_static_and_non_leaky() {
        // None of the generic messages should reveal reqwest/serde/DNS internals.
        for msg in [
            ReloadError::NotConfigured.client_message(),
            ReloadError::CpStatus(500).client_message(),
            ReloadError::AckStatus(500).client_message(),
        ] {
            for needle in ["reqwest", "connection refused", "dns", "expected field"] {
                assert!(
                    !msg.to_ascii_lowercase().contains(needle),
                    "client_message leaked `{}` via `{}`",
                    needle,
                    msg
                );
            }
        }
    }
}
