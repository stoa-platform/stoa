use crate::mcp::types::ToolCall;
use crate::policy::config::{PolicyConfig, PolicyDefinition};
use crate::policy::rule::Rule;
use crate::policy::violation::PolicyViolation;
use thiserror::Error;

/// Errors that can occur during policy configuration
#[derive(Debug, Error)]
pub enum PolicyConfigError {
    #[error("Failed to parse YAML: {0}")]
    YamlError(#[from] serde_yaml::Error),
    #[error("Invalid policy configuration: {0}")]
    InvalidConfig(String),
}

/// A compiled policy ready for evaluation
#[derive(Debug, Clone)]
pub struct Policy {
    pub name: String,
    pub description: Option<String>,
    pub enabled: bool,
    pub tools: Vec<String>,
    pub rules: Vec<Rule>,
}

impl From<PolicyDefinition> for Policy {
    fn from(def: PolicyDefinition) -> Self {
        Self {
            name: def.name,
            description: def.description,
            enabled: def.enabled,
            tools: def.tools,
            rules: def.rules,
        }
    }
}

impl Policy {
    /// Check if this policy applies to the given tool name
    pub fn matches_tool(&self, tool_name: &str) -> bool {
        self.tools.iter().any(|t| t == tool_name || t == "*")
    }
}

/// The main policy engine for evaluating tool calls
#[derive(Debug)]
pub struct PolicyEngine {
    policies: Vec<Policy>,
}

impl PolicyEngine {
    /// Create a new empty PolicyEngine
    pub fn new() -> Self {
        Self {
            policies: Vec::new(),
        }
    }

    /// Load policies from a YAML configuration string
    pub fn from_yaml(yaml: &str) -> Result<Self, PolicyConfigError> {
        let config = PolicyConfig::from_yaml(yaml)?;
        Ok(Self::from_config(config))
    }

    /// Create a PolicyEngine from a PolicyConfig
    pub fn from_config(config: PolicyConfig) -> Self {
        let policies = config.policies.into_iter().map(Policy::from).collect();
        Self { policies }
    }

    /// Add a policy to the engine
    pub fn add_policy(&mut self, policy: Policy) {
        self.policies.push(policy);
    }

    /// Get the number of policies loaded
    pub fn policy_count(&self) -> usize {
        self.policies.len()
    }

    /// Get the number of enabled policies
    pub fn enabled_policy_count(&self) -> usize {
        self.policies.iter().filter(|p| p.enabled).count()
    }

    /// Evaluate a tool call against all matching policies
    pub fn evaluate(&self, tool_call: &ToolCall) -> Result<(), PolicyViolation> {
        for policy in &self.policies {
            if !policy.enabled {
                continue;
            }

            if policy.matches_tool(&tool_call.name) {
                for rule in &policy.rules {
                    rule.check(&tool_call.arguments)
                        .map_err(|v| v.with_policy(&policy.name))?;
                }
            }
        }
        Ok(())
    }

    /// Evaluate and return all violations (doesn't stop at first)
    pub fn evaluate_all(&self, tool_call: &ToolCall) -> Vec<PolicyViolation> {
        let mut violations = Vec::new();

        for policy in &self.policies {
            if !policy.enabled {
                continue;
            }

            if policy.matches_tool(&tool_call.name) {
                for rule in &policy.rules {
                    if let Err(v) = rule.check(&tool_call.arguments) {
                        violations.push(v.with_policy(&policy.name));
                    }
                }
            }
        }

        violations
    }

    /// Get policies that match a specific tool
    pub fn matching_policies(&self, tool_name: &str) -> Vec<&Policy> {
        self.policies
            .iter()
            .filter(|p| p.enabled && p.matches_tool(tool_name))
            .collect()
    }
}

impl Default for PolicyEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const TEST_POLICIES: &str = r#"
version: "1.0"
policies:
  - name: "cycle-required"
    description: "Tickets must have a cycle assigned"
    enabled: true
    tools:
      - "Linear:create_issue"
      - "Linear:update_issue"
    rules:
      - field: "cycle"
        operator: "required"
        message: "Cycle is required"
  - name: "amount-limit"
    enabled: true
    tools:
      - "transfer-coins"
    rules:
      - field: "amount"
        operator: "lte"
        value: 10000
        message: "Transfers > 10K require attestation"
  - name: "disabled-policy"
    enabled: false
    tools:
      - "*"
    rules:
      - field: "blocked"
        operator: "required"
        message: "This should never trigger"
"#;

    #[test]
    fn test_from_yaml() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();
        assert_eq!(engine.policy_count(), 3);
        assert_eq!(engine.enabled_policy_count(), 2);
    }

    #[test]
    fn test_evaluate_passes_with_valid_args() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        let tool_call = ToolCall {
            name: "Linear:create_issue".to_string(),
            arguments: json!({
                "title": "Fix bug",
                "team": "STOA",
                "cycle": "Cycle 42"
            }),
        };

        assert!(engine.evaluate(&tool_call).is_ok());
    }

    #[test]
    fn test_evaluate_fails_without_required_field() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        let tool_call = ToolCall {
            name: "Linear:create_issue".to_string(),
            arguments: json!({
                "title": "Fix bug",
                "team": "STOA"
            }),
        };

        let result = engine.evaluate(&tool_call);
        assert!(result.is_err());

        let violation = result.unwrap_err();
        assert_eq!(violation.field, "cycle");
        assert_eq!(violation.policy_name, Some("cycle-required".to_string()));
    }

    #[test]
    fn test_evaluate_non_matching_tool_passes() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        let tool_call = ToolCall {
            name: "Linear:list_issues".to_string(),
            arguments: json!({}),
        };

        assert!(engine.evaluate(&tool_call).is_ok());
    }

    #[test]
    fn test_evaluate_amount_limit_passes() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        let tool_call = ToolCall {
            name: "transfer-coins".to_string(),
            arguments: json!({
                "amount": 5000,
                "to": "user123"
            }),
        };

        assert!(engine.evaluate(&tool_call).is_ok());
    }

    #[test]
    fn test_evaluate_amount_limit_fails() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        let tool_call = ToolCall {
            name: "transfer-coins".to_string(),
            arguments: json!({
                "amount": 15000,
                "to": "user123"
            }),
        };

        let result = engine.evaluate(&tool_call);
        assert!(result.is_err());

        let violation = result.unwrap_err();
        assert_eq!(violation.field, "amount");
    }

    #[test]
    fn test_disabled_policy_not_evaluated() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

        // This would trigger the disabled wildcard policy if it were enabled
        let tool_call = ToolCall {
            name: "any-tool".to_string(),
            arguments: json!({}),
        };

        assert!(engine.evaluate(&tool_call).is_ok());
    }

    #[test]
    fn test_evaluate_all_returns_multiple_violations() {
        let yaml = r#"
version: "1.0"
policies:
  - name: "multi-rule"
    enabled: true
    tools: ["test-tool"]
    rules:
      - field: "field1"
        operator: "required"
        message: "Field1 required"
      - field: "field2"
        operator: "required"
        message: "Field2 required"
"#;
        let engine = PolicyEngine::from_yaml(yaml).unwrap();

        let tool_call = ToolCall {
            name: "test-tool".to_string(),
            arguments: json!({}),
        };

        let violations = engine.evaluate_all(&tool_call);
        assert_eq!(violations.len(), 2);
    }

    #[test]
    fn test_matching_policies() {
        let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();
        let matching = engine.matching_policies("Linear:create_issue");
        assert_eq!(matching.len(), 1);
        assert_eq!(matching[0].name, "cycle-required");
    }

    #[test]
    fn test_wildcard_tool_matching() {
        let yaml = r#"
version: "1.0"
policies:
  - name: "global-policy"
    enabled: true
    tools: ["*"]
    rules:
      - field: "audit"
        operator: "required"
        message: "Audit field required for all tools"
"#;
        let engine = PolicyEngine::from_yaml(yaml).unwrap();

        let tool_call = ToolCall {
            name: "any-random-tool".to_string(),
            arguments: json!({}),
        };

        assert!(engine.evaluate(&tool_call).is_err());
    }

    #[test]
    fn test_add_policy() {
        let mut engine = PolicyEngine::new();
        assert_eq!(engine.policy_count(), 0);

        engine.add_policy(Policy {
            name: "test".to_string(),
            description: None,
            enabled: true,
            tools: vec!["test-tool".to_string()],
            rules: vec![],
        });

        assert_eq!(engine.policy_count(), 1);
    }
}
