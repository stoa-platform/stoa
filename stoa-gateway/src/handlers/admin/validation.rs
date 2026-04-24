//! Shared input validators for admin-API upsert endpoints (GW-1 P1-6, P1-9).
//!
//! The pattern is deliberately flat: each handler builds a `Vec<String>` of
//! error messages using the `require_*` helpers, and returns
//! `validation_error_response(errors)` (`400 Bad Request`) when the vec is
//! non-empty. The helpers are pure and do not allocate unless a check fails,
//! so the happy path stays cheap.
//!
//! Design notes:
//! - `require_non_empty` uses `trim().is_empty()` so whitespace-only values
//!   are rejected the same way empty strings are. Admin-API fields are
//!   identifiers / header names / URLs — none of them tolerate leading/
//!   trailing whitespace in practice.
//! - `require_https_url` uses `url::Url::parse` so scheme comparison is
//!   case-insensitive (`HTTPS://` works), CRLF-injection attempts are
//!   rejected at parse time, and empty / host-less URLs are caught
//!   explicitly (`Url::parse("https://")` succeeds but has no host).

use axum::{http::StatusCode, response::IntoResponse, response::Response, Json};

/// Push a "must not be empty" error for `field` if `value` is empty or
/// whitespace-only. Returns silently on success.
pub(super) fn require_non_empty(field: &str, value: &str, errors: &mut Vec<String>) {
    if value.trim().is_empty() {
        errors.push(format!("{} must not be empty", field));
    }
}

/// Push an error for `field` if `value` is not a syntactically valid HTTPS
/// URL. Uses `url::Url::parse` for case-insensitive scheme matching and
/// rejects CRLF-injection / host-less forms.
pub(super) fn require_https_url(field: &str, value: &str, errors: &mut Vec<String>) {
    match url::Url::parse(value) {
        Ok(parsed) => {
            // `Url::parse` lowercases the scheme already, so `HTTPS://x`
            // and `https://x` both compare equal here.
            if parsed.scheme() != "https" {
                errors.push(format!("{} must use https scheme", field));
            } else if parsed.host().is_none() {
                errors.push(format!("{} must have a host", field));
            }
        }
        Err(_) => {
            errors.push(format!("{} is not a valid URL", field));
        }
    }
}

/// Build a `400 Bad Request` response that lists every validation error.
/// Deliberately generic `{"status":"error","errors":[...]}` shape so
/// admin clients can parse it uniformly across endpoints.
pub(super) fn validation_error_response(errors: Vec<String>) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(serde_json::json!({
            "status": "error",
            "errors": errors,
        })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_require_non_empty_accepts_plain_value() {
        let mut errors = Vec::new();
        require_non_empty("id", "abc", &mut errors);
        assert!(errors.is_empty());
    }

    #[test]
    fn test_require_non_empty_rejects_blank() {
        for blank in ["", " ", "\t\n", "   "] {
            let mut errors = Vec::new();
            require_non_empty("id", blank, &mut errors);
            assert_eq!(errors.len(), 1, "value {:?} should be rejected", blank);
            assert!(errors[0].contains("id"));
        }
    }

    #[test]
    fn test_require_https_url_accepts_lowercase_https() {
        let mut errors = Vec::new();
        require_https_url("token_url", "https://token.example.com/path", &mut errors);
        assert!(errors.is_empty(), "errors = {:?}", errors);
    }

    // GW-1 P1-9 regression: uppercase scheme was rejected by the old
    // `starts_with("https://")` check. `Url::parse` lowercases the scheme
    // so both forms are accepted.
    #[test]
    fn test_require_https_url_accepts_uppercase_scheme() {
        let mut errors = Vec::new();
        require_https_url("token_url", "HTTPS://token.example.com/path", &mut errors);
        assert!(errors.is_empty(), "errors = {:?}", errors);
    }

    #[test]
    fn test_require_https_url_rejects_http() {
        let mut errors = Vec::new();
        require_https_url("token_url", "http://plain.example.com", &mut errors);
        assert_eq!(errors.len(), 1);
        assert!(errors[0].contains("https"));
    }

    #[test]
    fn test_require_https_url_rejects_hostless() {
        let mut errors = Vec::new();
        // `https://` (no host, no path) fails url::Url::parse with
        // EmptyHost → caught by the parse-error branch. This asserts
        // the rejection reaches the caller, regardless of which branch.
        require_https_url("token_url", "https://", &mut errors);
        assert_eq!(errors.len(), 1);
    }

    // GW-1 P1-9 regression: CRLF-injection variants must be rejected.
    // `starts_with("https://")` would accept "https://foo\nHost: evil";
    // `Url::parse` rejects it.
    #[test]
    fn test_require_https_url_rejects_crlf_injection() {
        let mut errors = Vec::new();
        require_https_url("token_url", "https://foo\r\nHost: evil", &mut errors);
        assert_eq!(errors.len(), 1);
    }

    #[test]
    fn test_require_https_url_rejects_garbage() {
        let mut errors = Vec::new();
        require_https_url("token_url", "not a url at all", &mut errors);
        assert_eq!(errors.len(), 1);
    }
}
