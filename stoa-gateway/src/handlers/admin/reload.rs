//! Route hot-reload endpoint (CAB-1828).

use axum::{extract::State, http::StatusCode, response::IntoResponse, Json};

use crate::state::AppState;

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
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({
                "status": "error",
                "message": format!("Route reload failed: {}", e)
            })),
        ),
    }
}

/// Fetch routes from Control Plane and swap the route table.
///
/// Shared logic used by the admin endpoint, SIGHUP handler, and watch loop.
pub async fn reload_routes_from_cp(state: &AppState) -> Result<usize, String> {
    let cp_url = state
        .config
        .control_plane_url
        .as_deref()
        .ok_or_else(|| "STOA_CONTROL_PLANE_URL not configured".to_string())?;

    let url = format!(
        "{}/v1/internal/gateways/routes",
        cp_url.trim_end_matches('/')
    );

    let mut request = state.http_client.get(&url);
    if let Some(ref token) = state.config.control_plane_api_key {
        request = request.header("X-Gateway-Key", token.as_str());
    }

    let response = request
        .send()
        .await
        .map_err(|e| format!("HTTP request failed: {}", e))?;

    if !response.status().is_success() {
        return Err(format!("CP returned status {}", response.status().as_u16()));
    }

    let routes: Vec<crate::routes::ApiRoute> = response
        .json()
        .await
        .map_err(|e| format!("Failed to parse response: {}", e))?;

    let count = state.route_registry.swap_all(routes);
    Ok(count)
}
