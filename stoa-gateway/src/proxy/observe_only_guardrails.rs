use axum::{
    body::{to_bytes, Body},
    extract::Request,
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
};
use serde_json::Value;
use tracing::{debug, warn};

use crate::{
    guardrails::{
        ContentFilter, ContentFilterOutcome, GuardrailsConfig, InjectionScanner, PiiScanner,
        PromptGuard, PromptGuardAction, PromptGuardOutcome,
    },
    metrics,
    state::AppState,
};

const MAX_OBSERVE_ONLY_GUARDRAIL_BODY_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum GuardrailBodySkipReason {
    NonJson,
    Oversized,
    Streaming,
    InvalidJson,
}

#[derive(Debug, Clone)]
pub(crate) enum GuardrailBodyApplicability {
    Applicable(Value),
    Skipped(GuardrailBodySkipReason),
}

pub(crate) fn resolve_guardrails_config(
    state: &AppState,
    tenant_id: Option<&str>,
) -> GuardrailsConfig {
    let global = GuardrailsConfig {
        pii_enabled: state.config.guardrails_pii_enabled,
        pii_redact: state.config.guardrails_pii_redact,
        injection_enabled: state.config.guardrails_injection_enabled,
        content_filter_enabled: state.config.guardrails_content_filter_enabled,
        prompt_guard_enabled: state.config.prompt_guard_enabled,
        prompt_guard_action: state.config.prompt_guard_action,
    };

    tenant_id
        .map(|tenant| state.guardrail_policy_store.resolve(tenant, &global))
        .unwrap_or(global)
}

pub(crate) async fn buffer_json_request_for_observe_only(
    request: Request<Body>,
) -> Result<(Request<Body>, GuardrailBodyApplicability), Response> {
    if !is_json_content_type(request.headers()) {
        return Ok((request, skipped(GuardrailBodySkipReason::NonJson)));
    }

    let Some(content_len) = content_length(request.headers()) else {
        return Ok((request, skipped(GuardrailBodySkipReason::Streaming)));
    };

    if content_len > MAX_OBSERVE_ONLY_GUARDRAIL_BODY_BYTES {
        return Ok((request, skipped(GuardrailBodySkipReason::Oversized)));
    }

    let (parts, body) = request.into_parts();
    let bytes = match to_bytes(body, MAX_OBSERVE_ONLY_GUARDRAIL_BODY_BYTES).await {
        Ok(bytes) => bytes,
        Err(error) => {
            warn!(
                error = %error,
                "Failed to buffer JSON request body for observe-only guardrails"
            );
            return Err((StatusCode::BAD_REQUEST, "Failed to read request body").into_response());
        }
    };
    let applicability = classify_buffered_json_body(&parts.headers, &bytes);
    Ok((Request::from_parts(parts, Body::from(bytes)), applicability))
}

pub(crate) fn classify_buffered_json_body(
    headers: &HeaderMap,
    body: &[u8],
) -> GuardrailBodyApplicability {
    if !is_json_content_type(headers) {
        return skipped(GuardrailBodySkipReason::NonJson);
    }
    if body.len() > MAX_OBSERVE_ONLY_GUARDRAIL_BODY_BYTES {
        return skipped(GuardrailBodySkipReason::Oversized);
    }

    match serde_json::from_slice::<Value>(body) {
        Ok(value) => GuardrailBodyApplicability::Applicable(value),
        Err(_) => skipped(GuardrailBodySkipReason::InvalidJson),
    }
}

fn skipped(reason: GuardrailBodySkipReason) -> GuardrailBodyApplicability {
    GuardrailBodyApplicability::Skipped(reason)
}

pub(crate) fn record_observe_only_guardrails(
    surface: &str,
    config: &GuardrailsConfig,
    body: &GuardrailBodyApplicability,
    rate_limit_evaluated: bool,
) {
    let GuardrailBodyApplicability::Applicable(value) = body else {
        if let GuardrailBodyApplicability::Skipped(reason) = body {
            without_guardrail_counter_increment(surface, *reason);
        }
        return;
    };

    if config.prompt_guard_enabled {
        let decision = match PromptGuard::scan(value, config.prompt_guard_action) {
            PromptGuardOutcome::Detected {
                action: PromptGuardAction::Block,
                ..
            } => "block",
            PromptGuardOutcome::Detected { .. } | PromptGuardOutcome::Pass => "allow",
        };
        record_decision(surface, "prompt_guard", decision);
    }

    if config.injection_enabled {
        let decision = if InjectionScanner::scan(value).is_some() {
            "block"
        } else {
            "allow"
        };
        record_decision(surface, "injection", decision);
    }

    if config.pii_enabled {
        let decision = match PiiScanner::scan(value) {
            (true, _) if config.pii_redact => "redact",
            (true, _) => "block",
            (false, _) => "allow",
        };
        record_decision(surface, "pii", decision);
    }

    if config.content_filter_enabled {
        let decision = match ContentFilter::scan(value) {
            ContentFilterOutcome::Blocked { .. } => "block",
            ContentFilterOutcome::Sensitive { .. } | ContentFilterOutcome::Pass => "allow",
        };
        record_decision(surface, "content_filter", decision);
    }

    if rate_limit_evaluated {
        record_decision(surface, "rate_limit", "allow");
    }
}

fn without_guardrail_counter_increment(surface: &str, reason: GuardrailBodySkipReason) {
    debug!(surface, reason = ?reason, "without_guardrail_counter_increment");
}

fn record_decision(surface: &str, guardrail: &str, decision: &str) {
    metrics::record_guardrail_evaluation("proxy", surface, guardrail);
    metrics::record_guardrail_decision("proxy", surface, guardrail, decision);
}

fn is_json_content_type(headers: &HeaderMap) -> bool {
    headers
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(';').next())
        .map(|mime| {
            let mime = mime.trim().to_ascii_lowercase();
            mime == "application/json" || mime.ends_with("+json")
        })
        .unwrap_or(false)
}

fn content_length(headers: &HeaderMap) -> Option<usize> {
    headers
        .get(header::CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<usize>().ok())
}

#[cfg(test)]
mod tests {
    use axum::http::Request as HttpRequest;

    use super::*;
    use crate::guardrails::PromptGuardAction;

    #[tokio::test]
    async fn observe_only_records_valid_json_and_preserves_streaming_body() {
        crate::metrics::init_all_metrics();
        let mut headers = HeaderMap::new();
        headers.insert(header::CONTENT_TYPE, "application/json".parse().unwrap());
        let raw = br#"{"message":"contact jane@example.com"}"#;
        let body = classify_buffered_json_body(&headers, raw);
        let config = GuardrailsConfig {
            pii_enabled: true,
            pii_redact: true,
            injection_enabled: true,
            content_filter_enabled: true,
            prompt_guard_enabled: true,
            prompt_guard_action: PromptGuardAction::Block,
        };
        let counter = crate::metrics::GUARDRAILS_DECISIONS_TOTAL.with_label_values(&[
            "proxy",
            "api_proxy",
            "pii",
            "redact",
        ]);
        let before = counter.get();

        record_observe_only_guardrails("api_proxy", &config, &body, false);

        assert_eq!(counter.get() - before, 1.0);

        let request = HttpRequest::builder()
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(r#"{"message":"hello"}"#))
            .unwrap();

        let (request, applicability) = buffer_json_request_for_observe_only(request).await.unwrap();

        assert!(matches!(
            applicability,
            GuardrailBodyApplicability::Skipped(GuardrailBodySkipReason::Streaming)
        ));
        let body = to_bytes(request.into_body(), 1024).await.unwrap();
        assert_eq!(&body[..], br#"{"message":"hello"}"#);
    }
}
