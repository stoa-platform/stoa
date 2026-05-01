//! MCP Protocol Binder
//!
//! Transforms a UAC contract into MCP tools registered in the ToolRegistry.
//! Each endpoint in the contract becomes a DynamicTool with the naming pattern:
//! `{tenant_id}_{contract_name}_{operation_id}`

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::RwLock;

use crate::mcp::tools::dynamic_tool::DynamicTool;
use crate::mcp::tools::{ToolAnnotations, ToolDefinition, ToolRegistry, ToolSchema};
use crate::uac::schema::{EndpointSideEffects, UacContractSpec, UacEndpoint};
use crate::uac::Action;

use super::{BindingOutput, ProtocolBinder};

/// MCP protocol binder — generates MCP tools from UAC contracts.
pub struct McpBinder {
    tool_registry: Arc<ToolRegistry>,
    contract_tool_names: RwLock<HashMap<String, Vec<String>>>,
}

impl McpBinder {
    /// Create a new MCP binder backed by the given tool registry.
    pub fn new(tool_registry: Arc<ToolRegistry>) -> Self {
        Self {
            tool_registry,
            contract_tool_names: RwLock::new(HashMap::new()),
        }
    }

    /// Tool name prefix for a contract (used for cascade deletion).
    pub fn tool_prefix(contract_key: &str) -> String {
        // contract_key = "tenant_id:contract_name"
        // prefix = "uac:tenant_id:contract_name:"
        format!("uac:{}:", contract_key)
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
    /// name. Legacy endpoints keep the namespaced UAC fallback.
    fn tool_name(contract: &UacContractSpec, endpoint: &UacEndpoint, index: usize) -> String {
        if let Some(llm) = endpoint.llm.as_ref() {
            return llm.tool_name.clone();
        }

        let op_id = endpoint
            .operation_id
            .clone()
            .unwrap_or_else(|| format!("{}-{}", contract.name, index));

        format!("uac:{}:{}:{}", contract.tenant_id, contract.name, op_id)
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

    /// Generate tool definitions from a contract (pure function, no side effects).
    pub fn generate_tool_definitions(contract: &UacContractSpec) -> Vec<ToolDefinition> {
        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                // Use first method for action hint (most endpoints have one primary method)
                let primary_method = endpoint
                    .methods
                    .first()
                    .map(|m| m.as_str())
                    .unwrap_or("GET");
                let action = Self::endpoint_action(endpoint, primary_method);
                let tool_name = Self::tool_name(contract, endpoint, i);
                let description = Self::description(contract, endpoint, primary_method);

                // Build input schema from endpoint schema or default empty object
                let input_schema = endpoint
                    .input_schema
                    .as_ref()
                    .map(crate::mcp::tools::dynamic_tool::schema_from_value)
                    .unwrap_or_else(|| ToolSchema {
                        schema_type: "object".to_string(),
                        properties: Default::default(),
                        required: vec![],
                    });

                ToolDefinition {
                    name: tool_name,
                    description,
                    input_schema,
                    output_schema: endpoint.output_schema.clone(),
                    annotations: Some(ToolAnnotations::from_action(action)),
                    tenant_id: Some(contract.tenant_id.clone()),
                }
            })
            .collect()
    }

    /// Create DynamicTool instances from a contract for registration.
    fn create_dynamic_tools(contract: &UacContractSpec) -> Vec<Arc<dyn crate::mcp::tools::Tool>> {
        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                let primary_method = endpoint
                    .methods
                    .first()
                    .map(|m| m.as_str())
                    .unwrap_or("GET");
                let action = Self::endpoint_action(endpoint, primary_method);
                let tool_name = Self::tool_name(contract, endpoint, i);
                let description = Self::description(contract, endpoint, primary_method);

                let input_schema = endpoint
                    .input_schema
                    .as_ref()
                    .map(crate::mcp::tools::dynamic_tool::schema_from_value)
                    .unwrap_or_else(|| ToolSchema {
                        schema_type: "object".to_string(),
                        properties: Default::default(),
                        required: vec![],
                    });

                let tool = DynamicTool::new(
                    &tool_name,
                    &description,
                    &endpoint.backend_url,
                    primary_method,
                    input_schema,
                    &contract.tenant_id,
                )
                .with_action(action)
                .with_annotations(ToolAnnotations::from_action(action));

                Arc::new(tool) as Arc<dyn crate::mcp::tools::Tool>
            })
            .collect()
    }
}

impl ProtocolBinder for McpBinder {
    async fn bind(&self, contract: &UacContractSpec) -> Result<BindingOutput, String> {
        let contract_key = format!("{}:{}", contract.tenant_id, contract.name);
        let prefix = Self::tool_prefix(&contract_key);

        // Remove existing tools for this contract (idempotent re-bind)
        self.tool_registry.remove_by_prefix(&prefix);
        if let Some(previous_names) = self.contract_tool_names.write().remove(&contract_key) {
            for name in previous_names {
                self.tool_registry.unregister(&name);
            }
        }

        // Create and register new tools
        let tools = Self::create_dynamic_tools(contract);
        let count = tools.len();
        let definitions = Self::generate_tool_definitions(contract);

        for tool in &tools {
            self.tool_registry.register(Arc::clone(tool));
        }
        self.contract_tool_names.write().insert(
            contract_key.clone(),
            definitions.iter().map(|d| d.name.clone()).collect(),
        );

        tracing::info!(
            contract = %contract_key,
            tools = count,
            "MCP binder: tools generated"
        );

        Ok(BindingOutput::Tools(definitions))
    }

    async fn unbind(&self, contract_key: &str) -> Result<usize, String> {
        let prefix = Self::tool_prefix(contract_key);
        let mut removed = self.tool_registry.remove_by_prefix(&prefix);
        if let Some(previous_names) = self.contract_tool_names.write().remove(contract_key) {
            for name in previous_names {
                if self.tool_registry.unregister(&name) {
                    removed += 1;
                }
            }
        }

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

    #[test]
    fn test_tool_prefix() {
        assert_eq!(
            McpBinder::tool_prefix("acme:payments"),
            "uac:acme:payments:"
        );
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
        assert_eq!(defs[0].name, "uac:acme:payments:list_payments");
        assert_eq!(defs[1].name, "uac:acme:payments:delete_payment");
    }

    #[test]
    fn test_generate_definitions_uses_llm_tool_name() {
        let mut contract = sample_contract();
        contract.endpoints[0].llm = Some(EndpointLlm {
            summary: "List customer payments.".to_string(),
            intent: "Use to inspect payments without changing state.".to_string(),
            tool_name: "list_customer_payments".to_string(),
            side_effects: EndpointSideEffects::Read,
            safe_for_agents: true,
            requires_human_approval: false,
            examples: vec![EndpointLlmExample {
                input: serde_json::json!({}),
                expected_output_contains: None,
            }],
        });

        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "list_customer_payments");
    }

    #[test]
    fn test_generate_definitions_name_fallback() {
        let mut contract = sample_contract();
        contract.endpoints[0].operation_id = None;
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert_eq!(defs[0].name, "uac:acme:payments:payments-0");
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
    fn test_generate_definitions_with_output_schema() {
        let mut contract = sample_contract();
        contract.endpoints[0].output_schema = Some(serde_json::json!({"type": "array"}));
        let defs = McpBinder::generate_tool_definitions(&contract);
        assert!(defs[0].output_schema.is_some());
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
        assert!(registry.exists("uac:acme:payments:list_payments"));
        assert!(registry.exists("uac:acme:payments:delete_payment"));
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
        contract.endpoints[0].llm = Some(EndpointLlm {
            summary: "List customer payments.".to_string(),
            intent: "Use to inspect payments without changing state.".to_string(),
            tool_name: "list_customer_payments".to_string(),
            side_effects: EndpointSideEffects::Read,
            safe_for_agents: true,
            requires_human_approval: false,
            examples: vec![EndpointLlmExample {
                input: serde_json::json!({}),
                expected_output_contains: None,
            }],
        });

        binder.bind(&contract).await.expect("bind");
        assert!(registry.exists("list_customer_payments"));

        let removed = binder.unbind("acme:payments").await.expect("unbind");
        assert_eq!(removed, 2);
        assert_eq!(registry.count(), 0);
    }

    #[tokio::test]
    async fn test_unbind_nonexistent_returns_zero() {
        let registry = Arc::new(ToolRegistry::new());
        let binder = McpBinder::new(registry.clone());

        let removed = binder.unbind("unknown:contract").await.expect("unbind");
        assert_eq!(removed, 0);
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
