//! MCP Protocol Binder
//!
//! Transforms a UAC contract into MCP tools registered in the ToolRegistry.
//! Each endpoint in the contract becomes a DynamicTool named
//! `endpoint.llm.tool_name`, or [`default_tool_name`] when it has none:
//! `{tenant_id}_{contract_name}_{operation_id|index}`.
//!
//! The names a contract registered are kept in the [`ContractRegistry`], so a
//! republication replaces exactly those tools and a deletion removes them,
//! whatever their names.

use std::fmt::Write as _;
use std::sync::Arc;

use sha2::{Digest, Sha256};

use crate::mcp::tools::dynamic_tool::{extract_path_tokens, schema_from_value, DynamicTool};
use crate::mcp::tools::{
    validation, Tool, ToolAnnotations, ToolDefinition, ToolRegistry, ToolSchema,
};
use crate::uac::registry::ContractRegistry;
use crate::uac::schema::{EndpointSideEffects, UacContractSpec, UacEndpoint};
use crate::uac::Action;

use super::{
    check_endpoint_templates, split_path_template, BindingOutput, ProtocolBinder, CONTRACT_REJECTED,
};

/// Longest default tool name. MCP clients commonly enforce
/// `^[a-zA-Z0-9_-]{1,64}$`.
pub const MAX_DEFAULT_TOOL_NAME_LEN: usize = 64;

/// Default MCP tool name of a contract endpoint that has no `llm.tool_name`.
///
/// `{tenant_id}_{contract_name}_{operation}`, each part reduced to
/// `[A-Za-z0-9_-]` (any other character becomes `_`). A name longer than
/// [`MAX_DEFAULT_TOOL_NAME_LEN`] is cut and ends with `_` plus 8 hex
/// characters of the SHA-256 of the full name, so it stays stable and two
/// long names that share a start stay distinct.
pub fn default_tool_name(tenant_id: &str, contract_name: &str, operation: &str) -> String {
    let full = [tenant_id, contract_name, operation]
        .iter()
        .map(|part| sanitize_name_part(part))
        .collect::<Vec<_>>()
        .join("_");
    if full.len() <= MAX_DEFAULT_TOOL_NAME_LEN {
        return full;
    }
    let mut hasher = Sha256::new();
    hasher.update(full.as_bytes());
    let digest = hasher.finalize();
    // `full` is ASCII after sanitising, so any byte index is a char boundary.
    let mut name = full[..MAX_DEFAULT_TOOL_NAME_LEN - 9].to_string();
    name.push('_');
    for byte in digest.iter().take(4) {
        let _ = write!(name, "{byte:02x}");
    }
    name
}

fn sanitize_name_part(part: &str) -> String {
    part.chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// What the binder derives from one endpoint, shared by the definitions and
/// the registered tools.
struct EndpointTool {
    name: String,
    description: String,
    method: String,
    action: Action,
    input_schema: ToolSchema,
    /// Path after the static prefix, `{param}` tokens included (`{id}/segment`).
    /// Empty when the path has no parameter.
    path_rest: String,
}

/// MCP protocol binder — generates MCP tools from UAC contracts.
pub struct McpBinder {
    tool_registry: Arc<ToolRegistry>,
    /// Holds the tool names of each contract across binder instances.
    contracts: Arc<ContractRegistry>,
}

impl McpBinder {
    /// Create a binder whose tool-name records live in a private registry.
    ///
    /// Production uses [`Self::with_contracts`] so the records outlive the
    /// binder built for one admin request.
    pub fn new(tool_registry: Arc<ToolRegistry>) -> Self {
        Self::with_contracts(tool_registry, Arc::new(ContractRegistry::new()))
    }

    /// Create a binder that records tool names in `contracts`.
    pub fn with_contracts(
        tool_registry: Arc<ToolRegistry>,
        contracts: Arc<ContractRegistry>,
    ) -> Self {
        Self {
            tool_registry,
            contracts,
        }
    }

    /// Map HTTP method to UAC Action.
    fn method_to_action(method: &str) -> Action {
        match method.to_uppercase().as_str() {
            "GET" => Action::Read,
            "POST" => Action::Create,
            "PUT" | "PATCH" => Action::Update,
            "DELETE" => Action::Delete,
            _ => Action::Read,
        }
    }

    /// Resolve the tool action from endpoint-level LLM metadata when present.
    fn endpoint_action(endpoint: &UacEndpoint, primary_method: &str) -> Action {
        match endpoint.llm.as_ref().map(|llm| llm.side_effects) {
            Some(EndpointSideEffects::None) | Some(EndpointSideEffects::Read) => Action::Read,
            Some(EndpointSideEffects::Destructive) => Action::Delete,
            Some(EndpointSideEffects::Write) | None => Self::method_to_action(primary_method),
        }
    }

    fn side_effects_label(side_effects: EndpointSideEffects) -> &'static str {
        match side_effects {
            EndpointSideEffects::None => "none",
            EndpointSideEffects::Read => "read",
            EndpointSideEffects::Write => "write",
            EndpointSideEffects::Destructive => "destructive",
        }
    }

    /// Build the generated MCP tool name.
    ///
    /// For LLM-ready endpoints, endpoint.llm.tool_name is the stable MCP tool
    /// name. Other endpoints get [`default_tool_name`].
    fn tool_name(contract: &UacContractSpec, endpoint: &UacEndpoint, index: usize) -> String {
        if let Some(llm) = endpoint.llm.as_ref() {
            return llm.tool_name.clone();
        }
        let operation = endpoint
            .operation_id
            .as_deref()
            .filter(|op| !op.is_empty())
            .map(str::to_string)
            .unwrap_or_else(|| index.to_string());
        default_tool_name(&contract.tenant_id, &contract.name, &operation)
    }

    /// Build the agent-facing tool description.
    fn description(
        contract: &UacContractSpec,
        endpoint: &UacEndpoint,
        primary_method: &str,
    ) -> String {
        let legacy = format!(
            "{} {} — {} [{}]",
            primary_method, endpoint.path, contract.name, contract.tenant_id
        );

        let Some(llm) = endpoint.llm.as_ref() else {
            return legacy;
        };

        let mut lines = vec![
            legacy,
            format!("Summary: {}", llm.summary),
            format!("Intent: {}", llm.intent),
            format!(
                "Side effects: {}",
                Self::side_effects_label(llm.side_effects)
            ),
            format!("Safe for agents: {}", llm.safe_for_agents),
            format!("Requires human approval: {}", llm.requires_human_approval),
        ];

        if llm.requires_human_approval {
            lines.push("HUMAN APPROVAL REQUIRED".to_string());
        }

        lines.join("\n")
    }

    /// Input schema of the endpoint, with each path parameter declared as a
    /// required string. A property the contract already defines is kept.
    fn input_schema(endpoint: &UacEndpoint, path_params: &[String]) -> ToolSchema {
        let mut schema = endpoint
            .input_schema
            .as_ref()
            .map(schema_from_value)
            .unwrap_or_else(|| ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            });
        for param in path_params {
            schema.properties.entry(param.clone()).or_insert_with(|| {
                serde_json::json!({
                    "type": "string",
                    "description": format!("Value of {{{param}}} in {}", endpoint.path),
                })
            });
            if !schema.required.contains(param) {
                schema.required.push(param.clone());
            }
        }
        schema
    }

    fn endpoint_tool(
        contract: &UacContractSpec,
        endpoint: &UacEndpoint,
        index: usize,
    ) -> EndpointTool {
        // Use first method for action hint (most endpoints have one primary method)
        let method = endpoint
            .methods
            .first()
            .map(|m| m.as_str())
            .unwrap_or("GET")
            .to_string();
        let action = Self::endpoint_action(endpoint, &method);
        let (_, path_rest) = split_path_template(&endpoint.path);
        let path_params = extract_path_tokens(path_rest);
        EndpointTool {
            name: Self::tool_name(contract, endpoint, index),
            description: Self::description(contract, endpoint, &method),
            input_schema: Self::input_schema(endpoint, &path_params),
            method,
            action,
            path_rest: path_rest.to_string(),
        }
    }

    /// Generate tool definitions from a contract (pure function, no side effects).
    pub fn generate_tool_definitions(contract: &UacContractSpec) -> Vec<ToolDefinition> {
        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                let spec = Self::endpoint_tool(contract, endpoint, i);
                ToolDefinition {
                    name: spec.name,
                    description: spec.description,
                    input_schema: spec.input_schema,
                    output_schema: endpoint.output_schema.clone(),
                    annotations: Some(ToolAnnotations::from_action(spec.action)),
                    tenant_id: Some(contract.tenant_id.clone()),
                }
            })
            .collect()
    }

    /// Create DynamicTool instances from a contract for registration.
    ///
    /// `backend_url` is the upstream URL of the path's static prefix. A path
    /// with parameters (`/customers/{id}/segment`) gets the rest as a path
    /// pattern: the call goes to `backend_url` joined to `C-1001/segment`, and
    /// the arguments used in the path are not sent again as query or body.
    /// A path parameter is one segment: a value with `/` or `\` is refused.
    fn create_dynamic_tools(contract: &UacContractSpec) -> Vec<Arc<dyn Tool>> {
        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                let spec = Self::endpoint_tool(contract, endpoint, i);
                let mut tool = DynamicTool::new(
                    &spec.name,
                    &spec.description,
                    &endpoint.backend_url,
                    &spec.method,
                    spec.input_schema,
                    &contract.tenant_id,
                )
                .with_action(spec.action)
                .with_annotations(ToolAnnotations::from_action(spec.action));
                if !spec.path_rest.is_empty() {
                    tool = tool
                        .with_path_pattern(spec.path_rest)
                        .with_single_segment_path_parameters();
                }
                Arc::new(tool) as Arc<dyn Tool>
            })
            .collect()
    }
}

impl ProtocolBinder for McpBinder {
    /// Replace the tools of a contract.
    ///
    /// Two endpoints with one name, a name held by another contract or by a
    /// tool from elsewhere, or an endpoint refused by
    /// [`check_endpoint_templates`] reject the contract before any registry
    /// change. A tool the registry's validation refuses is left out and not
    /// counted.
    async fn bind(&self, contract: &UacContractSpec) -> Result<BindingOutput, String> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);
        // POST /admin/contracts runs the REST binder first, which already
        // refuses these; this keeps the MCP binder safe on its own.
        check_endpoint_templates(contract)?;
        let tools = Self::create_dynamic_tools(contract);

        let mut seen: Vec<&str> = Vec::with_capacity(tools.len());
        for tool in &tools {
            if seen.contains(&tool.name()) {
                return Err(format!(
                    "{CONTRACT_REJECTED}two endpoints produce the MCP tool name {:?}",
                    tool.name()
                ));
            }
            seen.push(tool.name());
        }

        let mut valid = Vec::with_capacity(tools.len());
        for tool in tools {
            match validation::validate_tool(tool.as_ref()) {
                Ok(()) => valid.push(tool),
                Err(e) => tracing::warn!(
                    contract = %contract_key,
                    errors = %e,
                    "MCP binder: tool left out"
                ),
            }
        }
        let names: Vec<String> = valid.iter().map(|t| t.name().to_string()).collect();

        let previous = self
            .contracts
            .claim_tool_names(&contract_key, &names, |name| {
                self.tool_registry.exists(name)
            })
            .map_err(|e| format!("{CONTRACT_REJECTED}{e}"))?;

        for stale in previous.iter().filter(|name| !names.contains(name)) {
            self.tool_registry.unregister(stale);
        }
        for tool in valid {
            self.tool_registry.register(tool);
        }

        // Count what the registry holds now, not what the contract asked for.
        let definitions: Vec<ToolDefinition> = names
            .iter()
            .filter_map(|name| self.tool_registry.get(name))
            .map(|tool| tool.definition())
            .collect();

        tracing::info!(
            contract = %contract_key,
            tools = definitions.len(),
            "MCP binder: tools generated"
        );

        Ok(BindingOutput::Tools(definitions))
    }

    async fn unbind(&self, contract_key: &str) -> Result<usize, String> {
        let names = self.contracts.take_tool_names(contract_key);
        let removed = names
            .iter()
            .filter(|name| self.tool_registry.unregister(name))
            .count();

        tracing::info!(
            contract = %contract_key,
            removed,
            "MCP binder: tools removed"
        );

        Ok(removed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mcp::tools::ToolContext;
    use crate::uac::classifications::Classification;
    use crate::uac::schema::{
        ContractStatus, EndpointLlm, EndpointLlmExample, EndpointSideEffects, UacContractSpec,
        UacEndpoint,
    };

    fn sample_contract() -> UacContractSpec {
        let mut spec = UacContractSpec::new("payments", "acme");
        spec.status = ContractStatus::Published;
        spec.endpoints = vec![
            UacEndpoint {
                path: "/payments".to_string(),
                methods: vec!["GET".to_string(), "POST".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                method: None,
                description: None,
                operation_id: Some("list_payments".to_string()),
                input_schema: None,
                output_schema: None,
                llm: None,
            },
            UacEndpoint {
                path: "/payments/{id}".to_string(),
                methods: vec!["DELETE".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                method: None,
                description: None,
                operation_id: Some("delete_payment".to_string()),
                input_schema: None,
                output_schema: None,
                llm: None,
            },
        ];
        spec
    }

    fn read_llm(tool_name: &str) -> EndpointLlm {
        EndpointLlm {
            summary: "List customer payments.".to_string(),
            intent: "Use to inspect payments without changing state.".to_string(),
            tool_name: tool_name.to_string(),
            side_effects: EndpointSideEffects::Read,
            safe_for_agents: true,
            requires_human_approval: false,
            examples: vec![EndpointLlmExample {
                input: serde_json::json!({}),
                expected_output_contains: None,
            }],
        }
    }

    fn tool_context(tenant: &str) -> ToolContext {
        ToolContext {
            tenant_id: tenant.to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "c".to_string(),
            from_control_plane: false,
        }
    }

    fn sorted_names(registry: &ToolRegistry) -> Vec<String> {
        let mut names = registry.names();
        names.sort();
        names
    }

    #[test]
    fn test_method_to_action() {
        assert_eq!(McpBinder::method_to_action("GET"), Action::Read);
        assert_eq!(McpBinder::method_to_action("POST"), Action::Create);
        assert_eq!(McpBinder::method_to_action("PUT"), Action::Update);
        assert_eq!(McpBinder::method_to_action("PATCH"), Action::Update);
        assert_eq!(McpBinder::method_to_action("DELETE"), Action::Delete);
        assert_eq!(McpBinder::method_to_action("OPTIONS"), Action::Read);
    }

    #[test]
    fn test_generate_definitions_count() {
        let contract = sample_contract();
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs.len(), 2);
    }

    #[test]
    fn test_generate_definitions_tool_names() {
        let contract = sample_contract();
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "acme_payments_list_payments");
        assert_eq!(defs[1].name, "acme_payments_delete_payment");
    }

    #[test]
    fn test_generate_definitions_uses_llm_tool_name() {
        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(read_llm("list_customer_payments"));

        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "list_customer_payments");
    }

    #[test]
    fn llm_tool_name_is_used_as_given() {
        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(read_llm("payments.list:v2"));

        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "payments.list:v2");
    }

    #[test]
    fn test_generate_definitions_name_fallback() {
        let mut contract = sample_contract();
        contract.endpoints[0].operation_id = None;
        contract.endpoints[1].operation_id = Some(String::new());
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "acme_payments_0");
        assert_eq!(defs[1].name, "acme_payments_1");
    }

    #[test]
    fn default_tool_name_keeps_only_letters_digits_underscore_and_hyphen() {
        assert_eq!(
            default_tool_name("demo", "customer-api", "getCustomer"),
            "demo_customer-api_getCustomer"
        );
        assert_eq!(
            default_tool_name("acme corp", "v1.payments", "get:payment/{id}"),
            "acme_corp_v1_payments_get_payment__id_"
        );
        assert_eq!(default_tool_name("démo", "api", "0"), "d_mo_api_0");
    }

    #[test]
    fn default_tool_name_matches_the_strict_client_pattern() {
        let names = [
            default_tool_name("demo", "customer-api", "list"),
            default_tool_name("t:x", "a b", "op.with.dots"),
            default_tool_name(&"t".repeat(40), &"n".repeat(40), &"o".repeat(40)),
        ];
        for name in names {
            assert!(!name.is_empty() && name.len() <= 64, "{name}");
            assert!(
                name.chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-'),
                "{name}"
            );
        }
    }

    #[test]
    fn long_default_tool_name_is_cut_with_a_stable_hash_suffix() {
        let tenant = "tenant-with-a-long-identifier";
        let contract = "customer-referential-api";
        let a = default_tool_name(tenant, contract, "get_customer_by_external_reference");
        let b = default_tool_name(tenant, contract, "get_customer_by_external_reference_v2");

        assert_eq!(a.len(), 64);
        assert_eq!(b.len(), 64);
        assert_ne!(a, b);
        assert_eq!(
            a,
            default_tool_name(tenant, contract, "get_customer_by_external_reference")
        );
        let full = "tenant-with-a-long-identifier_customer-referential-api_get_customer_by_external_reference";
        let (head, suffix) = a.split_at(55);
        assert_eq!(head, &full[..55]);
        assert!(suffix.starts_with('_'));
        assert_eq!(suffix.len(), 9);
        assert!(suffix[1..].chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn default_tool_name_at_64_characters_is_not_cut() {
        let name = default_tool_name(&"t".repeat(20), &"n".repeat(20), &"o".repeat(22));
        assert_eq!(name.len(), 64);
        assert!(!name.contains("__"));
        assert!(name.ends_with(&"o".repeat(22)));
    }

    #[test]
    fn test_generate_definitions_description() {
        let contract = sample_contract();
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert!(defs[0].description.contains("GET"));
        assert!(defs[0].description.contains("/payments"));
        assert!(defs[0].description.contains("acme"));
    }

    #[test]
    fn test_generate_definitions_description_uses_llm_metadata() {
        let mut contract = sample_contract();
        contract.endpoints[1].llm = Some(EndpointLlm {
            summary: "Delete a payment.".to_string(),
            intent: "Use only after a human has approved permanent removal.".to_string(),
            tool_name: "delete_payment_after_approval".to_string(),
            side_effects: EndpointSideEffects::Destructive,
            safe_for_agents: false,
            requires_human_approval: true,
            examples: vec![EndpointLlmExample {
                input: serde_json::json!({ "id": "pay-123" }),
                expected_output_contains: None,
            }],
        });

        let defs = McpBinder::generate_tool_definitions(&contract);
        assert!(defs[1].description.contains("Summary: Delete a payment."));
        assert!(defs[1]
            .description
            .contains("Intent: Use only after a human has approved permanent removal."));
        assert!(defs[1].description.contains("Side effects: destructive"));
        assert!(defs[1]
            .description
            .contains("Requires human approval: true"));
        assert!(defs[1].description.contains("HUMAN APPROVAL REQUIRED"));
    }

    #[test]
    fn test_generate_definitions_action_from_method() {
        let contract = sample_contract();
        let defs = McpBinder::generate_tool_definitions(&contract);
        // First endpoint: GET → read_only_hint: true
        let ann0 = defs[0].annotations.as_ref().expect("annotations");
        assert_eq!(ann0.read_only_hint, Some(true));
        // Second endpoint: DELETE → destructive_hint: true
        let ann1 = defs[1].annotations.as_ref().expect("annotations");
        assert_eq!(ann1.destructive_hint, Some(true));
    }

    #[test]
    fn test_generate_definitions_tenant_id() {
        let contract = sample_contract();
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].tenant_id.as_deref(), Some("acme"));
        assert_eq!(defs[1].tenant_id.as_deref(), Some("acme"));
    }

    #[test]
    fn test_generate_definitions_with_input_schema() {
        let mut contract = sample_contract();
        contract.endpoints[0].input_schema = Some(serde_json::json!({
            "type": "object",
            "properties": {
                "amount": {"type": "number"}
            },
            "required": ["amount"]
        }));
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].input_schema.properties.len(), 1);
        assert!(defs[0].input_schema.properties.contains_key("amount"));
        assert_eq!(defs[0].input_schema.required, vec!["amount"]);
    }

    #[test]
    fn path_parameters_are_required_strings_without_input_schema() {
        let mut contract = sample_contract();
        contract.endpoints[1].path = "/payments/{id}/lines/{line}".to_string();
        let defs = McpBinder::generate_tool_definitions(&contract);

        let schema = &defs[1].input_schema;
        assert_eq!(schema.schema_type, "object");
        assert_eq!(schema.required, vec!["id", "line"]);
        for param in ["id", "line"] {
            let property = &schema.properties[param];
            assert_eq!(property["type"], "string");
            assert!(property["description"]
                .as_str()
                .is_some_and(|d| !d.is_empty()));
        }
        // An endpoint without parameters gets no invented property.
        assert!(defs[0].input_schema.properties.is_empty());
        assert!(defs[0].input_schema.required.is_empty());
    }

    #[test]
    fn path_parameters_complete_the_given_input_schema() {
        let mut contract = sample_contract();
        contract.endpoints[1].path = "/payments/{id}/lines/{line}".to_string();
        contract.endpoints[1].input_schema = Some(serde_json::json!({
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "Payment number"},
                "reason": {"type": "string"}
            },
            "required": ["reason"]
        }));
        let defs = McpBinder::generate_tool_definitions(&contract);

        let schema = &defs[1].input_schema;
        assert_eq!(schema.properties["id"]["type"], "integer");
        assert_eq!(schema.properties["id"]["description"], "Payment number");
        assert_eq!(schema.properties["reason"]["type"], "string");
        assert_eq!(schema.properties["line"]["type"], "string");
        assert_eq!(schema.required, vec!["reason", "id", "line"]);
    }

    #[test]
    fn test_generate_definitions_with_output_schema() {
        let mut contract = sample_contract();
        contract.endpoints[0].output_schema = Some(serde_json::json!({"type": "array"}));
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert!(defs[0].output_schema.is_some());
    }

    #[tokio::test]
    async fn tool_substitutes_path_parameters_under_the_static_prefix_url() {
        use wiremock::matchers::{method, path, query_param, query_param_is_missing};
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let backend = MockServer::start().await;
        Mock::given(method("GET"))
            .and(path("/customers/C-1001/segment"))
            .and(query_param("expand", "all"))
            .and(query_param_is_missing("id"))
            .respond_with(ResponseTemplate::new(200).set_body_string("segment"))
            .mount(&backend)
            .await;

        let mut contract = UacContractSpec::new("api", "demo");
        contract.status = ContractStatus::Published;
        contract.endpoints = vec![UacEndpoint {
            path: "/customers/{id}/segment".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: format!("{}/customers/", backend.uri()),
            method: None,
            description: None,
            operation_id: Some("get_segment".to_string()),
            input_schema: None,
            output_schema: None,
            llm: None,
        }];

        let registry = Arc::new(ToolRegistry::new());
        McpBinder::new(registry.clone())
            .bind(&contract)
            .await
            .expect("bind");
        let tool = registry.get("demo_api_get_segment").expect("tool");
        let result = tool
            .execute(
                serde_json::json!({"id": "C-1001", "expand": "all"}),
                &tool_context("demo"),
            )
            .await
            .expect("call reaches the backend sub-path");
        assert!(result.content.iter().any(|content| matches!(
            content,
            crate::mcp::tools::ToolContent::Text { text } if text == "segment"
        )));
    }

    /// A contract path parameter is one segment: `/` and `\` are refused
    /// before any request, not sent as `%2F` / `%5C`.
    #[tokio::test]
    async fn contract_tool_refuses_a_separator_in_a_path_parameter() {
        use wiremock::{Mock, MockServer, ResponseTemplate};

        let backend = MockServer::start().await;
        Mock::given(wiremock::matchers::any())
            .respond_with(ResponseTemplate::new(200).set_body_string("reached"))
            .mount(&backend)
            .await;

        let mut contract = UacContractSpec::new("api", "demo");
        contract.status = ContractStatus::Published;
        contract.endpoints = vec![UacEndpoint {
            path: "/customers/{id}".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: format!("{}/customers", backend.uri()),
            method: None,
            description: None,
            operation_id: Some("get_customer".to_string()),
            input_schema: None,
            output_schema: None,
            llm: None,
        }];

        let registry = Arc::new(ToolRegistry::new());
        McpBinder::new(registry.clone())
            .bind(&contract)
            .await
            .expect("bind");
        let tool = registry.get("demo_api_get_customer").expect("tool");
        for value in ["a/b", "a\\b", "group/project"] {
            let error = tool
                .execute(serde_json::json!({ "id": value }), &tool_context("demo"))
                .await
                .expect_err(value);
            assert!(
                matches!(error, crate::mcp::tools::ToolError::InvalidArguments(_)),
                "{value:?}: {error}"
            );
        }
        let received = backend.received_requests().await.expect("recording");
        assert!(received.is_empty(), "{} request(s) sent", received.len());
    }

    #[tokio::test]
    async fn test_bind_registers_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let contract = sample_contract();
        let result = binder.bind(&contract).await;
        assert!(result.is_ok());

        // Tools should be in the registry
        assert_eq!(registry.count(), 2);
        assert!(registry.exists("acme_payments_list_payments"));
        assert!(registry.exists("acme_payments_delete_payment"));
    }

    #[tokio::test]
    async fn test_bind_replaces_existing_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let contract = sample_contract();
        binder.bind(&contract).await.expect("first bind");
        assert_eq!(registry.count(), 2);

        // Re-bind with fewer endpoints
        let mut updated = sample_contract();
        updated.endpoints.pop();
        binder.bind(&updated).await.expect("second bind");
        assert_eq!(registry.count(), 1);
    }

    #[tokio::test]
    async fn republish_replaces_llm_named_tools_across_binder_instances() {
        // The admin handler builds a new binder for every request; the
        // records must live in the shared contract registry.
        let registry = Arc::new(ToolRegistry::new());
        let contracts = Arc::new(ContractRegistry::new());

        let mut first = sample_contract();
        first.endpoints[0].llm = Some(read_llm("list_customer_payments"));
        McpBinder::with_contracts(registry.clone(), contracts.clone())
            .bind(&first)
            .await
            .expect("first publish");
        assert_eq!(
            sorted_names(&registry),
            vec!["acme_payments_delete_payment", "list_customer_payments"]
        );

        let mut second = sample_contract();
        second.endpoints.remove(1);
        second.endpoints[0].llm = Some(read_llm("list_payments_v2"));
        let output = McpBinder::with_contracts(registry.clone(), contracts.clone())
            .bind(&second)
            .await
            .expect("republish");
        let BindingOutput::Tools(tools) = output else {
            panic!("tools expected");
        };
        assert_eq!(tools.len(), 1);
        assert_eq!(sorted_names(&registry), vec!["list_payments_v2"]);
        assert_eq!(
            contracts.tool_names("acme:payments"),
            vec!["list_payments_v2"]
        );
    }

    #[tokio::test]
    async fn test_unbind_removes_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let contract = sample_contract();
        binder.bind(&contract).await.expect("bind");
        assert_eq!(registry.count(), 2);

        let removed = binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(removed, 2);
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn regression_unbind_removes_llm_named_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(read_llm("list_customer_payments"));

        binder.bind(&contract).await.expect("bind");
        assert!(registry.exists("list_customer_payments"));

        let removed = binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(removed, 2);
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn unbind_from_another_binder_instance_removes_llm_named_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let contracts = Arc::new(ContractRegistry::new());

        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(read_llm("list_customer_payments"));
        McpBinder::with_contracts(registry.clone(), contracts.clone())
            .bind(&contract)
            .await
            .expect("publish");

        let removed = McpBinder::with_contracts(registry.clone(), contracts.clone())
            .unbind("acme:payments")
            .await
            .expect("delete");
        assert_eq!(removed, 2);
        assert_eq!(registry.count(), 0);
        assert!(contracts.tool_names("acme:payments").is_empty());
    }

    #[tokio::test]
    async fn name_taken_by_another_contract_rejects_without_partial_change() {
        let registry = Arc::new(ToolRegistry::new());
        let contracts = Arc::new(ContractRegistry::new());
        let binder = McpBinder::with_contracts(registry.clone(), contracts.clone());

        let mut owner = sample_contract();
        owner.endpoints[0].llm = Some(read_llm("shared_name"));
        binder.bind(&owner).await.expect("owner");

        // Another tenant's contract, first published without the clash.
        let mut other = sample_contract();
        other.tenant_id = "globex".to_string();
        binder.bind(&other).await.expect("other");
        let before = sorted_names(&registry);

        let mut clash = other.clone();
        clash.endpoints[1].llm = Some(read_llm("shared_name"));
        let error = binder.bind(&clash).await.expect_err("name taken");
        assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
        assert!(error.contains("shared_name"), "{error}");
        assert!(error.contains("acme:payments"), "{error}");

        // Nothing replaced, nothing removed, records unchanged.
        assert_eq!(sorted_names(&registry), before);
        let shared = registry.get("shared_name").expect("owner tool kept");
        assert_eq!(shared.tenant_id(), Some("acme"));
        assert_eq!(
            contracts.tool_names("globex:payments"),
            vec![
                "globex_payments_list_payments",
                "globex_payments_delete_payment"
            ]
        );
    }

    #[tokio::test]
    async fn name_of_a_tool_from_elsewhere_rejects_the_contract() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());
        registry.register(Arc::new(DynamicTool::new(
            "stoa_catalog",
            "Built-in",
            "http://localhost",
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
            "acme",
        )));

        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(read_llm("stoa_catalog"));
        let error = binder.bind(&contract).await.expect_err("name taken");
        assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
        assert_eq!(registry.names(), vec!["stoa_catalog"]);
        assert_eq!(
            registry.get("stoa_catalog").expect("kept").description(),
            "Built-in"
        );
    }

    #[tokio::test]
    async fn path_or_backend_url_the_rest_binder_refuses_is_refused_here_too() {
        let registry = Arc::new(ToolRegistry::new());
        let contracts = Arc::new(ContractRegistry::new());
        let binder = McpBinder::with_contracts(registry.clone(), contracts.clone());
        binder.bind(&sample_contract()).await.expect("first bind");
        let before = sorted_names(&registry);

        for (path, backend_url) in [
            (
                "/payments/{id}",
                "https://backend.acme.com/v1/payments/{id}",
            ),
            ("payments/{id}", "https://backend.acme.com/v1/payments"),
            ("/payments/{id", "https://backend.acme.com/v1/payments"),
            ("/payments/{}", "https://backend.acme.com/v1/payments"),
            ("/payments/p-{id}", "https://backend.acme.com/v1/payments"),
        ] {
            let mut contract = sample_contract();
            contract.endpoints[1].path = path.to_string();
            contract.endpoints[1].backend_url = backend_url.to_string();
            contract.endpoints[1].operation_id = Some("renamed".to_string());
            let error = binder.bind(&contract).await.expect_err(path);
            assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
            assert!(error.contains("endpoints[1]"), "{error}");
            assert_eq!(sorted_names(&registry), before, "{path}");
            let mut recorded = contracts.tool_names("acme:payments");
            recorded.sort();
            assert_eq!(recorded, before, "{path}");
        }
    }

    #[tokio::test]
    async fn two_endpoints_with_one_tool_name_reject_the_contract() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let mut contract = sample_contract();
        contract.endpoints[1].operation_id = Some("list_payments".to_string());
        let error = binder.bind(&contract).await.expect_err("duplicate");
        assert!(error.starts_with(CONTRACT_REJECTED), "{error}");
        assert!(error.contains("acme_payments_list_payments"), "{error}");
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn bound_tool_count_is_what_the_registry_accepted() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        // The registry refuses a tool whose input schema is not an object.
        let mut contract = sample_contract();
        contract.endpoints[1].input_schema = Some(serde_json::json!({"type": "array"}));
        let output = binder.bind(&contract).await.expect("bind");
        let BindingOutput::Tools(tools) = output else {
            panic!("tools expected");
        };
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "acme_payments_list_payments");
        assert_eq!(registry.count(), 1);
    }

    #[tokio::test]
    async fn test_unbind_nonexistent_returns_zero() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let removed = binder.unbind("unknown:contract").await.expect("unbind");
        assert_eq!(removed, 0);
    }

    #[tokio::test]
    async fn unbind_keeps_tools_of_a_contract_whose_key_extends_this_one() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let short = sample_contract();
        let mut long = sample_contract();
        long.name = "payments:archive".to_string();
        binder.bind(&short).await.expect("short");
        binder.bind(&long).await.expect("long");
        assert_eq!(registry.count(), 4);

        binder.unbind("acme:payments").await.expect("unbind short");
        assert_eq!(
            sorted_names(&registry),
            vec![
                "acme_payments_archive_delete_payment",
                "acme_payments_archive_list_payments"
            ]
        );
    }

    #[tokio::test]
    async fn test_bind_does_not_affect_non_contract_tools() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        // Register a manually added tool
        let manual_tool = Arc::new(DynamicTool::new(
            "manual_tool",
            "Manual",
            "http://localhost",
            "GET",
            ToolSchema {
                schema_type: "object".to_string(),
                properties: Default::default(),
                required: vec![],
            },
            "acme",
        ));
        registry.register(manual_tool);

        let contract = sample_contract();
        binder.bind(&contract).await.expect("bind");
        assert_eq!(registry.count(), 3); // 1 manual + 2 contract

        binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(registry.count(), 1); // manual tool survives
        assert!(registry.exists("manual_tool"));
    }

    #[test]
    fn test_classification_does_not_affect_tool_generation() {
        let mut contract = sample_contract();
        contract.classification = Classification::Vvh;
        let defs = McpBinder::generate_tool_definitions(&contract);
        // Classification is route-level concern, tools still generated
        assert_eq!(defs.len(), 2);
    }
}
