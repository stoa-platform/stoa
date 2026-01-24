use serde_json::json;
use stoa_policy_engine::mcp::ToolCall;
use stoa_policy_engine::policy::PolicyEngine;

const TEST_POLICIES: &str = r#"
version: "1.0"
policies:
  - name: "cycle-required"
    enabled: true
    tools: ["Linear:create_issue"]
    rules:
      - field: "cycle"
        operator: "required"
        message: "Cycle is required"
"#;

#[test]
fn test_cycle_required_passes_with_cycle() {
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
fn test_cycle_required_fails_without_cycle() {
    let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

    let tool_call = ToolCall {
        name: "Linear:create_issue".to_string(),
        arguments: json!({
            "title": "Fix bug",
            "team": "STOA"
            // pas de cycle !
        }),
    };

    let result = engine.evaluate(&tool_call);
    assert!(result.is_err());

    let violation = result.unwrap_err();
    assert_eq!(violation.field, "cycle");
    assert!(violation.message.contains("required"));
}

#[test]
fn test_non_matching_tool_passes() {
    let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

    let tool_call = ToolCall {
        name: "Linear:list_issues".to_string(), // pas dans la policy
        arguments: json!({}),
    };

    assert!(engine.evaluate(&tool_call).is_ok());
}

#[test]
fn test_amount_limit_policy() {
    let policies = r#"
version: "1.0"
policies:
  - name: "amount-limit"
    enabled: true
    tools: ["transfer-coins"]
    rules:
      - field: "amount"
        operator: "lte"
        value: 10000
        message: "Amount must be <= 10000"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with amount <= 10000
    let tool_call = ToolCall {
        name: "transfer-coins".to_string(),
        arguments: json!({"amount": 5000}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail with amount > 10000
    let tool_call = ToolCall {
        name: "transfer-coins".to_string(),
        arguments: json!({"amount": 15000}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_neq_operator() {
    let policies = r#"
version: "1.0"
policies:
  - name: "priority-check"
    enabled: true
    tools: ["broadcast"]
    rules:
      - field: "priority"
        operator: "neq"
        value: "critical"
        message: "Critical priority requires approval"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with non-critical priority
    let tool_call = ToolCall {
        name: "broadcast".to_string(),
        arguments: json!({"priority": "normal"}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail with critical priority
    let tool_call = ToolCall {
        name: "broadcast".to_string(),
        arguments: json!({"priority": "critical"}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_nested_field_access() {
    let policies = r#"
version: "1.0"
policies:
  - name: "nested-check"
    enabled: true
    tools: ["create-resource"]
    rules:
      - field: "metadata.owner.team"
        operator: "required"
        message: "Team owner is required"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with nested field present
    let tool_call = ToolCall {
        name: "create-resource".to_string(),
        arguments: json!({
            "name": "resource1",
            "metadata": {
                "owner": {
                    "team": "platform"
                }
            }
        }),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail with missing nested field
    let tool_call = ToolCall {
        name: "create-resource".to_string(),
        arguments: json!({
            "name": "resource1",
            "metadata": {
                "owner": {}
            }
        }),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_regex_matching() {
    let policies = r#"
version: "1.0"
policies:
  - name: "email-validation"
    enabled: true
    tools: ["create-user"]
    rules:
      - field: "email"
        operator: "matches"
        value: "^[a-zA-Z0-9._%+-]+@company\\.com$"
        message: "Email must be from company.com"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with valid email
    let tool_call = ToolCall {
        name: "create-user".to_string(),
        arguments: json!({"email": "user@company.com"}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail with invalid email
    let tool_call = ToolCall {
        name: "create-user".to_string(),
        arguments: json!({"email": "user@gmail.com"}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_contains_string() {
    let policies = r#"
version: "1.0"
policies:
  - name: "description-check"
    enabled: true
    tools: ["create-ticket"]
    rules:
      - field: "description"
        operator: "contains"
        value: "[CAB-"
        message: "Description must reference a CAB ticket"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with CAB reference
    let tool_call = ToolCall {
        name: "create-ticket".to_string(),
        arguments: json!({"description": "Fix for [CAB-123]"}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail without CAB reference
    let tool_call = ToolCall {
        name: "create-ticket".to_string(),
        arguments: json!({"description": "Generic fix"}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_contains_array() {
    let policies = r#"
version: "1.0"
policies:
  - name: "tags-check"
    enabled: true
    tools: ["publish"]
    rules:
      - field: "tags"
        operator: "contains"
        value: "reviewed"
        message: "Must include 'reviewed' tag"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with reviewed tag
    let tool_call = ToolCall {
        name: "publish".to_string(),
        arguments: json!({"tags": ["draft", "reviewed", "approved"]}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail without reviewed tag
    let tool_call = ToolCall {
        name: "publish".to_string(),
        arguments: json!({"tags": ["draft", "pending"]}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}

#[test]
fn test_multiple_rules_in_policy() {
    let policies = r#"
version: "1.0"
policies:
  - name: "multi-rule"
    enabled: true
    tools: ["complex-action"]
    rules:
      - field: "user_id"
        operator: "required"
        message: "User ID required"
      - field: "amount"
        operator: "gt"
        value: 0
        message: "Amount must be positive"
      - field: "amount"
        operator: "lte"
        value: 1000
        message: "Amount must be <= 1000"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Should pass with all rules satisfied
    let tool_call = ToolCall {
        name: "complex-action".to_string(),
        arguments: json!({"user_id": "u123", "amount": 500}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Should fail if missing user_id
    let tool_call = ToolCall {
        name: "complex-action".to_string(),
        arguments: json!({"amount": 500}),
    };
    let err = engine.evaluate(&tool_call).unwrap_err();
    assert_eq!(err.field, "user_id");

    // Should fail if amount too high
    let tool_call = ToolCall {
        name: "complex-action".to_string(),
        arguments: json!({"user_id": "u123", "amount": 2000}),
    };
    let err = engine.evaluate(&tool_call).unwrap_err();
    assert_eq!(err.field, "amount");
}

#[test]
fn test_wildcard_tool_matching() {
    let policies = r#"
version: "1.0"
policies:
  - name: "global-audit"
    enabled: true
    tools: ["*"]
    rules:
      - field: "audit_id"
        operator: "required"
        message: "All operations require audit ID"
"#;

    let engine = PolicyEngine::from_yaml(policies).unwrap();

    // Any tool should require audit_id
    let tool_call = ToolCall {
        name: "any-random-tool".to_string(),
        arguments: json!({}),
    };
    assert!(engine.evaluate(&tool_call).is_err());

    // Should pass with audit_id
    let tool_call = ToolCall {
        name: "another-tool".to_string(),
        arguments: json!({"audit_id": "aud-123"}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());
}

#[test]
fn test_mcp_error_response() {
    let engine = PolicyEngine::from_yaml(TEST_POLICIES).unwrap();

    let tool_call = ToolCall {
        name: "Linear:create_issue".to_string(),
        arguments: json!({"title": "Test"}),
    };

    let violation = engine.evaluate(&tool_call).unwrap_err();
    let mcp_error = violation.to_mcp_error();

    assert!(mcp_error.is_error);
    assert!(!mcp_error.content.is_empty());
}

#[test]
fn test_load_from_fixture_file() {
    let yaml = include_str!("../fixtures/policies.yaml");
    let engine = PolicyEngine::from_yaml(yaml).unwrap();

    assert_eq!(engine.policy_count(), 5);
    assert_eq!(engine.enabled_policy_count(), 4); // One is disabled

    // Test Linear cycle policy
    let tool_call = ToolCall {
        name: "Linear:create_issue".to_string(),
        arguments: json!({"title": "Test", "cycle": "Q1 2026"}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    // Test coins transfer policy
    let tool_call = ToolCall {
        name: "oasis__Economy-API__transfer-coins".to_string(),
        arguments: json!({"amount": 5000}),
    };
    assert!(engine.evaluate(&tool_call).is_ok());

    let tool_call = ToolCall {
        name: "oasis__Economy-API__transfer-coins".to_string(),
        arguments: json!({"amount": 15000}),
    };
    assert!(engine.evaluate(&tool_call).is_err());
}
