//! LLM API Proxy (CAB-1568: STOA Dogfood)
//!
//! Transparent proxy for LLM API calls (Anthropic /v1/messages).
//! - Authenticates consumers via STOA API keys
//! - Injects real upstream API key
//! - Streams SSE responses transparently
//! - Extracts token usage for async metering

use axum::{
    body::Body,
    extract::{Request, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
};
use futures::StreamExt as _;
use reqwest::Client;
use serde::Deserialize;
use std::sync::OnceLock;
use std::time::{Duration, Instant};
use tracing::{debug, error, info, warn};

use crate::state::AppState;

/// Dedicated HTTP client for LLM proxy (long timeouts, large bodies).
fn llm_client(timeout: Duration) -> &'static Client {
    static CLIENT: OnceLock<Client> = OnceLock::new();
    CLIENT.get_or_init(|| {
        Client::builder()
            .timeout(timeout)
            .connect_timeout(Duration::from_secs(10))
            .pool_max_idle_per_host(64)
            .http1_only()
            .build()
            .expect("LLM proxy HTTP client")
    })
}

/// Proxy handler for POST /v1/messages (and /v1/messages/count_tokens).
///
/// Flow:
/// 1. Extract and validate STOA API key (X-API-Key or x-api-key header)
/// 2. Replace auth with real upstream API key
/// 3. Forward request to upstream, preserving anthropic-version header
/// 4. Stream response back to client
/// 5. Async: extract token usage and POST to CP API for metering
pub async fn llm_proxy_handler(State(state): State<AppState>, request: Request<Body>) -> Response {
    if !state.config.llm_proxy_enabled {
        return (StatusCode::NOT_FOUND, "LLM proxy not enabled").into_response();
    }

    let upstream_api_key = match &state.config.llm_proxy_api_key {
        Some(key) if !key.is_empty() => key.clone(),
        _ => {
            error!("LLM proxy: upstream API key not configured (STOA_LLM_PROXY_API_KEY)");
            return (
                StatusCode::SERVICE_UNAVAILABLE,
                "LLM proxy upstream not configured",
            )
                .into_response();
        }
    };

    // Step 1: Extract consumer API key from request
    let consumer_key = extract_api_key(request.headers());
    let consumer_key = match consumer_key {
        Some(key) => key,
        None => {
            return (
                StatusCode::UNAUTHORIZED,
                "Missing API key (x-api-key header required)",
            )
                .into_response();
        }
    };

    // Step 2: Validate consumer against Control Plane
    let consumer_info = match state.api_key_validator.validate(&consumer_key).await {
        Ok(info) => info,
        Err(e) => {
            warn!(error = %e, "LLM proxy: API key validation failed");
            return (StatusCode::UNAUTHORIZED, "Invalid API key").into_response();
        }
    };

    let tenant_id = consumer_info.tenant_id.clone();
    let subscription_id = consumer_info.subscription_id.clone();

    debug!(
        tenant_id = %tenant_id,
        subscription_id = %subscription_id,
        "LLM proxy: consumer authenticated"
    );

    // Step 3: Build upstream request
    let request_path = request.uri().path().to_string();
    let upstream_url = format!("{}{}", state.config.llm_proxy_upstream_url, request_path);

    let timeout = Duration::from_secs(state.config.llm_proxy_timeout_secs);
    let client = llm_client(timeout);

    // Collect request body
    let (parts, body) = request.into_parts();
    let body_bytes = match axum::body::to_bytes(body, 10 * 1024 * 1024).await {
        Ok(bytes) => bytes,
        Err(e) => {
            warn!(error = %e, "LLM proxy: failed to read request body");
            return (StatusCode::BAD_REQUEST, "Failed to read request body").into_response();
        }
    };

    // Build upstream headers: keep anthropic-version, anthropic-beta, content-type
    let mut upstream_headers = HeaderMap::new();
    for key in &[
        "anthropic-version",
        "anthropic-beta",
        "content-type",
        "accept",
    ] {
        if let Some(val) = parts.headers.get(*key) {
            if let Ok(name) = header::HeaderName::from_bytes(key.as_bytes()) {
                upstream_headers.insert(name, val.clone());
            }
        }
    }
    // Inject real upstream API key
    upstream_headers.insert(
        "x-api-key",
        HeaderValue::from_str(&upstream_api_key).unwrap_or_else(|_| HeaderValue::from_static("")),
    );

    let start = Instant::now();

    // Step 4: Send to upstream
    let upstream_resp = match client
        .post(&upstream_url)
        .headers(upstream_headers)
        .body(body_bytes.to_vec())
        .send()
        .await
    {
        Ok(resp) => resp,
        Err(e) => {
            error!(error = %e, upstream_url = %upstream_url, "LLM proxy: upstream request failed");
            return (StatusCode::BAD_GATEWAY, format!("Upstream error: {e}")).into_response();
        }
    };

    let upstream_status = upstream_resp.status();
    let upstream_headers = upstream_resp.headers().clone();
    let is_streaming = upstream_headers
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .map(|ct| ct.contains("text/event-stream"))
        .unwrap_or(false);

    // Build response headers
    let mut response_headers = HeaderMap::new();
    for (key, val) in &upstream_headers {
        // Forward relevant headers
        let key_str = key.as_str();
        if key_str.starts_with("content-type")
            || key_str.starts_with("anthropic-")
            || key_str.starts_with("x-ratelimit-")
            || key_str == "request-id"
            || key_str == "retry-after"
        {
            response_headers.insert(key.clone(), val.clone());
        }
    }

    if is_streaming {
        // SSE streaming: passthrough stream, capture body for metering
        let metering_url = state
            .config
            .llm_proxy_metering_url
            .clone()
            .or_else(|| state.config.control_plane_url.clone());
        let cp_api_key = state.config.control_plane_api_key.clone();
        let http_client = state.http_client.clone();

        let byte_stream = upstream_resp.bytes_stream();

        // Collect chunks for metering while streaming to client
        let (tx, rx) = tokio::sync::mpsc::channel::<Result<Vec<u8>, std::io::Error>>(64);
        let metering_tenant = tenant_id.clone();
        let metering_sub = subscription_id.clone();
        let metering_path = request_path.clone();

        // Spawn a task to forward bytes and collect them for metering
        let collected = std::sync::Arc::new(tokio::sync::Mutex::new(Vec::<u8>::new()));
        let collected_writer = collected.clone();

        tokio::spawn(async move {
            let mut stream = byte_stream;
            while let Some(chunk) = stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        collected_writer.lock().await.extend_from_slice(&bytes);
                        if tx.send(Ok(bytes.to_vec())).await.is_err() {
                            break; // Client disconnected
                        }
                    }
                    Err(e) => {
                        warn!(error = %e, "LLM proxy: stream chunk error");
                        let _ = tx.send(Err(std::io::Error::other(e.to_string()))).await;
                        break;
                    }
                }
            }
        });

        // Convert mpsc receiver to a Stream for axum
        let body_stream = tokio_stream::wrappers::ReceiverStream::new(rx);

        let body = Body::from_stream(body_stream);
        let mut response = Response::new(body);
        *response.status_mut() =
            StatusCode::from_u16(upstream_status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
        *response.headers_mut() = response_headers;

        // Spawn async metering (non-blocking, fire-and-forget)
        tokio::spawn(async move {
            // Wait a bit for stream to complete
            tokio::time::sleep(Duration::from_millis(100)).await;
            // Wait up to 5 min for the stream to finish (check every 500ms)
            for _ in 0..600 {
                tokio::time::sleep(Duration::from_millis(500)).await;
                // Try to lock — if the stream task is done, it won't hold the lock
                let data = collected.lock().await;
                if data.is_empty() {
                    continue;
                }
                // Check if the stream looks complete (ends with double newline or data: [DONE])
                let tail = String::from_utf8_lossy(&data[data.len().saturating_sub(100)..]);
                if tail.contains("data: [DONE]")
                    || tail.contains("\"stop_reason\"")
                    || tail.ends_with("\n\n")
                {
                    let elapsed = start.elapsed();
                    let body_str = String::from_utf8_lossy(&data);
                    if let Some(usage) = extract_sse_usage(&body_str) {
                        info!(
                            tenant_id = %metering_tenant,
                            subscription_id = %metering_sub,
                            input_tokens = usage.input_tokens,
                            output_tokens = usage.output_tokens,
                            latency_ms = elapsed.as_millis() as u64,
                            "LLM proxy: usage extracted from SSE stream"
                        );
                        record_usage_to_cp(&MeteringParams {
                            client: &http_client,
                            metering_url: metering_url.as_deref(),
                            api_key: cp_api_key.as_deref(),
                            tenant_id: &metering_tenant,
                            subscription_id: &metering_sub,
                            path: &metering_path,
                            usage: &usage,
                            latency_ms: elapsed.as_millis() as u64,
                        })
                        .await;
                    }
                    break;
                }
            }
        });

        response
    } else {
        // Non-streaming: read full body, extract usage, return
        let body_bytes = match upstream_resp.bytes().await {
            Ok(b) => b,
            Err(e) => {
                error!(error = %e, "LLM proxy: failed to read upstream response");
                return (StatusCode::BAD_GATEWAY, "Failed to read upstream response")
                    .into_response();
            }
        };

        let elapsed = start.elapsed();

        // Extract usage from JSON response
        if let Some(usage) = extract_json_usage(&body_bytes) {
            info!(
                tenant_id = %tenant_id,
                subscription_id = %subscription_id,
                input_tokens = usage.input_tokens,
                output_tokens = usage.output_tokens,
                latency_ms = elapsed.as_millis() as u64,
                "LLM proxy: usage extracted from response"
            );

            let metering_url = state
                .config
                .llm_proxy_metering_url
                .clone()
                .or_else(|| state.config.control_plane_url.clone());
            let cp_api_key = state.config.control_plane_api_key.clone();
            let http_client = state.http_client.clone();

            // Async metering (non-blocking)
            tokio::spawn(async move {
                record_usage_to_cp(&MeteringParams {
                    client: &http_client,
                    metering_url: metering_url.as_deref(),
                    api_key: cp_api_key.as_deref(),
                    tenant_id: &tenant_id,
                    subscription_id: &subscription_id,
                    path: &request_path,
                    usage: &usage,
                    latency_ms: elapsed.as_millis() as u64,
                })
                .await;
            });
        }

        let mut response = Response::new(Body::from(body_bytes));
        *response.status_mut() =
            StatusCode::from_u16(upstream_status.as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
        *response.headers_mut() = response_headers;
        response
    }
}

/// Extract API key from request headers (x-api-key or Authorization: Bearer).
fn extract_api_key(headers: &HeaderMap) -> Option<String> {
    // x-api-key header (Anthropic SDK style)
    if let Some(val) = headers.get("x-api-key").and_then(|v| v.to_str().ok()) {
        return Some(val.to_string());
    }
    // Authorization: Bearer (alternative)
    if let Some(val) = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
    {
        if let Some(token) = val.strip_prefix("Bearer ") {
            return Some(token.to_string());
        }
    }
    None
}

/// Token usage from Anthropic response.
#[derive(Debug, Clone)]
pub struct LlmUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
}

/// Anthropic response usage block.
#[derive(Debug, Deserialize)]
struct AnthropicUsage {
    input_tokens: u64,
    output_tokens: u64,
}

/// Anthropic response (partial — only what we need).
#[derive(Debug, Deserialize)]
struct AnthropicResponse {
    usage: Option<AnthropicUsage>,
}

/// Extract usage from a non-streaming JSON response.
fn extract_json_usage(body: &[u8]) -> Option<LlmUsage> {
    let resp: AnthropicResponse = serde_json::from_slice(body).ok()?;
    let usage = resp.usage?;
    Some(LlmUsage {
        input_tokens: usage.input_tokens,
        output_tokens: usage.output_tokens,
    })
}

/// Extract usage from SSE stream body.
///
/// Anthropic SSE streams contain a `message_delta` event with cumulative usage
/// and a final `message_stop` event. The usage is in the `message_delta` event:
/// ```text
/// event: message_delta
/// data: {"type":"message_delta","usage":{"output_tokens":42}}
/// ```
/// Or in `message_start`:
/// ```text
/// event: message_start
/// data: {"type":"message_start","message":{"usage":{"input_tokens":15,"output_tokens":0},...}}
/// ```
fn extract_sse_usage(body: &str) -> Option<LlmUsage> {
    let mut input_tokens: u64 = 0;
    let mut output_tokens: u64 = 0;

    for line in body.lines() {
        if !line.starts_with("data: ") {
            continue;
        }
        let json_str = &line[6..];
        if json_str == "[DONE]" {
            continue;
        }

        // Try to parse as a generic JSON value
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(json_str) {
            let event_type = val.get("type").and_then(|v| v.as_str()).unwrap_or("");

            match event_type {
                "message_start" => {
                    // input_tokens from message_start.message.usage
                    if let Some(msg_usage) = val.get("message").and_then(|m| m.get("usage")) {
                        if let Some(it) = msg_usage.get("input_tokens").and_then(|v| v.as_u64()) {
                            input_tokens = it;
                        }
                    }
                }
                "message_delta" => {
                    // output_tokens from message_delta.usage
                    if let Some(delta_usage) = val.get("usage") {
                        if let Some(ot) = delta_usage.get("output_tokens").and_then(|v| v.as_u64())
                        {
                            output_tokens = ot;
                        }
                    }
                }
                _ => {}
            }
        }
    }

    if input_tokens > 0 || output_tokens > 0 {
        Some(LlmUsage {
            input_tokens,
            output_tokens,
        })
    } else {
        None
    }
}

/// Parameters for usage recording.
struct MeteringParams<'a> {
    client: &'a Client,
    metering_url: Option<&'a str>,
    api_key: Option<&'a str>,
    tenant_id: &'a str,
    subscription_id: &'a str,
    path: &'a str,
    usage: &'a LlmUsage,
    latency_ms: u64,
}

/// Record usage to Control Plane API (fire-and-forget).
async fn record_usage_to_cp(params: &MeteringParams<'_>) {
    let base_url = match params.metering_url {
        Some(url) if !url.is_empty() => url,
        _ => {
            debug!("LLM proxy metering: no CP URL configured, skipping");
            return;
        }
    };

    let url = format!("{}/api/v1/usage/record", base_url);
    let total_tokens = params.usage.input_tokens + params.usage.output_tokens;

    let payload = serde_json::json!({
        "tenant_id": params.tenant_id,
        "subscription_id": params.subscription_id,
        "endpoint": params.path,
        "request_count": 1,
        "total_tokens": total_tokens,
        "input_tokens": params.usage.input_tokens,
        "output_tokens": params.usage.output_tokens,
        "total_latency_ms": params.latency_ms,
    });

    let mut req = params.client.post(&url).json(&payload);
    if let Some(key) = params.api_key {
        req = req.header("X-API-Key", key);
    }

    match req.timeout(Duration::from_secs(5)).send().await {
        Ok(resp) if resp.status().is_success() => {
            debug!(tenant_id = %params.tenant_id, total_tokens, "Usage recorded to CP");
        }
        Ok(resp) => {
            warn!(
                status = resp.status().as_u16(),
                tenant_id = %params.tenant_id,
                "Usage recording failed (non-2xx)"
            );
        }
        Err(e) => {
            warn!(error = %e, "Usage recording request failed");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_json_usage() {
        let body = br#"{"id":"msg_01","type":"message","role":"assistant","content":[{"type":"text","text":"Hello"}],"model":"claude-sonnet-4-20250514","usage":{"input_tokens":10,"output_tokens":25}}"#;
        let usage = extract_json_usage(body).unwrap();
        assert_eq!(usage.input_tokens, 10);
        assert_eq!(usage.output_tokens, 25);
    }

    #[test]
    fn test_extract_json_usage_no_usage() {
        let body = br#"{"error":{"type":"invalid_request_error","message":"bad"}}"#;
        assert!(extract_json_usage(body).is_none());
    }

    #[test]
    fn test_extract_sse_usage() {
        let body = r#"event: message_start
data: {"type":"message_start","message":{"id":"msg_01","type":"message","role":"assistant","content":[],"model":"claude-sonnet-4-20250514","usage":{"input_tokens":42,"output_tokens":0}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}

event: message_stop
data: {"type":"message_stop"}

"#;
        let usage = extract_sse_usage(body).unwrap();
        assert_eq!(usage.input_tokens, 42);
        assert_eq!(usage.output_tokens, 15);
    }

    #[test]
    fn test_extract_sse_usage_empty() {
        let body = "event: ping\ndata: {}\n\n";
        assert!(extract_sse_usage(body).is_none());
    }

    #[test]
    fn test_extract_api_key_from_x_api_key() {
        let mut headers = HeaderMap::new();
        headers.insert("x-api-key", HeaderValue::from_static("stoa_sk_test123"));
        let key = extract_api_key(&headers).unwrap();
        assert_eq!(key, "stoa_sk_test123");
    }

    #[test]
    fn test_extract_api_key_from_bearer() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer stoa_sk_test456"),
        );
        let key = extract_api_key(&headers).unwrap();
        assert_eq!(key, "stoa_sk_test456");
    }

    #[test]
    fn test_extract_api_key_missing() {
        let headers = HeaderMap::new();
        assert!(extract_api_key(&headers).is_none());
    }
}
