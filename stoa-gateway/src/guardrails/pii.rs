//! PII Scanner — Detects and redacts personally identifiable information
//!
//! Scans JSON argument values recursively for:
//! - Email addresses
//! - Phone numbers (US/international formats)
//! - Credit card numbers (Visa, MC, Amex, Discover)
//! - US Social Security Numbers
//! - IPv4 addresses
//!
//! Allowlists URLs and UUIDs to reduce false positives.

use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::Value;

const REDACTED: &str = "[REDACTED]";

// Allowlist patterns — matched BEFORE PII patterns to avoid false positives
static URL_PATTERN: Lazy<Regex> = Lazy::new(|| Regex::new(r"https?://[^\s]+").expect("URL regex"));

static UUID_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
        .expect("UUID regex")
});

// PII patterns
static EMAIL_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}").expect("email regex")
});

static PHONE_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}")
        .expect("phone regex")
});

static CC_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
    )
    .expect("credit card regex")
});

static SSN_PATTERN: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b").expect("SSN regex"));

static IPV4_PATTERN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
    )
    .expect("IPv4 regex")
});

pub struct PiiScanner;

impl PiiScanner {
    /// Scan a JSON value for PII. Returns (has_pii, redacted_value).
    pub fn scan(value: &Value) -> (bool, Value) {
        let mut found = false;
        let redacted = Self::walk(value, &mut found);
        (found, redacted)
    }

    fn walk(value: &Value, found: &mut bool) -> Value {
        match value {
            Value::String(s) => {
                let redacted = Self::redact_string(s, found);
                Value::String(redacted)
            }
            Value::Array(arr) => Value::Array(arr.iter().map(|v| Self::walk(v, found)).collect()),
            Value::Object(map) => Value::Object(
                map.iter()
                    .map(|(k, v)| (k.clone(), Self::walk(v, found)))
                    .collect(),
            ),
            other => other.clone(),
        }
    }

    fn redact_string(s: &str, found: &mut bool) -> String {
        // Strip allowlisted patterns before scanning to avoid false positives
        let sanitized = URL_PATTERN.replace_all(s, "___URL___");
        let sanitized = UUID_PATTERN.replace_all(&sanitized, "___UUID___");

        // Check each PII pattern against the sanitized string
        let has_pii = EMAIL_PATTERN.is_match(&sanitized)
            || PHONE_PATTERN.is_match(&sanitized)
            || CC_PATTERN.is_match(&sanitized)
            || SSN_PATTERN.is_match(&sanitized)
            || IPV4_PATTERN.is_match(&sanitized);

        if !has_pii {
            return s.to_string();
        }

        *found = true;

        // Redact in the original string (preserving non-PII content)
        let mut result = s.to_string();
        result = EMAIL_PATTERN.replace_all(&result, REDACTED).to_string();
        result = PHONE_PATTERN.replace_all(&result, REDACTED).to_string();
        result = CC_PATTERN.replace_all(&result, REDACTED).to_string();
        result = SSN_PATTERN.replace_all(&result, REDACTED).to_string();
        result = IPV4_PATTERN.replace_all(&result, REDACTED).to_string();
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_no_pii() {
        let val = json!({"query": "list all APIs"});
        let (found, _) = PiiScanner::scan(&val);
        assert!(!found);
    }

    #[test]
    fn test_email_detected() {
        let val = json!({"data": "contact john@example.com"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert_eq!(
            redacted["data"].as_str().unwrap(),
            &format!("contact {REDACTED}")
        );
    }

    #[test]
    fn test_phone_detected() {
        let val = json!({"phone": "+1 (555) 123-4567"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert!(redacted["phone"].as_str().unwrap().contains(REDACTED));
    }

    #[test]
    fn test_credit_card_detected() {
        let val = json!({"payment": "card 4111111111111111 ok"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert!(redacted["payment"].as_str().unwrap().contains(REDACTED));
    }

    #[test]
    fn test_ssn_detected() {
        let val = json!({"ssn": "123-45-6789"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert_eq!(redacted["ssn"].as_str().unwrap(), REDACTED);
    }

    #[test]
    fn test_ipv4_detected() {
        let val = json!({"host": "server at 192.168.1.100"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert!(redacted["host"].as_str().unwrap().contains(REDACTED));
    }

    #[test]
    fn test_url_allowlisted() {
        let val = json!({"endpoint": "https://api.example.com/v1/users"});
        let (found, _) = PiiScanner::scan(&val);
        assert!(!found);
    }

    #[test]
    fn test_uuid_allowlisted() {
        let val = json!({"id": "550e8400-e29b-41d4-a716-446655440000"});
        let (found, _) = PiiScanner::scan(&val);
        assert!(!found);
    }

    #[test]
    fn test_nested_object() {
        let val = json!({
            "user": {
                "name": "John",
                "email": "john@corp.com"
            }
        });
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        assert!(redacted["user"]["email"]
            .as_str()
            .unwrap()
            .contains(REDACTED));
        assert_eq!(redacted["user"]["name"], "John");
    }

    #[test]
    fn test_array_scanning() {
        let val = json!({"items": ["hello", "user@test.com", "world"]});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        let items = redacted["items"].as_array().unwrap();
        assert_eq!(items[0], "hello");
        assert_eq!(items[1], REDACTED);
        assert_eq!(items[2], "world");
    }

    #[test]
    fn test_non_string_values_pass_through() {
        let val = json!({"count": 42, "active": true, "data": null});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(!found);
        assert_eq!(redacted, val);
    }

    #[test]
    fn test_mixed_pii_and_url() {
        let val = json!({"msg": "See https://api.com and email john@test.com"});
        let (found, redacted) = PiiScanner::scan(&val);
        assert!(found);
        let text = redacted["msg"].as_str().unwrap();
        assert!(text.contains("https://api.com"));
        assert!(text.contains(REDACTED));
    }
}
