//! gRPC→MCP Bridge (CAB-1755)
//!
//! Exposes gRPC services as MCP tools. Each RPC method becomes a tool that:
//! - Accepts JSON arguments matching the protobuf message schema
//! - Sends JSON-encoded gRPC requests (application/grpc+json) to the backend
//! - Returns JSON responses from the backend
//!
//! Uses gRPC-web JSON encoding for simplicity — no binary protobuf serialization.
//! This means the backend must support `application/grpc+json` or a gRPC-web proxy
//! must be in front of it (e.g., Envoy, grpc-web).

use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;

use crate::mcp::tools::{
    Tool, ToolAnnotations, ToolContent, ToolContext, ToolDefinition, ToolError, ToolResult,
    ToolSchema,
};
use crate::metrics;
use crate::uac::Action;

use super::proto_parser::{ProtoFile, ProtoMessage, ProtoMethod};

/// MCP tool that bridges a gRPC method.
///
/// When called via MCP, converts JSON arguments to a gRPC-JSON request,
/// sends it to the backend, and returns the JSON response.
pub struct GrpcBridgeTool {
    /// Tool name (derived from service + method)
    tool_name: String,
    /// Human-readable description
    tool_description: String,
    /// gRPC method metadata
    method: ProtoMethod,
    /// Input message schema (for JSON Schema generation)
    input_message: Option<ProtoMessage>,
    /// Full gRPC path (e.g., /package.Service/Method)
    grpc_path: String,
    /// Backend gRPC endpoint URL
    endpoint_url: String,
    /// HTTP client for making requests
    http_client: reqwest::Client,
    /// Tenant that owns this tool (None = global)
    tenant_id: Option<String>,
}

impl GrpcBridgeTool {
    /// Create a new gRPC bridge tool for a specific RPC method.
    pub fn new(
        service_name: &str,
        method: ProtoMethod,
        input_message: Option<ProtoMessage>,
        package: &str,
        endpoint_url: &str,
        http_client: reqwest::Client,
        tenant_id: Option<String>,
    ) -> Self {
        let grpc_path = method.grpc_path(package, service_name);
        let tool_name = format!(
            "grpc_{}_{}",
            service_name.to_lowercase(),
            method.name.to_lowercase()
        );

        let doc = method.documentation.as_deref().unwrap_or("gRPC method");
        let streaming_info = match (method.client_streaming, method.server_streaming) {
            (false, false) => "unary",
            (false, true) => "server-streaming",
            (true, false) => "client-streaming",
            (true, true) => "bidirectional-streaming",
        };
        let tool_description = format!(
            "gRPC bridge: {service_name}.{} ({streaming_info}) — {doc}",
            method.name
        );

        Self {
            tool_name,
            tool_description,
            method,
            input_message,
            grpc_path,
            endpoint_url: endpoint_url.to_string(),
            http_client,
            tenant_id,
        }
    }

    /// Build JSON Schema properties from the input message definition.
    fn build_input_properties(&self) -> HashMap<String, Value> {
        let mut props = HashMap::new();

        if let Some(ref msg) = self.input_message {
            for field in &msg.fields {
                let schema_type = field.json_schema_type();
                let mut field_schema = serde_json::json!({
                    "type": schema_type,
                    "description": format!("Proto field: {} ({})", field.name, field.field_type)
                });

                if field.repeated {
                    field_schema = serde_json::json!({
                        "type": "array",
                        "items": { "type": schema_type },
                        "description": format!("Proto repeated field: {} ({})", field.name, field.field_type)
                    });
                }

                props.insert(field.name.clone(), field_schema);
            }
        }

        // If no message definition, accept a generic JSON object
        if props.is_empty() {
            props.insert(
                "payload".to_string(),
                serde_json::json!({
                    "type": "object",
                    "description": "gRPC request payload as JSON"
                }),
            );
        }

        props
    }

    /// Build the list of required fields from the input message.
    fn build_required_fields(&self) -> Vec<String> {
        match &self.input_message {
            Some(msg) => msg
                .fields
                .iter()
                .filter(|f| !f.optional)
                .map(|f| f.name.clone())
                .collect(),
            None => vec!["payload".to_string()],
        }
    }
}

#[async_trait]
impl Tool for GrpcBridgeTool {
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
            required: self.build_required_fields(),
        }
    }

    fn output_schema(&self) -> Option<Value> {
        None
    }

    fn required_action(&self) -> Action {
        Action::Read
    }

    fn tenant_id(&self) -> Option<&str> {
        self.tenant_id.as_deref()
    }

    async fn execute(&self, args: Value, _ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        // Streaming methods are not supported via MCP (unary only)
        if self.method.client_streaming || self.method.server_streaming {
            return Err(ToolError::InvalidArguments(format!(
                "Streaming gRPC method '{}' cannot be called via MCP bridge (unary only)",
                self.method.name
            )));
        }

        metrics::track_grpc_bridge_request(&self.method.name);

        // Build the JSON payload for gRPC-JSON encoding
        let payload = if self.input_message.is_some() {
            // Use the args directly as the message fields
            args.clone()
        } else {
            // Fallback: use the "payload" field
            args.get("payload")
                .cloned()
                .unwrap_or(Value::Object(serde_json::Map::new()))
        };

        // Build the full URL: endpoint + gRPC path
        let url = format!(
            "{}/{}",
            self.endpoint_url.trim_end_matches('/'),
            self.grpc_path.trim_start_matches('/')
        );

        // Send as gRPC-web JSON (application/json for gRPC-web compatibility)
        let response = self
            .http_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .json(&payload)
            .send()
            .await
            .map_err(|e| {
                ToolError::ExecutionFailed(format!(
                    "gRPC request to {} failed: {e}",
                    self.grpc_path
                ))
            })?;

        let status = response.status();
        let resp_headers = response.headers().clone();

        // Check for gRPC status in headers
        let grpc_status = resp_headers
            .get("grpc-status")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.parse::<u32>().ok());

        let body = response.text().await.map_err(|e| {
            ToolError::ExecutionFailed(format!("Failed to read gRPC response: {e}"))
        })?;

        // Handle gRPC errors
        if let Some(gs) = grpc_status {
            if gs != 0 {
                let grpc_message = resp_headers
                    .get("grpc-message")
                    .and_then(|v| v.to_str().ok())
                    .unwrap_or("Unknown error");
                metrics::track_grpc_bridge_response(&self.method.name, false);
                return Ok(ToolResult {
                    content: vec![ToolContent::Text {
                        text: format!("gRPC error (status {gs}): {grpc_message}"),
                    }],
                    is_error: Some(true),
                });
            }
        }

        if !status.is_success() {
            metrics::track_grpc_bridge_response(&self.method.name, false);
            return Ok(ToolResult {
                content: vec![ToolContent::Text {
                    text: format!("gRPC endpoint returned HTTP {status}: {body}"),
                }],
                is_error: Some(true),
            });
        }

        // Try to parse as JSON for pretty printing
        let output = match serde_json::from_str::<Value>(&body) {
            Ok(json) => serde_json::to_string_pretty(&json).unwrap_or(body),
            Err(_) => body,
        };

        metrics::track_grpc_bridge_response(&self.method.name, true);

        Ok(ToolResult {
            content: vec![ToolContent::Text { text: output }],
            is_error: None,
        })
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.tool_name.clone(),
            description: self.tool_description.clone(),
            input_schema: self.input_schema(),
            output_schema: self.output_schema(),
            annotations: Some(
                ToolAnnotations::from_action(Action::Read)
                    .with_title(format!("gRPC: {}", self.method.name)),
            ),
            tenant_id: self.tenant_id.clone(),
        }
    }
}

/// Create MCP tools from a parsed proto file.
///
/// Each unary RPC method becomes a tool. Streaming methods are registered
/// but return an error when called (MCP doesn't support streaming).
pub fn create_tools_from_proto(
    proto: &ProtoFile,
    endpoint_url: &str,
    http_client: reqwest::Client,
    tenant_id: Option<String>,
) -> Vec<GrpcBridgeTool> {
    let mut tools = Vec::new();

    for service in &proto.services {
        for method in &service.methods {
            let input_message = proto.messages.get(&method.input_type).cloned();

            let tool = GrpcBridgeTool::new(
                &service.name,
                method.clone(),
                input_message,
                &proto.package,
                endpoint_url,
                http_client.clone(),
                tenant_id.clone(),
            );

            tools.push(tool);
        }
    }

    tools
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::grpc::proto_parser::parse_proto;

    const TEST_PROTO: &str = r#"
syntax = "proto3";
package test.v1;

// Test service for unit testing.
service TestService {
    // Simple unary call.
    rpc GetItem (GetItemRequest) returns (GetItemResponse);
    // Server streaming.
    rpc WatchItems (WatchRequest) returns (stream ItemEvent);
}

message GetItemRequest {
    string id = 1;
    optional string locale = 2;
}

message GetItemResponse {
    string id = 1;
    string name = 2;
    int32 quantity = 3;
}

message WatchRequest {
    repeated string ids = 1;
}

message ItemEvent {
    string item_id = 1;
    string event_type = 2;
}
"#;

    fn make_tool(method_index: usize) -> GrpcBridgeTool {
        let proto = parse_proto(TEST_PROTO).expect("should parse");
        let service = &proto.services[0];
        let method = &service.methods[method_index];
        let input_message = proto.messages.get(&method.input_type).cloned();
        GrpcBridgeTool::new(
            &service.name,
            method.clone(),
            input_message,
            &proto.package,
            "http://localhost:50051",
            reqwest::Client::new(),
            None,
        )
    }

    #[test]
    fn test_tool_name_format() {
        let tool = make_tool(0);
        assert_eq!(tool.name(), "grpc_testservice_getitem");
    }

    #[test]
    fn test_tool_description() {
        let tool = make_tool(0);
        let desc = tool.description();
        assert!(desc.contains("gRPC bridge"));
        assert!(desc.contains("TestService.GetItem"));
        assert!(desc.contains("unary"));
        assert!(desc.contains("Simple unary call"));
    }

    #[test]
    fn test_streaming_description() {
        let tool = make_tool(1);
        let desc = tool.description();
        assert!(desc.contains("server-streaming"));
    }

    #[test]
    fn test_input_schema_from_message() {
        let tool = make_tool(0);
        let schema = tool.input_schema();
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.contains_key("id"));
        assert!(schema.properties.contains_key("locale"));
        // "id" should be required, "locale" is optional
        assert!(schema.required.contains(&"id".to_string()));
        assert!(!schema.required.contains(&"locale".to_string()));
    }

    #[test]
    fn test_input_schema_types() {
        let tool = make_tool(0);
        let props = &tool.input_schema().properties;
        let id_schema = &props["id"];
        assert_eq!(id_schema["type"], "string");
    }

    #[test]
    fn test_grpc_path() {
        let tool = make_tool(0);
        assert_eq!(tool.grpc_path, "/test.v1.TestService/GetItem");
    }

    #[test]
    fn test_create_tools_from_proto() {
        let proto = parse_proto(TEST_PROTO).expect("should parse");
        let tools = create_tools_from_proto(
            &proto,
            "http://localhost:50051",
            reqwest::Client::new(),
            None,
        );
        // Should create tools for all methods (unary + streaming)
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].name(), "grpc_testservice_getitem");
        assert_eq!(tools[1].name(), "grpc_testservice_watchitems");
    }

    #[test]
    fn test_tool_definition() {
        let tool = make_tool(0);
        let def = tool.definition();
        assert_eq!(def.name, "grpc_testservice_getitem");
        assert!(def.annotations.is_some());
        let ann = def.annotations.unwrap();
        assert!(ann
            .title
            .as_ref()
            .is_some_and(|t| t.contains("gRPC: GetItem")));
    }

    #[test]
    fn test_build_input_properties_repeated() {
        let tool = make_tool(1); // WatchItems with repeated ids
        let props = tool.build_input_properties();
        let ids_schema = &props["ids"];
        assert_eq!(ids_schema["type"], "array");
        assert_eq!(ids_schema["items"]["type"], "string");
    }

    #[tokio::test]
    async fn test_streaming_method_returns_error() {
        let tool = make_tool(1); // WatchItems is server-streaming
        let ctx = ToolContext {
            tenant_id: "test".to_string(),
            user_id: None,
            user_email: None,
            request_id: "req-1".to_string(),
            roles: vec![],
            scopes: vec![],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test".to_string(),
            from_control_plane: false,
        };
        let result = tool.execute(serde_json::json!({"ids": ["1"]}), &ctx).await;
        assert!(result.is_err());
        match result {
            Err(ToolError::InvalidArguments(msg)) => {
                assert!(msg.contains("Streaming"));
                assert!(msg.contains("unary only"));
            }
            _ => panic!("Expected InvalidArguments error"),
        }
    }

    #[test]
    fn test_no_input_message_fallback() {
        let method = ProtoMethod {
            name: "CustomCall".to_string(),
            input_type: "UnknownMessage".to_string(),
            output_type: "UnknownResponse".to_string(),
            client_streaming: false,
            server_streaming: false,
            documentation: None,
        };
        let tool = GrpcBridgeTool::new(
            "TestService",
            method,
            None, // no message definition
            "test.v1",
            "http://localhost:50051",
            reqwest::Client::new(),
            Some("tenant-a".to_string()),
        );
        let schema = tool.input_schema();
        // Should fall back to generic "payload" field
        assert!(schema.properties.contains_key("payload"));
        assert!(schema.required.contains(&"payload".to_string()));
        assert_eq!(tool.tenant_id(), Some("tenant-a"));
    }
}
