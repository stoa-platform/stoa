//! STOA Token Compression (STC) — Lossless JSON compression for LLM agents
//!
//! ADR-060: Reduces LLM token consumption by stripping redundant JSON punctuation.
//! Three techniques applied in order:
//! 1. Unquoted keys: `{"name":"foo"}` → `{name:"foo"}`
//! 2. Compact arrays: `"tags":["a","b","c"]` → `tags[3]:"a","b","c"`
//! 3. Columnar objects: `[{"id":1},{"id":2}]` → `[2]{id}:1 / 2`
//!
//! Activated via `Accept-Encoding: stc` header. Zero overhead when disabled.
//! CAB-1936 Phase 2.

use async_trait::async_trait;
use serde_json::Value;

use super::super::sdk::{Phase, Plugin, PluginContext, PluginMetadata, PluginResult};

/// STC version identifier.
const STC_VERSION: &str = "1";

/// Header value clients send to request STC compression.
const STC_ENCODING: &str = "stc";

/// Store key for cross-phase flag (PreUpstream → PostUpstream).
const STC_REQUESTED_KEY: &str = "stc_requested";

// ============================================================================
// Encoder
// ============================================================================

/// Encode a JSON string into STC format (lossless compression).
///
/// Returns the compressed string and the compression ratio (compressed/original).
pub fn encode_stc(json_str: &str) -> Result<(String, f64), String> {
    let value: Value = serde_json::from_str(json_str).map_err(|e| format!("invalid JSON: {e}"))?;
    let encoded = encode_value(&value);
    let ratio = if json_str.is_empty() {
        1.0
    } else {
        encoded.len() as f64 / json_str.len() as f64
    };
    Ok((encoded, ratio))
}

fn encode_value(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => format!("\"{}\"", escape_str(s)),
        Value::Array(arr) => encode_array(arr),
        Value::Object(obj) => encode_object(obj),
    }
}

fn escape_str(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t")
}

/// Check if a key can be safely unquoted (Technique 1).
fn is_identifier(key: &str) -> bool {
    if key.is_empty() {
        return false;
    }
    let first = key.as_bytes()[0];
    if !(first.is_ascii_alphabetic() || first == b'_') {
        return false;
    }
    key.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
}

fn encode_object(obj: &serde_json::Map<String, Value>) -> String {
    if obj.is_empty() {
        return "{}".to_string();
    }

    let entries: Vec<String> = obj
        .iter()
        .map(|(k, v)| {
            let key = if is_identifier(k) {
                k.clone()
            } else {
                format!("\"{}\"", escape_str(k))
            };
            // Technique 2: compact arrays of homogeneous primitives
            if let Value::Array(arr) = v {
                if let Some(compact) = try_compact_array(arr) {
                    return format!("{key}[{}]: {compact}", arr.len());
                }
            }
            format!("{key}: {}", encode_value(v))
        })
        .collect();

    format!("{{{}}}", entries.join(", "))
}

fn encode_array(arr: &[Value]) -> String {
    if arr.is_empty() {
        return "[]".to_string();
    }

    // Technique 3: columnar objects
    if let Some(columnar) = try_columnar_objects(arr) {
        return columnar;
    }

    // Technique 2: compact primitives
    if let Some(compact) = try_compact_array(arr) {
        return format!("[{}]", compact);
    }

    // Fallback: recursive encoding
    let items: Vec<String> = arr.iter().map(encode_value).collect();
    format!("[{}]", items.join(", "))
}

/// Technique 2: Compact homogeneous primitive arrays.
/// Returns inner content without brackets (caller adds context).
fn try_compact_array(arr: &[Value]) -> Option<String> {
    if arr.is_empty() {
        return None;
    }

    // Check all elements are the same primitive type
    let all_strings = arr.iter().all(|v| v.is_string());
    let all_numbers = arr.iter().all(|v| v.is_number());
    let all_bools = arr.iter().all(|v| v.is_boolean());

    if !all_strings && !all_numbers && !all_bools {
        return None;
    }

    let items: Vec<String> = arr.iter().map(encode_value).collect();
    Some(items.join(","))
}

/// Technique 3: Columnar notation for arrays of homogeneous flat objects.
fn try_columnar_objects(arr: &[Value]) -> Option<String> {
    if arr.len() < 2 {
        return None;
    }

    // All elements must be objects
    let objects: Vec<&serde_json::Map<String, Value>> =
        arr.iter().filter_map(|v| v.as_object()).collect();

    if objects.len() != arr.len() {
        return None;
    }

    // All objects must have the same keys in the same order
    let keys: Vec<&String> = objects[0].keys().collect();
    if keys.is_empty() {
        return None;
    }

    for obj in &objects[1..] {
        let obj_keys: Vec<&String> = obj.keys().collect();
        if obj_keys != keys {
            return None;
        }
    }

    // All values must be primitives (no nested objects/arrays)
    for obj in &objects {
        for v in obj.values() {
            if v.is_object() || v.is_array() {
                return None;
            }
        }
    }

    let key_list = keys
        .iter()
        .map(|k| k.as_str())
        .collect::<Vec<_>>()
        .join(",");
    let rows: Vec<String> = objects
        .iter()
        .map(|obj| {
            keys.iter()
                .map(|k| encode_value(&obj[k.as_str()]))
                .collect::<Vec<_>>()
                .join(",")
        })
        .collect();

    Some(format!(
        "[{}]{{{}}}: {}",
        arr.len(),
        key_list,
        rows.join(" / ")
    ))
}

// ============================================================================
// Decoder
// ============================================================================

/// Decode an STC-encoded string back to standard JSON.
///
/// This is the inverse of `encode_stc`. Roundtrip fidelity: encode → decode = identical JSON.
pub fn decode_stc(stc: &str) -> Result<String, String> {
    // Phase 1: Restore columnar objects → standard JSON arrays
    let result = restore_columnar(stc);
    // Phase 2: Restore compact arrays
    let result = restore_compact_arrays(&result);
    // Phase 3: Re-quote unquoted keys
    let result = requote_keys(&result);

    // Validate result is valid JSON
    serde_json::from_str::<Value>(&result)
        .map_err(|e| format!("decoded STC is not valid JSON: {e}"))?;

    Ok(result)
}

fn restore_columnar(input: &str) -> String {
    let mut result = String::with_capacity(input.len());
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        // Look for pattern: [N]{key1,key2}: val1,val2 / val3,val4
        if chars[i] == '[' && i + 1 < chars.len() && chars[i + 1].is_ascii_digit() {
            if let Some((replacement, consumed)) = try_parse_columnar(&chars[i..]) {
                result.push_str(&replacement);
                i += consumed;
                continue;
            }
        }
        result.push(chars[i]);
        i += 1;
    }

    result
}

fn try_parse_columnar(chars: &[char]) -> Option<(String, usize)> {
    // Parse [N]
    let mut pos = 1; // skip '['
    let mut count_str = String::new();
    while pos < chars.len() && chars[pos].is_ascii_digit() {
        count_str.push(chars[pos]);
        pos += 1;
    }
    if pos >= chars.len() || chars[pos] != ']' || count_str.is_empty() {
        return None;
    }
    pos += 1; // skip ']'

    // Must be followed by '{'
    if pos >= chars.len() || chars[pos] != '{' {
        return None;
    }
    pos += 1; // skip '{'

    // Parse key1,key2,...}
    let mut keys_str = String::new();
    while pos < chars.len() && chars[pos] != '}' {
        keys_str.push(chars[pos]);
        pos += 1;
    }
    if pos >= chars.len() {
        return None;
    }
    pos += 1; // skip '}'

    // Must be followed by ': '
    if pos + 1 >= chars.len() || chars[pos] != ':' || chars[pos + 1] != ' ' {
        return None;
    }
    pos += 2; // skip ': '

    let count: usize = count_str.parse().ok()?;
    let keys: Vec<&str> = keys_str.split(',').collect();

    // Parse rows separated by ' / '
    let remaining: String = chars[pos..].iter().collect();
    let rows = split_rows(&remaining, count);
    if rows.len() != count {
        return None;
    }

    // Build JSON array of objects
    let objects: Vec<String> = rows
        .iter()
        .map(|row| {
            let values = split_values_respecting_quotes(row, keys.len());
            let pairs: Vec<String> = keys
                .iter()
                .zip(values.iter())
                .map(|(k, v)| format!("\"{}\":{}", k, v.trim()))
                .collect();
            format!("{{{}}}", pairs.join(","))
        })
        .collect();

    let json_array = format!("[{}]", objects.join(","));
    let total_consumed = calculate_consumed(chars, count);

    Some((json_array, total_consumed))
}

fn split_rows(s: &str, expected: usize) -> Vec<String> {
    let mut rows = Vec::new();
    let mut current = String::new();
    let mut in_quote = false;
    let chars: Vec<char> = s.chars().collect();
    let mut i = 0;

    while i < chars.len() && rows.len() < expected {
        if chars[i] == '"' {
            in_quote = !in_quote;
            current.push(chars[i]);
        } else if !in_quote
            && i + 2 < chars.len()
            && chars[i] == ' '
            && chars[i + 1] == '/'
            && chars[i + 2] == ' '
            && rows.len() < expected - 1
        {
            rows.push(current.trim().to_string());
            current = String::new();
            i += 3; // skip ' / '
            continue;
        } else {
            current.push(chars[i]);
        }
        i += 1;
    }
    if !current.trim().is_empty() {
        rows.push(current.trim().to_string());
    }
    rows
}

fn calculate_consumed(chars: &[char], count: usize) -> usize {
    // Re-scan from start to find the end of the columnar expression
    let s: String = chars.iter().collect();
    // Find ': ' after '}'
    let after_keys = s.find("}: ").map(|p| p + 3).unwrap_or(0);
    let remaining = &s[after_keys..];
    let rows = split_rows(remaining, count);

    let mut consumed = after_keys;
    for (i, row) in rows.iter().enumerate() {
        consumed += row.len();
        if i < rows.len() - 1 {
            consumed += 3; // ' / '
        }
    }
    consumed
}

fn restore_compact_arrays(input: &str) -> String {
    let mut result = String::with_capacity(input.len());
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;

    while i < chars.len() {
        // Look for pattern: identifier[N]: values (inside object context)
        if chars[i].is_ascii_alphabetic() || chars[i] == '_' {
            if let Some((replacement, consumed)) = try_parse_compact_array(&chars[i..]) {
                result.push_str(&replacement);
                i += consumed;
                continue;
            }
        }
        result.push(chars[i]);
        i += 1;
    }

    result
}

fn try_parse_compact_array(chars: &[char]) -> Option<(String, usize)> {
    // Parse identifier
    let mut pos = 0;
    let mut ident = String::new();
    while pos < chars.len() && (chars[pos].is_ascii_alphanumeric() || chars[pos] == '_') {
        ident.push(chars[pos]);
        pos += 1;
    }
    if ident.is_empty() || pos >= chars.len() || chars[pos] != '[' {
        return None;
    }
    pos += 1; // skip '['

    // Parse count
    let mut count_str = String::new();
    while pos < chars.len() && chars[pos].is_ascii_digit() {
        count_str.push(chars[pos]);
        pos += 1;
    }
    if count_str.is_empty() || pos >= chars.len() || chars[pos] != ']' {
        return None;
    }
    pos += 1; // skip ']'

    // Must be followed by ': '
    if pos + 1 >= chars.len() || chars[pos] != ':' || chars[pos + 1] != ' ' {
        return None;
    }
    pos += 2; // skip ': '

    let count: usize = count_str.parse().ok()?;

    // Parse exactly `count` values separated by commas, respecting quotes.
    // After `count-1` commas we have all values. Stop before the next comma
    // (which belongs to the parent object) or closing brace.
    let mut values = Vec::new();
    let mut current = String::new();
    let mut in_quote = false;
    let mut scan = pos;

    while scan < chars.len() {
        let ch = chars[scan];
        if ch == '"' {
            in_quote = !in_quote;
            current.push(ch);
        } else if ch == ',' && !in_quote {
            if values.len() < count - 1 {
                // Comma between array values
                values.push(current.trim().to_string());
                current = String::new();
            } else {
                // This comma belongs to the parent — stop here
                break;
            }
        } else if (ch == '}' || ch == ']') && !in_quote {
            // End of parent container — stop here
            break;
        } else {
            current.push(ch);
        }
        scan += 1;
    }
    // Push the last value
    values.push(current.trim().to_string());

    if values.len() != count {
        return None;
    }

    let values_json = values.join(", ");
    let replacement = format!("\"{ident}\": [{values_json}]");

    Some((replacement, scan))
}

fn requote_keys(input: &str) -> String {
    let mut result = String::with_capacity(input.len());
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    let mut in_quote = false;

    while i < chars.len() {
        if chars[i] == '"' {
            in_quote = !in_quote;
            result.push(chars[i]);
            i += 1;
            continue;
        }

        if in_quote {
            result.push(chars[i]);
            i += 1;
            continue;
        }

        // Look for unquoted key followed by ':'
        if (chars[i].is_ascii_alphabetic() || chars[i] == '_') && is_after_object_start(&result) {
            let mut key = String::new();
            let start = i;
            while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                key.push(chars[i]);
                i += 1;
            }
            // Skip whitespace
            while i < chars.len() && chars[i] == ' ' {
                i += 1;
            }
            if i < chars.len() && chars[i] == ':' {
                result.push_str(&format!("\"{}\"", key));
            } else {
                // Not a key, restore position
                result.push_str(&key);
                // Also push any whitespace we skipped
                i = start + key.len();
            }
            continue;
        }

        result.push(chars[i]);
        i += 1;
    }

    result
}

fn is_after_object_start(s: &str) -> bool {
    let trimmed = s.trim_end();
    trimmed.ends_with('{') || trimmed.ends_with(',')
}

fn split_values_respecting_quotes(s: &str, expected: usize) -> Vec<String> {
    let mut values = Vec::new();
    let mut current = String::new();
    let mut in_quote = false;

    for ch in s.chars() {
        if ch == '"' {
            in_quote = !in_quote;
            current.push(ch);
        } else if ch == ',' && !in_quote && values.len() < expected - 1 {
            values.push(current.trim().to_string());
            current = String::new();
        } else {
            current.push(ch);
        }
    }
    values.push(current.trim().to_string());
    values
}

// ============================================================================
// Plugin
// ============================================================================

/// STOA Token Compression plugin.
///
/// - **PreUpstream**: Checks `Accept-Encoding: stc` header, sets flag in store
/// - **PostUpstream**: If flag set and response is JSON, compresses body with STC
pub struct StcPlugin;

impl StcPlugin {
    pub fn new() -> Self {
        Self
    }
}

impl Default for StcPlugin {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Plugin for StcPlugin {
    fn metadata(&self) -> PluginMetadata {
        PluginMetadata {
            name: "stc-compression".to_string(),
            version: STC_VERSION.to_string(),
            description: "STOA Token Compression — lossless JSON compression for LLM agents"
                .to_string(),
            phases: vec![Phase::PreUpstream, Phase::PostUpstream],
        }
    }

    async fn execute(&self, phase: Phase, ctx: &mut PluginContext) -> PluginResult {
        match phase {
            Phase::PreUpstream => {
                // Check if client requests STC encoding
                if let Some(accept) = ctx.get_request_header("accept-encoding") {
                    if accept.split(',').any(|e| e.trim() == STC_ENCODING) {
                        ctx.store_set(STC_REQUESTED_KEY, "true");
                    }
                }
                PluginResult::Continue
            }
            Phase::PostUpstream => {
                // Only compress if client requested STC
                if ctx.store_get(STC_REQUESTED_KEY) != Some("true") {
                    return PluginResult::Continue;
                }

                // Only compress JSON responses
                let is_json = ctx
                    .response_headers
                    .get("content-type")
                    .and_then(|v| v.to_str().ok())
                    .is_some_and(|ct| ct.contains("application/json"));

                if !is_json {
                    return PluginResult::Continue;
                }

                // Get response body
                let body_str = match ctx.get_response_body_str() {
                    Some(s) => s.to_string(),
                    None => return PluginResult::Continue,
                };

                // Encode
                match encode_stc(&body_str) {
                    Ok((encoded, ratio)) => {
                        ctx.set_response_body(&encoded);
                        ctx.set_response_header("content-encoding", STC_ENCODING);
                        ctx.set_response_header("content-type", "application/stc+json");
                        ctx.set_response_header("x-stc-version", STC_VERSION);
                        ctx.set_response_header("x-stc-ratio", &format!("{:.2}", ratio));
                    }
                    Err(_) => {
                        // Compression failed — return original body unchanged
                    }
                }

                PluginResult::Continue
            }
            _ => PluginResult::Continue,
        }
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, StatusCode};

    // --- Encoder Tests ---

    #[test]
    fn test_encode_simple_object() {
        let json = r#"{"name":"foo","count":42,"active":true}"#;
        let (encoded, ratio) = encode_stc(json).unwrap();
        assert!(encoded.contains("name:"));
        assert!(encoded.contains("count:"));
        assert!(ratio < 1.0);
    }

    #[test]
    fn test_encode_unquoted_keys() {
        let json = r#"{"api_version":"v2","name":"test"}"#;
        let (encoded, _) = encode_stc(json).unwrap();
        // Keys should be unquoted (valid identifiers)
        assert!(encoded.contains("api_version:"));
        assert!(encoded.contains("name:"));
        // Values should remain quoted
        assert!(encoded.contains("\"v2\""));
    }

    #[test]
    fn test_encode_non_identifier_keys_stay_quoted() {
        let json = r#"{"special-key":"value","123start":"value"}"#;
        let (encoded, _) = encode_stc(json).unwrap();
        assert!(encoded.contains("\"special-key\""));
        assert!(encoded.contains("\"123start\""));
    }

    #[test]
    fn test_encode_compact_string_array() {
        let json = r#"{"tags":["api","gateway","mcp"]}"#;
        let (encoded, _) = encode_stc(json).unwrap();
        assert!(encoded.contains("tags[3]:"));
    }

    #[test]
    fn test_encode_compact_number_array() {
        let json = r#"{"scores":[95,87,91]}"#;
        let (encoded, _) = encode_stc(json).unwrap();
        assert!(encoded.contains("scores[3]:"));
    }

    #[test]
    fn test_encode_mixed_array_not_compacted() {
        let json = r#"{"mix":["a",1,true]}"#;
        let (encoded, _) = encode_stc(json).unwrap();
        // Mixed types should not use compact notation
        assert!(!encoded.contains("mix[3]:"));
    }

    #[test]
    fn test_encode_columnar_objects() {
        let json = r#"[{"id":1,"name":"users"},{"id":2,"name":"orders"}]"#;
        let (encoded, _) = encode_stc(json).unwrap();
        assert!(encoded.contains("[2]{id,name}:"));
        assert!(encoded.contains(" / "));
    }

    #[test]
    fn test_encode_single_object_array_not_columnar() {
        let json = r#"[{"id":1}]"#;
        let (encoded, _) = encode_stc(json).unwrap();
        // Single element should not use columnar
        assert!(!encoded.contains("[1]{"));
    }

    #[test]
    fn test_encode_empty_object() {
        let json = "{}";
        let (encoded, _) = encode_stc(json).unwrap();
        assert_eq!(encoded, "{}");
    }

    #[test]
    fn test_encode_empty_array() {
        let json = "[]";
        let (encoded, _) = encode_stc(json).unwrap();
        assert_eq!(encoded, "[]");
    }

    #[test]
    fn test_encode_null() {
        let json = "null";
        let (encoded, _) = encode_stc(json).unwrap();
        assert_eq!(encoded, "null");
    }

    #[test]
    fn test_encode_nested_objects_not_columnar() {
        let json = r#"[{"id":1,"meta":{"x":1}},{"id":2,"meta":{"x":2}}]"#;
        let (encoded, _) = encode_stc(json).unwrap();
        // Nested objects prevent columnar encoding
        assert!(!encoded.contains("[2]{"));
    }

    #[test]
    fn test_encode_invalid_json() {
        let result = encode_stc("not json {{{");
        assert!(result.is_err());
    }

    // --- Decoder Tests ---

    #[test]
    fn test_decode_unquoted_keys() {
        let stc = r#"{name: "foo", count: 42}"#;
        let json = decode_stc(stc).unwrap();
        let v: Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["name"], "foo");
        assert_eq!(v["count"], 42);
    }

    // --- Roundtrip Tests ---

    #[test]
    fn test_roundtrip_simple_object() {
        let json = r#"{"name":"foo","count":42,"active":true}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_compact_arrays() {
        let json = r#"{"tags":["api","gateway","mcp"],"scores":[95,87,91]}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_columnar_objects() {
        let json =
            r#"[{"id":1,"name":"users","method":"GET"},{"id":2,"name":"orders","method":"POST"}]"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_nested_structure() {
        let json = r#"{"api":{"version":"v2","endpoints":["/users","/orders"]},"count":5}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_unicode() {
        let json = r#"{"greeting":"こんにちは","emoji":"🚀"}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_special_chars_in_values() {
        let json = r#"{"query":"SELECT * FROM \"users\" WHERE id = 1"}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_empty_strings() {
        let json = r#"{"empty":"","also_empty":""}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_null_values() {
        let json = r#"{"name":"test","value":null}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_deeply_nested() {
        let json = r#"{"a":{"b":{"c":{"d":"deep"}}}}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, _) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
    }

    #[test]
    fn test_roundtrip_real_mcp_tool_response() {
        let json = r#"{"tools":[{"name":"echo","description":"Echo tool","inputSchema":{"type":"object","properties":{"message":{"type":"string"}}}},{"name":"weather","description":"Weather lookup","inputSchema":{"type":"object","properties":{"city":{"type":"string"}}}}]}"#;
        let original: Value = serde_json::from_str(json).unwrap();
        let (encoded, ratio) = encode_stc(json).unwrap();
        let decoded = decode_stc(&encoded).unwrap();
        let restored: Value = serde_json::from_str(&decoded).unwrap();
        assert_eq!(original, restored);
        // STC should reduce size
        assert!(ratio < 1.0, "Expected compression, got ratio {ratio}");
    }

    // --- Plugin Tests ---

    fn make_plugin_ctx(
        phase: Phase,
        accept_encoding: Option<&str>,
        response_body: Option<&str>,
    ) -> PluginContext {
        let mut headers = HeaderMap::new();
        if let Some(ae) = accept_encoding {
            headers.insert("accept-encoding", ae.parse().unwrap());
        }
        let mut ctx = PluginContext::new(
            phase,
            "test-tenant".to_string(),
            "/mcp/tools/call".to_string(),
            "POST".to_string(),
            headers,
        );
        if let Some(body) = response_body {
            ctx.response_body = Some(body.as_bytes().to_vec());
            ctx.response_headers
                .insert("content-type", "application/json".parse().unwrap());
            ctx.response_status = Some(StatusCode::OK);
        }
        ctx
    }

    #[tokio::test]
    async fn test_plugin_pre_upstream_sets_flag() {
        let plugin = StcPlugin::new();
        let mut ctx = make_plugin_ctx(Phase::PreUpstream, Some("stc"), None);

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(ctx.store_get(STC_REQUESTED_KEY), Some("true"));
    }

    #[tokio::test]
    async fn test_plugin_pre_upstream_no_flag_without_header() {
        let plugin = StcPlugin::new();
        let mut ctx = make_plugin_ctx(Phase::PreUpstream, None, None);

        let result = plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert_eq!(ctx.store_get(STC_REQUESTED_KEY), None);
    }

    #[tokio::test]
    async fn test_plugin_pre_upstream_mixed_encodings() {
        let plugin = StcPlugin::new();
        let mut ctx = make_plugin_ctx(Phase::PreUpstream, Some("gzip, stc, br"), None);

        plugin.execute(Phase::PreUpstream, &mut ctx).await;
        assert_eq!(ctx.store_get(STC_REQUESTED_KEY), Some("true"));
    }

    #[tokio::test]
    async fn test_plugin_post_upstream_compresses() {
        let plugin = StcPlugin::new();
        let json = r#"{"name":"test","count":42}"#;
        let mut ctx = make_plugin_ctx(Phase::PostUpstream, None, Some(json));
        ctx.store_set(STC_REQUESTED_KEY, "true");

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));

        // Body should be compressed
        let body = ctx.get_response_body_str().unwrap();
        assert!(body.contains("name:"));
        assert!(!body.contains("\"name\""));

        // Headers should be set
        assert_eq!(
            ctx.response_headers.get("content-encoding").unwrap(),
            STC_ENCODING
        );
        assert_eq!(
            ctx.response_headers.get("content-type").unwrap(),
            "application/stc+json"
        );
        assert_eq!(
            ctx.response_headers.get("x-stc-version").unwrap(),
            STC_VERSION
        );
        assert!(ctx.response_headers.get("x-stc-ratio").is_some());
    }

    #[tokio::test]
    async fn test_plugin_post_upstream_passthrough_without_flag() {
        let plugin = StcPlugin::new();
        let json = r#"{"name":"test"}"#;
        let mut ctx = make_plugin_ctx(Phase::PostUpstream, None, Some(json));
        // No STC_REQUESTED_KEY set

        plugin.execute(Phase::PostUpstream, &mut ctx).await;

        // Body should be unchanged
        assert_eq!(ctx.get_response_body_str().unwrap(), json);
        assert!(ctx.response_headers.get("content-encoding").is_none());
    }

    #[tokio::test]
    async fn test_plugin_post_upstream_passthrough_non_json() {
        let plugin = StcPlugin::new();
        let mut ctx = PluginContext::new(
            Phase::PostUpstream,
            "test-tenant".to_string(),
            "/path".to_string(),
            "GET".to_string(),
            HeaderMap::new(),
        );
        ctx.response_body = Some(b"<html>not json</html>".to_vec());
        ctx.response_headers
            .insert("content-type", "text/html".parse().unwrap());
        ctx.store_set(STC_REQUESTED_KEY, "true");

        plugin.execute(Phase::PostUpstream, &mut ctx).await;

        // Body should be unchanged (not JSON)
        assert_eq!(
            ctx.get_response_body_str().unwrap(),
            "<html>not json</html>"
        );
    }

    #[tokio::test]
    async fn test_plugin_post_upstream_no_body() {
        let plugin = StcPlugin::new();
        let mut ctx = make_plugin_ctx(Phase::PostUpstream, None, None);
        ctx.store_set(STC_REQUESTED_KEY, "true");
        ctx.response_headers
            .insert("content-type", "application/json".parse().unwrap());

        let result = plugin.execute(Phase::PostUpstream, &mut ctx).await;
        assert!(matches!(result, PluginResult::Continue));
        assert!(ctx.response_body.is_none());
    }

    // --- is_identifier Tests ---

    #[test]
    fn test_is_identifier_valid() {
        assert!(is_identifier("name"));
        assert!(is_identifier("_private"));
        assert!(is_identifier("camelCase"));
        assert!(is_identifier("snake_case"));
        assert!(is_identifier("UPPER"));
        assert!(is_identifier("a1"));
    }

    #[test]
    fn test_is_identifier_invalid() {
        assert!(!is_identifier(""));
        assert!(!is_identifier("123"));
        assert!(!is_identifier("special-key"));
        assert!(!is_identifier("has space"));
        assert!(!is_identifier("dot.key"));
    }
}
