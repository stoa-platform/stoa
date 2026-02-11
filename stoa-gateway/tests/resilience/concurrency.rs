//! Concurrency tests — verify gateway handles high concurrent load without deadlocks.

use axum::body::Body;
use axum::http::{Request, StatusCode};
use std::sync::Arc;
use tower::ServiceExt;

use crate::common::TestApp;

/// DoD #5: 1,000 concurrent tool list calls complete without deadlock (< 5s).
#[tokio::test]
async fn test_1000_concurrent_tool_calls() {
    let app = TestApp::new();
    let router = Arc::new(app);

    let mut handles = Vec::with_capacity(1000);
    for _ in 0..1000 {
        let r = router.clone();
        handles.push(tokio::spawn(async move {
            let (status, _) = r
                .post_json(
                    "/mcp/tools/list",
                    r#"{"jsonrpc":"2.0","method":"tools/list","id":1}"#,
                )
                .await;
            status
        }));
    }

    let deadline = tokio::time::timeout(std::time::Duration::from_secs(5), async {
        let mut results = Vec::with_capacity(1000);
        for handle in handles {
            results.push(handle.await.expect("task should not panic"));
        }
        results
    })
    .await;

    let results = deadline.expect("1000 concurrent requests should complete within 5s");
    assert_eq!(results.len(), 1000);

    // All requests should get a response (not hang or crash)
    for (i, status) in results.iter().enumerate() {
        assert!(
            status.is_success() || *status == StatusCode::BAD_REQUEST,
            "Request {} unexpected status: {}",
            i,
            status
        );
    }
}

/// 100 concurrent GET /admin/health calls.
#[tokio::test]
async fn test_concurrent_admin_health() {
    let config = stoa_gateway::config::Config {
        admin_api_token: Some("test-token".to_string()),
        auto_register: false,
        ..stoa_gateway::config::Config::default()
    };
    let state = stoa_gateway::state::AppState::new(config);
    let router = Arc::new(stoa_gateway::build_router(state));

    let mut handles = Vec::with_capacity(100);
    for _ in 0..100 {
        let r = router.clone();
        handles.push(tokio::spawn(async move {
            let request = Request::builder()
                .method("GET")
                .uri("/admin/health")
                .header("Authorization", "Bearer test-token")
                .body(Body::empty())
                .expect("valid request");

            let response = (*r).clone().oneshot(request).await.expect("ok");
            response.status()
        }));
    }

    let deadline = tokio::time::timeout(std::time::Duration::from_secs(5), async {
        let mut results = Vec::with_capacity(100);
        for handle in handles {
            results.push(handle.await.expect("task should not panic"));
        }
        results
    })
    .await;

    let results = deadline.expect("100 concurrent admin/health should complete within 5s");
    assert_eq!(results.len(), 100);
    for status in &results {
        assert_eq!(*status, StatusCode::OK);
    }
}

/// Mix of concurrent requests to different endpoints.
#[tokio::test]
async fn test_concurrent_mixed_endpoints() {
    let config = stoa_gateway::config::Config {
        admin_api_token: Some("test-token".to_string()),
        auto_register: false,
        ..stoa_gateway::config::Config::default()
    };
    let state = stoa_gateway::state::AppState::new(config);
    let router = Arc::new(stoa_gateway::build_router(state));

    let mut handles = Vec::with_capacity(300);

    // 100 health checks
    for _ in 0..100 {
        let r = router.clone();
        handles.push(tokio::spawn(async move {
            let request = Request::builder()
                .method("GET")
                .uri("/health")
                .body(Body::empty())
                .expect("valid request");
            let response = (*r).clone().oneshot(request).await.expect("ok");
            response.status()
        }));
    }

    // 100 MCP discovery
    for _ in 0..100 {
        let r = router.clone();
        handles.push(tokio::spawn(async move {
            let request = Request::builder()
                .method("GET")
                .uri("/mcp")
                .body(Body::empty())
                .expect("valid request");
            let response = (*r).clone().oneshot(request).await.expect("ok");
            response.status()
        }));
    }

    // 100 admin health (authenticated)
    for _ in 0..100 {
        let r = router.clone();
        handles.push(tokio::spawn(async move {
            let request = Request::builder()
                .method("GET")
                .uri("/admin/health")
                .header("Authorization", "Bearer test-token")
                .body(Body::empty())
                .expect("valid request");
            let response = (*r).clone().oneshot(request).await.expect("ok");
            response.status()
        }));
    }

    let deadline = tokio::time::timeout(std::time::Duration::from_secs(5), async {
        let mut results = Vec::with_capacity(300);
        for handle in handles {
            results.push(handle.await.expect("task should not panic"));
        }
        results
    })
    .await;

    let results = deadline.expect("300 concurrent mixed requests should complete within 5s");
    assert_eq!(results.len(), 300);

    // All should complete with some valid HTTP status
    for status in &results {
        assert!(status.as_u16() < 600, "Unexpected status code: {}", status);
    }
}
