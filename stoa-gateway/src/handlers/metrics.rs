// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use crate::metrics::Metrics;
use axum::{extract::State, http::header, response::IntoResponse};

/// Prometheus metrics endpoint.
///
/// Returns metrics in Prometheus text format.
///
/// # Endpoint
/// `GET /metrics`
pub async fn metrics_handler(State(metrics): State<Metrics>) -> impl IntoResponse {
    let body = metrics.encode();
    (
        [(
            header::CONTENT_TYPE,
            "text/plain; version=0.0.4; charset=utf-8",
        )],
        body,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
        routing::get,
        Router,
    };
    use tower::ServiceExt;

    #[tokio::test]
    async fn test_metrics_endpoint() {
        let metrics = Metrics::new();
        let app = Router::new()
            .route("/metrics", get(metrics_handler))
            .with_state(metrics);

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/metrics")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);

        let content_type = response.headers().get(header::CONTENT_TYPE).unwrap();
        assert!(content_type.to_str().unwrap().contains("text/plain"));
    }
}
