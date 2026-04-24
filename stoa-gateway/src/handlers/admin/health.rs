//! Admin health endpoint.
//!
//! This endpoint is **not** a Kubernetes liveness or readiness probe.
//! It reports static metadata (version, git provider) plus registry
//! counters for dashboards and operator-driven checks. K8s probes live
//! on `/health`, `/health/live`, `/ready`, and `/health/ready` and are
//! wired separately in `src/lib.rs::build_router`.

use axum::{extract::State, Json};
use serde::Serialize;

use crate::state::AppState;

#[derive(Serialize)]
pub struct AdminHealthResponse {
    pub status: String,
    pub version: String,
    pub routes_count: usize,
    pub policies_count: usize,
    /// GW-1 P2-1: number of registered UAC contracts.
    pub contracts_count: usize,
    /// GW-1 P2-1: number of stored skills in the resolver.
    pub skills_count: usize,
    /// GW-1 P2-1: seconds since this process started. Useful for
    /// correlating admin observations with restart timestamps in
    /// dashboards and post-incident reviews.
    pub uptime_seconds: u64,
    pub git_provider: String,
}

pub async fn admin_health(State(state): State<AppState>) -> Json<AdminHealthResponse> {
    Json(AdminHealthResponse {
        status: "ok".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        routes_count: state.route_registry.count(),
        policies_count: state.policy_registry.count(),
        contracts_count: state.contract_registry.count(),
        skills_count: state.skill_resolver.skill_count(),
        uptime_seconds: state.start_time.elapsed().as_secs(),
        git_provider: state.config.git_provider.to_string(),
    })
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    use crate::config::Config;
    use crate::handlers::admin::test_helpers::{build_admin_router, create_test_state};
    use crate::state::AppState;

    #[tokio::test]
    async fn test_admin_health() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["status"], "ok");
        assert!(data["version"].is_string());
        assert_eq!(data["routes_count"], 0);
        assert_eq!(data["policies_count"], 0);
        assert_eq!(data["git_provider"], "gitlab");
    }

    // GW-1 P2-1: enriched counters + uptime must be part of the response
    // shape so dashboards can plot them without flag-guarding on version.
    #[tokio::test]
    async fn regression_admin_health_exposes_contracts_skills_uptime() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["contracts_count"], 0);
        assert_eq!(data["skills_count"], 0);
        assert!(
            data["uptime_seconds"].is_u64(),
            "uptime_seconds must be a number, got {:?}",
            data["uptime_seconds"]
        );
    }

    #[tokio::test]
    async fn test_admin_health_reports_github_provider() {
        let config = Config {
            admin_api_token: Some("secret".into()),
            git_provider: crate::config::GitProvider::Github,
            ..Config::default()
        };
        let state = AppState::new(config);
        let app = build_admin_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/health")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(data["git_provider"], "github");
    }
}
