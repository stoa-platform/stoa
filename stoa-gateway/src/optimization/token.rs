//! Token Optimizer Implementation
//!
//! 4-stage pipeline for reducing JSON payload size:
//! 1. Null removal
//! 2. Schema pruning (OpenAPI)
//! 3. Key shortening
//! 4. Pagination injection

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use tracing::debug;

/// Optimization level
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OptimizationLevel {
    /// No transformation — backward compatible
    #[default]
    None,
    /// Null removal + pagination only
    Moderate,
    /// Full optimization: pruning + null removal + key shortening + pagination
    Aggressive,
}

impl OptimizationLevel {
    /// Parse from string (case-insensitive)
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "none" => OptimizationLevel::None,
            "moderate" => OptimizationLevel::Moderate,
            "aggressive" => OptimizationLevel::Aggressive,
            _ => OptimizationLevel::None,
        }
    }
}

/// Optimization settings from client capability negotiation
#[derive(Debug, Clone, Default)]
pub struct OptimizationSettings {
    /// Optimization level
    pub level: OptimizationLevel,
    /// Maximum response tokens (affects pagination)
    pub max_response_tokens: Option<usize>,
    /// Include key mapping in response (for reversibility)
    pub include_key_map: bool,
}

impl OptimizationSettings {
    /// Parse from MCP initialize capabilities
    pub fn from_capabilities(capabilities: &Value) -> Self {
        let token_opt = capabilities.get("tokenOptimization");

        match token_opt {
            Some(opt) => {
                let level = opt
                    .get("level")
                    .and_then(|v| v.as_str())
                    .map(OptimizationLevel::from_str)
                    .unwrap_or(OptimizationLevel::None);

                let max_tokens = opt
                    .get("maxResponseTokens")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as usize);

                let include_map = opt
                    .get("includeKeyMap")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);

                Self {
                    level,
                    max_response_tokens: max_tokens,
                    include_key_map: include_map,
                }
            }
            None => Self::default(),
        }
    }

    /// Check if optimization is enabled (level != None)
    pub fn is_enabled(&self) -> bool {
        self.level != OptimizationLevel::None
    }

    /// Serialize to metadata string for session storage
    pub fn to_metadata(&self) -> Result<String, serde_json::Error> {
        serde_json::to_string(&serde_json::json!({
            "level": match self.level {
                OptimizationLevel::None => "none",
                OptimizationLevel::Moderate => "moderate",
                OptimizationLevel::Aggressive => "aggressive",
            },
            "maxResponseTokens": self.max_response_tokens,
            "includeKeyMap": self.include_key_map,
        }))
    }

    /// Parse from metadata string
    pub fn from_metadata(s: &str) -> Result<Self, serde_json::Error> {
        let v: Value = serde_json::from_str(s)?;
        Ok(Self::from_capabilities(
            &serde_json::json!({ "tokenOptimization": v }),
        ))
    }
}

/// Key shortening mappings (reversible)
const KEY_MAPPINGS: &[(&str, &str)] = &[
    ("description", "desc"),
    ("properties", "props"),
    ("required", "req"),
    ("parameters", "params"),
    ("responses", "resp"),
    ("operationId", "opId"),
    ("requestBody", "body"),
    ("additionalProperties", "addProps"),
    ("discriminator", "discrim"),
    ("deprecated", "depr"),
];

/// Keys to prune from OpenAPI schemas
const PRUNE_KEYS: &[&str] = &[
    "description",
    "example",
    "examples",
    "externalDocs",
    "summary", // Often redundant with operationId
];

/// Token Optimizer - applies 4-stage optimization pipeline
pub struct TokenOptimizer {
    settings: OptimizationSettings,
}

impl TokenOptimizer {
    /// Create a new optimizer with given settings
    pub fn new(settings: OptimizationSettings) -> Self {
        Self { settings }
    }

    /// Create optimizer with default settings (no optimization)
    pub fn none() -> Self {
        Self {
            settings: OptimizationSettings::default(),
        }
    }

    /// Optimize a JSON value through the pipeline
    ///
    /// Returns (optimized_value, stats)
    pub fn optimize(&self, value: &Value) -> (Value, OptimizationStats) {
        if self.settings.level == OptimizationLevel::None {
            return (value.clone(), OptimizationStats::default());
        }

        let input_size = value.to_string().len();
        let mut result = value.clone();

        // Stage 1: Null removal (always for Moderate+)
        result = self.remove_nulls(&result);

        // Stage 2: Schema pruning (Aggressive only)
        if self.settings.level == OptimizationLevel::Aggressive {
            result = self.prune_schemas(&result);
        }

        // Stage 3: Key shortening (Aggressive only)
        if self.settings.level == OptimizationLevel::Aggressive {
            result = self.shorten_keys(&result);
        }

        // Stage 4: Pagination injection (always for Moderate+)
        let max_items = self
            .settings
            .max_response_tokens
            .map(|t| t / 100)
            .unwrap_or(10);
        result = self.inject_pagination(&result, max_items);

        let output_size = result.to_string().len();
        let stats = OptimizationStats {
            input_bytes: input_size,
            output_bytes: output_size,
            reduction_pct: if input_size > 0 {
                ((input_size - output_size) as f64 / input_size as f64 * 100.0) as u8
            } else {
                0
            },
        };

        debug!(
            input_bytes = stats.input_bytes,
            output_bytes = stats.output_bytes,
            reduction_pct = stats.reduction_pct,
            level = ?self.settings.level,
            "Token optimization applied"
        );

        (result, stats)
    }

    /// Optimize a JSON string (parses, optimizes, re-serializes)
    pub fn optimize_string(&self, json_str: &str) -> (String, OptimizationStats) {
        if self.settings.level == OptimizationLevel::None {
            return (
                json_str.to_string(),
                OptimizationStats {
                    input_bytes: json_str.len(),
                    output_bytes: json_str.len(),
                    reduction_pct: 0,
                },
            );
        }

        match serde_json::from_str::<Value>(json_str) {
            Ok(value) => {
                let (optimized, stats) = self.optimize(&value);
                (optimized.to_string(), stats)
            }
            Err(_) => {
                // Not valid JSON, return as-is
                (
                    json_str.to_string(),
                    OptimizationStats {
                        input_bytes: json_str.len(),
                        output_bytes: json_str.len(),
                        reduction_pct: 0,
                    },
                )
            }
        }
    }

    /// Stage 1: Remove null, empty strings, empty arrays, empty objects
    fn remove_nulls(&self, value: &Value) -> Value {
        match value {
            Value::Object(map) => {
                let cleaned: Map<String, Value> = map
                    .iter()
                    .filter_map(|(k, v)| {
                        let cleaned_v = self.remove_nulls(v);
                        if self.is_empty_value(&cleaned_v) {
                            None
                        } else {
                            Some((k.clone(), cleaned_v))
                        }
                    })
                    .collect();
                Value::Object(cleaned)
            }
            Value::Array(arr) => {
                let cleaned: Vec<Value> = arr
                    .iter()
                    .map(|v| self.remove_nulls(v))
                    .filter(|v| !self.is_empty_value(v))
                    .collect();
                Value::Array(cleaned)
            }
            _ => value.clone(),
        }
    }

    /// Check if a value is considered "empty"
    fn is_empty_value(&self, value: &Value) -> bool {
        match value {
            Value::Null => true,
            Value::String(s) => s.is_empty(),
            Value::Array(arr) => arr.is_empty(),
            Value::Object(map) => map.is_empty(),
            _ => false,
        }
    }

    /// Stage 2: Prune OpenAPI schema verbosity
    fn prune_schemas(&self, value: &Value) -> Value {
        match value {
            Value::Object(map) => {
                let pruned: Map<String, Value> = map
                    .iter()
                    .filter_map(|(k, v)| {
                        // Remove specified keys
                        if PRUNE_KEYS.contains(&k.as_str()) {
                            return None;
                        }
                        // Remove x-* extension keys
                        if k.starts_with("x-") {
                            return None;
                        }
                        Some((k.clone(), self.prune_schemas(v)))
                    })
                    .collect();
                Value::Object(pruned)
            }
            Value::Array(arr) => Value::Array(arr.iter().map(|v| self.prune_schemas(v)).collect()),
            _ => value.clone(),
        }
    }

    /// Stage 3: Shorten common keys
    fn shorten_keys(&self, value: &Value) -> Value {
        match value {
            Value::Object(map) => {
                let shortened: Map<String, Value> = map
                    .iter()
                    .map(|(k, v)| {
                        let new_key = KEY_MAPPINGS
                            .iter()
                            .find(|(long, _)| *long == k.as_str())
                            .map(|(_, short)| short.to_string())
                            .unwrap_or_else(|| k.clone());
                        (new_key, self.shorten_keys(v))
                    })
                    .collect();
                Value::Object(shortened)
            }
            Value::Array(arr) => Value::Array(arr.iter().map(|v| self.shorten_keys(v)).collect()),
            _ => value.clone(),
        }
    }

    /// Stage 4: Inject pagination for large arrays
    fn inject_pagination(&self, value: &Value, max_items: usize) -> Value {
        match value {
            Value::Object(map) => {
                let paginated: Map<String, Value> = map
                    .iter()
                    .map(|(k, v)| (k.clone(), self.inject_pagination(v, max_items)))
                    .collect();
                Value::Object(paginated)
            }
            Value::Array(arr) if arr.len() > max_items => {
                let remaining = arr.len() - max_items;
                let mut truncated: Vec<Value> = arr.iter().take(max_items).cloned().collect();
                truncated.push(Value::String(format!(
                    "...and {} more. Use pagination to see all.",
                    remaining
                )));
                Value::Array(truncated)
            }
            Value::Array(arr) => Value::Array(
                arr.iter()
                    .map(|v| self.inject_pagination(v, max_items))
                    .collect(),
            ),
            _ => value.clone(),
        }
    }
}

/// Optimization statistics
#[derive(Debug, Clone, Default)]
pub struct OptimizationStats {
    /// Input size in bytes
    pub input_bytes: usize,
    /// Output size in bytes
    pub output_bytes: usize,
    /// Reduction percentage (0-100)
    pub reduction_pct: u8,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_remove_nulls() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Moderate,
            ..Default::default()
        });

        let input = json!({
            "name": "test",
            "value": null,
            "empty_string": "",
            "empty_array": [],
            "empty_object": {},
            "valid_array": [1, null, 2],
            "nested": {
                "keep": "this",
                "remove": null
            }
        });

        let result = optimizer.remove_nulls(&input);

        assert!(result.get("value").is_none());
        assert!(result.get("empty_string").is_none());
        assert!(result.get("empty_array").is_none());
        assert!(result.get("empty_object").is_none());
        assert_eq!(result.get("name").unwrap(), "test");
        assert_eq!(result["valid_array"].as_array().unwrap().len(), 2);
        assert!(result["nested"].get("remove").is_none());
        assert_eq!(result["nested"]["keep"], "this");
    }

    #[test]
    fn test_prune_schemas() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            ..Default::default()
        });

        let input = json!({
            "type": "object",
            "description": "This is a long description that wastes tokens",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The unique identifier",
                    "example": "abc-123"
                }
            },
            "x-custom-extension": "remove this",
            "externalDocs": {
                "url": "https://example.com"
            }
        });

        let result = optimizer.prune_schemas(&input);

        assert!(result.get("description").is_none());
        assert!(result.get("x-custom-extension").is_none());
        assert!(result.get("externalDocs").is_none());
        assert_eq!(result["type"], "object");
        assert!(result["properties"]["id"].get("description").is_none());
        assert!(result["properties"]["id"].get("example").is_none());
        assert_eq!(result["properties"]["id"]["type"], "string");
    }

    #[test]
    fn test_shorten_keys() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            ..Default::default()
        });

        let input = json!({
            "description": "test",
            "properties": {
                "name": {
                    "type": "string"
                }
            },
            "required": ["name"],
            "parameters": [],
            "responses": {}
        });

        let result = optimizer.shorten_keys(&input);

        assert!(result.get("desc").is_some());
        assert!(result.get("description").is_none());
        assert!(result.get("props").is_some());
        assert!(result.get("properties").is_none());
        assert!(result.get("req").is_some());
        assert!(result.get("params").is_some());
        assert!(result.get("resp").is_some());
    }

    #[test]
    fn test_inject_pagination() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Moderate,
            max_response_tokens: Some(500), // 5 items max
            ..Default::default()
        });

        let input = json!({
            "items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        });

        let result = optimizer.inject_pagination(&input, 5);
        let items = result["items"].as_array().unwrap();

        assert_eq!(items.len(), 6); // 5 items + pagination message
        assert_eq!(
            items[5].as_str().unwrap(),
            "...and 7 more. Use pagination to see all."
        );
    }

    #[test]
    fn test_level_none_no_change() {
        let optimizer = TokenOptimizer::none();

        let input = json!({
            "description": "keep",
            "value": null,
            "items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        });

        let (result, stats) = optimizer.optimize(&input);

        assert_eq!(result, input);
        assert_eq!(stats.reduction_pct, 0);
    }

    #[test]
    fn test_aggressive_significant_reduction() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            max_response_tokens: Some(1000),
            ..Default::default()
        });

        // Simulated OpenAPI schema
        let input = json!({
            "openapi": "3.0.0",
            "info": {
                "title": "Test API",
                "description": "A very long description that provides context but wastes tokens for AI clients who just need the structure",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "getUsers",
                        "description": "Get all users from the database with pagination support",
                        "parameters": [
                            {
                                "name": "limit",
                                "description": "Maximum number of results",
                                "in": "query",
                                "required": false,
                                "schema": {
                                    "type": "integer",
                                    "description": "The limit value",
                                    "example": 10
                                }
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "Successful response",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "description": "List of users",
                                            "items": {
                                                "type": "object",
                                                "description": "User object",
                                                "properties": {
                                                    "id": {
                                                        "type": "string",
                                                        "description": "User ID"
                                                    },
                                                    "name": {
                                                        "type": "string",
                                                        "description": "User name"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "x-custom": "extension data"
                    }
                }
            }
        });

        let (result, stats) = optimizer.optimize(&input);

        // Should have significant reduction
        assert!(
            stats.reduction_pct >= 30,
            "Expected at least 30% reduction, got {}%",
            stats.reduction_pct
        );

        // Verify structure preserved
        assert!(result.get("openapi").is_some());
        assert!(result["paths"]["/users"]["get"].get("opId").is_some()); // shortened key

        // Verify descriptions removed
        assert!(result["info"].get("desc").is_none()); // pruned then shortened
        assert!(result["paths"]["/users"]["get"].get("desc").is_none());
    }

    #[test]
    fn test_optimize_string() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Moderate,
            ..Default::default()
        });

        let input = r#"{"name": "test", "value": null, "empty": ""}"#;
        let (result, stats) = optimizer.optimize_string(input);

        let parsed: Value = serde_json::from_str(&result).unwrap();
        assert!(parsed.get("value").is_none());
        assert!(stats.reduction_pct > 0);
    }

    #[test]
    fn test_optimize_string_invalid_json() {
        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            ..Default::default()
        });

        let input = "not valid json";
        let (result, stats) = optimizer.optimize_string(input);

        assert_eq!(result, input);
        assert_eq!(stats.reduction_pct, 0);
    }

    #[test]
    fn test_optimization_performance() {
        use std::time::Instant;

        let optimizer = TokenOptimizer::new(OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            max_response_tokens: Some(4096),
            ..Default::default()
        });

        // Generate a ~10KB payload
        let mut items = Vec::new();
        for i in 0..100 {
            items.push(json!({
                "id": format!("item-{}", i),
                "name": format!("Item number {}", i),
                "description": "A moderately long description that adds to the payload size",
                "value": i,
                "metadata": {
                    "created": "2024-01-01",
                    "updated": null,
                    "tags": ["tag1", "tag2"]
                }
            }));
        }
        let input = json!({ "items": items });
        let input_str = input.to_string();
        assert!(input_str.len() > 10000, "Input should be > 10KB");

        let start = Instant::now();
        let (_result, _stats) = optimizer.optimize(&input);
        let elapsed = start.elapsed();

        assert!(
            elapsed.as_millis() < 50,
            "Optimization should complete in < 50ms, took {:?}",
            elapsed
        );
    }

    #[test]
    fn test_settings_metadata_roundtrip() {
        let settings = OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            max_response_tokens: Some(4096),
            include_key_map: true,
        };

        let metadata = settings.to_metadata().unwrap();
        let restored = OptimizationSettings::from_metadata(&metadata).unwrap();

        assert_eq!(restored.level, settings.level);
        assert_eq!(restored.max_response_tokens, settings.max_response_tokens);
        assert_eq!(restored.include_key_map, settings.include_key_map);
    }

    #[test]
    fn test_is_enabled() {
        let none = OptimizationSettings::default();
        assert!(!none.is_enabled());

        let moderate = OptimizationSettings {
            level: OptimizationLevel::Moderate,
            ..Default::default()
        };
        assert!(moderate.is_enabled());

        let aggressive = OptimizationSettings {
            level: OptimizationLevel::Aggressive,
            ..Default::default()
        };
        assert!(aggressive.is_enabled());
    }
}
