//! Custom serde deserializers used across the config structs.
//!
//! Docs long advertised CSV-style env-var input for `Vec<String>` fields
//! (e.g. `STOA_SNAPSHOT_EXTRA_PII_PATTERNS=card_number,ssn_us`). The default
//! Figment + serde path refuses that with `InvalidType(Str, "a sequence")`
//! which crashes `Config::load()`. These helpers accept both CSV strings
//! and native sequences (YAML lists, JSON arrays) so the documented env
//! form keeps working.

use serde::de::{self, Deserializer, SeqAccess, Visitor};
use std::fmt;

/// Deserialize a `Vec<String>` from either a CSV string, a JSON array
/// string (`"[\"a\",\"b\"]"`), or a native sequence.
///
/// Rules:
/// - Each element is trimmed of surrounding whitespace.
/// - Empty elements are dropped (`"a,,b"` → `["a", "b"]`, `""` → `[]`).
/// - JSON array strings are parsed via `serde_json::from_str` and trimmed.
pub fn string_list<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: Deserializer<'de>,
{
    struct StringListVisitor;

    impl<'de> Visitor<'de> for StringListVisitor {
        type Value = Vec<String>;

        fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
            f.write_str("a sequence of strings, a CSV string, or a JSON array of strings")
        }

        fn visit_str<E>(self, value: &str) -> Result<Vec<String>, E>
        where
            E: de::Error,
        {
            let trimmed = value.trim();
            if trimmed.is_empty() {
                return Ok(Vec::new());
            }

            // JSON array form — e.g. `["a","b"]`.
            if trimmed.starts_with('[') {
                let parsed: Vec<String> = serde_json::from_str(trimmed)
                    .map_err(|err| de::Error::custom(format!("invalid JSON array: {err}")))?;
                return Ok(parsed
                    .into_iter()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect());
            }

            // CSV form — drop empty segments, trim each element.
            Ok(trimmed
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect())
        }

        fn visit_string<E>(self, value: String) -> Result<Vec<String>, E>
        where
            E: de::Error,
        {
            self.visit_str(&value)
        }

        fn visit_seq<S>(self, mut seq: S) -> Result<Vec<String>, S::Error>
        where
            S: SeqAccess<'de>,
        {
            let mut out = Vec::new();
            while let Some(item) = seq.next_element::<String>()? {
                let trimmed = item.trim();
                if !trimmed.is_empty() {
                    out.push(trimmed.to_string());
                }
            }
            Ok(out)
        }
    }

    deserializer.deserialize_any(StringListVisitor)
}

#[cfg(test)]
mod tests {
    use super::string_list;
    use serde::Deserialize;

    #[derive(Debug, Deserialize)]
    struct Wrap {
        #[serde(deserialize_with = "string_list", default)]
        items: Vec<String>,
    }

    #[test]
    fn csv_basic() {
        let w: Wrap = serde_json::from_value(serde_json::json!({ "items": "a,b,c" })).unwrap();
        assert_eq!(w.items, vec!["a", "b", "c"]);
    }

    #[test]
    fn csv_trims_whitespace() {
        let w: Wrap =
            serde_json::from_value(serde_json::json!({ "items": " a , b , c " })).unwrap();
        assert_eq!(w.items, vec!["a", "b", "c"]);
    }

    #[test]
    fn csv_drops_empty_segments() {
        let w: Wrap = serde_json::from_value(serde_json::json!({ "items": "a,,b" })).unwrap();
        assert_eq!(w.items, vec!["a", "b"]);
    }

    #[test]
    fn csv_empty_string() {
        let w: Wrap = serde_json::from_value(serde_json::json!({ "items": "" })).unwrap();
        assert!(w.items.is_empty());
    }

    #[test]
    fn csv_whitespace_only() {
        let w: Wrap = serde_json::from_value(serde_json::json!({ "items": "   " })).unwrap();
        assert!(w.items.is_empty());
    }

    #[test]
    fn json_array_string() {
        let w: Wrap =
            serde_json::from_value(serde_json::json!({ "items": "[\"a\",\"b\"]" })).unwrap();
        assert_eq!(w.items, vec!["a", "b"]);
    }

    #[test]
    fn json_array_string_trims_elements() {
        let w: Wrap =
            serde_json::from_value(serde_json::json!({ "items": "[\"  a  \",\" b \"]" })).unwrap();
        assert_eq!(w.items, vec!["a", "b"]);
    }

    #[test]
    fn native_sequence() {
        let w: Wrap = serde_json::from_value(serde_json::json!({ "items": ["a", "b"] })).unwrap();
        assert_eq!(w.items, vec!["a", "b"]);
    }

    #[test]
    fn native_sequence_trims() {
        let w: Wrap =
            serde_json::from_value(serde_json::json!({ "items": [" a ", "", "b"] })).unwrap();
        assert_eq!(w.items, vec!["a", "b"]);
    }
}
