//! STOA Policy Engine - High-performance policy evaluation for MCP Gateway
//!
//! This crate provides a policy engine that evaluates tool calls against
//! configurable policies defined in YAML format.
//!
//! # Example
//!
//! ```rust
//! use stoa_policy_engine::policy::PolicyEngine;
//! use stoa_policy_engine::mcp::ToolCall;
//! use serde_json::json;
//!
//! let policies = r#"
//! version: "1.0"
//! policies:
//!   - name: "cycle-required"
//!     enabled: true
//!     tools: ["Linear:create_issue"]
//!     rules:
//!       - field: "cycle"
//!         operator: "required"
//!         message: "Cycle is required"
//! "#;
//!
//! let engine = PolicyEngine::from_yaml(policies).unwrap();
//!
//! let tool_call = ToolCall {
//!     name: "Linear:create_issue".to_string(),
//!     arguments: json!({"title": "Fix bug", "cycle": "Cycle 42"}),
//! };
//!
//! assert!(engine.evaluate(&tool_call).is_ok());
//! ```

pub mod mcp;
pub mod policy;
pub mod tenant;

// Re-export commonly used types at the crate root
pub use mcp::{ToolCall, ToolResult};
pub use policy::{PolicyEngine, PolicyViolation};
pub use tenant::TenantContext;

/// Crate version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Evaluate a tool call against policies loaded from YAML
///
/// This is a convenience function for simple use cases.
///
/// # Example
///
/// ```rust
/// use stoa_policy_engine::evaluate_tool_call;
/// use serde_json::json;
///
/// let policies = r#"
/// version: "1.0"
/// policies:
///   - name: "test"
///     enabled: true
///     tools: ["*"]
///     rules: []
/// "#;
///
/// let result = evaluate_tool_call(policies, "test-tool", json!({}));
/// assert!(result.is_ok());
/// ```
pub fn evaluate_tool_call(
    policies_yaml: &str,
    tool_name: &str,
    arguments: serde_json::Value,
) -> Result<(), PolicyViolation> {
    let engine = PolicyEngine::from_yaml(policies_yaml)
        .map_err(|e| PolicyViolation::new("_config", &e.to_string()))?;

    let tool_call = ToolCall {
        name: tool_name.to_string(),
        arguments,
    };

    engine.evaluate(&tool_call)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_version() {
        assert!(!VERSION.is_empty());
    }

    #[test]
    fn test_evaluate_tool_call_convenience() {
        let policies = r#"
version: "1.0"
policies:
  - name: "test"
    enabled: true
    tools: ["test-tool"]
    rules:
      - field: "required_field"
        operator: "required"
        message: "Field is required"
"#;

        // Should pass with required field
        let result = evaluate_tool_call(policies, "test-tool", json!({"required_field": "value"}));
        assert!(result.is_ok());

        // Should fail without required field
        let result = evaluate_tool_call(policies, "test-tool", json!({}));
        assert!(result.is_err());
    }
}
