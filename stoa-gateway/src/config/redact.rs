//! Secret-bearing value wrapper that hides the inner value from `Debug`.
//!
//! `Redacted<T>` is `#[serde(transparent)]` so it serializes/deserializes
//! exactly like its inner `T`. Only the `Debug` output is replaced with a
//! fixed `<redacted>` sentinel. Use this on config fields that carry
//! credentials (tokens, secrets, API keys) to prevent accidental leakage
//! via `format!("{:?}", …)` / `tracing::debug!(?…)` / `panic!("{:?}", …)`.

use std::fmt;

use serde::{Deserialize, Serialize};

/// Wrapper that passes through serde but hides the value from Debug.
#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Redacted<T>(pub T);

impl<T> Redacted<T> {
    pub fn new(value: T) -> Self {
        Self(value)
    }

    pub fn into_inner(self) -> T {
        self.0
    }

    pub fn get(&self) -> &T {
        &self.0
    }
}

impl<T> fmt::Debug for Redacted<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("<redacted>")
    }
}

impl<T> std::ops::Deref for Redacted<T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl<T> From<T> for Redacted<T> {
    fn from(value: T) -> Self {
        Self(value)
    }
}

/// Format helper for `impl Debug` on structs that contain `Option<String>`
/// secrets but do not use the `Redacted<T>` wrapper (e.g. to preserve the
/// public API shape of existing types).
pub fn debug_redact_opt_string(value: &Option<String>) -> &'static str {
    if value.is_some() {
        "Some(<redacted>)"
    } else {
        "None"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debug_hides_inner_string() {
        let r = Redacted::new("super-secret-xyz".to_string());
        let formatted = format!("{:?}", r);
        assert_eq!(formatted, "<redacted>");
        assert!(!formatted.contains("super-secret-xyz"));
    }

    #[test]
    fn debug_hides_inner_option_string() {
        let r = Redacted::new(Some("secret-abc".to_string()));
        let formatted = format!("{:?}", r);
        assert_eq!(formatted, "<redacted>");
        assert!(!formatted.contains("secret-abc"));
    }

    #[test]
    fn serde_transparent_roundtrip_string() {
        let r = Redacted::new("value".to_string());
        let json = serde_json::to_string(&r).unwrap();
        assert_eq!(json, "\"value\"");
        let back: Redacted<String> = serde_json::from_str(&json).unwrap();
        assert_eq!(back.get(), "value");
    }

    #[test]
    fn serde_transparent_roundtrip_option() {
        let some = Redacted::new(Some("v".to_string()));
        assert_eq!(serde_json::to_string(&some).unwrap(), "\"v\"");
        let none: Redacted<Option<String>> = Redacted::new(None);
        assert_eq!(serde_json::to_string(&none).unwrap(), "null");
    }

    #[test]
    fn deref_exposes_inner() {
        let r = Redacted::new("hello".to_string());
        assert_eq!(r.len(), 5);
    }

    #[test]
    fn debug_redact_opt_string_helper() {
        assert_eq!(
            debug_redact_opt_string(&Some("x".to_string())),
            "Some(<redacted>)"
        );
        assert_eq!(debug_redact_opt_string(&None), "None");
    }
}
