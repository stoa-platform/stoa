//! MCP Protocol Binder
//!
//! Transforms a UAC contract into MCP tools registered in the ToolRegistry.
//! Each endpoint in the contract becomes a DynamicTool with the naming pattern:
//! `{tenant_id}_{contract_name}_{operation_id}`

use std::sync::Arc;

use crate::mcp::tools::dynamic_tool::DynamicTool;
use crate::mcp::tools::{ToolAnnotations, ToolDefinition, ToolRegistry, ToolSchema};
use crate::uac::schema::UacContractSpec;
use crate::uac::Action;

use super::{BindingOutput, ProtocolBinder};

/// MCP protocol binder — generates MCP tools from UAC contracts.
pub struct McpBinder {
    tool_registry: Arc<ToolRegistry>,
}

impl McpBinder {
    /// Create a new MCP binder backed by the given tool registry.
    pub fn new(tool_registry: Arc<ToolRegistry>) -> Self {
        Self { tool_registry }
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

    /// Generate tool definitions from a contract (pure function, no side effects).
    pub fn generate_tool_definitions(contract: &UacContractSpec) -> Vec<ToolDefinition> {
        contract
            .endpoints
            .iter()
            .enumerate()
            .map(|(i, endpoint)| {
                let op_id = endpoint
                    .operation_id
                    .clone()
                    .unwrap_or_else(|| format!("{}-{}", contract.name, i));

                let tool_name = format!("uac:{}:{}:{}", contract.tenant_id, contract.name, op_id);

                // Use first method for action hint (most endpoints have one primary method)
                let primary_method = endpoint
                    .methods
                    .first()
                    .map(|m| m.as_str())
                    .unwrap_or("GET");
                let action = Self::method_to_action(primary_method);

                let description = format!(
                    "{} {} — {} [{}]",
                    primary_method, endpoint.path, contract.name, contract.tenant_id
                );

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
                let op_id = endpoint
                    .operation_id
                    .clone()
                    .unwrap_or_else(|| format!("{}-{}", contract.name, i));

                let tool_name = format!("uac:{}:{}:{}", contract.tenant_id, contract.name, op_id);

                let primary_method = endpoint
                    .methods
                    .first()
                    .map(|m| m.as_str())
                    .unwrap_or("GET");
                let action = Self::method_to_action(primary_method);

                let description = format!(
                    "{} {} — {} [{}]",
                    primary_method, endpoint.path, contract.name, contract.tenant_id
                );

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

        // Create and register new tools
        let tools = Self::create_dynamic_tools(contract);
        let count = tools.len();

        for tool in &tools {
            self.tool_registry.register(Arc::clone(tool));
        }

        tracing::info!(
            contract = %contract_key,
            tools = count,
            "MCP binder: tools generated"
        );

        // Return definitions for the response
        let definitions = Self::generate_tool_definitions(contract);
        Ok(BindingOutput::Tools(definitions))
    }

    async fn unbind(&self, contract_key: &str) -> Result<usize, String> {
        let prefix = Self::tool_prefix(contract_key);
        let removed = self.tool_registry.remove_by_prefix(&prefix);

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
    use crate::uac::schema::{ContractStatus, UacContractSpec, UacEndpoint};

    fn sample_contract() -> UacContractSpec {
        let mut spec = UacContractSpec::new("payments", "acme");
        spec.status = ContractStatus::Published;
        spec.endpoints = vec![
            UacEndpoint {
                path: "/payments".to_string(),
                methods: vec!["GET".to_string(), "POST".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                operation_id: Some("list_payments".to_string()),
                input_schema: None,
                output_schema: None,
            },
            UacEndpoint {
                path: "/payments/{id}".to_string(),
                methods: vec!["DELETE".to_string()],
                backend_url: "https://backend.acme.com/v1/payments".to_string(),
                operation_id: Some("delete_payment".to_string()),
                input_schema: None,
                output_schema: None,
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
