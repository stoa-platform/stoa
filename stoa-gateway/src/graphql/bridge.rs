//! GraphQL→MCP Bridge (CAB-1756)
//!
//! Exposes GraphQL queries and mutations as MCP tools. Each GraphQL field
//! on the root Query/Mutation type becomes a tool that:
//! - Accepts JSON arguments matching the GraphQL argument schema
//! - Sends a GraphQL request to the backend
//! - Returns the JSON response

use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;

use crate::mcp::tools::{
    Tool, ToolAnnotations, ToolContent, ToolContext, ToolDefinition, ToolError, ToolResult,
    ToolSchema,
};
use crate::metrics;
use crate::uac::Action;

use super::introspection::{GraphQLField, GraphQLSchema};

/// The kind of GraphQL operation (query or mutation).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OperationKind {
    Query,
    Mutation,
}

impl OperationKind {
    fn keyword(self) -> &'static str {
        match self {
            Self::Query => "query",
            Self::Mutation => "mutation",
        }
    }
}

/// MCP tool that bridges a GraphQL query or mutation.
///
/// When called via MCP, builds a GraphQL request from JSON arguments,
/// sends it to the backend, and returns the JSON response.
pub struct GraphQLBridgeTool {
    /// Tool name (derived from operation kind + field name)
    tool_name: String,
    /// Human-readable description
    tool_description: String,
    /// GraphQL field definition (from introspection)
    field: GraphQLField,
    /// Whether this is a query or mutation
    operation_kind: OperationKind,
    /// Backend GraphQL endpoint URL
    endpoint_url: String,
    /// HTTP client for making requests
    http_client: reqwest::Client,
    /// Tenant that owns this tool (None = global)
    tenant_id: Option<String>,
}

impl GraphQLBridgeTool {
    /// Create a new GraphQL bridge tool for a specific query/mutation field.
    pub fn new(
        field: GraphQLField,
        operation_kind: OperationKind,
        endpoint_url: &str,
        http_client: reqwest::Client,
        tenant_id: Option<String>,
    ) -> Self {
        let kind_prefix = match operation_kind {
            OperationKind::Query => "query",
            OperationKind::Mutation => "mutation",
        };
        let tool_name = format!("graphql_{kind_prefix}_{}", field.name.to_lowercase());

        let desc = field.description.as_deref().unwrap_or("GraphQL operation");
        let return_type = field.return_type.leaf_name().unwrap_or("Unknown");
        let tool_description = format!(
            "GraphQL {kind_prefix}: {} → {return_type} — {desc}",
            field.name
        );

        Self {
            tool_name,
            tool_description,
            field,
            operation_kind,
            endpoint_url: endpoint_url.to_string(),
            http_client,
            tenant_id,
        }
    }

    /// Build JSON Schema properties from the GraphQL field arguments.
    fn build_input_properties(&self) -> HashMap<String, Value> {
        let mut props = HashMap::new();

        for arg in &self.field.args {
            let schema_type = arg.arg_type.json_schema_type();
            let is_list = arg.arg_type.is_list();

            let desc = arg.description.as_deref().unwrap_or(&arg.name);

            let field_schema = if is_list {
                serde_json::json!({
                    "type": "array",
                    "items": { "type": schema_type },
                    "description": desc
                })
            } else {
                serde_json::json!({
                    "type": schema_type,
                    "description": desc
                })
            };

            props.insert(arg.name.clone(), field_schema);
        }

        // If no args, accept a generic variables object
        if props.is_empty() {
            props.insert(
                "_variables".to_string(),
                serde_json::json!({
                    "type": "object",
                    "description": "GraphQL variables (optional)"
                }),
            );
        }

        props
    }

    /// Build the list of required arguments (NON_NULL types without defaults).
    fn build_required_args(&self) -> Vec<String> {
        self.field
            .args
            .iter()
            .filter(|a| a.arg_type.is_non_null() && a.default_value.is_none())
            .map(|a| a.name.clone())
            .collect()
    }

    /// Build a GraphQL query string from the field definition and arguments.
    ///
    /// Example output for `user(id: $id)`:
    /// ```graphql
    /// query($id: ID!) { user(id: $id) { __typename } }
    /// ```
    fn build_query(&self, args: &Value) -> String {
        let keyword = self.operation_kind.keyword();
        let field_name = &self.field.name;

        if self.field.args.is_empty() {
            return format!("{keyword} {{ {field_name} }}");
        }

        // Build variable declarations and field arguments
        let mut var_decls = Vec::new();
        let mut field_args = Vec::new();

        for arg in &self.field.args {
            // Only include args that are provided
            if args.get(&arg.name).is_some() {
                let gql_type = graphql_type_string(&arg.arg_type);
                var_decls.push(format!("${}: {gql_type}", arg.name));
                field_args.push(format!("{}: ${}", arg.name, arg.name));
            }
        }

        if var_decls.is_empty() {
            format!("{keyword} {{ {field_name} }}")
        } else {
            let vars = var_decls.join(", ");
            let args_str = field_args.join(", ");
            format!("{keyword}({vars}) {{ {field_name}({args_str}) }}")
        }
    }
}

/// Convert a GraphQLTypeRef to a GraphQL type string (e.g., "String!", "[ID!]").
fn graphql_type_string(type_ref: &super::introspection::GraphQLTypeRef) -> String {
    match type_ref.kind.as_str() {
        "NON_NULL" => {
            if let Some(ref inner) = type_ref.of_type {
                format!("{}!", graphql_type_string(inner))
            } else {
                "String!".to_string()
            }
        }
        "LIST" => {
            if let Some(ref inner) = type_ref.of_type {
                format!("[{}]", graphql_type_string(inner))
            } else {
                "[String]".to_string()
            }
        }
        _ => type_ref
            .name
            .clone()
            .unwrap_or_else(|| "String".to_string()),
    }
}

#[async_trait]
impl Tool for GraphQLBridgeTool {
    fn name(&self) -> &str {
        &self.tool_name
    }

    fn description(&self) -> &str {
        &self.tool_description
    }

    fn input_schema(&self) -> ToolSchema {
        ToolSchema {
            schema_type: "object".to_string(),
            properties: self.build_input_properties(),
            required: self.build_required_args(),
        }
    }

    fn output_schema(&self) -> Option<Value> {
        None
    }

    fn required_action(&self) -> Action {
        match self.operation_kind {
            OperationKind::Query => Action::Read,
            OperationKind::Mutation => Action::Create,
        }
    }

    fn tenant_id(&self) -> Option<&str> {
        self.tenant_id.as_deref()
    }

    async fn execute(&self, args: Value, _ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        metrics::track_graphql_bridge_request(&self.field.name);

        // Build the GraphQL query
        let query = self.build_query(&args);

        // Build variables from args (exclude internal _variables key)
        let variables = if self.field.args.is_empty() {
            args.get("_variables").cloned().unwrap_or(Value::Null)
        } else {
            args.clone()
        };

        // Build the GraphQL request payload
        let payload = serde_json::json!({
            "query": query,
            "variables": variables
        });

        // Send to the backend
        let response = self
            .http_client
            .post(&self.endpoint_url)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .json(&payload)
            .send()
            .await
            .map_err(|e| {
                ToolError::ExecutionFailed(format!(
                    "GraphQL request to {} failed: {e}",
                    self.endpoint_url
                ))
            })?;

        let status = response.status();
        let body = response.text().await.map_err(|e| {
            ToolError::ExecutionFailed(format!("Failed to read GraphQL response: {e}"))
        })?;

        if !status.is_success() {
            metrics::track_graphql_bridge_response(&self.field.name, false);
            return Ok(ToolResult {
                content: vec![ToolContent::Text {
                    text: format!("GraphQL endpoint returned HTTP {status}: {body}"),
                }],
                is_error: Some(true),
            });
        }

        // Check for GraphQL errors in response
        if let Ok(json) = serde_json::from_str::<Value>(&body) {
            if let Some(errors) = json.get("errors") {
                if errors.is_array() && !errors.as_array().unwrap_or(&vec![]).is_empty() {
                    metrics::track_graphql_bridge_response(&self.field.name, false);
                    let pretty =
                        serde_json::to_string_pretty(&json).unwrap_or_else(|_| body.clone());
                    return Ok(ToolResult {
                        content: vec![ToolContent::Text { text: pretty }],
                        is_error: Some(true),
                    });
                }
            }
        }

        // Pretty-print the response
        let output = match serde_json::from_str::<Value>(&body) {
            Ok(json) => serde_json::to_string_pretty(&json).unwrap_or(body),
            Err(_) => body,
        };

        metrics::track_graphql_bridge_response(&self.field.name, true);

        Ok(ToolResult {
            content: vec![ToolContent::Text { text: output }],
            is_error: None,
        })
    }

    fn definition(&self) -> ToolDefinition {
        let kind_label = match self.operation_kind {
            OperationKind::Query => "Query",
            OperationKind::Mutation => "Mutation",
        };
        ToolDefinition {
            name: self.tool_name.clone(),
            description: self.tool_description.clone(),
            input_schema: self.input_schema(),
            output_schema: self.output_schema(),
            annotations: Some(
                ToolAnnotations::from_action(self.required_action())
                    .with_title(format!("GraphQL {kind_label}: {}", self.field.name)),
            ),
            tenant_id: self.tenant_id.clone(),
        }
    }
}

/// Create MCP tools from a parsed GraphQL schema.
///
/// Each query field becomes a read tool, each mutation field becomes a write tool.
pub fn create_tools_from_schema(
    schema: &GraphQLSchema,
    endpoint_url: &str,
    http_client: reqwest::Client,
    tenant_id: Option<String>,
) -> Vec<GraphQLBridgeTool> {
    let mut tools = Vec::new();

    for field in &schema.queries {
        tools.push(GraphQLBridgeTool::new(
            field.clone(),
            OperationKind::Query,
            endpoint_url,
            http_client.clone(),
            tenant_id.clone(),
        ));
    }

    for field in &schema.mutations {
        tools.push(GraphQLBridgeTool::new(
            field.clone(),
            OperationKind::Mutation,
            endpoint_url,
            http_client.clone(),
            tenant_id.clone(),
        ));
    }

    tools
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graphql::introspection::{parse_introspection, GraphQLArg, GraphQLTypeRef};

    fn sample_schema() -> GraphQLSchema {
        let json = serde_json::json!({
            "data": {
                "__schema": {
                    "queryType": { "name": "Query" },
                    "mutationType": { "name": "Mutation" },
                    "types": [
                        {
                            "name": "Query",
                            "kind": "OBJECT",
                            "description": null,
                            "fields": [
                                {
                                    "name": "user",
                                    "description": "Get a user by ID",
                                    "args": [{
                                        "name": "id",
                                        "description": "User ID",
                                        "type": {
                                            "name": null,
                                            "kind": "NON_NULL",
                                            "ofType": { "name": "ID", "kind": "SCALAR", "ofType": null }
                                        },
                                        "defaultValue": null
                                    }],
                                    "type": { "name": "User", "kind": "OBJECT", "ofType": null }
                                },
                                {
                                    "name": "users",
                                    "description": "List users",
                                    "args": [],
                                    "type": {
                                        "name": null,
                                        "kind": "LIST",
                                        "ofType": { "name": "User", "kind": "OBJECT", "ofType": null }
                                    }
                                }
                            ]
                        },
                        {
                            "name": "Mutation",
                            "kind": "OBJECT",
                            "description": null,
                            "fields": [
                                {
                                    "name": "createUser",
                                    "description": "Create a new user",
                                    "args": [
                                        {
                                            "name": "name",
                                            "description": "User name",
                                            "type": {
                                                "name": null,
                                                "kind": "NON_NULL",
                                                "ofType": { "name": "String", "kind": "SCALAR", "ofType": null }
                                            },
                                            "defaultValue": null
                                        },
                                        {
                                            "name": "email",
                                            "description": "Optional email",
                                            "type": { "name": "String", "kind": "SCALAR", "ofType": null },
                                            "defaultValue": null
                                        }
                                    ],
                                    "type": { "name": "User", "kind": "OBJECT", "ofType": null }
                                }
                            ]
                        },
                        {
                            "name": "User",
                            "kind": "OBJECT",
                            "description": null,
                            "fields": [
                                { "name": "id", "description": null, "args": [], "type": { "name": "ID", "kind": "SCALAR", "ofType": null } },
                                { "name": "name", "description": null, "args": [], "type": { "name": "String", "kind": "SCALAR", "ofType": null } }
                            ]
                        }
                    ]
                }
            }
        });
        parse_introspection(&json).expect("should parse")
    }

    fn make_query_tool() -> GraphQLBridgeTool {
        let schema = sample_schema();
        GraphQLBridgeTool::new(
            schema.queries[0].clone(), // user(id: ID!)
            OperationKind::Query,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            None,
        )
    }

    fn make_mutation_tool() -> GraphQLBridgeTool {
        let schema = sample_schema();
        GraphQLBridgeTool::new(
            schema.mutations[0].clone(), // createUser(name: String!, email: String)
            OperationKind::Mutation,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            Some("tenant-a".to_string()),
        )
    }

    #[test]
    fn test_query_tool_name() {
        let tool = make_query_tool();
        assert_eq!(tool.name(), "graphql_query_user");
    }

    #[test]
    fn test_mutation_tool_name() {
        let tool = make_mutation_tool();
        assert_eq!(tool.name(), "graphql_mutation_createuser");
    }

    #[test]
    fn test_query_tool_description() {
        let tool = make_query_tool();
        let desc = tool.description();
        assert!(desc.contains("GraphQL query"));
        assert!(desc.contains("user"));
        assert!(desc.contains("User"));
        assert!(desc.contains("Get a user by ID"));
    }

    #[test]
    fn test_mutation_tool_description() {
        let tool = make_mutation_tool();
        let desc = tool.description();
        assert!(desc.contains("GraphQL mutation"));
        assert!(desc.contains("createUser"));
    }

    #[test]
    fn test_query_input_schema() {
        let tool = make_query_tool();
        let schema = tool.input_schema();
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.contains_key("id"));
        assert!(schema.required.contains(&"id".to_string()));
    }

    #[test]
    fn test_mutation_input_schema() {
        let tool = make_mutation_tool();
        let schema = tool.input_schema();
        assert!(schema.properties.contains_key("name"));
        assert!(schema.properties.contains_key("email"));
        // name is NON_NULL without default → required
        assert!(schema.required.contains(&"name".to_string()));
        // email is nullable → not required
        assert!(!schema.required.contains(&"email".to_string()));
    }

    #[test]
    fn test_query_required_action() {
        let tool = make_query_tool();
        assert_eq!(tool.required_action(), Action::Read);
    }

    #[test]
    fn test_mutation_required_action() {
        let tool = make_mutation_tool();
        assert_eq!(tool.required_action(), Action::Create);
    }

    #[test]
    fn test_query_build_query() {
        let tool = make_query_tool();
        let args = serde_json::json!({"id": "123"});
        let query = tool.build_query(&args);
        assert!(query.starts_with("query("));
        assert!(query.contains("$id: ID!"));
        assert!(query.contains("user(id: $id)"));
    }

    #[test]
    fn test_query_build_query_no_args_provided() {
        let schema = sample_schema();
        let tool = GraphQLBridgeTool::new(
            schema.queries[1].clone(), // users (no args)
            OperationKind::Query,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            None,
        );
        let query = tool.build_query(&serde_json::json!({}));
        assert_eq!(query, "query { users }");
    }

    #[test]
    fn test_mutation_build_query() {
        let tool = make_mutation_tool();
        let args = serde_json::json!({"name": "Alice", "email": "alice@example.com"});
        let query = tool.build_query(&args);
        assert!(query.starts_with("mutation("));
        assert!(query.contains("$name: String!"));
        assert!(query.contains("$email: String"));
        assert!(query.contains("createUser("));
    }

    #[test]
    fn test_tool_definition() {
        let tool = make_query_tool();
        let def = tool.definition();
        assert_eq!(def.name, "graphql_query_user");
        assert!(def.annotations.is_some());
        let ann = def.annotations.unwrap();
        assert!(ann
            .title
            .as_ref()
            .is_some_and(|t| t.contains("GraphQL Query: user")));
    }

    #[test]
    fn test_tenant_id() {
        let tool = make_mutation_tool();
        assert_eq!(tool.tenant_id(), Some("tenant-a"));
    }

    #[test]
    fn test_create_tools_from_schema() {
        let schema = sample_schema();
        let tools = create_tools_from_schema(
            &schema,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            None,
        );
        // 2 queries + 1 mutation = 3 tools
        assert_eq!(tools.len(), 3);
        assert_eq!(tools[0].name(), "graphql_query_user");
        assert_eq!(tools[1].name(), "graphql_query_users");
        assert_eq!(tools[2].name(), "graphql_mutation_createuser");
    }

    #[test]
    fn test_no_args_schema_fallback() {
        let field = GraphQLField {
            name: "version".to_string(),
            description: Some("Get version".to_string()),
            args: vec![],
            return_type: GraphQLTypeRef {
                name: Some("String".to_string()),
                kind: "SCALAR".to_string(),
                of_type: None,
            },
        };
        let tool = GraphQLBridgeTool::new(
            field,
            OperationKind::Query,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            None,
        );
        let schema = tool.input_schema();
        assert!(schema.properties.contains_key("_variables"));
    }

    #[test]
    fn test_graphql_type_string() {
        let non_null_string = GraphQLTypeRef {
            name: None,
            kind: "NON_NULL".to_string(),
            of_type: Some(Box::new(GraphQLTypeRef {
                name: Some("String".to_string()),
                kind: "SCALAR".to_string(),
                of_type: None,
            })),
        };
        assert_eq!(graphql_type_string(&non_null_string), "String!");

        let list_id = GraphQLTypeRef {
            name: None,
            kind: "LIST".to_string(),
            of_type: Some(Box::new(GraphQLTypeRef {
                name: Some("ID".to_string()),
                kind: "SCALAR".to_string(),
                of_type: None,
            })),
        };
        assert_eq!(graphql_type_string(&list_id), "[ID]");
    }

    #[test]
    fn test_build_required_args_with_default() {
        let field = GraphQLField {
            name: "search".to_string(),
            description: None,
            args: vec![
                GraphQLArg {
                    name: "query".to_string(),
                    description: None,
                    arg_type: GraphQLTypeRef {
                        name: None,
                        kind: "NON_NULL".to_string(),
                        of_type: Some(Box::new(GraphQLTypeRef {
                            name: Some("String".to_string()),
                            kind: "SCALAR".to_string(),
                            of_type: None,
                        })),
                    },
                    default_value: None,
                },
                GraphQLArg {
                    name: "limit".to_string(),
                    description: None,
                    arg_type: GraphQLTypeRef {
                        name: None,
                        kind: "NON_NULL".to_string(),
                        of_type: Some(Box::new(GraphQLTypeRef {
                            name: Some("Int".to_string()),
                            kind: "SCALAR".to_string(),
                            of_type: None,
                        })),
                    },
                    default_value: Some("10".to_string()),
                },
            ],
            return_type: GraphQLTypeRef {
                name: Some("String".to_string()),
                kind: "SCALAR".to_string(),
                of_type: None,
            },
        };
        let tool = GraphQLBridgeTool::new(
            field,
            OperationKind::Query,
            "http://localhost:4000/graphql",
            reqwest::Client::new(),
            None,
        );
        let required = tool.build_required_args();
        // query is NON_NULL without default → required
        assert!(required.contains(&"query".to_string()));
        // limit is NON_NULL WITH default → not required
        assert!(!required.contains(&"limit".to_string()));
    }
}
