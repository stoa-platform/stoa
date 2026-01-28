// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
use serde::{Deserialize, Serialize};

use crate::policy::rule::Rule;

/// Root configuration structure for policy YAML files
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyConfig {
    pub version: String,
    pub policies: Vec<PolicyDefinition>,
}

/// Definition of a single policy in the configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PolicyDefinition {
    pub name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
    pub tools: Vec<String>,
    pub rules: Vec<Rule>,
}

fn default_enabled() -> bool {
    true
}

impl PolicyConfig {
    /// Parse a PolicyConfig from YAML string
    pub fn from_yaml(yaml: &str) -> Result<Self, serde_yaml::Error> {
        serde_yaml::from_str(yaml)
    }

    /// Serialize the PolicyConfig to YAML string
    pub fn to_yaml(&self) -> Result<String, serde_yaml::Error> {
        serde_yaml::to_string(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_YAML: &str = r#"
version: "1.0"
policies:
  - name: "cycle-required"
    description: "Tickets must have a cycle"
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
        message: "Amount must be <= 10000"
"#;

    #[test]
    fn test_parse_yaml_config() {
        let config = PolicyConfig::from_yaml(SAMPLE_YAML).unwrap();
        assert_eq!(config.version, "1.0");
        assert_eq!(config.policies.len(), 2);
    }

    #[test]
    fn test_policy_definition_fields() {
        let config = PolicyConfig::from_yaml(SAMPLE_YAML).unwrap();
        let policy = &config.policies[0];

        assert_eq!(policy.name, "cycle-required");
        assert_eq!(
            policy.description,
            Some("Tickets must have a cycle".to_string())
        );
        assert!(policy.enabled);
        assert_eq!(policy.tools.len(), 2);
        assert_eq!(policy.rules.len(), 1);
    }

    #[test]
    fn test_default_enabled() {
        let yaml = r#"
version: "1.0"
policies:
  - name: "test"
    tools: ["test-tool"]
    rules: []
"#;
        let config = PolicyConfig::from_yaml(yaml).unwrap();
        assert!(config.policies[0].enabled);
    }

    #[test]
    fn test_disabled_policy() {
        let yaml = r#"
version: "1.0"
policies:
  - name: "test"
    enabled: false
    tools: ["test-tool"]
    rules: []
"#;
        let config = PolicyConfig::from_yaml(yaml).unwrap();
        assert!(!config.policies[0].enabled);
    }

    #[test]
    fn test_roundtrip_yaml() {
        let config = PolicyConfig::from_yaml(SAMPLE_YAML).unwrap();
        let yaml_out = config.to_yaml().unwrap();
        let config2 = PolicyConfig::from_yaml(&yaml_out).unwrap();

        assert_eq!(config.version, config2.version);
        assert_eq!(config.policies.len(), config2.policies.len());
    }
}
