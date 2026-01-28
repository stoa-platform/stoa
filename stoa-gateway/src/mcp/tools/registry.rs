// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Tool Registry
//!
//! CAB-912: Registry for MCP tools with async execution.

use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::Arc;

use crate::mcp::protocol::{ToolCallResponse, ToolDefinition};
use crate::uac::EnforcementContext;

// =============================================================================
// Tool Trait
// =============================================================================

/// Trait for MCP tools that can be executed asynchronously.
///
/// Tools must be thread-safe (Send + Sync) to support concurrent execution.
#[async_trait]
pub trait Tool: Send + Sync {
    /// Returns the unique name of the tool.
    fn name(&self) -> &str;

    /// Returns a human-readable description of the tool.
    fn description(&self) -> &str;

    /// Returns the JSON Schema for the tool's input arguments.
    fn input_schema(&self) -> serde_json::Value;

    /// Execute the tool with the given arguments and enforcement context.
    ///
    /// # Arguments
    /// * `args` - Tool arguments as key-value pairs
    /// * `ctx` - Enforcement context with tenant, user, and policy information
    ///
    /// # Returns
    /// * `ToolCallResponse` with content blocks and error status
    async fn execute(
        &self,
        args: HashMap<String, serde_json::Value>,
        ctx: EnforcementContext,
    ) -> ToolCallResponse;
}

// =============================================================================
// Tool Registry
// =============================================================================

/// Registry of available MCP tools.
///
/// Thread-safe registry that manages tool registration and lookup.
pub struct ToolRegistry {
    tools: HashMap<String, Arc<dyn Tool>>,
}

impl ToolRegistry {
    /// Create a new empty registry.
    pub fn new() -> Self {
        Self {
            tools: HashMap::new(),
        }
    }

    /// Register a tool in the registry.
    ///
    /// If a tool with the same name already exists, it will be replaced.
    pub fn register<T: Tool + 'static>(&mut self, tool: T) {
        let name = tool.name().to_string();
        self.tools.insert(name, Arc::new(tool));
    }

    /// Get a tool by name.
    pub fn get(&self, name: &str) -> Option<Arc<dyn Tool>> {
        self.tools.get(name).cloned()
    }

    /// List all registered tools.
    pub fn list(&self) -> Vec<ToolDefinition> {
        self.tools
            .values()
            .map(|tool| ToolDefinition {
                name: tool.name().to_string(),
                description: tool.description().to_string(),
                input_schema: tool.input_schema(),
            })
            .collect()
    }

    /// Get the number of registered tools.
    pub fn len(&self) -> usize {
        self.tools.len()
    }

    /// Check if the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.tools.is_empty()
    }
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    struct MockTool {
        name: String,
    }

    #[async_trait]
    impl Tool for MockTool {
        fn name(&self) -> &str {
            &self.name
        }

        fn description(&self) -> &str {
            "A mock tool for testing"
        }

        fn input_schema(&self) -> serde_json::Value {
            serde_json::json!({
                "type": "object",
                "properties": {
                    "message": { "type": "string" }
                }
            })
        }

        async fn execute(
            &self,
            _args: HashMap<String, serde_json::Value>,
            _ctx: EnforcementContext,
        ) -> ToolCallResponse {
            ToolCallResponse::text("Mock response")
        }
    }

    #[test]
    fn test_registry_register_and_get() {
        let mut registry = ToolRegistry::new();
        registry.register(MockTool {
            name: "test_tool".to_string(),
        });

        assert_eq!(registry.len(), 1);
        assert!(registry.get("test_tool").is_some());
        assert!(registry.get("nonexistent").is_none());
    }

    #[test]
    fn test_registry_list() {
        let mut registry = ToolRegistry::new();
        registry.register(MockTool {
            name: "tool1".to_string(),
        });
        registry.register(MockTool {
            name: "tool2".to_string(),
        });

        let tools = registry.list();
        assert_eq!(tools.len(), 2);
    }
}
