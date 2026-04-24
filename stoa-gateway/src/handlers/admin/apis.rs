//! API Routes CRUD admin endpoints.

use std::sync::Arc;

use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use tracing::warn;
use uuid::Uuid;

use crate::proxy::dynamic::is_blocked_url;
use crate::routes::ApiRoute;
use crate::state::AppState;
use crate::telemetry::deploy::DeployStep;

pub async fn upsert_api(
    State(state): State<AppState>,
    Json(route): Json<ApiRoute>,
) -> impl IntoResponse {
    let deployment_id = Uuid::new_v4();
    let api_id = route.id.clone();
    let tenant = route.tenant_id.clone();
    let emitter = &state.deploy_progress;
    let aid = Some(api_id.as_str());
    let tid = Some(tenant.as_str());

    // Step 1: Validating — input validation + SSRF pre-check (CAB-1920)
    emitter.step_started(
        deployment_id,
        DeployStep::Validating,
        format!("Validating API route '{}'", api_id),
        aid,
        tid,
    );

    // GW-1 P1-6: reject empty/blank required identifier fields in one pass.
    // `methods` stays permissive — the struct doc treats empty as "all methods".
    let mut errors: Vec<String> = Vec::new();
    super::validation::require_non_empty("id", &route.id, &mut errors);
    super::validation::require_non_empty("name", &route.name, &mut errors);
    super::validation::require_non_empty("tenant_id", &route.tenant_id, &mut errors);
    super::validation::require_non_empty("path_prefix", &route.path_prefix, &mut errors);
    super::validation::require_non_empty("backend_url", &route.backend_url, &mut errors);
    if !route.path_prefix.trim().is_empty() && !route.path_prefix.starts_with('/') {
        errors.push("path_prefix must start with '/'".to_string());
    }
    if !errors.is_empty() {
        warn!(api_id = %api_id, ?errors, "Admin API rejected: validation failed");
        return super::validation::validation_error_response(errors);
    }

    // SSRF pre-check: block private/internal IPs at registration time,
    // even though trusted_backend bypasses the proxy-time check (CAB-1893).
    // Defense-in-depth: validate before storing, not just before proxying.
    if is_blocked_url(&route.backend_url) {
        warn!(
            api_id = %api_id,
            backend_url = %route.backend_url,
            "Admin API rejected: backend_url targets private/internal IP range"
        );
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "error": "backend_url targets a private/internal IP range",
                "detail": "URLs pointing to localhost, RFC 1918, link-local, or IPv6 loopback are not allowed"
            })),
        )
            .into_response();
    }

    emitter.step_completed(
        deployment_id,
        DeployStep::Validating,
        format!("API route '{}' validated", api_id),
        aid,
        tid,
    );

    // Step 2: Applying routes
    emitter.step_started(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!("Applying route '{}'", api_id),
        aid,
        tid,
    );
    // Mark admin-registered routes as trusted — SSRF check skipped (CAB-1893)
    let mut route = route;
    route.trusted_backend = true;
    let existed = state.route_registry.upsert(route).is_some();
    emitter.step_completed(
        deployment_id,
        DeployStep::ApplyingRoutes,
        format!(
            "Route '{}' {}",
            api_id,
            if existed { "updated" } else { "created" }
        ),
        aid,
        tid,
    );

    // GW-1 P2-8: `upsert_api` does NOT apply policies and does NOT have
    // a separate activation phase — `route_registry.upsert` above both
    // persists and activates the route in one call. Emitting fake
    // `ApplyingPolicies` / `Activating` step_started + step_completed
    // events around empty blocks produced a mendacious timeline that
    // confused operators reading the deploy_progress stream during
    // post-incident reviews. The `DeployStep` variants stay defined in
    // `telemetry/deploy.rs` for genuine consumers (contract-level flows
    // that actually bind policies). The honest sequence emitted here
    // is: Validating → ApplyingRoutes → Done.

    // Done
    emitter.step_completed(
        deployment_id,
        DeployStep::Done,
        format!("API sync complete for '{}'", api_id),
        aid,
        tid,
    );

    let status = if existed {
        StatusCode::OK
    } else {
        StatusCode::CREATED
    };
    (
        status,
        Json(serde_json::json!({
            "id": api_id,
            "status": "ok",
            "deployment_id": deployment_id.to_string()
        })),
    )
        .into_response()
}

pub async fn list_apis(State(state): State<AppState>) -> Json<Vec<Arc<ApiRoute>>> {
    Json(state.route_registry.list())
}

pub async fn get_api(State(state): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    match state.route_registry.get(&id) {
        Some(route) => Json(route).into_response(),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}

pub async fn delete_api(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    match state.route_registry.remove(&id) {
        Some(_) => StatusCode::NO_CONTENT.into_response(),
        None => (StatusCode::NOT_FOUND, "API not found").into_response(),
    }
}

#[cfg(test)]
mod tests {
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    use crate::handlers::admin::test_helpers::{
        auth_json_req, auth_req, build_admin_router, create_test_state,
    };

    #[tokio::test]
    async fn test_upsert_and_list_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": ["GET", "POST"],
            "spec_hash": "abc123",
            "activated": true
        });

        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::CREATED);

        // List routes
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
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
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 1);
        assert_eq!(data[0]["name"], "payments");
    }

    #[tokio::test]
    async fn test_get_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("GET", "/apis/nonexistent"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_upsert_update_existing_returns_200() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let route = serde_json::json!({
            "id": "r1", "name": "payments", "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments", "backend_url": "https://backend.test",
            "methods": ["GET"], "spec_hash": "abc", "activated": true
        });
        // First insert → CREATED
        let _ = app
            .clone()
            .oneshot(auth_json_req("POST", "/apis", route.clone()))
            .await
            .unwrap();
        // Second insert (update) → OK
        let response = app
            .oneshot(auth_json_req("POST", "/apis", route))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_delete_api_not_found() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let response = app
            .oneshot(auth_req("DELETE", "/apis/ghost"))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_delete_api() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);

        // Upsert a route first
        let route = serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": [],
            "spec_hash": "abc",
            "activated": true
        });

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .header("Content-Type", "application/json")
                    .body(Body::from(serde_json::to_string(&route).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        // Delete it
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("DELETE")
                    .uri("/apis/r1")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::NO_CONTENT);

        // Verify it's gone
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let body = axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let data: Vec<serde_json::Value> = serde_json::from_slice(&body).unwrap();
        assert_eq!(data.len(), 0);
    }

    // ─── GW-1 P1-6 regression: required fields on upsert_api ──────────

    async fn post_and_read_errors(
        app: axum::Router,
        body: serde_json::Value,
    ) -> (StatusCode, Vec<String>) {
        let response = app
            .oneshot(auth_json_req("POST", "/apis", body))
            .await
            .unwrap();
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), 64 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let errors = json["errors"]
            .as_array()
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        (status, errors)
    }

    fn valid_api_payload() -> serde_json::Value {
        serde_json::json!({
            "id": "r1",
            "name": "payments",
            "tenant_id": "acme",
            "path_prefix": "/apis/acme/payments",
            "backend_url": "https://backend.test",
            "methods": ["GET"],
            "spec_hash": "h",
            "activated": true
        })
    }

    #[tokio::test]
    async fn test_upsert_api_rejects_empty_id() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let mut p = valid_api_payload();
        p["id"] = serde_json::json!("");
        let (status, errors) = post_and_read_errors(app, p).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(
            errors.iter().any(|e| e.contains("id")),
            "errors = {:?}",
            errors
        );
    }

    #[tokio::test]
    async fn test_upsert_api_rejects_empty_tenant_id() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let mut p = valid_api_payload();
        p["tenant_id"] = serde_json::json!("");
        let (status, errors) = post_and_read_errors(app, p).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(errors.iter().any(|e| e.contains("tenant_id")));
    }

    #[tokio::test]
    async fn test_upsert_api_rejects_path_prefix_without_leading_slash() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let mut p = valid_api_payload();
        p["path_prefix"] = serde_json::json!("apis/acme/payments");
        let (status, errors) = post_and_read_errors(app, p).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(errors.iter().any(|e| e.contains("path_prefix")));
    }

    #[tokio::test]
    async fn test_upsert_api_reports_all_missing_fields_at_once() {
        let state = create_test_state(Some("secret"));
        let app = build_admin_router(state);
        let p = serde_json::json!({
            "id": "",
            "name": "",
            "tenant_id": "",
            "path_prefix": "",
            "backend_url": "",
            "methods": [],
            "spec_hash": "",
            "activated": true
        });
        let (status, errors) = post_and_read_errors(app, p).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        // All five required identifier fields reported in one batch.
        for field in ["id", "name", "tenant_id", "path_prefix", "backend_url"] {
            assert!(
                errors.iter().any(|e| e.contains(field)),
                "missing error for {} in {:?}",
                field,
                errors
            );
        }
    }

    // ─── GW-1 P2-8: deploy step honesty ──────────────────────────────
    //
    // `upsert_api` does not apply policies and does not have a separate
    // activation phase — `route_registry.upsert` both persists and
    // activates the route in one call. Emitting fake `ApplyingPolicies`
    // / `Activating` step_started + step_completed events around empty
    // blocks produced a mendacious timeline that confused operators
    // reading the `deploy_progress` stream during post-incident review.
    //
    // Capturing `tracing::debug!` events from inside an axum handler is
    // unreliable (tower's Service futures can reattach the dispatcher
    // across poll boundaries, defeating `subscriber::set_default`), so
    // we assert source-level: the `upsert_api` function body must not
    // reference the two enum variants the fake steps were built on.
    // The variants stay defined in `telemetry/deploy.rs` for genuine
    // consumers (contract-level flows) — this check is scoped to the
    // `upsert_api` body, not the whole module.
    #[test]
    fn regression_upsert_api_source_does_not_emit_fake_policy_or_activating() {
        let src = include_str!("apis.rs");

        let handler_start = src
            .find("pub async fn upsert_api")
            .expect("upsert_api fn must exist");
        let handler_tail = &src[handler_start..];
        let handler_end = handler_tail
            .find("\npub async fn list_apis")
            .expect("list_apis fn must immediately follow upsert_api");
        let body = &handler_tail[..handler_end];

        assert!(
            !body.contains("DeployStep::ApplyingPolicies"),
            "upsert_api must not emit ApplyingPolicies (GW-1 P2-8 — was a fake step with no underlying work)"
        );
        assert!(
            !body.contains("DeployStep::Activating"),
            "upsert_api must not emit Activating (GW-1 P2-8 — was a fake step with no underlying work)"
        );
        for expected in [
            "DeployStep::Validating",
            "DeployStep::ApplyingRoutes",
            "DeployStep::Done",
        ] {
            assert!(
                body.contains(expected),
                "upsert_api is expected to emit {} (honest step removed?)",
                expected
            );
        }
    }
}
