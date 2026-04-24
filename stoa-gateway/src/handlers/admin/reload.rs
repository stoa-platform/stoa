//! Route hot-reload endpoint (CAB-1828).
//!
//! GW-1 P1-0: the admin response NEVER echoes reqwest/serde error details
//! back to the caller (would leak internal control-plane URLs, DNS names,
//! parser internals). Full errors are logged server-side with a
//! `request_id` for correlation; the HTTP body only carries a generic
//! message plus the id.

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};
use thiserror::Error;
use tracing::error;
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
}

impl ReloadError {
    /// HTTP status to surface on the admin endpoint.
    fn http_status(&self) -> StatusCode {
        match self {
            Self::NotConfigured => StatusCode::SERVICE_UNAVAILABLE,
            Self::CpUnreachable(_) | Self::CpStatus(_) | Self::ParseFailed(_) => {
                StatusCode::BAD_GATEWAY
            }
        }
    }

    /// Generic, non-leaky client message.
    fn client_message(&self) -> &'static str {
        match self {
            Self::NotConfigured => "Route reload unavailable: control plane URL not configured",
            Self::CpUnreachable(_) => "Route reload failed: control plane unreachable",
            Self::CpStatus(_) => "Route reload failed: control plane returned an error",
            Self::ParseFailed(_) => "Route reload failed: control plane response malformed",
        }
    }
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
    if let Some(ref token) = state.config.control_plane_api_key {
        request = request.header("X-Gateway-Key", token.as_str());
    }

    let response = request.send().await.map_err(ReloadError::CpUnreachable)?;

    if !response.status().is_success() {
        return Err(ReloadError::CpStatus(response.status().as_u16()));
    }

    let routes: Vec<crate::routes::ApiRoute> =
        response.json().await.map_err(ReloadError::ParseFailed)?;

    let count = state.route_registry.swap_all(routes);
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn test_client_messages_are_static_and_non_leaky() {
        // None of the generic messages should reveal reqwest/serde/DNS internals.
        for msg in [
            ReloadError::NotConfigured.client_message(),
            ReloadError::CpStatus(500).client_message(),
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
