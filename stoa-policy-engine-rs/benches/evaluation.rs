use criterion::{black_box, criterion_group, criterion_main, Criterion};
use serde_json::json;
use stoa_policy_engine::mcp::ToolCall;
use stoa_policy_engine::policy::PolicyEngine;

const POLICIES: &str = r#"
version: "1.0"
policies:
  - name: "cycle-required"
    enabled: true
    tools: ["Linear:create_issue", "Linear:update_issue"]
    rules:
      - field: "cycle"
        operator: "required"
        message: "Cycle is required"
  - name: "amount-limit"
    enabled: true
    tools: ["transfer-coins"]
    rules:
      - field: "amount"
        operator: "lte"
        value: 10000
        message: "Amount must be <= 10000"
  - name: "email-validation"
    enabled: true
    tools: ["create-user"]
    rules:
      - field: "email"
        operator: "matches"
        value: "^[a-zA-Z0-9._%+-]+@company\\.com$"
        message: "Email must be from company.com"
  - name: "nested-field-check"
    enabled: true
    tools: ["create-resource"]
    rules:
      - field: "metadata.owner.team"
        operator: "required"
        message: "Team required"
"#;

fn bench_engine_creation(c: &mut Criterion) {
    c.bench_function("engine_from_yaml", |b| {
        b.iter(|| PolicyEngine::from_yaml(black_box(POLICIES)).unwrap())
    });
}

fn bench_evaluate_matching_policy(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
    let tool_call = ToolCall {
        name: "Linear:create_issue".to_string(),
        arguments: json!({
            "title": "Fix bug",
            "team": "STOA",
            "cycle": "Cycle 42"
        }),
    };

    c.bench_function("evaluate_matching_pass", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

fn bench_evaluate_matching_policy_fail(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
    let tool_call = ToolCall {
        name: "Linear:create_issue".to_string(),
        arguments: json!({
            "title": "Fix bug",
            "team": "STOA"
            // missing cycle
        }),
    };

    c.bench_function("evaluate_matching_fail", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

fn bench_evaluate_non_matching(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
    let tool_call = ToolCall {
        name: "unrelated-tool".to_string(),
        arguments: json!({}),
    };

    c.bench_function("evaluate_non_matching", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

fn bench_evaluate_regex(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
    let tool_call = ToolCall {
        name: "create-user".to_string(),
        arguments: json!({
            "email": "user@company.com"
        }),
    };

    c.bench_function("evaluate_regex", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

fn bench_evaluate_nested_field(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
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

    c.bench_function("evaluate_nested_field", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

fn bench_evaluate_numeric_comparison(c: &mut Criterion) {
    let engine = PolicyEngine::from_yaml(POLICIES).unwrap();
    let tool_call = ToolCall {
        name: "transfer-coins".to_string(),
        arguments: json!({
            "amount": 5000
        }),
    };

    c.bench_function("evaluate_numeric", |b| {
        b.iter(|| engine.evaluate(black_box(&tool_call)))
    });
}

criterion_group!(
    benches,
    bench_engine_creation,
    bench_evaluate_matching_policy,
    bench_evaluate_matching_policy_fail,
    bench_evaluate_non_matching,
    bench_evaluate_regex,
    bench_evaluate_nested_field,
    bench_evaluate_numeric_comparison,
);
criterion_main!(benches);
