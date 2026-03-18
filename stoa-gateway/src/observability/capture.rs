//! Snapshot Capture — Header masking, body masking, snapshot assembly (CAB-1645)
//!
//! All masking happens at capture time so stored data is always PII-safe.

use std::collections::HashMap;
use std::time::Instant;

use axum::http::HeaderMap;
use regex::Regex;

use crate::guardrails::PiiScanner;

use super::snapshot::ErrorSnapshot;

/// Headers that are always redacted (case-insensitive check).
const SENSITIVE_HEADERS: &[&str] = &[
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
];

/// Mask sensitive headers from a HeaderMap.
///
/// Sensitive headers (auth, cookies) are replaced with `[REDACTED]`.
/// Extra patterns are applied to header values.
pub fn mask_headers(headers: &HeaderMap, extra_patterns: &[Regex]) -> HashMap<String, String> {
    let mut result = HashMap::new();
    for (name, value) in headers.iter() {
        let name_lower = name.as_str().to_lowercase();
        let val_str = value.to_str().unwrap_or("[non-utf8]");

        if SENSITIVE_HEADERS.contains(&name_lower.as_str()) {
            result.insert(name_lower, "[REDACTED]".to_string());
        } else {
            let mut masked = val_str.to_string();
            for pattern in extra_patterns {
                masked = pattern.replace_all(&masked, "[REDACTED]").to_string();
            }
            result.insert(name_lower, masked);
        }
    }
    result
}

/// Mask a body excerpt with PII redaction.
///
/// 1. Truncate to max_bytes
/// 2. Convert to UTF-8 (lossy)
/// 3. If valid JSON → PiiScanner::scan (recursive redaction)
/// 4. If plain text → redact_text
///
/// Returns (masked_excerpt, pii_found).
pub fn mask_body_excerpt(
    bytes: &[u8],
    max_bytes: usize,
    extra_patterns: &[Regex],
) -> (Option<String>, bool) {
    if bytes.is_empty() {
        return (None, false);
    }

    let truncated = if bytes.len() > max_bytes {
        &bytes[..max_bytes]
    } else {
        bytes
    };

    let text = String::from_utf8_lossy(truncated);

    // Try JSON parsing for structured PII scanning
    if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&text) {
        let (pii_found, redacted) = PiiScanner::scan(&json_val);
        let mut result = serde_json::to_string(&redacted).unwrap_or_else(|_| text.to_string());

        // Apply extra patterns
        let extra_pii = apply_extra_patterns(&mut result, extra_patterns);

        return (Some(result), pii_found || extra_pii);
    }

    // Plain text: use redact_text
    let (pii_found, mut redacted) = redact_text(&text);
    let extra_pii = apply_extra_patterns(&mut redacted, extra_patterns);

    (Some(redacted), pii_found || extra_pii)
}

/// Apply extra PII patterns to a string. Returns true if any matched.
fn apply_extra_patterns(text: &mut String, patterns: &[Regex]) -> bool {
    let mut found = false;
    for pattern in patterns {
        if pattern.is_match(text) {
            found = true;
            *text = pattern.replace_all(text, "[REDACTED]").to_string();
        }
    }
    found
}

/// Redact PII from plain text using the same patterns as PiiScanner.
///
/// Public wrapper over the PiiScanner's internal string redaction logic.
pub fn redact_text(s: &str) -> (bool, String) {
    // Use PiiScanner::scan on a JSON string value to reuse the same logic
    let val = serde_json::Value::String(s.to_string());
    let (found, redacted) = PiiScanner::scan(&val);
    let result = redacted.as_str().unwrap_or(s).to_string();
    (found, result)
}

/// Input for building an error snapshot.
pub struct SnapshotInput<'a> {
    pub request_id: String,
    pub method: String,
    pub path: String,
    pub status_code: u16,
    pub error_category: String,
    pub duration_ms: f64,
    pub request_headers: &'a HeaderMap,
    pub request_body: &'a [u8],
    pub response_headers: &'a HeaderMap,
    pub response_body: &'a [u8],
    pub max_body_bytes: usize,
    pub extra_patterns: &'a [Regex],
}

/// Build a complete ErrorSnapshot from request/response data.
pub fn build_snapshot(input: SnapshotInput<'_>) -> ErrorSnapshot {
    let masked_req_headers = mask_headers(input.request_headers, input.extra_patterns);
    let masked_resp_headers = mask_headers(input.response_headers, input.extra_patterns);

    let (req_excerpt, req_pii) = mask_body_excerpt(
        input.request_body,
        input.max_body_bytes,
        input.extra_patterns,
    );
    let (resp_excerpt, resp_pii) = mask_body_excerpt(
        input.response_body,
        input.max_body_bytes,
        input.extra_patterns,
    );

    ErrorSnapshot {
        request_id: input.request_id,
        captured_at: Some(Instant::now()),
        timestamp: chrono::Utc::now().to_rfc3339(),
        method: input.method,
        path: input.path,
        status_code: input.status_code,
        error_category: input.error_category,
        duration_ms: input.duration_ms,
        request_headers: masked_req_headers,
        request_body_excerpt: req_excerpt,
        response_headers: masked_resp_headers,
        response_body_excerpt: resp_excerpt,
        pii_found: req_pii || resp_pii,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, HeaderValue};

    #[test]
    fn mask_headers_redacts_auth() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "authorization",
            HeaderValue::from_static("Bearer secret123"),
        );
        headers.insert("content-type", HeaderValue::from_static("application/json"));
        headers.insert("cookie", HeaderValue::from_static("session=abc"));

        let masked = mask_headers(&headers, &[]);
        assert_eq!(masked["authorization"], "[REDACTED]");
        assert_eq!(masked["cookie"], "[REDACTED]");
        assert_eq!(masked["content-type"], "application/json");
    }

    #[test]
    fn mask_headers_applies_extra_patterns() {
        let mut headers = HeaderMap::new();
        headers.insert("x-custom", HeaderValue::from_static("token-abc123"));

        let pattern = Regex::new(r"token-\w+").expect("regex");
        let masked = mask_headers(&headers, &[pattern]);
        assert_eq!(masked["x-custom"], "[REDACTED]");
    }

    #[test]
    fn mask_headers_passthrough_normal() {
        let mut headers = HeaderMap::new();
        headers.insert("accept", HeaderValue::from_static("*/*"));
        let masked = mask_headers(&headers, &[]);
        assert_eq!(masked["accept"], "*/*");
    }

    #[test]
    fn mask_body_empty() {
        let (excerpt, pii) = mask_body_excerpt(b"", 4096, &[]);
        assert!(excerpt.is_none());
        assert!(!pii);
    }

    #[test]
    fn mask_body_json_with_pii() {
        let body = br#"{"email":"john@example.com","data":"hello"}"#;
        let (excerpt, pii) = mask_body_excerpt(body, 4096, &[]);
        assert!(pii);
        let text = excerpt.expect("should have excerpt");
        assert!(text.contains("[REDACTED]"));
        assert!(text.contains("hello"));
    }

    #[test]
    fn mask_body_plain_text_with_pii() {
        let body = b"Contact: john@example.com for info";
        let (excerpt, pii) = mask_body_excerpt(body, 4096, &[]);
        assert!(pii);
        let text = excerpt.expect("should have excerpt");
        assert!(text.contains("[REDACTED]"));
        assert!(text.contains("Contact:"));
    }

    #[test]
    fn mask_body_truncation() {
        let body = b"a]repeated text that is very long and should be truncated";
        let (excerpt, _) = mask_body_excerpt(body, 10, &[]);
        let text = excerpt.expect("should have excerpt");
        assert!(text.len() <= 10);
    }

    #[test]
    fn mask_body_no_pii() {
        let body = br#"{"status":"error","code":500}"#;
        let (excerpt, pii) = mask_body_excerpt(body, 4096, &[]);
        assert!(!pii);
        assert!(excerpt.is_some());
    }

    #[test]
    fn mask_body_binary_lossy() {
        let body = &[0xFF, 0xFE, 0x68, 0x65, 0x6c, 0x6c, 0x6f]; // invalid UTF-8 + "hello"
        let (excerpt, _) = mask_body_excerpt(body, 4096, &[]);
        assert!(excerpt.is_some());
    }

    #[test]
    fn mask_body_extra_patterns() {
        let body = b"Error: account-12345 failed";
        let pattern = Regex::new(r"account-\d+").expect("regex");
        let (excerpt, pii) = mask_body_excerpt(body, 4096, &[pattern]);
        assert!(pii);
        let text = excerpt.expect("should have excerpt");
        assert!(text.contains("[REDACTED]"));
        assert!(!text.contains("12345"));
    }

    #[test]
    fn redact_text_with_email() {
        let (found, text) = redact_text("Hello user@test.com world");
        assert!(found);
        assert!(text.contains("[REDACTED]"));
        assert!(text.contains("Hello"));
    }

    #[test]
    fn redact_text_no_pii() {
        let (found, text) = redact_text("Hello world");
        assert!(!found);
        assert_eq!(text, "Hello world");
    }

    #[test]
    fn build_snapshot_assembles_all_parts() {
        let mut req_headers = HeaderMap::new();
        req_headers.insert("authorization", HeaderValue::from_static("Bearer token"));
        req_headers.insert("content-type", HeaderValue::from_static("application/json"));

        let resp_headers = HeaderMap::new();
        let req_body = br#"{"email":"test@test.com"}"#;
        let resp_body = b"Internal Server Error";

        let snap = build_snapshot(SnapshotInput {
            request_id: "req-123".to_string(),
            method: "POST".to_string(),
            path: "/api/test".to_string(),
            status_code: 500,
            error_category: "backend".to_string(),
            duration_ms: 42.5,
            request_headers: &req_headers,
            request_body: req_body,
            response_headers: &resp_headers,
            response_body: resp_body,
            max_body_bytes: 4096,
            extra_patterns: &[],
        });

        assert_eq!(snap.request_id, "req-123");
        assert_eq!(snap.status_code, 500);
        assert_eq!(snap.request_headers["authorization"], "[REDACTED]");
        assert_eq!(snap.request_headers["content-type"], "application/json");
        assert!(snap.pii_found); // email in request body
        assert!(snap
            .request_body_excerpt
            .as_ref()
            .unwrap()
            .contains("[REDACTED]"));
        assert!(snap.response_body_excerpt.is_some());
        assert!(snap.captured_at.is_some());
    }
}
