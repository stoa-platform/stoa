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

/// Proxy handler for POST /v1/messages, /v1/messages/count_tokens, /v1/chat/completions.
///
/// Flow:
/// 1. Detect API format from request path (Anthropic vs OpenAI-compatible)
/// 2. Extract and validate STOA API key (X-API-Key or Authorization: Bearer)
/// 3. Replace auth with real upstream API key (format-aware header injection)
/// 4. Forward request to upstream (provider-aware URL routing)
/// 5. Stream response back to client
/// 6. Async: extract token usage (format-aware) and POST to CP API for metering
pub async fn llm_proxy_handler(State(state): State<AppState>, request: Request<Body>) -> Response {
    if !state.config.llm_proxy_enabled {
        return (StatusCode::NOT_FOUND, "LLM proxy not enabled").into_response();
    }

    // Step 0: Detect API format from request path
    let request_path = request.uri().path().to_string();
    let api_format = LlmApiFormat::from_path(&request_path);

    // Step 1: Extract consumer API key from request
    let consumer_key = extract_api_key(request.headers());
    let consumer_key = match consumer_key {
        Some(key) => key,
        None => {
            return (
                StatusCode::UNAUTHORIZED,
                "Missing API key (x-api-key or Authorization: Bearer header required)",
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
        format = ?api_format,
        "LLM proxy: consumer authenticated"
    );

    // Step 3: Resolve upstream — subscription-aware Azure routing or static fallback (CAB-1615)
    let resolved = resolve_upstream(&state, api_format, &subscription_id, &request_path);
    let (upstream_url, upstream_headers_preset) = match resolved {
        UpstreamResolution::Azure { url, headers } => (url, Some(headers)),
        UpstreamResolution::Static { url, api_key } => {
            (url, None::<Vec<(String, String)>>)
            // api_key is consumed below when building headers
        }
        UpstreamResolution::Error(msg) => {
            return (StatusCode::SERVICE_UNAVAILABLE, msg).into_response();
        }
    };

    // Re-resolve the static API key for header building (only when not Azure-routed)
    let static_api_key = if upstream_headers_preset.is_none() {
        let key = match api_format {
            LlmApiFormat::OpenAiCompat => state
                .config
                .llm_proxy_mistral_api_key
                .clone()
                .or_else(|| state.config.llm_proxy_api_key.clone()),
            LlmApiFormat::Anthropic => state.config.llm_proxy_api_key.clone(),
        };
        match key {
            Some(k) if !k.is_empty() => Some(k),
            _ => {
                error!("LLM proxy: upstream API key not configured");
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    "LLM proxy upstream not configured",
                )
                    .into_response();
            }
        }
    } else {
        None // Azure route already has headers with api-key
    };

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

    // Build upstream headers (format-aware)
    let mut upstream_headers = HeaderMap::new();
    if let Some(azure_headers) = upstream_headers_preset {
        // Azure-routed: use pre-built headers from transform_request
        for (key, val) in &azure_headers {
            if let (Ok(name), Ok(value)) = (
                header::HeaderName::from_bytes(key.as_bytes()),
                HeaderValue::from_str(val),
            ) {
                upstream_headers.insert(name, value);
            }
        }
    } else {
        // Static routing: build headers based on API format
        let api_key = static_api_key.as_deref().unwrap_or("");
        match api_format {
            LlmApiFormat::Anthropic => {
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
                upstream_headers.insert(
                    "x-api-key",
                    HeaderValue::from_str(api_key)
                        .unwrap_or_else(|_| HeaderValue::from_static("")),
                );
            }
            LlmApiFormat::OpenAiCompat => {
                for key in &["content-type", "accept"] {
                    if let Some(val) = parts.headers.get(*key) {
                        if let Ok(name) = header::HeaderName::from_bytes(key.as_bytes()) {
                            upstream_headers.insert(name, val.clone());
                        }
                    }
                }
                let bearer = format!("Bearer {}", api_key);
                upstream_headers.insert(
                    header::AUTHORIZATION,
                    HeaderValue::from_str(&bearer)
                        .unwrap_or_else(|_| HeaderValue::from_static("Bearer ")),
                );
            }
        }
    }

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

    // Build response headers (forward relevant headers from upstream response)
    let mut response_headers = HeaderMap::new();
    for (key, val) in &upstream_headers {
        let key_str = key.as_str();
        if key_str.starts_with("content-type")
            || key_str.starts_with("anthropic-")
            || key_str.starts_with("x-ratelimit-")
            || key_str == "request-id"
            || key_str == "retry-after"
            // OpenAI-compatible headers
            || key_str == "x-request-id"
            || key_str.starts_with("openai-")
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

/// Resolved upstream target — either Azure (subscription-routed) or static (config-based).
#[derive(Debug)]
enum UpstreamResolution {
    /// Azure OpenAI: custom URL + api-key headers from transform_request.
    Azure {
        url: String,
        headers: Vec<(String, String)>,
    },
    /// Static routing: base_url + request_path, API key resolved separately.
    Static {
        url: String,
        api_key: Option<String>,
    },
    /// Configuration error — return to caller as SERVICE_UNAVAILABLE.
    Error(String),
}

/// Resolve the upstream URL and auth for a request (CAB-1615).
///
/// Priority:
/// 1. If LLM router is enabled and subscription has a mapping → Azure transform
/// 2. Else → static config (Mistral or Anthropic upstream)
fn resolve_upstream(
    state: &AppState,
    api_format: LlmApiFormat,
    subscription_id: &str,
    request_path: &str,
) -> UpstreamResolution {
    // Try subscription-aware routing for OpenAI-compatible requests
    if api_format == LlmApiFormat::OpenAiCompat {
        if let Some(ref router) = state.llm_router {
            let mapping = &state.config.llm_router.subscription_mapping;
            if !mapping.is_empty() {
                if let Some(provider) = router.select_for_subscription(subscription_id, mapping) {
                    // Azure OpenAI provider — use transform_request for URL + headers
                    if provider.provider == crate::llm::LlmProvider::AzureOpenAi {
                        match crate::llm::transform_request(provider) {
                            Ok(azure_req) => {
                                info!(
                                    subscription_id = %subscription_id,
                                    backend_id = ?provider.backend_id,
                                    url = %azure_req.url,
                                    "LLM proxy: subscription routed to Azure OpenAI"
                                );
                                return UpstreamResolution::Azure {
                                    url: azure_req.url,
                                    headers: azure_req.headers,
                                };
                            }
                            Err(e) => {
                                error!(
                                    error = %e,
                                    subscription_id = %subscription_id,
                                    backend_id = ?provider.backend_id,
                                    "LLM proxy: Azure transform failed"
                                );
                                return UpstreamResolution::Error(format!(
                                    "Azure OpenAI configuration error: {e}"
                                ));
                            }
                        }
                    }
                    // Non-Azure provider from router — use its base_url with standard path
                    let url = format!(
                        "{}{}",
                        provider.base_url.trim_end_matches('/'),
                        request_path
                    );
                    let api_key = provider
                        .api_key_env
                        .as_deref()
                        .and_then(|env| std::env::var(env).ok());
                    return UpstreamResolution::Static { url, api_key };
                }
                // Subscription not in mapping — fall through to static routing
                debug!(
                    subscription_id = %subscription_id,
                    "LLM proxy: subscription not in routing map, using static upstream"
                );
            }
        }
    }

    // Static routing fallback
    let (base_url, api_key) = match api_format {
        LlmApiFormat::OpenAiCompat => {
            let key = state
                .config
                .llm_proxy_mistral_api_key
                .clone()
                .or_else(|| state.config.llm_proxy_api_key.clone());
            let url = if state.config.llm_proxy_mistral_api_key.is_some() {
                state.config.llm_proxy_mistral_upstream_url.clone()
            } else {
                state.config.llm_proxy_upstream_url.clone()
            };
            (url, key)
        }
        LlmApiFormat::Anthropic => (
            state.config.llm_proxy_upstream_url.clone(),
            state.config.llm_proxy_api_key.clone(),
        ),
    };

    let url = format!("{}{}", base_url.trim_end_matches('/'), request_path);
    UpstreamResolution::Static { url, api_key }
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

/// OpenAI-compatible response usage block (used by Mistral, OpenAI, vLLM, etc.).
#[derive(Debug, Deserialize)]
struct OpenAiUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
}

/// OpenAI-compatible response (partial — only what we need).
#[derive(Debug, Deserialize)]
struct OpenAiResponse {
    usage: Option<OpenAiUsage>,
}

/// API format detected from request path or configuration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LlmApiFormat {
    /// Anthropic: /v1/messages, x-api-key header, AnthropicResponse schema.
    Anthropic,
    /// OpenAI-compatible: /v1/chat/completions, Authorization: Bearer, OpenAiResponse schema.
    OpenAiCompat,
}

impl LlmApiFormat {
    /// Detect API format from request path.
    pub fn from_path(path: &str) -> Self {
        if path.starts_with("/v1/chat/completions") {
            LlmApiFormat::OpenAiCompat
        } else {
            // Default to Anthropic for /v1/messages and other paths
            LlmApiFormat::Anthropic
        }
    }
}

/// Extract usage from a non-streaming JSON response.
///
/// Tries Anthropic format first (`usage.input_tokens/output_tokens`),
/// then falls back to OpenAI-compatible format (`usage.prompt_tokens/completion_tokens`).
fn extract_json_usage(body: &[u8]) -> Option<LlmUsage> {
    // Try Anthropic format first
    if let Ok(resp) = serde_json::from_slice::<AnthropicResponse>(body) {
        if let Some(usage) = resp.usage {
            return Some(LlmUsage {
                input_tokens: usage.input_tokens,
                output_tokens: usage.output_tokens,
            });
        }
    }

    // Fallback to OpenAI-compatible format (Mistral, OpenAI, vLLM, etc.)
    if let Ok(resp) = serde_json::from_slice::<OpenAiResponse>(body) {
        if let Some(usage) = resp.usage {
            return Some(LlmUsage {
                input_tokens: usage.prompt_tokens,
                output_tokens: usage.completion_tokens,
            });
        }
    }

    None
}

/// Extract usage from SSE stream body.
///
/// Supports two SSE formats:
///
/// **Anthropic SSE** — usage split across events:
/// ```text
/// event: message_start
/// data: {"type":"message_start","message":{"usage":{"input_tokens":15,"output_tokens":0},...}}
///
/// event: message_delta
/// data: {"type":"message_delta","usage":{"output_tokens":42}}
/// ```
///
/// **OpenAI-compatible SSE** (Mistral, OpenAI, vLLM) — usage in final chunk:
/// ```text
/// data: {"choices":[...],"usage":{"prompt_tokens":10,"completion_tokens":25}}
///
/// data: [DONE]
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
                // Anthropic SSE format
                "message_start" => {
                    if let Some(msg_usage) = val.get("message").and_then(|m| m.get("usage")) {
                        if let Some(it) = msg_usage.get("input_tokens").and_then(|v| v.as_u64()) {
                            input_tokens = it;
                        }
                    }
                }
                "message_delta" => {
                    if let Some(delta_usage) = val.get("usage") {
                        if let Some(ot) = delta_usage.get("output_tokens").and_then(|v| v.as_u64())
                        {
                            output_tokens = ot;
                        }
                    }
                }
                _ => {
                    // OpenAI-compatible SSE format: usage in final chunk
                    // (no "type" field, but has "usage.prompt_tokens")
                    if let Some(usage) = val.get("usage") {
                        if let Some(pt) = usage.get("prompt_tokens").and_then(|v| v.as_u64()) {
                            input_tokens = pt;
                        }
                        if let Some(ct) = usage.get("completion_tokens").and_then(|v| v.as_u64()) {
                            output_tokens = ct;
                        }
                    }
                }
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

    // --- OpenAI-compatible format tests (Mistral, OpenAI, vLLM) ---

    #[test]
    fn test_extract_json_usage_openai_format() {
        let body = br#"{"id":"chatcmpl-abc","object":"chat.completion","model":"mistral-small-latest","choices":[{"index":0,"message":{"role":"assistant","content":"Hello"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":25,"total_tokens":35}}"#;
        let usage = extract_json_usage(body).unwrap();
        assert_eq!(usage.input_tokens, 10);
        assert_eq!(usage.output_tokens, 25);
    }

    #[test]
    fn test_extract_json_usage_mistral_format() {
        // Mistral uses the exact same format as OpenAI
        let body = br#"{"id":"cmpl-123","object":"chat.completion","model":"mistral-7b","choices":[{"index":0,"message":{"role":"assistant","content":"Test"},"finish_reason":"stop"}],"usage":{"prompt_tokens":8,"completion_tokens":12,"total_tokens":20}}"#;
        let usage = extract_json_usage(body).unwrap();
        assert_eq!(usage.input_tokens, 8);
        assert_eq!(usage.output_tokens, 12);
    }

    #[test]
    fn test_extract_json_usage_tries_both_formats() {
        // Anthropic format should be tried first and succeed
        let anthropic_body = br#"{"usage":{"input_tokens":5,"output_tokens":10}}"#;
        let usage = extract_json_usage(anthropic_body).unwrap();
        assert_eq!(usage.input_tokens, 5);
        assert_eq!(usage.output_tokens, 10);

        // OpenAI format should work as fallback
        let openai_body = br#"{"usage":{"prompt_tokens":7,"completion_tokens":14}}"#;
        let usage = extract_json_usage(openai_body).unwrap();
        assert_eq!(usage.input_tokens, 7);
        assert_eq!(usage.output_tokens, 14);
    }

    #[test]
    fn test_extract_sse_usage_openai_format() {
        let body = "data: {\"id\":\"chatcmpl-1\",\"choices\":[{\"delta\":{\"content\":\"Hi\"}}]}\n\ndata: {\"id\":\"chatcmpl-1\",\"choices\":[],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":25,\"total_tokens\":35}}\n\ndata: [DONE]\n\n";
        let usage = extract_sse_usage(body).unwrap();
        assert_eq!(usage.input_tokens, 10);
        assert_eq!(usage.output_tokens, 25);
    }

    #[test]
    fn test_extract_sse_usage_openai_no_usage_chunk() {
        // Stream without a usage chunk (some providers don't include it)
        let body = "data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n\ndata: [DONE]\n\n";
        assert!(extract_sse_usage(body).is_none());
    }

    #[test]
    fn test_api_format_from_path() {
        assert_eq!(
            LlmApiFormat::from_path("/v1/messages"),
            LlmApiFormat::Anthropic
        );
        assert_eq!(
            LlmApiFormat::from_path("/v1/messages/count_tokens"),
            LlmApiFormat::Anthropic
        );
        assert_eq!(
            LlmApiFormat::from_path("/v1/chat/completions"),
            LlmApiFormat::OpenAiCompat
        );
        // Unknown paths default to Anthropic
        assert_eq!(
            LlmApiFormat::from_path("/v1/unknown"),
            LlmApiFormat::Anthropic
        );
    }

    // --- Subscription-aware routing tests (CAB-1615) ---

    /// Build a minimal AppState for resolve_upstream tests.
    fn make_test_state(
        router_enabled: bool,
        providers: Vec<crate::llm::ProviderConfig>,
        subscription_mapping: crate::llm::SubscriptionMapping,
    ) -> AppState {
        let mut config = crate::config::Config::default();
        config.llm_proxy_enabled = true;
        config.llm_proxy_upstream_url = "https://api.anthropic.com".to_string();
        config.llm_proxy_mistral_upstream_url = "https://api.mistral.ai".to_string();
        config.llm_router.enabled = router_enabled;
        config.llm_router.providers = providers;
        config.llm_router.subscription_mapping = subscription_mapping;
        AppState::new(config)
    }

    fn make_azure_provider(backend_id: &str, deployment: &str) -> crate::llm::ProviderConfig {
        crate::llm::ProviderConfig {
            provider: crate::llm::LlmProvider::AzureOpenAi,
            backend_id: Some(backend_id.to_string()),
            base_url: "https://test-ns.openai.azure.com".to_string(),
            api_key_env: Some("TEST_AZURE_KEY".to_string()),
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: 5.0,
            cost_per_1m_output: 15.0,
            priority: 1,
            deployment: Some(deployment.to_string()),
            api_version: Some("2024-10-21".to_string()),
        }
    }

    fn make_openai_provider(backend_id: &str) -> crate::llm::ProviderConfig {
        crate::llm::ProviderConfig {
            provider: crate::llm::LlmProvider::OpenAi,
            backend_id: Some(backend_id.to_string()),
            base_url: "https://api.openai.com/v1".to_string(),
            api_key_env: Some("TEST_OPENAI_KEY".to_string()),
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: 5.0,
            cost_per_1m_output: 15.0,
            priority: 1,
            deployment: None,
            api_version: None,
        }
    }

    #[test]
    fn resolve_upstream_azure_subscription_routing() {
        // Set the Azure API key env var for transform_request
        std::env::set_var("TEST_AZURE_KEY", "test-azure-api-key-12345");

        let provider = make_azure_provider("projet-alpha", "gpt-4o");
        let mapping = crate::llm::SubscriptionMapping::from_pairs(vec![(
            "sub-123".to_string(),
            "projet-alpha".to_string(),
        )]);

        let state = make_test_state(true, vec![provider], mapping);

        let result =
            resolve_upstream(&state, LlmApiFormat::OpenAiCompat, "sub-123", "/v1/chat/completions");

        match result {
            UpstreamResolution::Azure { url, headers } => {
                assert!(
                    url.contains("test-ns.openai.azure.com"),
                    "URL should target Azure: {url}"
                );
                assert!(
                    url.contains("deployments/gpt-4o"),
                    "URL should contain deployment: {url}"
                );
                assert!(
                    url.contains("api-version=2024-10-21"),
                    "URL should have api-version: {url}"
                );
                // Verify api-key header is present
                let has_api_key = headers.iter().any(|(k, _)| k == "api-key");
                assert!(has_api_key, "Should have api-key header");
            }
            other => panic!("Expected Azure resolution, got: {other:?}"),
        }

        std::env::remove_var("TEST_AZURE_KEY");
    }

    #[test]
    fn resolve_upstream_static_fallback_no_mapping() {
        let provider = make_azure_provider("projet-alpha", "gpt-4o");
        // Empty mapping — no subscriptions configured
        let mapping = crate::llm::SubscriptionMapping::new();

        let state = make_test_state(true, vec![provider], mapping);

        let result = resolve_upstream(
            &state,
            LlmApiFormat::OpenAiCompat,
            "sub-unknown",
            "/v1/chat/completions",
        );

        match result {
            UpstreamResolution::Static { url, .. } => {
                // Falls through to static because mapping is empty
                assert!(
                    url.contains("/v1/chat/completions"),
                    "URL should contain path: {url}"
                );
            }
            other => panic!("Expected Static resolution, got: {other:?}"),
        }
    }

    #[test]
    fn resolve_upstream_static_for_anthropic_format() {
        let provider = make_azure_provider("projet-alpha", "gpt-4o");
        let mapping = crate::llm::SubscriptionMapping::from_pairs(vec![(
            "sub-123".to_string(),
            "projet-alpha".to_string(),
        )]);

        let state = make_test_state(true, vec![provider], mapping);

        // Anthropic format should ALWAYS use static routing (Azure is OpenAI-compat only)
        let result =
            resolve_upstream(&state, LlmApiFormat::Anthropic, "sub-123", "/v1/messages");

        match result {
            UpstreamResolution::Static { url, .. } => {
                assert!(
                    url.contains("api.anthropic.com"),
                    "Anthropic should use static upstream: {url}"
                );
            }
            other => panic!("Expected Static resolution for Anthropic, got: {other:?}"),
        }
    }

    #[test]
    fn resolve_upstream_non_azure_provider_from_router() {
        let provider = make_openai_provider("openai-main");
        let mapping = crate::llm::SubscriptionMapping::from_pairs(vec![(
            "sub-oai".to_string(),
            "openai-main".to_string(),
        )]);

        let state = make_test_state(true, vec![provider], mapping);

        let result = resolve_upstream(
            &state,
            LlmApiFormat::OpenAiCompat,
            "sub-oai",
            "/v1/chat/completions",
        );

        match result {
            UpstreamResolution::Static { url, .. } => {
                assert!(
                    url.contains("api.openai.com"),
                    "Non-Azure provider should use base_url: {url}"
                );
                assert!(
                    url.contains("/v1/chat/completions"),
                    "Should append request path: {url}"
                );
            }
            other => panic!("Expected Static resolution for non-Azure provider, got: {other:?}"),
        }
    }

    #[test]
    fn resolve_upstream_router_disabled() {
        let provider = make_azure_provider("projet-alpha", "gpt-4o");
        let mapping = crate::llm::SubscriptionMapping::from_pairs(vec![(
            "sub-123".to_string(),
            "projet-alpha".to_string(),
        )]);

        // Router disabled — should fall through to static
        let state = make_test_state(false, vec![provider], mapping);

        let result = resolve_upstream(
            &state,
            LlmApiFormat::OpenAiCompat,
            "sub-123",
            "/v1/chat/completions",
        );

        match result {
            UpstreamResolution::Static { url, .. } => {
                // Should NOT hit Azure even though mapping exists, because router is disabled
                assert!(
                    !url.contains("azure"),
                    "Should not route to Azure when disabled: {url}"
                );
            }
            other => panic!("Expected Static when router disabled, got: {other:?}"),
        }
    }

    #[test]
    fn resolve_upstream_azure_missing_api_key() {
        // Do NOT set TEST_AZURE_MISSING env var — it should fail
        std::env::remove_var("TEST_AZURE_MISSING");

        let mut provider = make_azure_provider("projet-beta", "gpt-4o");
        provider.api_key_env = Some("TEST_AZURE_MISSING".to_string());

        let mapping = crate::llm::SubscriptionMapping::from_pairs(vec![(
            "sub-beta".to_string(),
            "projet-beta".to_string(),
        )]);

        let state = make_test_state(true, vec![provider], mapping);

        let result = resolve_upstream(
            &state,
            LlmApiFormat::OpenAiCompat,
            "sub-beta",
            "/v1/chat/completions",
        );

        match result {
            UpstreamResolution::Error(msg) => {
                assert!(
                    msg.contains("Azure OpenAI"),
                    "Error should mention Azure: {msg}"
                );
            }
            other => panic!("Expected Error for missing API key, got: {other:?}"),
        }
    }
}
