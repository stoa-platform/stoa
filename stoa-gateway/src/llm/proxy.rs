//! LLM Proxy — Transparent Anthropic API proxy with per-consumer metering (CAB-1568)
//!
//! Proxies `/v1/messages` to `api.anthropic.com`, identifying each consumer by
//! their `stoa_sk_*` API key. Extracts token usage from responses (both streaming
//! SSE and non-streaming JSON) and POSTs metering to the Control Plane API.

use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use bytes::Bytes;
use futures::StreamExt;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, error, warn};

use crate::state::AppState;

/// Proxy handler for `POST /v1/messages` → Anthropic API.
///
/// 1. Identifies consumer by `x-api-key: stoa_sk_*` header
/// 2. Replaces with real Anthropic key from `ANTHROPIC_API_KEY` env
/// 3. Forwards request and streams response back transparently
/// 4. Extracts token usage and POSTs to CP API asynchronously
pub async fn llm_proxy_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    if !state.config.llm_proxy_enabled {
        return (StatusCode::NOT_FOUND, "LLM proxy not enabled").into_response();
    }

    // Extract consumer API key (stoa_sk_* prefix required)
    let consumer_key = match headers.get("x-api-key").and_then(|v| v.to_str().ok()) {
        Some(k) if k.starts_with("stoa_sk_") => k,
        _ => {
            return (StatusCode::UNAUTHORIZED, "Missing or invalid stoa_sk_* API key")
                .into_response()
        }
    };
    // Use key suffix as consumer identifier (never log the full key)
    let consumer_id = &consumer_key[consumer_key.len().saturating_sub(12)..];

    // Resolve real Anthropic API key from environment
    let anthropic_key = match std::env::var("ANTHROPIC_API_KEY") {
        Ok(k) if !k.is_empty() => k,
        _ => {
            return (StatusCode::BAD_GATEWAY, "Upstream API key not configured").into_response()
        }
    };

    let is_stream = serde_json::from_slice::<Value>(&body)
        .ok()
        .and_then(|v| v.get("stream")?.as_bool())
        .unwrap_or(false);

    // Build upstream request
    let upstream_url = format!(
        "{}/v1/messages",
        state
            .config
            .llm_proxy_upstream_url
            .as_deref()
            .unwrap_or("https://api.anthropic.com")
    );
    let mut req = state
        .http_client
        .post(&upstream_url)
        .header("x-api-key", &anthropic_key)
        .header("content-type", "application/json");

    // Forward Anthropic-specific headers
    for name in ["anthropic-version", "anthropic-beta"] {
        if let Some(v) = headers.get(name) {
            req = req.header(name, v.clone());
        }
    }

    let upstream_resp = match req.body(body.to_vec()).send().await {
        Ok(r) => r,
        Err(e) => {
            error!(error = %e, "LLM proxy upstream error");
            return (StatusCode::BAD_GATEWAY, "Upstream request failed").into_response();
        }
    };

    let status =
        StatusCode::from_u16(upstream_resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let content_type = upstream_resp.headers().get("content-type").cloned();

    if is_stream && status.is_success() {
        proxy_streaming(state, upstream_resp, status, content_type, consumer_id).await
    } else {
        proxy_buffered(state, upstream_resp, status, content_type, consumer_id).await
    }
}

/// Streaming proxy: tee the SSE byte stream, extract usage from events.
async fn proxy_streaming(
    state: AppState,
    upstream_resp: reqwest::Response,
    status: StatusCode,
    content_type: Option<axum::http::HeaderValue>,
    consumer_id: &str,
) -> Response {
    let input_tokens = Arc::new(AtomicU64::new(0));
    let output_tokens = Arc::new(AtomicU64::new(0));
    let model: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));
    let sse_buf: Arc<Mutex<String>> = Arc::new(Mutex::new(String::new()));

    let (tx, rx) = tokio::sync::mpsc::channel::<Result<Bytes, std::io::Error>>(64);

    let it = input_tokens.clone();
    let ot = output_tokens.clone();
    let mc = model.clone();
    let sb = sse_buf.clone();
    let cp_url = state.config.control_plane_url.clone();
    let cp_key = state.config.control_plane_api_key.clone();
    let http = state.http_client.clone();
    let cid = consumer_id.to_string();

    tokio::spawn(async move {
        let mut stream = upstream_resp.bytes_stream();
        while let Some(chunk) = stream.next().await {
            match chunk {
                Ok(bytes) => {
                    if let Ok(text) = std::str::from_utf8(&bytes) {
                        extract_sse_usage(text, &sb, &it, &ot, &mc).await;
                    }
                    if tx.send(Ok(bytes)).await.is_err() {
                        break;
                    }
                }
                Err(e) => {
                    let _ = tx
                        .send(Err(std::io::Error::new(std::io::ErrorKind::Other, e)))
                        .await;
                    break;
                }
            }
        }
        drop(tx);
        let mdl = mc.lock().await.clone();
        fire_metering(
            &http,
            cp_url.as_deref(),
            cp_key.as_deref(),
            &cid,
            &mdl,
            it.load(Ordering::Relaxed),
            ot.load(Ordering::Relaxed),
        )
        .await;
    });

    let rx_stream = tokio_stream::wrappers::ReceiverStream::new(rx);
    let mut builder = Response::builder().status(status);
    if let Some(ct) = content_type {
        builder = builder.header("content-type", ct);
    }
    builder
        .body(Body::from_stream(rx_stream))
        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

/// Non-streaming proxy: buffer response, extract usage from JSON body.
async fn proxy_buffered(
    state: AppState,
    upstream_resp: reqwest::Response,
    status: StatusCode,
    content_type: Option<axum::http::HeaderValue>,
    consumer_id: &str,
) -> Response {
    let resp_body = match upstream_resp.bytes().await {
        Ok(b) => b,
        Err(e) => {
            error!(error = %e, "LLM proxy: failed to read upstream response");
            return (StatusCode::BAD_GATEWAY, "Failed to read upstream response").into_response();
        }
    };

    let (in_t, out_t, mdl) = if let Ok(v) = serde_json::from_slice::<Value>(&resp_body) {
        (
            v.pointer("/usage/input_tokens")
                .and_then(|t| t.as_u64())
                .unwrap_or(0),
            v.pointer("/usage/output_tokens")
                .and_then(|t| t.as_u64())
                .unwrap_or(0),
            v.get("model")
                .and_then(|t| t.as_str())
                .unwrap_or("unknown")
                .to_string(),
        )
    } else {
        (0, 0, "unknown".to_string())
    };

    let http = state.http_client.clone();
    let cp_url = state.config.control_plane_url.clone();
    let cp_key = state.config.control_plane_api_key.clone();
    let cid = consumer_id.to_string();
    tokio::spawn(async move {
        fire_metering(&http, cp_url.as_deref(), cp_key.as_deref(), &cid, &mdl, in_t, out_t).await;
    });

    let mut builder = Response::builder().status(status);
    if let Some(ct) = content_type {
        builder = builder.header("content-type", ct);
    }
    builder
        .body(Body::from(resp_body))
        .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
}

/// Parse SSE event chunks, accumulating input/output token counts.
async fn extract_sse_usage(
    text: &str,
    buf: &Mutex<String>,
    input_tokens: &AtomicU64,
    output_tokens: &AtomicU64,
    model: &Mutex<String>,
) {
    let mut b = buf.lock().await;
    b.push_str(text);
    while let Some(pos) = b.find("\n\n") {
        let event = b[..pos].to_string();
        b.drain(..pos + 2);
        for line in event.lines() {
            if let Some(data) = line.strip_prefix("data: ") {
                if let Ok(v) = serde_json::from_str::<Value>(data) {
                    match v.get("type").and_then(|t| t.as_str()) {
                        Some("message_start") => {
                            if let Some(t) =
                                v.pointer("/message/usage/input_tokens").and_then(|t| t.as_u64())
                            {
                                input_tokens.store(t, Ordering::Relaxed);
                            }
                            if let Some(m) =
                                v.pointer("/message/model").and_then(|t| t.as_str())
                            {
                                *model.lock().await = m.to_string();
                            }
                        }
                        Some("message_delta") => {
                            if let Some(t) =
                                v.pointer("/usage/output_tokens").and_then(|t| t.as_u64())
                            {
                                output_tokens.store(t, Ordering::Relaxed);
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }
}

/// Fire-and-forget usage POST to Control Plane API.
async fn fire_metering(
    http: &reqwest::Client,
    cp_url: Option<&str>,
    cp_key: Option<&str>,
    consumer_id: &str,
    model: &str,
    input_tokens: u64,
    output_tokens: u64,
) {
    if input_tokens == 0 && output_tokens == 0 {
        return;
    }
    debug!(
        consumer_id = %consumer_id,
        model = %model,
        input_tokens = %input_tokens,
        output_tokens = %output_tokens,
        "Recording LLM proxy usage"
    );
    // Record to Prometheus
    super::LLM_COST_TOTAL
        .with_label_values(&["anthropic", model])
        .inc_by(0.0); // Actual cost calculated by CP API

    if let Some(url) = cp_url {
        let payload = serde_json::json!({
            "consumer_id": consumer_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "provider": "anthropic",
        });
        let mut req = http
            .post(format!("{}/v1/usage/record", url))
            .json(&payload)
            .timeout(std::time::Duration::from_secs(5));
        if let Some(key) = cp_key {
            req = req.header("X-API-Key", key);
        }
        if let Err(e) = req.send().await {
            warn!(error = %e, "Failed to POST usage to CP API");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn extract_sse_message_start() {
        let buf = Mutex::new(String::new());
        let input = AtomicU64::new(0);
        let output = AtomicU64::new(0);
        let model = Mutex::new(String::new());

        let chunk = "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"model\":\"claude-sonnet-4-20250514\",\"usage\":{\"input_tokens\":42}}}\n\n";
        extract_sse_usage(chunk, &buf, &input, &output, &model).await;

        assert_eq!(input.load(Ordering::Relaxed), 42);
        assert_eq!(*model.lock().await, "claude-sonnet-4-20250514");
    }

    #[tokio::test]
    async fn extract_sse_message_delta() {
        let buf = Mutex::new(String::new());
        let input = AtomicU64::new(0);
        let output = AtomicU64::new(0);
        let model = Mutex::new(String::new());

        let chunk =
            "event: message_delta\ndata: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":99}}\n\n";
        extract_sse_usage(chunk, &buf, &input, &output, &model).await;

        assert_eq!(output.load(Ordering::Relaxed), 99);
    }

    #[tokio::test]
    async fn extract_sse_partial_chunks() {
        let buf = Mutex::new(String::new());
        let input = AtomicU64::new(0);
        let output = AtomicU64::new(0);
        let model = Mutex::new(String::new());

        // First partial chunk
        extract_sse_usage(
            "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"model\":\"claude-opus-4-20250514\",\"usage\":{\"input_tokens\":",
            &buf, &input, &output, &model,
        ).await;
        assert_eq!(input.load(Ordering::Relaxed), 0); // Not yet complete

        // Second chunk completes the event
        extract_sse_usage("100}}}\n\n", &buf, &input, &output, &model).await;
        assert_eq!(input.load(Ordering::Relaxed), 100);
    }
}
