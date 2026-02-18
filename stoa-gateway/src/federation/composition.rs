//! Tool Composition
//!
//! Enables composing multiple tools into a single compound tool.
//! Sequential execution with data passing between steps.

// Infrastructure prepared for K8s CRD watcher integration (Phase 7)
#![allow(dead_code)]

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{debug, error, warn};

use crate::mcp::tools::{Tool, ToolContext, ToolError, ToolRegistry, ToolResult, ToolSchema};
use crate::uac::Action;

/// A composed tool that executes multiple tools in sequence
pub struct ComposedTool {
    /// Tool name
    name: String,
    /// Human-readable description
    description: String,
    /// Input schema for the composed tool
    input_schema: ToolSchema,
    /// Execution steps
    steps: Vec<CompositionStep>,
    /// Tool registry for resolving step tools
    registry: Arc<ToolRegistry>,
}

/// A single step in a tool composition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositionStep {
    /// Name of the tool to execute
    pub tool_name: String,
    /// Input mapping: composed input key -> step tool input key
    #[serde(default)]
    pub input_mapping: HashMap<String, InputMapping>,
    /// Optional description of what this step does
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// Input mapping for a composition step
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum InputMapping {
    /// Direct input from composed tool arguments
    Direct(String),
    /// Reference to a previous step's output
    StepOutput {
        step: usize,
        #[serde(default)]
        path: Option<String>,
    },
    /// Static value
    Static(Value),
}

impl ComposedTool {
    /// Create a new composed tool
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        input_schema: ToolSchema,
        steps: Vec<CompositionStep>,
        registry: Arc<ToolRegistry>,
    ) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            input_schema,
            steps,
            registry,
        }
    }

    /// Resolve input mappings for a step
    fn resolve_inputs(
        &self,
        step: &CompositionStep,
        initial_args: &Value,
        previous_results: &[Value],
    ) -> Result<Value, ToolError> {
        let mut resolved = serde_json::Map::new();

        for (target_key, mapping) in &step.input_mapping {
            let value = match mapping {
                InputMapping::Direct(source_key) => {
                    initial_args.get(source_key).cloned().unwrap_or(Value::Null)
                }
                InputMapping::StepOutput {
                    step: step_idx,
                    path,
                } => {
                    if *step_idx >= previous_results.len() {
                        return Err(ToolError::ExecutionFailed(format!(
                            "Step {} references non-existent step {}",
                            step.tool_name, step_idx
                        )));
                    }
                    let result = &previous_results[*step_idx];
                    if let Some(json_path) = path {
                        // Simple JSONPath-like extraction (just top-level keys)
                        result.get(json_path).cloned().unwrap_or(Value::Null)
                    } else {
                        result.clone()
                    }
                }
                InputMapping::Static(value) => value.clone(),
            };
            resolved.insert(target_key.clone(), value);
        }

        Ok(Value::Object(resolved))
    }
}

#[async_trait]
impl Tool for ComposedTool {
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn input_schema(&self) -> ToolSchema {
        self.input_schema.clone()
    }

    fn required_action(&self) -> Action {
        // Return the most "dangerous" action from all steps
        let mut max_action = Action::Read;
        for step in &self.steps {
            if let Some(tool) = self.registry.get(&step.tool_name) {
                let action = tool.required_action();
                if action_severity(&action) > action_severity(&max_action) {
                    max_action = action;
                }
            }
        }
        max_action
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        debug!(
            tool = %self.name,
            steps = self.steps.len(),
            "Executing composed tool"
        );

        let mut results: Vec<Value> = Vec::new();

        for (idx, step) in self.steps.iter().enumerate() {
            debug!(
                step = idx,
                tool = %step.tool_name,
                "Executing composition step"
            );

            // Get the tool for this step
            let tool = self.registry.get(&step.tool_name).ok_or_else(|| {
                ToolError::ExecutionFailed(format!(
                    "Composed tool step {} references unknown tool: {}",
                    idx, step.tool_name
                ))
            })?;

            // Resolve inputs for this step
            let step_args = if step.input_mapping.is_empty() {
                // If no mapping, pass initial args
                args.clone()
            } else {
                self.resolve_inputs(step, &args, &results)?
            };

            // Execute the step
            match tool.execute(step_args, ctx).await {
                Ok(result) => {
                    // Parse result content as JSON if possible
                    let result_value = if !result.content.is_empty() {
                        if let Some(first) = result.content.first() {
                            // Extract text from ToolContent enum
                            let text = match first {
                                crate::mcp::tools::ToolContent::Text { text } => text.clone(),
                                crate::mcp::tools::ToolContent::Resource { text, .. } => {
                                    text.clone().unwrap_or_default()
                                }
                                crate::mcp::tools::ToolContent::Image { .. } => String::new(),
                            };
                            serde_json::from_str(&text).unwrap_or(Value::String(text))
                        } else {
                            Value::Null
                        }
                    } else {
                        Value::Null
                    };
                    results.push(result_value);
                }
                Err(e) => {
                    error!(
                        step = idx,
                        tool = %step.tool_name,
                        error = %e,
                        "Composition step failed"
                    );
                    return Err(ToolError::ExecutionFailed(format!(
                        "Step {} ({}) failed: {}",
                        idx, step.tool_name, e
                    )));
                }
            }
        }

        // Return the last step's result
        if let Some(last_result) = results.last() {
            Ok(ToolResult::text(
                serde_json::to_string_pretty(last_result).unwrap_or_default(),
            ))
        } else {
            warn!(tool = %self.name, "Composed tool has no steps");
            Ok(ToolResult::text("{}"))
        }
    }
}

/// Map action to severity level for escalation comparison
fn action_severity(action: &Action) -> u8 {
    match action {
        Action::Read | Action::ViewMetrics | Action::ViewLogs | Action::ViewAudit => 0,
        Action::List | Action::Search => 1,
        Action::Create
        | Action::Update
        | Action::CreateApi
        | Action::UpdateApi
        | Action::PublishApi
        | Action::DeprecateApi
        | Action::Subscribe
        | Action::ManageSubscription
        | Action::ManageUsers
        | Action::ManageTenants
        | Action::ManageContracts => 2,
        Action::Delete | Action::DeleteApi | Action::Unsubscribe => 3,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_composition_step_serialization() {
        let step = CompositionStep {
            tool_name: "step_tool".to_string(),
            input_mapping: HashMap::from([(
                "arg1".to_string(),
                InputMapping::Direct("input_arg".to_string()),
            )]),
            description: Some("First step".to_string()),
        };

        let json = serde_json::to_value(&step).unwrap();
        assert_eq!(json["tool_name"], "step_tool");
    }

    #[test]
    fn test_input_mapping_direct() {
        let mapping = InputMapping::Direct("source".to_string());
        let json = serde_json::to_value(&mapping).unwrap();
        assert_eq!(json, "source");
    }

    #[test]
    fn test_input_mapping_static() {
        let mapping = InputMapping::Static(json!({"key": "value"}));
        let json = serde_json::to_value(&mapping).unwrap();
        assert_eq!(json["key"], "value");
    }

    #[test]
    fn test_composed_tool_creation() {
        let registry = Arc::new(ToolRegistry::new());
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = ComposedTool::new(
            "composed_test",
            "A test composed tool",
            schema,
            vec![CompositionStep {
                tool_name: "inner_tool".to_string(),
                input_mapping: HashMap::new(),
                description: None,
            }],
            registry,
        );

        assert_eq!(tool.name(), "composed_test");
        assert_eq!(tool.required_action(), Action::Read);
    }

    #[test]
    fn test_resolve_inputs_direct() {
        let registry = Arc::new(ToolRegistry::new());
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = ComposedTool::new("test", "test", schema, vec![], registry);

        let step = CompositionStep {
            tool_name: "test".to_string(),
            input_mapping: HashMap::from([(
                "dest".to_string(),
                InputMapping::Direct("source".to_string()),
            )]),
            description: None,
        };

        let args = json!({"source": "value123"});
        let resolved = tool.resolve_inputs(&step, &args, &[]).unwrap();

        assert_eq!(resolved["dest"], "value123");
    }

    #[test]
    fn test_resolve_inputs_static() {
        let registry = Arc::new(ToolRegistry::new());
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = ComposedTool::new("test", "test", schema, vec![], registry);

        let step = CompositionStep {
            tool_name: "test".to_string(),
            input_mapping: HashMap::from([(
                "dest".to_string(),
                InputMapping::Static(json!("static_value")),
            )]),
            description: None,
        };

        let resolved = tool.resolve_inputs(&step, &json!({}), &[]).unwrap();

        assert_eq!(resolved["dest"], "static_value");
    }

    #[test]
    fn test_resolve_inputs_step_output() {
        let registry = Arc::new(ToolRegistry::new());
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let tool = ComposedTool::new("test", "test", schema, vec![], registry);

        let step = CompositionStep {
            tool_name: "test".to_string(),
            input_mapping: HashMap::from([(
                "dest".to_string(),
                InputMapping::StepOutput {
                    step: 0,
                    path: Some("result".to_string()),
                },
            )]),
            description: None,
        };

        let previous_results = vec![json!({"result": "from_step_0"})];
        let resolved = tool
            .resolve_inputs(&step, &json!({}), &previous_results)
            .unwrap();

        assert_eq!(resolved["dest"], "from_step_0");
    }

    #[test]
    fn test_action_severity_ordering() {
        assert!(action_severity(&Action::Read) < action_severity(&Action::List));
        assert!(action_severity(&Action::List) < action_severity(&Action::Create));
        assert!(action_severity(&Action::Create) < action_severity(&Action::Delete));
    }

    #[test]
    fn test_composed_action_escalation() {
        use crate::mcp::tools::dynamic_tool::DynamicTool;

        let registry = Arc::new(ToolRegistry::new());

        // Register a read tool and a delete tool
        let read_tool = DynamicTool::new(
            "read_step",
            "Reads data",
            "http://localhost/read",
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "test-tenant",
        )
        .with_action(Action::Read);

        let delete_tool = DynamicTool::new(
            "delete_step",
            "Deletes data",
            "http://localhost/delete",
            "DELETE",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: HashMap::new(),
                required: vec![],
            },
            "test-tenant",
        )
        .with_action(Action::Delete);

        registry.register(Arc::new(read_tool));
        registry.register(Arc::new(delete_tool));

        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let composed = ComposedTool::new(
            "read_then_delete",
            "Reads then deletes",
            schema,
            vec![
                CompositionStep {
                    tool_name: "read_step".to_string(),
                    input_mapping: HashMap::new(),
                    description: None,
                },
                CompositionStep {
                    tool_name: "delete_step".to_string(),
                    input_mapping: HashMap::new(),
                    description: None,
                },
            ],
            registry,
        );

        // Should escalate to Delete (the most dangerous action)
        assert_eq!(composed.required_action(), Action::Delete);
    }

    #[test]
    fn test_composed_action_no_registered_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let schema = ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::new(),
            required: vec![],
        };

        let composed = ComposedTool::new(
            "orphan",
            "Steps reference unknown tools",
            schema,
            vec![CompositionStep {
                tool_name: "nonexistent".to_string(),
                input_mapping: HashMap::new(),
                description: None,
            }],
            registry,
        );

        // Unknown tools are skipped, defaults to Read
        assert_eq!(composed.required_action(), Action::Read);
    }
}
