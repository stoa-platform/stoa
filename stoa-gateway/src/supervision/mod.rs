//! HEGEMON Supervision Tier Middleware (CAB-1636)
//!
//! Axum middleware that enforces supervision tiers for HEGEMON worker requests.
//! Runs after auth/quota but before handlers.
//!
//! Tier selection via `X-Hegemon-Supervision` header:
//!
//! | Tier      | Header value  | Behavior                                              |
//! |-----------|---------------|-------------------------------------------------------|
//! | AUTOPILOT | `autopilot`   | All requests pass. Rate limits + token budget active. |
//! | CO-PILOT  | `copilot`     | Mutations → fire-and-forget webhook. Non-blocking.    |
//! | COMMAND   | `command`     | Mutations → HTTP 403. GET/HEAD/OPTIONS only.          |
//!
//! Config:
//! - `STOA_SUPERVISION_ENABLED` (default: false)
//! - `STOA_SUPERVISION_WEBHOOK_URL` (optional, for CO-PILOT notifications)
//! - `STOA_SUPERVISION_DEFAULT_TIER` (default: "autopilot")

use axum::{
    body::Body,
    extract::State,
    http::{Method, Request, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use std::fmt;
use tracing::{debug, info, instrument, warn};

use crate::metrics;
use crate::state::AppState;

/// Header name for supervision tier selection.
const SUPERVISION_HEADER: &str = "x-hegemon-supervision";

/// Supervision tiers for HEGEMON workers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum SupervisionTier {
    /// All requests pass through. Rate limits and token budget still enforced.
    Autopilot,
    /// Read requests pass. Mutations trigger a fire-and-forget webhook notification.
    CoPilot,
    /// Read requests pass. Mutations are blocked with HTTP 403.
    Command,
}

impl SupervisionTier {
    /// Parse a tier from a header value string.
    pub fn from_header(value: &str) -> Option<Self> {
        match value.to_lowercase().trim() {
            "autopilot" => Some(Self::Autopilot),
            "copilot" | "co-pilot" => Some(Self::CoPilot),
            "command" => Some(Self::Command),
            _ => None,
        }
    }

    /// Parse from the config default tier string.
    pub fn from_config_default(value: &str) -> Self {
        Self::from_header(value).unwrap_or(Self::Autopilot)
    }
}

impl fmt::Display for SupervisionTier {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Autopilot => write!(f, "autopilot"),
            Self::CoPilot => write!(f, "copilot"),
            Self::Command => write!(f, "command"),
        }
    }
}

/// Response body when a mutation is blocked by COMMAND tier.
#[derive(Debug, Serialize)]
struct SupervisionBlockedResponse {
    error: String,
    message: String,
    tier: String,
    method: String,
}

/// Returns true for HTTP methods that represent mutations.
fn is_mutation(method: &Method) -> bool {
    matches!(
        *method,
        Method::POST | Method::PUT | Method::DELETE | Method::PATCH
    )
}

/// Supervision tier middleware.
///
/// Extracts the supervision tier from the `X-Hegemon-Supervision` header
/// (falls back to `STOA_SUPERVISION_DEFAULT_TIER` config).
/// Evaluates the tier against the request method and either passes,
/// fires a webhook (CO-PILOT), or blocks (COMMAND).
#[instrument(name = "policy.supervision", skip_all, fields(otel.kind = "internal"))]
pub async fn supervision_middleware(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Response {
    // Skip if supervision is disabled
    if !state.config.supervision_enabled {
        return next.run(request).await;
    }

    // Begin latency tracking for supervision stage (CAB-1790)
    let tracker = request
        .extensions()
        .get::<crate::diagnostics::latency::SharedTracker>()
        .cloned();
    if let Some(ref t) = tracker {
        if let Ok(mut guard) = t.lock() {
            guard.begin_stage(crate::diagnostics::latency::Stage::Supervision);
        }
    }

    // Extract tier from header, fall back to config default
    let tier = request
        .headers()
        .get(SUPERVISION_HEADER)
        .and_then(|v| v.to_str().ok())
        .and_then(SupervisionTier::from_header)
        .unwrap_or_else(|| {
            SupervisionTier::from_config_default(&state.config.supervision_default_tier)
        });

    let method = request.method().clone();
    let is_mut = is_mutation(&method);

    // End supervision stage before handing off to next middleware
    if let Some(ref t) = tracker {
        if let Ok(mut guard) = t.lock() {
            guard.end_stage();
        }
    }

    match tier {
        SupervisionTier::Autopilot => {
            // All requests pass through
            debug!(tier = "autopilot", method = %method, "supervision: pass");
            metrics::record_supervision_decision("autopilot", "pass");
            next.run(request).await
        }
        SupervisionTier::CoPilot => {
            if is_mut {
                // Fire-and-forget webhook notification for mutations
                debug!(tier = "copilot", method = %method, "supervision: notify (mutation)");
                metrics::record_supervision_decision("copilot", "notify");

                // Fire webhook asynchronously (non-blocking)
                if let Some(ref webhook_url) = state.config.supervision_webhook_url {
                    let url = webhook_url.clone();
                    let method_str = method.to_string();
                    let uri = request.uri().to_string();
                    tokio::spawn(async move {
                        fire_webhook(&url, &method_str, &uri).await;
                    });
                }
            } else {
                debug!(tier = "copilot", method = %method, "supervision: pass (read)");
                metrics::record_supervision_decision("copilot", "pass");
            }
            // Always pass through — webhook is fire-and-forget
            next.run(request).await
        }
        SupervisionTier::Command => {
            if is_mut {
                // Block mutations with 403
                info!(tier = "command", method = %method, "supervision: block (mutation)");
                metrics::record_supervision_decision("command", "block");

                let body = SupervisionBlockedResponse {
                    error: "supervision_blocked".to_string(),
                    message: format!(
                        "COMMAND tier: {} requests are blocked. Only GET/HEAD/OPTIONS allowed.",
                        method
                    ),
                    tier: "command".to_string(),
                    method: method.to_string(),
                };
                return (StatusCode::FORBIDDEN, Json(body)).into_response();
            }

            debug!(tier = "command", method = %method, "supervision: pass (read)");
            metrics::record_supervision_decision("command", "pass");
            next.run(request).await
        }
    }
}

/// Fire a webhook notification for CO-PILOT tier mutations.
/// Best-effort: failures are logged but never block the request.
async fn fire_webhook(url: &str, method: &str, uri: &str) {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build();

    let client = match client {
        Ok(c) => c,
        Err(e) => {
            warn!(error = %e, "supervision: failed to build webhook client");
            return;
        }
    };

    let payload = serde_json::json!({
        "event": "hegemon_supervision_notify",
        "tier": "copilot",
        "method": method,
        "uri": uri,
        "timestamp": chrono::Utc::now().to_rfc3339(),
    });

    match client.post(url).json(&payload).send().await {
        Ok(resp) => {
            debug!(status = %resp.status(), "supervision: webhook sent");
        }
        Err(e) => {
            warn!(error = %e, url = url, "supervision: webhook failed (non-blocking)");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::{get, put},
        Router,
    };
    use tower::ServiceExt;

    use crate::config::Config;

    fn create_test_state(enabled: bool) -> AppState {
        let config = Config {
            supervision_enabled: enabled,
            supervision_default_tier: "autopilot".to_string(),
            supervision_webhook_url: None,
            ..Config::default()
        };
        AppState::new(config)
    }

    fn create_test_state_with_tier(enabled: bool, default_tier: &str) -> AppState {
        let config = Config {
            supervision_enabled: enabled,
            supervision_default_tier: default_tier.to_string(),
            supervision_webhook_url: None,
            ..Config::default()
        };
        AppState::new(config)
    }

    async fn echo_handler() -> &'static str {
        "ok"
    }

    fn build_test_router(state: AppState) -> Router {
        Router::new()
            .route("/test", get(echo_handler).post(echo_handler))
            .route("/test/resource", put(echo_handler).delete(echo_handler))
            .layer(middleware::from_fn_with_state(
                state.clone(),
                supervision_middleware,
            ))
            .with_state(state)
    }

    // === SupervisionTier parsing ===

    #[test]
    fn test_tier_from_header_valid() {
        assert_eq!(
            SupervisionTier::from_header("autopilot"),
            Some(SupervisionTier::Autopilot)
        );
        assert_eq!(
            SupervisionTier::from_header("copilot"),
            Some(SupervisionTier::CoPilot)
        );
        assert_eq!(
            SupervisionTier::from_header("co-pilot"),
            Some(SupervisionTier::CoPilot)
        );
        assert_eq!(
            SupervisionTier::from_header("command"),
            Some(SupervisionTier::Command)
        );
    }

    #[test]
    fn test_tier_from_header_case_insensitive() {
        assert_eq!(
            SupervisionTier::from_header("AUTOPILOT"),
            Some(SupervisionTier::Autopilot)
        );
        assert_eq!(
            SupervisionTier::from_header("CoPilot"),
            Some(SupervisionTier::CoPilot)
        );
        assert_eq!(
            SupervisionTier::from_header("COMMAND"),
            Some(SupervisionTier::Command)
        );
    }

    #[test]
    fn test_tier_from_header_invalid() {
        assert_eq!(SupervisionTier::from_header("unknown"), None);
        assert_eq!(SupervisionTier::from_header(""), None);
    }

    #[test]
    fn test_tier_from_config_default_fallback() {
        assert_eq!(
            SupervisionTier::from_config_default("invalid"),
            SupervisionTier::Autopilot
        );
    }

    #[test]
    fn test_tier_display() {
        assert_eq!(SupervisionTier::Autopilot.to_string(), "autopilot");
        assert_eq!(SupervisionTier::CoPilot.to_string(), "copilot");
        assert_eq!(SupervisionTier::Command.to_string(), "command");
    }

    // === is_mutation ===

    #[test]
    fn test_is_mutation() {
        assert!(is_mutation(&Method::POST));
        assert!(is_mutation(&Method::PUT));
        assert!(is_mutation(&Method::DELETE));
        assert!(is_mutation(&Method::PATCH));
        assert!(!is_mutation(&Method::GET));
        assert!(!is_mutation(&Method::HEAD));
        assert!(!is_mutation(&Method::OPTIONS));
    }

    // === Middleware: disabled ===

    #[tokio::test]
    async fn test_disabled_passes_all_requests() {
        let state = create_test_state(false);
        let router = build_test_router(state);

        // POST should pass when supervision is disabled
        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    // === Middleware: AUTOPILOT ===

    #[tokio::test]
    async fn test_autopilot_passes_get() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::GET)
            .header(SUPERVISION_HEADER, "autopilot")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_autopilot_passes_post() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .header(SUPERVISION_HEADER, "autopilot")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    // === Middleware: CO-PILOT ===

    #[tokio::test]
    async fn test_copilot_passes_get() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::GET)
            .header(SUPERVISION_HEADER, "copilot")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_copilot_passes_post_nonblocking() {
        // CO-PILOT allows mutations through (webhook is fire-and-forget)
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .header(SUPERVISION_HEADER, "copilot")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    // === Middleware: COMMAND ===

    #[tokio::test]
    async fn test_command_passes_get() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::GET)
            .header(SUPERVISION_HEADER, "command")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_command_blocks_post() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .header(SUPERVISION_HEADER, "command")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_command_blocks_put() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test/resource")
            .method(Method::PUT)
            .header(SUPERVISION_HEADER, "command")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_command_blocks_delete() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test/resource")
            .method(Method::DELETE)
            .header(SUPERVISION_HEADER, "command")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    // === Middleware: default tier ===

    #[tokio::test]
    async fn test_no_header_defaults_to_autopilot() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        // POST without header should pass (default = autopilot)
        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_no_header_with_command_default_blocks_post() {
        let state = create_test_state_with_tier(true, "command");
        let router = build_test_router(state);

        // POST without header, but default_tier = command → blocked
        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn test_header_overrides_default_tier() {
        // Default is command, but header says autopilot → should pass
        let state = create_test_state_with_tier(true, "command");
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .header(SUPERVISION_HEADER, "autopilot")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::OK);
    }

    // === Blocked response body ===

    #[tokio::test]
    async fn test_command_block_response_body() {
        let state = create_test_state(true);
        let router = build_test_router(state);

        let request = Request::builder()
            .uri("/test")
            .method(Method::POST)
            .header(SUPERVISION_HEADER, "command")
            .body(Body::empty())
            .expect("request");
        let response = router.oneshot(request).await.expect("response");
        assert_eq!(response.status(), StatusCode::FORBIDDEN);

        let body = axum::body::to_bytes(response.into_body(), 1024)
            .await
            .expect("body");
        let json: serde_json::Value = serde_json::from_slice(&body).expect("json");
        assert_eq!(json["error"], "supervision_blocked");
        assert_eq!(json["tier"], "command");
        assert_eq!(json["method"], "POST");
    }
}
