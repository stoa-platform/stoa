#![no_main]

use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;
use stoa_policy_engine::mcp::ToolCall;
use stoa_policy_engine::policy::PolicyEngine;

const POLICIES: &str = r#"
version: "1.0"
policies:
  - name: "cycle-required"
    enabled: true
    tools: ["Linear:create_issue"]
    rules:
      - field: "cycle"
        operator: "required"
        message: "Cycle is required"
  - name: "amount-limit"
    enabled: true
    tools: ["transfer"]
    rules:
      - field: "amount"
        operator: "lte"
        value: 10000
        message: "Amount limit exceeded"
  - name: "nested-check"
    enabled: true
    tools: ["create"]
    rules:
      - field: "meta.owner"
        operator: "required"
        message: "Owner required"
  - name: "wildcard"
    enabled: true
    tools: ["*"]
    rules:
      - field: "audit"
        operator: "eq"
        value: "bypass"
        message: "Audit bypass detected"
"#;

#[derive(Arbitrary, Debug)]
struct FuzzInput {
    tool_name: String,
    arguments: FuzzArguments,
}

#[derive(Arbitrary, Debug)]
struct FuzzArguments {
    cycle: Option<String>,
    amount: Option<i64>,
    title: Option<String>,
    meta_owner: Option<String>,
    audit: Option<String>,
    extra_field: Option<String>,
}

fuzz_target!(|input: FuzzInput| {
    // Build the JSON arguments from the fuzz input
    let mut args = serde_json::Map::new();

    if let Some(ref cycle) = input.arguments.cycle {
        args.insert("cycle".to_string(), serde_json::json!(cycle));
    }
    if let Some(amount) = input.arguments.amount {
        args.insert("amount".to_string(), serde_json::json!(amount));
    }
    if let Some(ref title) = input.arguments.title {
        args.insert("title".to_string(), serde_json::json!(title));
    }
    if let Some(ref owner) = input.arguments.meta_owner {
        args.insert(
            "meta".to_string(),
            serde_json::json!({"owner": owner}),
        );
    }
    if let Some(ref audit) = input.arguments.audit {
        args.insert("audit".to_string(), serde_json::json!(audit));
    }
    if let Some(ref extra) = input.arguments.extra_field {
        args.insert("extra".to_string(), serde_json::json!(extra));
    }

    let tool_call = ToolCall {
        name: input.tool_name,
        arguments: serde_json::Value::Object(args),
    };

    // Load engine (should never fail with valid YAML)
    let engine = PolicyEngine::from_yaml(POLICIES).expect("Valid YAML");

    // Evaluate - should never panic regardless of input
    let _ = engine.evaluate(&tool_call);
    let _ = engine.evaluate_all(&tool_call);
});
