//! mTLS admin endpoints (CAB-864).

use axum::{extract::State, Json};

use crate::state::AppState;

/// GET /admin/mtls/config — current mTLS configuration (trusted_proxies redacted)
pub async fn mtls_config(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsConfigResponse> {
    Json(crate::auth::mtls::MtlsConfigResponse::from(
        &state.config.mtls,
    ))
}

/// GET /admin/mtls/stats — mTLS validation stats
pub async fn mtls_stats(
    State(state): State<AppState>,
) -> Json<crate::auth::mtls::MtlsStatsSnapshot> {
    Json(state.mtls_stats.snapshot())
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_req, build_full_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_mtls_config_endpoint() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/mtls/config")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_mtls_stats_endpoint() {
        let state = create_test_state(Some("secret"));
        let app = build_full_admin_router(state);
        let response = app.oneshot(auth_req("GET", "/mtls/stats")).await.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }
}
