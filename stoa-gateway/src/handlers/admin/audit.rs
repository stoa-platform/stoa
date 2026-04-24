//! Structured audit log for admin-API mutations (GW-1 P1-4 — tactical).
//!
//! Every request that reaches `/admin/*` emits a single `tracing` event
//! tagged `audit = true` after the inner handlers have produced a
//! response. The fields are deliberately flat and cheap to emit; they
//! are sized to satisfy DORA / ISO 27001 A.12.4.1 minimum requirements
//! without committing to a durable pipeline yet — log collection,
//! immutability, and long-term retention are follow-up work.
//!
//! Emitted fields:
//!
//! - `audit = true` — filter tag for downstream collection.
//! - `request_id` — fresh UUIDv4 per request.
//! - `method` / `path` — HTTP method + raw URI path (no query, no body).
//! - `status` / `duration_ms` — response status + handler round-trip wall time.
//! - `actor` — `admin` on 2xx/3xx, `unknown` otherwise, `anonymous` if no
//!   `Authorization` header was sent.
//! - `action` — derived from method + path (`POST /admin/apis` →
//!   `apis.upsert`). Coarse facet for dashboards.
//! - `resource` — raw URI path minus the `/admin` prefix.
//! - `outcome` — `success` for 2xx, otherwise `failure`.
//!
//! The middleware deliberately **does not** touch the request or
//! response body — no payload data, no secrets, no tokens are ever
//! captured. The `Authorization` header is only read as a present /
//! absent boolean to distinguish anonymous from authenticated-but-
//! rejected requests.

use std::time::Instant;

use axum::{body::Body, http::Request, middleware::Next, response::Response};
use tracing::info;
use uuid::Uuid;

/// Axum middleware — emits one audit `tracing::info!` event per admin
/// request, after the inner handler chain has produced the response.
///
/// Applied as the **outermost** layer on the admin sub-router so it
/// sees rate-limited (429) and unauthenticated (401) responses too —
/// brute-force attempts are part of the audit trail.
pub async fn admin_audit_log(request: Request<Body>, next: Next) -> Response {
    let request_id = Uuid::new_v4();
    let method = request.method().clone();
    let path = request.uri().path().to_string();
    let has_auth_header = request
        .headers()
        .contains_key(axum::http::header::AUTHORIZATION);
    let started = Instant::now();

    let response = next.run(request).await;

    let status = response.status().as_u16();
    let duration_ms = started.elapsed().as_millis() as u64;

    let outcome = if response.status().is_success() {
        "success"
    } else {
        "failure"
    };
    let actor = if !has_auth_header {
        "anonymous"
    } else if response.status().is_success() || response.status().is_redirection() {
        "admin"
    } else {
        "unknown"
    };
    let action = action_category(method.as_str(), &path);
    let resource = strip_admin_prefix(&path);

    info!(
        audit = true,
        request_id = %request_id,
        method = %method,
        path = %path,
        status,
        duration_ms,
        actor,
        action = %action,
        resource = %resource,
        outcome,
        "admin API request",
    );

    response
}

/// Derive a coarse `"<group>.<verb>"` action label from method + path.
/// Used for audit dashboards and alerting rules. Keep the mapping
/// intentionally small — richer taxonomies belong in the downstream
/// collector, not in the hot path.
fn action_category(method: &str, path: &str) -> String {
    let trimmed = strip_admin_prefix(path);
    let group = trimmed
        .trim_start_matches('/')
        .split('/')
        .next()
        .filter(|s| !s.is_empty())
        .unwrap_or("root");

    let verb = match method {
        "GET" | "HEAD" => "read",
        "POST" => {
            if trimmed.ends_with("/reset") {
                "reset"
            } else if trimmed.ends_with("/sync") {
                "sync"
            } else if trimmed.ends_with("/invalidate") || trimmed.ends_with("/clear") {
                "invalidate"
            } else if trimmed.ends_with("/reload") {
                "reload"
            } else {
                "upsert"
            }
        }
        "PUT" | "PATCH" => "update",
        "DELETE" => "delete",
        _ => "other",
    };
    format!("{}.{}", group, verb)
}

/// Return the portion of `path` that follows the `/admin` prefix, or
/// the path itself when the prefix isn't present (tests that mount
/// handlers directly).
fn strip_admin_prefix(path: &str) -> &str {
    path.strip_prefix("/admin").unwrap_or(path)
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use axum::{
        body::Body,
        http::{Request, StatusCode},
        middleware,
        routing::{get, post},
        Router,
    };
    use tower::ServiceExt;
    use tracing::subscriber::DefaultGuard;
    use tracing_subscriber::fmt::MakeWriter;

    use super::{action_category, admin_audit_log};

    // ── Pure-function coverage ─────────────────────────────────────

    #[test]
    fn test_action_category_maps_common_admin_verbs() {
        assert_eq!(action_category("POST", "/admin/apis"), "apis.upsert");
        assert_eq!(action_category("DELETE", "/admin/apis/r1"), "apis.delete");
        assert_eq!(action_category("GET", "/admin/contracts"), "contracts.read");
        assert_eq!(
            action_category("PUT", "/admin/skills/acme%2Fx"),
            "skills.update"
        );
        assert_eq!(
            action_category("POST", "/admin/routes/reload"),
            "routes.reload"
        );
        assert_eq!(
            action_category("POST", "/admin/cache/clear"),
            "cache.invalidate"
        );
        assert_eq!(
            action_category("POST", "/admin/prompt-cache/invalidate"),
            "prompt-cache.invalidate"
        );
        assert_eq!(
            action_category("POST", "/admin/circuit-breakers/api-x/reset"),
            "circuit-breakers.reset"
        );
        assert_eq!(action_category("POST", "/admin/skills/sync"), "skills.sync");
    }

    #[test]
    fn test_action_category_root_and_unknown_method() {
        assert_eq!(action_category("GET", "/admin"), "root.read");
        assert_eq!(action_category("CONNECT", "/admin/apis"), "apis.other");
    }

    // ── Middleware end-to-end: capture one event per request ───────

    /// Shared `Vec<u8>` that implements `std::io::Write`, used as the
    /// sink of `tracing_subscriber::fmt::json()`.
    #[derive(Clone, Default)]
    struct SharedBuf(Arc<Mutex<Vec<u8>>>);

    impl SharedBuf {
        fn lines(&self) -> Vec<serde_json::Value> {
            let bytes = self.0.lock().unwrap().clone();
            String::from_utf8_lossy(&bytes)
                .lines()
                .filter(|l| !l.is_empty())
                .filter_map(|l| serde_json::from_str(l).ok())
                .collect()
        }
    }

    impl std::io::Write for SharedBuf {
        fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    impl<'a> MakeWriter<'a> for SharedBuf {
        type Writer = SharedBuf;
        fn make_writer(&'a self) -> Self::Writer {
            self.clone()
        }
    }

    fn install_capture_subscriber() -> (SharedBuf, DefaultGuard) {
        let buf = SharedBuf::default();
        let subscriber = tracing_subscriber::fmt()
            .json()
            .with_writer(buf.clone())
            .with_max_level(tracing::Level::INFO)
            .finish();
        let guard = tracing::subscriber::set_default(subscriber);
        (buf, guard)
    }

    async fn ok_handler() -> &'static str {
        "ok"
    }

    async fn err_handler() -> (StatusCode, &'static str) {
        (StatusCode::BAD_REQUEST, "nope")
    }

    fn find_audit_events(buf: &SharedBuf) -> Vec<serde_json::Value> {
        buf.lines()
            .into_iter()
            .filter(|event| {
                // Tracing JSON layer writes fields under `fields.<name>`.
                let fields = event.get("fields").cloned().unwrap_or_default();
                fields.get("audit").and_then(|v| v.as_bool()) == Some(true)
            })
            .collect()
    }

    #[tokio::test]
    async fn regression_mutation_emits_structured_audit_event() {
        let (buf, _guard) = install_capture_subscriber();

        let app: Router = Router::new()
            .route("/admin/apis", post(ok_handler))
            .layer(middleware::from_fn(admin_audit_log));

        let _ = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/admin/apis")
                    .header("Authorization", "Bearer secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let events = find_audit_events(&buf);
        assert_eq!(
            events.len(),
            1,
            "expected exactly one audit event, got {:?}",
            events
        );
        let fields = &events[0]["fields"];
        assert_eq!(fields["method"], "POST");
        assert_eq!(fields["path"], "/admin/apis");
        assert_eq!(fields["action"], "apis.upsert");
        assert_eq!(fields["resource"], "/apis");
        assert_eq!(fields["status"], 200);
        assert_eq!(fields["outcome"], "success");
        assert_eq!(fields["actor"], "admin");
        // request_id parses as a UUID.
        let rid = fields["request_id"].as_str().expect("request_id string");
        assert!(uuid::Uuid::parse_str(rid).is_ok(), "bad uuid: {}", rid);
        // duration_ms is a number.
        assert!(fields["duration_ms"].is_number());
        // No body content leaked — assert against the known field set.
        let keys: std::collections::HashSet<&str> = fields
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        assert!(!keys.contains("body"), "body must never be logged");
        assert!(
            !keys.contains("authorization"),
            "authorization header must never be logged"
        );
    }

    #[tokio::test]
    async fn regression_failure_status_records_outcome_failure_and_actor_unknown() {
        let (buf, _guard) = install_capture_subscriber();

        let app: Router = Router::new()
            .route("/admin/apis", post(err_handler))
            .layer(middleware::from_fn(admin_audit_log));

        let _ = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/admin/apis")
                    .header("Authorization", "Bearer wrong")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let events = find_audit_events(&buf);
        assert_eq!(events.len(), 1);
        let fields = &events[0]["fields"];
        assert_eq!(fields["status"], 400);
        assert_eq!(fields["outcome"], "failure");
        // Auth header present but non-2xx → actor classified as unknown
        // (credentials rejected by the inner auth layer).
        assert_eq!(fields["actor"], "unknown");
    }

    #[tokio::test]
    async fn test_anonymous_request_records_actor_anonymous() {
        let (buf, _guard) = install_capture_subscriber();

        let app: Router = Router::new()
            .route("/admin/health", get(ok_handler))
            .layer(middleware::from_fn(admin_audit_log));

        let _ = app
            .oneshot(
                Request::builder()
                    .uri("/admin/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let events = find_audit_events(&buf);
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["fields"]["actor"], "anonymous");
    }
}
