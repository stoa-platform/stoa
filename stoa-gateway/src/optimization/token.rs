//! Token Optimization Pipeline
//!
//! Implements multi-stage token reduction for AI clients:
//! - Schema pruning (strip descriptions, examples, x-* extensions)
//! - Null/empty removal
//! - Key shortening (reversible mapping)
//! - Pagination injection for large arrays

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::HashMap;

/// Key shortening mappings (forward: long -> short)
pub static KEY_SHORTENING_MAP: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    let mut m = HashMap::new();
    // OpenAPI schema keys
    m.insert("description", "desc");
    m.insert("properties", "props");
    m.insert("additionalProperties", "addProps");
    m.insert("required", "req");
    m.insert("minimum", "min");
    m.insert("maximum", "max");
    m.insert("minLength", "minLen");
    m.insert("maxLength", "maxLen");
    m.insert("minItems", "minItems"); // Already short
    m.insert("maxItems", "maxItems"); // Already short
    m.insert("nullable", "null");
    m.insert("readOnly", "ro");
    m.insert("writeOnly", "wo");
    m.insert("deprecated", "depr");
    m.insert("default", "def");
    m.insert("example", "ex");
    m.insert("examples", "exs");
    m.insert("format", "fmt");
    m.insert("pattern", "pat");
    m.insert("enum", "enum"); // Already short
    m.insert("items", "items"); // Already short
    m.insert("allOf", "allOf"); // Keep as-is (JSON Schema keyword)
    m.insert("oneOf", "oneOf");
    m.insert("anyOf", "anyOf");
    m.insert("parameters", "params");
    m.insert("requestBody", "reqBody");
    m.insert("responses", "resp");
    m.insert("operationId", "opId");
    m.insert("summary", "sum");
    m.insert("content", "cont");
    m.insert("schema", "sch");
    // MCP-specific
    m.insert("inputSchema", "inSch");
    m.insert("annotations", "annot");
    m.insert("arguments", "args");
    m.insert("displayName", "name");
    m
});

/// Key expansion mappings (reverse: short -> long)
pub static KEY_EXPANSION_MAP: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    KEY_SHORTENING_MAP
        .iter()
        .filter(|(k, v)| k != v) // Only include entries that actually changed
        .map(|(k, v)| (*v, *k))
        .collect()
});

/// Optimization level for token reduction
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OptimizationLevel {
    /// No optimization - pass through as-is
    None,
    /// Moderate optimization (recommended for most clients)
    /// - Remove null/empty fields
    /// - Strip descriptions from nested schemas
    /// - Pagination injection (50 items)
    #[default]
    Moderate,
    /// Aggressive optimization (maximum token savings)
    /// - All moderate optimizations
    /// - Key shortening
    /// - Strip ALL descriptions and examples
    /// - Pagination injection (20 items)
    Aggressive,
}

impl OptimizationLevel {
    /// Parse from string (for MCP initialize capability)
    #[allow(dead_code)]
    pub fn from_str_opt(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "none" | "off" | "disabled" => Some(Self::None),
            "moderate" | "medium" | "default" => Some(Self::Moderate),
            "aggressive" | "high" | "maximum" | "max" => Some(Self::Aggressive),
            _ => None,
        }
    }

    /// Get the array pagination limit for this level
    #[allow(dead_code)]
    pub fn array_limit(&self) -> usize {
        match self {
            Self::None => usize::MAX,
            Self::Moderate => 50,
            Self::Aggressive => 20,
        }
    }
}

/// Optimization preferences (per-session)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OptimizationPrefs {
    /// Optimization level
    pub level: OptimizationLevel,
    /// Maximum response tokens (soft limit, best effort)
    #[serde(default)]
    pub max_response_tokens: Option<usize>,
    /// Whether to shorten keys (only in Aggressive mode by default)
    #[serde(default)]
    pub shorten_keys: Option<bool>,
    /// Custom array pagination limit (overrides level default)
    #[serde(default)]
    pub array_limit: Option<usize>,
}

impl OptimizationPrefs {
    /// Create with a specific level
    pub fn with_level(level: OptimizationLevel) -> Self {
        Self {
            level,
            ..Default::default()
        }
    }

    /// Should keys be shortened?
    #[allow(dead_code)]
    pub fn should_shorten_keys(&self) -> bool {
        self.shorten_keys
            .unwrap_or(self.level == OptimizationLevel::Aggressive)
    }

    /// Get effective array limit
    #[allow(dead_code)]
    pub fn effective_array_limit(&self) -> usize {
        self.array_limit.unwrap_or_else(|| self.level.array_limit())
    }
}

/// Result of optimization with metrics
#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct OptimizationResult {
    /// Optimized JSON value
    pub value: Value,
    /// Input size in bytes
    pub input_bytes: usize,
    /// Output size in bytes
    pub output_bytes: usize,
    /// Reduction ratio (0.0 to 1.0, where 0.8 = 80% reduction)
    pub reduction_ratio: f64,
    /// Number of fields removed
    pub fields_removed: usize,
    /// Number of arrays truncated
    pub arrays_truncated: usize,
}

impl OptimizationResult {
    /// Calculate reduction percentage
    #[allow(dead_code)]
    pub fn reduction_percent(&self) -> f64 {
        self.reduction_ratio * 100.0
    }
}

/// Token optimizer
#[allow(dead_code)]
pub struct TokenOptimizer {
    prefs: OptimizationPrefs,
}

#[allow(dead_code)]
impl TokenOptimizer {
    /// Create a new optimizer with the given preferences
    pub fn new(prefs: OptimizationPrefs) -> Self {
        Self { prefs }
    }

    /// Create an optimizer with default moderate level
    #[allow(dead_code)]
    pub fn moderate() -> Self {
        Self::new(OptimizationPrefs::with_level(OptimizationLevel::Moderate))
    }

    /// Create an optimizer with aggressive level
    #[allow(dead_code)]
    pub fn aggressive() -> Self {
        Self::new(OptimizationPrefs::with_level(OptimizationLevel::Aggressive))
    }

    /// Create a no-op optimizer (passthrough)
    #[allow(dead_code)]
    pub fn none() -> Self {
        Self::new(OptimizationPrefs::with_level(OptimizationLevel::None))
    }

    /// Get the optimization level
    #[allow(dead_code)]
    pub fn level(&self) -> OptimizationLevel {
        self.prefs.level
    }

    /// Optimize a JSON value
    pub fn optimize(&self, value: &Value) -> OptimizationResult {
        let input_json = serde_json::to_string(value).unwrap_or_default();
        let input_bytes = input_json.len();

        if self.prefs.level == OptimizationLevel::None {
            return OptimizationResult {
                value: value.clone(),
                input_bytes,
                output_bytes: input_bytes,
                reduction_ratio: 0.0,
                fields_removed: 0,
                arrays_truncated: 0,
            };
        }

        let mut stats = OptimizationStats::default();
        let optimized = self.optimize_value(value, 0, &mut stats);

        let output_json = serde_json::to_string(&optimized).unwrap_or_default();
        let output_bytes = output_json.len();

        let reduction_ratio = if input_bytes > 0 {
            1.0 - (output_bytes as f64 / input_bytes as f64)
        } else {
            0.0
        };

        OptimizationResult {
            value: optimized,
            input_bytes,
            output_bytes,
            reduction_ratio,
            fields_removed: stats.fields_removed,
            arrays_truncated: stats.arrays_truncated,
        }
    }

    /// Optimize a JSON string (convenience method)
    pub fn optimize_str(&self, json: &str) -> Result<OptimizationResult, serde_json::Error> {
        let value: Value = serde_json::from_str(json)?;
        Ok(self.optimize(&value))
    }

    /// Internal recursive optimization
    fn optimize_value(&self, value: &Value, depth: usize, stats: &mut OptimizationStats) -> Value {
        match value {
            Value::Object(obj) => self.optimize_object(obj, depth, stats),
            Value::Array(arr) => self.optimize_array(arr, depth, stats),
            // Primitives pass through
            _ => value.clone(),
        }
    }

    /// Optimize a JSON object
    fn optimize_object(
        &self,
        obj: &Map<String, Value>,
        depth: usize,
        stats: &mut OptimizationStats,
    ) -> Value {
        let mut result = Map::new();

        for (key, value) in obj {
            // Skip keys that should be pruned
            if self.should_prune_key(key, depth) {
                stats.fields_removed += 1;
                continue;
            }

            // Skip null values
            if value.is_null() {
                stats.fields_removed += 1;
                continue;
            }

            // Skip empty arrays/objects in moderate+ mode
            if self.prefs.level != OptimizationLevel::None {
                if let Value::Array(arr) = value {
                    if arr.is_empty() {
                        stats.fields_removed += 1;
                        continue;
                    }
                }
                if let Value::Object(obj) = value {
                    if obj.is_empty() {
                        stats.fields_removed += 1;
                        continue;
                    }
                }
            }

            // Shorten key if enabled
            let output_key = if self.prefs.should_shorten_keys() {
                KEY_SHORTENING_MAP
                    .get(key.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| key.clone())
            } else {
                key.clone()
            };

            // Recursively optimize value
            let optimized_value = self.optimize_value(value, depth + 1, stats);
            result.insert(output_key, optimized_value);
        }

        Value::Object(result)
    }

    /// Optimize a JSON array
    fn optimize_array(
        &self,
        arr: &[Value],
        depth: usize,
        stats: &mut OptimizationStats,
    ) -> Value {
        let limit = self.prefs.effective_array_limit();

        if arr.len() > limit {
            stats.arrays_truncated += 1;

            let mut result: Vec<Value> = arr[..limit]
                .iter()
                .map(|v| self.optimize_value(v, depth + 1, stats))
                .collect();

            // Add truncation marker
            let remaining = arr.len() - limit;
            result.push(Value::String(format!("...and {} more items", remaining)));

            Value::Array(result)
        } else {
            Value::Array(
                arr.iter()
                    .map(|v| self.optimize_value(v, depth + 1, stats))
                    .collect(),
            )
        }
    }

    /// Check if a key should be pruned
    fn should_prune_key(&self, key: &str, depth: usize) -> bool {
        match self.prefs.level {
            OptimizationLevel::None => false,
            OptimizationLevel::Moderate => {
                // Strip x-* extensions everywhere
                if key.starts_with("x-") {
                    return true;
                }
                // Strip descriptions/examples only at depth > 1 (nested schemas)
                if depth > 1 && (key == "description" || key == "example" || key == "examples") {
                    return true;
                }
                false
            }
            OptimizationLevel::Aggressive => {
                // Strip x-* extensions
                if key.starts_with("x-") {
                    return true;
                }
                // Strip descriptions and examples everywhere
                if key == "description" || key == "example" || key == "examples" {
                    return true;
                }
                // Strip verbose OpenAPI metadata
                if key == "externalDocs" || key == "servers" || key == "info" {
                    return true;
                }
                false
            }
        }
    }
}

/// Internal stats tracking during optimization
#[allow(dead_code)]
#[derive(Default)]
struct OptimizationStats {
    fields_removed: usize,
    arrays_truncated: usize,
}

/// Expand shortened keys back to their original form
///
/// This is useful when a client needs to interpret the response
/// and wants full key names.
#[allow(dead_code)]
pub fn expand_keys(value: &Value) -> Value {
    match value {
        Value::Object(obj) => {
            let mut result = Map::new();
            for (key, val) in obj {
                let expanded_key = KEY_EXPANSION_MAP
                    .get(key.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_else(|| key.clone());
                result.insert(expanded_key, expand_keys(val));
            }
            Value::Object(result)
        }
        Value::Array(arr) => Value::Array(arr.iter().map(expand_keys).collect()),
        _ => value.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_optimization_level_from_str() {
        assert_eq!(
            OptimizationLevel::from_str_opt("none"),
            Some(OptimizationLevel::None)
        );
        assert_eq!(
            OptimizationLevel::from_str_opt("moderate"),
            Some(OptimizationLevel::Moderate)
        );
        assert_eq!(
            OptimizationLevel::from_str_opt("aggressive"),
            Some(OptimizationLevel::Aggressive)
        );
        assert_eq!(
            OptimizationLevel::from_str_opt("max"),
            Some(OptimizationLevel::Aggressive)
        );
        assert_eq!(OptimizationLevel::from_str_opt("unknown"), None);
    }

    #[test]
    fn test_no_optimization() {
        let optimizer = TokenOptimizer::none();
        let input = json!({
            "description": "A test",
            "nullable": null,
            "items": []
        });

        let result = optimizer.optimize(&input);
        assert_eq!(result.value, input);
        assert_eq!(result.reduction_ratio, 0.0);
    }

    #[test]
    fn test_null_removal() {
        let optimizer = TokenOptimizer::moderate();
        let input = json!({
            "name": "test",
            "value": null,
            "nested": {
                "keep": 1,
                "remove": null
            }
        });

        let result = optimizer.optimize(&input);
        assert!(result.value.get("value").is_none());
        assert!(result.value["nested"].get("remove").is_none());
        assert_eq!(result.value["nested"]["keep"], 1);
    }

    #[test]
    fn test_empty_removal() {
        let optimizer = TokenOptimizer::moderate();
        let input = json!({
            "name": "test",
            "empty_array": [],
            "empty_object": {},
            "valid_array": [1, 2, 3]
        });

        let result = optimizer.optimize(&input);
        assert!(result.value.get("empty_array").is_none());
        assert!(result.value.get("empty_object").is_none());
        assert!(result.value.get("valid_array").is_some());
    }

    #[test]
    fn test_x_extension_removal() {
        let optimizer = TokenOptimizer::moderate();
        let input = json!({
            "name": "test",
            "x-custom": "should be removed",
            "x-another": { "nested": true }
        });

        let result = optimizer.optimize(&input);
        assert!(result.value.get("x-custom").is_none());
        assert!(result.value.get("x-another").is_none());
        assert_eq!(result.fields_removed, 2);
    }

    #[test]
    fn test_nested_description_removal_moderate() {
        let optimizer = TokenOptimizer::moderate();
        let input = json!({
            "description": "Top level - keep",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Nested - remove in moderate"
                }
            }
        });

        let result = optimizer.optimize(&input);
        // Top-level description kept in moderate mode
        assert!(result.value.get("description").is_some());
        // Nested description removed
        assert!(result.value["properties"]["field"]
            .get("description")
            .is_none());
    }

    #[test]
    fn test_aggressive_description_removal() {
        let optimizer = TokenOptimizer::aggressive();
        let input = json!({
            "description": "Top level - remove in aggressive",
            "name": "test"
        });

        let result = optimizer.optimize(&input);
        assert!(result.value.get("description").is_none());
        assert_eq!(result.value["name"], "test");
    }

    #[test]
    fn test_key_shortening() {
        let optimizer = TokenOptimizer::aggressive();
        let input = json!({
            "properties": {
                "field": {
                    "type": "string"
                }
            },
            "required": ["field"],
            "inputSchema": {}
        });

        let result = optimizer.optimize(&input);
        // Keys should be shortened
        assert!(result.value.get("props").is_some());
        assert!(result.value.get("properties").is_none());
        assert!(result.value.get("req").is_some());
        assert!(result.value.get("required").is_none());
    }

    #[test]
    fn test_array_pagination() {
        let mut prefs = OptimizationPrefs::with_level(OptimizationLevel::Moderate);
        prefs.array_limit = Some(3);
        let optimizer = TokenOptimizer::new(prefs);

        let input = json!({
            "items": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        });

        let result = optimizer.optimize(&input);
        let items = result.value["items"].as_array().unwrap();
        assert_eq!(items.len(), 4); // 3 items + marker
        assert_eq!(items[0], 1);
        assert_eq!(items[1], 2);
        assert_eq!(items[2], 3);
        assert_eq!(items[3], "...and 7 more items");
        assert_eq!(result.arrays_truncated, 1);
    }

    #[test]
    fn test_key_expansion() {
        let shortened = json!({
            "desc": "A description",
            "props": {
                "field": {
                    "fmt": "email"
                }
            },
            "req": ["field"]
        });

        let expanded = expand_keys(&shortened);
        assert!(expanded.get("description").is_some());
        assert!(expanded.get("desc").is_none());
        assert!(expanded.get("properties").is_some());
        assert!(expanded["properties"]["field"].get("format").is_some());
    }

    #[test]
    fn test_reduction_metrics() {
        let optimizer = TokenOptimizer::aggressive();
        let input = json!({
            "description": "This is a very long description that should be removed entirely in aggressive mode to save tokens for AI clients",
            "name": "api",
            "properties": {
                "field1": {
                    "type": "string",
                    "description": "Another description to remove",
                    "example": "example value"
                },
                "field2": {
                    "type": "integer",
                    "description": "Yet another description",
                    "x-custom": "extension to remove"
                }
            },
            "x-vendor-specific": "remove this too",
            "nullable": null,
            "empty": []
        });

        let result = optimizer.optimize(&input);

        // Should have significant reduction
        assert!(
            result.reduction_ratio > 0.5,
            "Expected >50% reduction, got {:.1}%",
            result.reduction_percent()
        );
        assert!(result.fields_removed > 5);
    }

    #[test]
    fn test_optimization_prefs_defaults() {
        let prefs = OptimizationPrefs::default();
        assert_eq!(prefs.level, OptimizationLevel::Moderate);
        assert!(!prefs.should_shorten_keys()); // Moderate doesn't shorten by default
        assert_eq!(prefs.effective_array_limit(), 50);
    }

    #[test]
    fn test_optimization_prefs_aggressive() {
        let prefs = OptimizationPrefs::with_level(OptimizationLevel::Aggressive);
        assert!(prefs.should_shorten_keys());
        assert_eq!(prefs.effective_array_limit(), 20);
    }

    #[test]
    fn test_real_world_openapi_schema() {
        let optimizer = TokenOptimizer::aggressive();
        let input = json!({
            "openapi": "3.0.0",
            "info": {
                "title": "Pet Store API",
                "description": "A sample API that uses a petstore as an example",
                "version": "1.0.0"
            },
            "paths": {
                "/pets": {
                    "get": {
                        "summary": "List all pets",
                        "description": "Returns all pets from the system that the user has access to",
                        "operationId": "listPets",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "description": "How many items to return at one time",
                                "required": false,
                                "schema": {
                                    "type": "integer",
                                    "format": "int32",
                                    "minimum": 1,
                                    "maximum": 100,
                                    "default": 10,
                                    "x-example": 25
                                }
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "A paged array of pets",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/Pet"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Pet": {
                        "type": "object",
                        "description": "A pet in the store",
                        "required": ["id", "name"],
                        "properties": {
                            "id": {
                                "type": "integer",
                                "format": "int64",
                                "description": "Unique identifier for the pet",
                                "example": 1
                            },
                            "name": {
                                "type": "string",
                                "description": "Name of the pet",
                                "example": "Fluffy"
                            },
                            "tag": {
                                "type": "string",
                                "description": "Tag for grouping pets",
                                "x-nullable": true
                            }
                        }
                    }
                }
            }
        });

        let result = optimizer.optimize(&input);

        // Should achieve significant reduction on realistic OpenAPI
        assert!(
            result.reduction_ratio > 0.3,
            "Expected >30% reduction on OpenAPI, got {:.1}%",
            result.reduction_percent()
        );

        // Verify key transformations happened
        let output = &result.value;
        assert!(output.get("info").is_none()); // info stripped in aggressive
        assert!(output["paths"]["/pets"]["get"].get("desc").is_none()); // description stripped

        // Verify x-* extensions removed
        let params = &output["paths"]["/pets"]["get"]["params"];
        if let Some(arr) = params.as_array() {
            if !arr.is_empty() {
                assert!(arr[0]["sch"].get("x-example").is_none());
            }
        }
    }
}
