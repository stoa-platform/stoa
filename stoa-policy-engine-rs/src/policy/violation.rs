// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use crate::mcp::types::ToolResult;
use thiserror::Error;

/// Represents a policy violation that occurred during evaluation
#[derive(Debug, Clone, Error)]
#[error("Policy violation on field '{field}': {message}")]
pub struct PolicyViolation {
    pub field: String,
    pub message: String,
    pub policy_name: Option<String>,
}

impl PolicyViolation {
    /// Create a new policy violation
    pub fn new(field: &str, message: &str) -> Self {
        Self {
            field: field.to_string(),
            message: message.to_string(),
            policy_name: None,
        }
    }

    /// Add the policy name to this violation
    pub fn with_policy(mut self, policy_name: &str) -> Self {
        self.policy_name = Some(policy_name.to_string());
        self
    }

    /// Convert to MCP ToolResult error format
    pub fn to_mcp_error(&self) -> ToolResult {
        ToolResult::error(&format!(
            "Policy Violation: {}\n\nField: {}\nPolicy: {}",
            self.message,
            self.field,
            self.policy_name.as_deref().unwrap_or("unknown")
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_policy_violation_new() {
        let violation = PolicyViolation::new("cycle", "Cycle is required");
        assert_eq!(violation.field, "cycle");
        assert_eq!(violation.message, "Cycle is required");
        assert!(violation.policy_name.is_none());
    }

    #[test]
    fn test_policy_violation_with_policy() {
        let violation =
            PolicyViolation::new("cycle", "Cycle is required").with_policy("linear-cycle-required");
        assert_eq!(
            violation.policy_name,
            Some("linear-cycle-required".to_string())
        );
    }

    #[test]
    fn test_policy_violation_to_mcp_error() {
        let violation =
            PolicyViolation::new("cycle", "Cycle is required").with_policy("linear-cycle-required");
        let result = violation.to_mcp_error();
        assert!(result.is_error);
    }

    #[test]
    fn test_policy_violation_display() {
        let violation = PolicyViolation::new("amount", "Amount exceeds limit");
        let display = format!("{}", violation);
        assert!(display.contains("amount"));
        assert!(display.contains("Amount exceeds limit"));
    }
}
