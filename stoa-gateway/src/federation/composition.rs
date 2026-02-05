//! Tool Composition Engine
//!
//! Enables creating compound tools that orchestrate multiple tool invocations
//! in sequence, with data mapping between steps.
//!
//! # Example Composition
//!
//! ```yaml
//! composition:
//!   name: stoa_onboard_api
//!   description: Complete API onboarding workflow
//!   steps:
//!     - name: create
//!       tool: stoa_create_api
//!       map:
//!         name: "$.input.name"
//!         version: "$.input.version"
//!     - name: deploy
//!       tool: stoa_deploy_api
//!       map:
//!         api_id: "$.steps.create.result.api_id"
//!         env: "dev"
//!     - name: subscribe
//!       tool: stoa_subscribe_api
//!       map:
//!         api_id: "$.steps.create.result.api_id"
//!         tenant_id: "$.context.tenant_id"
//! ```

use super::{FederationError, Result};
use crate::k8s::{CompositionConfig, CompositionStep};
use crate::mcp::tools::{ToolDefinition, ToolRegistry, ToolResult, ToolSchema};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, error, info, instrument, warn};

/// Result of executing a composition step
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepResult {
    /// Step name
    pub name: String,

    /// Tool that was invoked
    pub tool: String,

    /// Whether the step succeeded
    pub success: bool,

    /// Result value (if successful)
    pub result: Option<Value>,

    /// Error message (if failed)
    pub error: Option<String>,

    /// Execution time in milliseconds
    pub duration_ms: u64,
}

/// Context for composition execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositionContext {
    /// Input arguments to the composed tool
    pub input: Value,

    /// Context values (tenant_id, user_id, etc.)
    pub context: HashMap<String, Value>,

    /// Results from previous steps
    pub steps: HashMap<String, StepResult>,
}

impl CompositionContext {
    /// Create a new composition context
    pub fn new(input: Value, context: HashMap<String, Value>) -> Self {
        Self {
            input,
            context,
            steps: HashMap::new(),
        }
    }

    /// Add a step result
    pub fn add_step_result(&mut self, name: &str, result: StepResult) {
        self.steps.insert(name.to_string(), result);
    }

    /// Resolve a JSONPath expression against the context
    ///
    /// Supports:
    /// - `$.input.field` - Access input arguments
    /// - `$.context.tenant_id` - Access context values
    /// - `$.steps.step_name.result.field` - Access previous step results
    /// - `"literal"` - Literal string value
    pub fn resolve(&self, path: &str) -> Option<Value> {
        let path = path.trim();

        // Literal value (quoted string)
        if (path.starts_with('"') && path.ends_with('"'))
            || (path.starts_with('\'') && path.ends_with('\''))
        {
            return Some(Value::String(path[1..path.len() - 1].to_string()));
        }

        // JSONPath expression
        if !path.starts_with("$.") {
            // Treat as literal
            return Some(Value::String(path.to_string()));
        }

        let parts: Vec<&str> = path[2..].split('.').collect();
        if parts.is_empty() {
            return None;
        }

        match parts[0] {
            "input" => self.navigate_value(&self.input, &parts[1..]),
            "context" => {
                if parts.len() < 2 {
                    return None;
                }
                self.context.get(parts[1]).cloned()
            }
            "steps" => {
                if parts.len() < 3 {
                    return None;
                }
                let step_name = parts[1];
                let step_result = self.steps.get(step_name)?;

                match parts[2] {
                    "result" => {
                        if let Some(result) = &step_result.result {
                            self.navigate_value(result, &parts[3..])
                        } else {
                            None
                        }
                    }
                    "error" => step_result.error.clone().map(Value::String),
                    "success" => Some(Value::Bool(step_result.success)),
                    _ => None,
                }
            }
            _ => None,
        }
    }

    /// Navigate into a JSON value using path parts
    fn navigate_value(&self, value: &Value, parts: &[&str]) -> Option<Value> {
        if parts.is_empty() {
            return Some(value.clone());
        }

        match value {
            Value::Object(obj) => {
                let field = obj.get(parts[0])?;
                self.navigate_value(field, &parts[1..])
            }
            Value::Array(arr) => {
                // Support array index: $.steps.create.result.items[0]
                let part = parts[0];
                if let Some(idx_start) = part.find('[') {
                    let field = &part[..idx_start];
                    let idx_str = &part[idx_start + 1..part.len() - 1];
                    let idx: usize = idx_str.parse().ok()?;

                    if field.is_empty() {
                        arr.get(idx).cloned()
                    } else {
                        // Navigate to field first, then index
                        None // Complex case, not implemented
                    }
                } else {
                    None // Can't navigate into array without index
                }
            }
            _ => {
                if parts.is_empty() {
                    Some(value.clone())
                } else {
                    None
                }
            }
        }
    }
}

/// A composed tool that executes multiple steps
pub struct ComposedTool {
    /// Tool name
    name: String,

    /// Tool description
    description: String,

    /// Input schema for the composed tool
    input_schema: ToolSchema,

    /// Composition configuration
    config: CompositionConfig,

    /// Tool registry for looking up step tools
    registry: Arc<RwLock<ToolRegistry>>,
}

impl ComposedTool {
    /// Create a new composed tool
    pub fn new(config: CompositionConfig, registry: Arc<RwLock<ToolRegistry>>) -> Self {
        // Convert properties from Value to HashMap<String, Value>
        let properties_map: HashMap<String, Value> = config
            .input_schema
            .get("properties")
            .and_then(|v| v.as_object())
            .map(|obj| obj.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default();

        let input_schema = ToolSchema {
            schema_type: config
                .input_schema
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("object")
                .to_string(),
            properties: properties_map,
            required: config
                .input_schema
                .get("required")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default(),
        };

        Self {
            name: config.name.clone(),
            description: config.description.clone(),
            input_schema,
            config,
            registry,
        }
    }

    /// Execute the composed tool
    #[instrument(skip(self, context), fields(tool = %self.name))]
    pub async fn execute(
        &self,
        input: Value,
        context: HashMap<String, Value>,
    ) -> Result<CompositionResult> {
        let mut ctx = CompositionContext::new(input, context);
        let mut results = Vec::new();
        let start = std::time::Instant::now();

        info!(
            "Executing composed tool {} with {} steps",
            self.name,
            self.config.steps.len()
        );

        for (idx, step) in self.config.steps.iter().enumerate() {
            let step_name = step
                .name
                .clone()
                .unwrap_or_else(|| format!("step_{}", idx));

            // Check condition if present
            if let Some(condition) = &step.condition {
                let cond_result = ctx.resolve(condition);
                if !matches!(cond_result, Some(Value::Bool(true))) {
                    debug!(
                        "Skipping step {} due to condition: {}",
                        step_name, condition
                    );
                    continue;
                }
            }

            // Execute step
            match self.execute_step(step, &ctx, &step_name).await {
                Ok(result) => {
                    ctx.add_step_result(&step_name, result.clone());
                    results.push(result);
                }
                Err(e) => {
                    let error_result = StepResult {
                        name: step_name.clone(),
                        tool: step.tool.clone(),
                        success: false,
                        result: None,
                        error: Some(e.to_string()),
                        duration_ms: 0,
                    };

                    ctx.add_step_result(&step_name, error_result.clone());
                    results.push(error_result);

                    // Handle error based on strategy
                    match self.config.error_strategy.as_str() {
                        "fail_fast" => {
                            if !step.continue_on_error {
                                return Err(FederationError::Composition(format!(
                                    "Step {} failed: {}",
                                    step_name, e
                                )));
                            }
                        }
                        "continue" => {
                            warn!("Step {} failed (continuing): {}", step_name, e);
                        }
                        "rollback" => {
                            // In a full implementation, execute rollback logic
                            return Err(FederationError::Composition(format!(
                                "Step {} failed, rollback not implemented: {}",
                                step_name, e
                            )));
                        }
                        _ => {}
                    }
                }
            }
        }

        let duration_ms = start.elapsed().as_millis() as u64;
        let success = results.iter().all(|r| r.success);

        info!(
            "Composed tool {} completed in {}ms (success: {})",
            self.name, duration_ms, success
        );

        Ok(CompositionResult {
            success,
            steps: results,
            duration_ms,
            final_result: ctx
                .steps
                .values()
                .last()
                .and_then(|r| r.result.clone()),
        })
    }

    /// Execute a single step
    async fn execute_step(
        &self,
        step: &CompositionStep,
        ctx: &CompositionContext,
        step_name: &str,
    ) -> Result<StepResult> {
        let start = std::time::Instant::now();

        // Build arguments by resolving mappings
        let mut arguments = serde_json::Map::new();
        for (key, path) in &step.map {
            if let Some(value) = ctx.resolve(path) {
                arguments.insert(key.clone(), value);
            } else {
                warn!(
                    "Failed to resolve path {} for step {}",
                    path, step_name
                );
            }
        }

        debug!(
            "Step {} calling tool {} with args: {:?}",
            step_name, step.tool, arguments
        );

        // Look up and execute the tool
        // In a full implementation, this would use the registry to find and execute the tool
        // For now, return a placeholder result
        let result_value = serde_json::json!({
            "status": "executed",
            "tool": step.tool,
            "arguments": arguments
        });

        let duration_ms = start.elapsed().as_millis() as u64;

        Ok(StepResult {
            name: step_name.to_string(),
            tool: step.tool.clone(),
            success: true,
            result: Some(result_value),
            error: None,
            duration_ms,
        })
    }

    /// Get the tool definition
    pub fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.name.clone(),
            description: self.description.clone(),
            input_schema: self.input_schema.clone(),
        }
    }
}

/// Result of executing a composed tool
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositionResult {
    /// Whether all steps succeeded
    pub success: bool,

    /// Results from each step
    pub steps: Vec<StepResult>,

    /// Total execution time in milliseconds
    pub duration_ms: u64,

    /// Final result (from last successful step)
    pub final_result: Option<Value>,
}

impl CompositionResult {
    /// Convert to MCP tool result
    pub fn to_tool_result(&self) -> ToolResult {
        if self.success {
            ToolResult::text(serde_json::to_string_pretty(self).unwrap_or_default())
        } else {
            let error_msg = self
                .steps
                .iter()
                .find(|s| !s.success)
                .and_then(|s| s.error.clone())
                .unwrap_or_else(|| "Composition failed".to_string());

            // ToolResult::error returns is_error: Some(true)
            ToolResult {
                content: vec![crate::mcp::tools::ToolContent::Text { text: error_msg }],
                is_error: Some(true),
            }
        }
    }
}

/// Composition engine manages composed tools
pub struct CompositionEngine {
    /// Registered composed tools
    tools: RwLock<HashMap<String, Arc<ComposedTool>>>,

    /// Tool registry for looking up step tools
    registry: Arc<RwLock<ToolRegistry>>,
}

impl CompositionEngine {
    /// Create a new composition engine
    pub fn new(registry: Arc<RwLock<ToolRegistry>>) -> Self {
        Self {
            tools: RwLock::new(HashMap::new()),
            registry,
        }
    }

    /// Register a composed tool
    pub async fn register(&self, config: CompositionConfig) -> Result<()> {
        let name = config.name.clone();
        let tool = ComposedTool::new(config, Arc::clone(&self.registry));

        self.tools.write().await.insert(name.clone(), Arc::new(tool));

        info!("Registered composed tool: {}", name);
        Ok(())
    }

    /// Unregister a composed tool
    pub async fn unregister(&self, name: &str) -> Result<()> {
        self.tools.write().await.remove(name);
        info!("Unregistered composed tool: {}", name);
        Ok(())
    }

    /// Execute a composed tool
    pub async fn execute(
        &self,
        name: &str,
        input: Value,
        context: HashMap<String, Value>,
    ) -> Result<CompositionResult> {
        let tool = {
            let tools = self.tools.read().await;
            tools.get(name).cloned()
        };

        match tool {
            Some(t) => t.execute(input, context).await,
            None => Err(FederationError::Composition(format!(
                "Composed tool {} not found",
                name
            ))),
        }
    }

    /// Get all registered composed tools
    pub async fn tools(&self) -> Vec<String> {
        self.tools.read().await.keys().cloned().collect()
    }

    /// Get a composed tool's definition
    pub async fn get_definition(&self, name: &str) -> Option<ToolDefinition> {
        let tools = self.tools.read().await;
        tools.get(name).map(|t| t.definition())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_composition_context_resolve_input() {
        let ctx = CompositionContext::new(
            serde_json::json!({
                "name": "test-api",
                "version": "1.0"
            }),
            HashMap::new(),
        );

        assert_eq!(
            ctx.resolve("$.input.name"),
            Some(Value::String("test-api".to_string()))
        );
        assert_eq!(
            ctx.resolve("$.input.version"),
            Some(Value::String("1.0".to_string()))
        );
        assert_eq!(ctx.resolve("$.input.missing"), None);
    }

    #[test]
    fn test_composition_context_resolve_context() {
        let mut context = HashMap::new();
        context.insert(
            "tenant_id".to_string(),
            Value::String("tenant-acme".to_string()),
        );

        let ctx = CompositionContext::new(serde_json::json!({}), context);

        assert_eq!(
            ctx.resolve("$.context.tenant_id"),
            Some(Value::String("tenant-acme".to_string()))
        );
    }

    #[test]
    fn test_composition_context_resolve_step_result() {
        let mut ctx = CompositionContext::new(serde_json::json!({}), HashMap::new());

        ctx.add_step_result(
            "create",
            StepResult {
                name: "create".to_string(),
                tool: "stoa_create_api".to_string(),
                success: true,
                result: Some(serde_json::json!({
                    "api_id": "api-123",
                    "status": "created"
                })),
                error: None,
                duration_ms: 100,
            },
        );

        assert_eq!(
            ctx.resolve("$.steps.create.result.api_id"),
            Some(Value::String("api-123".to_string()))
        );
        assert_eq!(ctx.resolve("$.steps.create.success"), Some(Value::Bool(true)));
    }

    #[test]
    fn test_composition_context_resolve_literal() {
        let ctx = CompositionContext::new(serde_json::json!({}), HashMap::new());

        assert_eq!(
            ctx.resolve("\"literal_value\""),
            Some(Value::String("literal_value".to_string()))
        );
        assert_eq!(
            ctx.resolve("'single_quoted'"),
            Some(Value::String("single_quoted".to_string()))
        );
        assert_eq!(
            ctx.resolve("dev"),
            Some(Value::String("dev".to_string()))
        );
    }

    #[test]
    fn test_composition_result_to_tool_result() {
        let result = CompositionResult {
            success: true,
            steps: vec![StepResult {
                name: "test".to_string(),
                tool: "test_tool".to_string(),
                success: true,
                result: Some(serde_json::json!({"data": "test"})),
                error: None,
                duration_ms: 50,
            }],
            duration_ms: 50,
            final_result: Some(serde_json::json!({"data": "test"})),
        };

        let tool_result = result.to_tool_result();
        assert!(tool_result.is_error.is_none() || tool_result.is_error == Some(false));
    }

    #[test]
    fn test_composition_result_error_to_tool_result() {
        let result = CompositionResult {
            success: false,
            steps: vec![StepResult {
                name: "test".to_string(),
                tool: "test_tool".to_string(),
                success: false,
                result: None,
                error: Some("Something went wrong".to_string()),
                duration_ms: 50,
            }],
            duration_ms: 50,
            final_result: None,
        };

        let tool_result = result.to_tool_result();
        assert_eq!(tool_result.is_error, Some(true));
    }
}
