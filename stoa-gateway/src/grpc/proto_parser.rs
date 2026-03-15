//! Proto File Parser (CAB-1755)
//!
//! Lightweight `.proto` text parser that extracts service definitions,
//! RPC methods, and message field schemas without requiring `protoc`.
//!
//! Supports proto3 syntax with:
//! - Service and RPC method extraction
//! - Message field parsing (name, type, number)
//! - Nested message support
//! - Package and option extraction
//! - Comment-based documentation extraction

use std::collections::HashMap;

/// A parsed `.proto` file.
#[derive(Debug, Clone)]
pub struct ProtoFile {
    /// Proto syntax version (e.g., "proto3")
    pub syntax: String,
    /// Package name (e.g., "grpc.health.v1")
    pub package: String,
    /// Service definitions
    pub services: Vec<ProtoService>,
    /// Top-level message definitions
    pub messages: HashMap<String, ProtoMessage>,
    /// File-level options
    pub options: HashMap<String, String>,
}

/// A gRPC service definition.
#[derive(Debug, Clone)]
pub struct ProtoService {
    /// Service name
    pub name: String,
    /// RPC methods
    pub methods: Vec<ProtoMethod>,
    /// Leading comment documentation
    pub documentation: Option<String>,
}

/// An RPC method definition.
#[derive(Debug, Clone)]
pub struct ProtoMethod {
    /// Method name
    pub name: String,
    /// Input message type name
    pub input_type: String,
    /// Output message type name
    pub output_type: String,
    /// Whether the client sends a stream
    pub client_streaming: bool,
    /// Whether the server sends a stream
    pub server_streaming: bool,
    /// Leading comment documentation
    pub documentation: Option<String>,
}

impl ProtoMethod {
    /// Build the full gRPC path: `/package.Service/Method`
    pub fn grpc_path(&self, package: &str, service_name: &str) -> String {
        if package.is_empty() {
            format!("/{service_name}/{}", self.name)
        } else {
            format!("/{package}.{service_name}/{}", self.name)
        }
    }
}

/// A protobuf message definition.
#[derive(Debug, Clone)]
pub struct ProtoMessage {
    /// Message name
    pub name: String,
    /// Fields
    pub fields: Vec<ProtoField>,
    /// Leading comment documentation
    pub documentation: Option<String>,
}

/// A message field.
#[derive(Debug, Clone)]
pub struct ProtoField {
    /// Field name
    pub name: String,
    /// Field type (e.g., "string", "int32", "MyMessage")
    pub field_type: String,
    /// Field number
    pub number: u32,
    /// Whether this is a repeated field
    pub repeated: bool,
    /// Whether this is an optional field (proto3 explicit optional)
    pub optional: bool,
}

impl ProtoField {
    /// Convert proto field type to JSON Schema type.
    pub fn json_schema_type(&self) -> &str {
        match self.field_type.as_str() {
            "string" | "bytes" => "string",
            "bool" => "boolean",
            "int32" | "sint32" | "uint32" | "fixed32" | "sfixed32" | "int64" | "sint64"
            | "uint64" | "fixed64" | "sfixed64" => "integer",
            "float" | "double" => "number",
            _ => "object", // nested message types
        }
    }

    /// Check if this is a scalar (non-message) type.
    pub fn is_scalar(&self) -> bool {
        matches!(
            self.field_type.as_str(),
            "string"
                | "bytes"
                | "bool"
                | "int32"
                | "sint32"
                | "uint32"
                | "fixed32"
                | "sfixed32"
                | "int64"
                | "sint64"
                | "uint64"
                | "fixed64"
                | "sfixed64"
                | "float"
                | "double"
        )
    }
}

/// Parse a `.proto` file content into a `ProtoFile`.
///
/// This is a best-effort text parser — it handles common proto3 patterns
/// but may not cover all edge cases (oneofs, maps, extensions, etc.).
pub fn parse_proto(content: &str) -> Result<ProtoFile, String> {
    let mut syntax = String::from("proto3");
    let mut package = String::new();
    let mut services: Vec<ProtoService> = Vec::new();
    let mut messages: HashMap<String, ProtoMessage> = HashMap::new();
    let mut options: HashMap<String, String> = HashMap::new();

    let lines: Vec<&str> = content.lines().collect();
    let mut i = 0;
    let mut last_comment: Option<String> = None;

    while i < lines.len() {
        let line = lines[i].trim();

        // Skip empty lines
        if line.is_empty() {
            last_comment = None;
            i += 1;
            continue;
        }

        // Collect single-line comments as documentation
        if line.starts_with("//") {
            let comment_text = line.trim_start_matches("//").trim();
            match &mut last_comment {
                Some(existing) => {
                    existing.push(' ');
                    existing.push_str(comment_text);
                }
                None => {
                    last_comment = Some(comment_text.to_string());
                }
            }
            i += 1;
            continue;
        }

        // Skip block comments
        if line.starts_with("/*") {
            while i < lines.len() && !lines[i].contains("*/") {
                i += 1;
            }
            i += 1;
            continue;
        }

        // Parse syntax
        if line.starts_with("syntax") {
            if let Some(val) = extract_quoted_value(line) {
                syntax = val;
            }
            i += 1;
            continue;
        }

        // Parse package
        if line.starts_with("package") {
            package = line
                .trim_start_matches("package")
                .trim()
                .trim_end_matches(';')
                .trim()
                .to_string();
            i += 1;
            continue;
        }

        // Parse option
        if line.starts_with("option") {
            if let Some((key, val)) = parse_option(line) {
                options.insert(key, val);
            }
            i += 1;
            continue;
        }

        // Skip import statements
        if line.starts_with("import") {
            i += 1;
            continue;
        }

        // Parse service
        if line.starts_with("service") {
            let (service, consumed) = parse_service(&lines[i..], last_comment.take())?;
            services.push(service);
            i += consumed;
            continue;
        }

        // Parse message
        if line.starts_with("message") {
            let (msg, consumed) = parse_message(&lines[i..], last_comment.take())?;
            messages.insert(msg.name.clone(), msg);
            i += consumed;
            continue;
        }

        // Parse enum (skip for now, just consume the block)
        if line.starts_with("enum") {
            let consumed = skip_block(&lines[i..]);
            i += consumed;
            continue;
        }

        last_comment = None;
        i += 1;
    }

    Ok(ProtoFile {
        syntax,
        package,
        services,
        messages,
        options,
    })
}

/// Parse a service block.
fn parse_service(
    lines: &[&str],
    documentation: Option<String>,
) -> Result<(ProtoService, usize), String> {
    let first = lines[0].trim();
    let name = first
        .trim_start_matches("service")
        .trim()
        .trim_end_matches('{')
        .trim()
        .to_string();

    let mut methods: Vec<ProtoMethod> = Vec::new();
    let mut i = 1;
    let mut last_comment: Option<String> = None;

    while i < lines.len() {
        let line = lines[i].trim();

        if line == "}" {
            i += 1;
            break;
        }

        // Collect comments
        if line.starts_with("//") {
            let text = line.trim_start_matches("//").trim();
            match &mut last_comment {
                Some(existing) => {
                    existing.push(' ');
                    existing.push_str(text);
                }
                None => {
                    last_comment = Some(text.to_string());
                }
            }
            i += 1;
            continue;
        }

        // Parse RPC method
        if line.starts_with("rpc") {
            if let Some(method) = parse_rpc_method(line, last_comment.take()) {
                methods.push(method);
            }
        } else {
            last_comment = None;
        }

        i += 1;
    }

    Ok((
        ProtoService {
            name,
            methods,
            documentation,
        },
        i,
    ))
}

/// Parse an RPC method line.
///
/// Format: `rpc MethodName (InputType) returns (OutputType);`
/// With streaming: `rpc Method (stream InputType) returns (stream OutputType);`
fn parse_rpc_method(line: &str, documentation: Option<String>) -> Option<ProtoMethod> {
    let line = line.trim().trim_end_matches(';').trim_end_matches('}');
    // Remove inline options block: `{ option ... }` or `{}`
    let line = if let Some(pos) = line.find('{') {
        &line[..pos]
    } else {
        line
    };

    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() < 4 || parts[0] != "rpc" {
        return None;
    }

    let method_name = parts[1].to_string();

    // Find input type between first ( and )
    let full = parts[2..].join(" ");
    let (input_section, rest) = split_at_keyword(&full, "returns")?;

    let (client_streaming, input_type) = parse_type_section(&input_section);
    let (server_streaming, output_type) = parse_type_section(&rest);

    Some(ProtoMethod {
        name: method_name,
        input_type,
        output_type,
        client_streaming,
        server_streaming,
        documentation,
    })
}

/// Split a string at the "returns" keyword.
fn split_at_keyword(s: &str, keyword: &str) -> Option<(String, String)> {
    let lower = s.to_lowercase();
    let pos = lower.find(keyword)?;
    let before = s[..pos].trim().to_string();
    let after = s[pos + keyword.len()..].trim().to_string();
    Some((before, after))
}

/// Parse a type section like "(stream MyMessage)" into (is_streaming, type_name).
fn parse_type_section(s: &str) -> (bool, String) {
    let s = s
        .trim()
        .trim_start_matches('(')
        .trim_end_matches(')')
        .trim();

    if let Some(rest) = s.strip_prefix("stream") {
        (true, rest.trim().to_string())
    } else {
        (false, s.to_string())
    }
}

/// Parse a message block.
fn parse_message(
    lines: &[&str],
    documentation: Option<String>,
) -> Result<(ProtoMessage, usize), String> {
    let first = lines[0].trim();

    // Extract the message name (everything between "message" and "{")
    let brace_pos = first.find('{');
    let name = match brace_pos {
        Some(pos) => first["message".len()..pos].trim().to_string(),
        None => first.trim_start_matches("message").trim().to_string(),
    };

    let mut fields: Vec<ProtoField> = Vec::new();

    // Count braces on the first line to handle single-line messages like:
    // `message Empty {}` or `message Foo { string id = 1; }`
    let mut brace_depth: i32 = 0;
    for ch in first.chars() {
        match ch {
            '{' => brace_depth += 1,
            '}' => brace_depth -= 1,
            _ => {}
        }
    }

    // Single-line message: braces opened and closed on the same line
    if brace_depth == 0 && brace_pos.is_some() {
        // Extract content between { and }
        let open = brace_pos.unwrap_or(0);
        if let Some(close) = first.rfind('}') {
            let inner = first[open + 1..close].trim();
            if !inner.is_empty() {
                // May contain semicolon-separated fields on one line
                for part in inner.split(';') {
                    let part = part.trim();
                    if !part.is_empty() {
                        if let Some(field) = parse_field(part) {
                            fields.push(field);
                        }
                    }
                }
            }
        }
        return Ok((
            ProtoMessage {
                name,
                fields,
                documentation,
            },
            1, // consumed only the one line
        ));
    }

    // Multi-line message: iterate until brace_depth reaches 0
    let mut i = 1;

    while i < lines.len() {
        let line = lines[i].trim();

        // Track brace depth for nested messages/oneofs
        for ch in line.chars() {
            match ch {
                '{' => brace_depth += 1,
                '}' => brace_depth -= 1,
                _ => {}
            }
        }

        if brace_depth == 0 {
            i += 1;
            break;
        }

        // Only parse fields at depth 1 (skip nested message internals)
        if brace_depth == 1 && !line.starts_with("//") && !line.is_empty() {
            if let Some(field) = parse_field(line) {
                fields.push(field);
            }
        }

        i += 1;
    }

    Ok((
        ProtoMessage {
            name,
            fields,
            documentation,
        },
        i,
    ))
}

/// Parse a field line like: `string name = 1;` or `repeated int32 ids = 3;`
fn parse_field(line: &str) -> Option<ProtoField> {
    let line = line.trim().trim_end_matches(';').trim();

    // Skip nested messages, enums, oneofs, reserved, map, option
    if line.starts_with("message")
        || line.starts_with("enum")
        || line.starts_with("oneof")
        || line.starts_with("reserved")
        || line.starts_with("map")
        || line.starts_with("option ")
        || line.starts_with("//")
        || line.is_empty()
        || line == "}"
    {
        return None;
    }

    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() < 4 {
        return None;
    }

    let mut idx = 0;
    let mut repeated = false;
    let mut optional = false;

    // Check for repeated/optional modifier
    if parts[idx] == "repeated" {
        repeated = true;
        idx += 1;
    } else if parts[idx] == "optional" {
        optional = true;
        idx += 1;
    }

    if idx + 3 > parts.len() {
        return None;
    }

    let field_type = parts[idx].to_string();
    let name = parts[idx + 1].to_string();

    // parts[idx + 2] should be "="
    if parts[idx + 2] != "=" {
        return None;
    }

    let number: u32 = parts.get(idx + 3)?.parse().ok()?;

    Some(ProtoField {
        name,
        field_type,
        number,
        repeated,
        optional,
    })
}

/// Extract a quoted value from a line like `syntax = "proto3";`
fn extract_quoted_value(line: &str) -> Option<String> {
    let start = line.find('"')? + 1;
    let end = line[start..].find('"')? + start;
    Some(line[start..end].to_string())
}

/// Parse an option line like `option java_package = "com.example";`
fn parse_option(line: &str) -> Option<(String, String)> {
    let line = line
        .trim_start_matches("option")
        .trim()
        .trim_end_matches(';');
    let eq_pos = line.find('=')?;
    let key = line[..eq_pos].trim().to_string();
    let val = line[eq_pos + 1..].trim().trim_matches('"').to_string();
    Some((key, val))
}

/// Skip a block delimited by braces, returning the number of lines consumed.
fn skip_block(lines: &[&str]) -> usize {
    let mut depth = 0;
    let mut i = 0;
    for line in lines {
        for ch in line.chars() {
            match ch {
                '{' => depth += 1,
                '}' => depth -= 1,
                _ => {}
            }
        }
        i += 1;
        if depth == 0 && i > 0 {
            break;
        }
    }
    i
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_PROTO: &str = r#"
syntax = "proto3";

package grpc.health.v1;

option java_package = "io.grpc.health.v1";

// Health checking service.
service Health {
    // Unary health check.
    rpc Check (HealthCheckRequest) returns (HealthCheckResponse);

    // Streaming health watch.
    rpc Watch (HealthCheckRequest) returns (stream HealthCheckResponse);
}

message HealthCheckRequest {
    string service = 1;
}

message HealthCheckResponse {
    enum ServingStatus {
        UNKNOWN = 0;
        SERVING = 1;
        NOT_SERVING = 2;
    }
    ServingStatus status = 1;
}
"#;

    #[test]
    fn test_parse_basic_proto() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        assert_eq!(proto.syntax, "proto3");
        assert_eq!(proto.package, "grpc.health.v1");
        assert_eq!(proto.services.len(), 1);
    }

    #[test]
    fn test_parse_service() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        let service = &proto.services[0];
        assert_eq!(service.name, "Health");
        assert_eq!(service.methods.len(), 2);
        assert!(service.documentation.is_some());
        assert!(service
            .documentation
            .as_ref()
            .unwrap()
            .contains("Health checking"));
    }

    #[test]
    fn test_parse_unary_method() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        let check = &proto.services[0].methods[0];
        assert_eq!(check.name, "Check");
        assert_eq!(check.input_type, "HealthCheckRequest");
        assert_eq!(check.output_type, "HealthCheckResponse");
        assert!(!check.client_streaming);
        assert!(!check.server_streaming);
    }

    #[test]
    fn test_parse_server_streaming_method() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        let watch = &proto.services[0].methods[1];
        assert_eq!(watch.name, "Watch");
        assert!(!watch.client_streaming);
        assert!(watch.server_streaming);
    }

    #[test]
    fn test_parse_message() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        let req = proto
            .messages
            .get("HealthCheckRequest")
            .expect("should exist");
        assert_eq!(req.fields.len(), 1);
        assert_eq!(req.fields[0].name, "service");
        assert_eq!(req.fields[0].field_type, "string");
        assert_eq!(req.fields[0].number, 1);
    }

    #[test]
    fn test_parse_message_with_enum() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        let resp = proto
            .messages
            .get("HealthCheckResponse")
            .expect("should exist");
        // The enum is nested inside the message; our parser skips nested blocks
        // and only captures top-level fields at depth 1
        assert_eq!(resp.fields.len(), 1);
        assert_eq!(resp.fields[0].name, "status");
    }

    #[test]
    fn test_grpc_path() {
        let method = ProtoMethod {
            name: "Check".to_string(),
            input_type: "HealthCheckRequest".to_string(),
            output_type: "HealthCheckResponse".to_string(),
            client_streaming: false,
            server_streaming: false,
            documentation: None,
        };
        assert_eq!(
            method.grpc_path("grpc.health.v1", "Health"),
            "/grpc.health.v1.Health/Check"
        );
    }

    #[test]
    fn test_grpc_path_no_package() {
        let method = ProtoMethod {
            name: "Echo".to_string(),
            input_type: "EchoRequest".to_string(),
            output_type: "EchoResponse".to_string(),
            client_streaming: false,
            server_streaming: false,
            documentation: None,
        };
        assert_eq!(method.grpc_path("", "EchoService"), "/EchoService/Echo");
    }

    #[test]
    fn test_parse_options() {
        let proto = parse_proto(SAMPLE_PROTO).expect("should parse");
        assert_eq!(
            proto.options.get("java_package").map(|s| s.as_str()),
            Some("io.grpc.health.v1")
        );
    }

    #[test]
    fn test_field_json_schema_type() {
        let field = ProtoField {
            name: "count".to_string(),
            field_type: "int32".to_string(),
            number: 1,
            repeated: false,
            optional: false,
        };
        assert_eq!(field.json_schema_type(), "integer");

        let field = ProtoField {
            name: "name".to_string(),
            field_type: "string".to_string(),
            number: 2,
            repeated: false,
            optional: false,
        };
        assert_eq!(field.json_schema_type(), "string");
    }

    #[test]
    fn test_field_is_scalar() {
        let scalar = ProtoField {
            name: "x".to_string(),
            field_type: "double".to_string(),
            number: 1,
            repeated: false,
            optional: false,
        };
        assert!(scalar.is_scalar());

        let message = ProtoField {
            name: "nested".to_string(),
            field_type: "MyMessage".to_string(),
            number: 2,
            repeated: false,
            optional: false,
        };
        assert!(!message.is_scalar());
    }

    #[test]
    fn test_parse_repeated_field() {
        let proto_content = r#"
syntax = "proto3";
message ListRequest {
    repeated string ids = 1;
    int32 page_size = 2;
    optional string cursor = 3;
}
"#;
        let proto = parse_proto(proto_content).expect("should parse");
        let msg = proto.messages.get("ListRequest").expect("should exist");
        assert_eq!(msg.fields.len(), 3);
        assert!(msg.fields[0].repeated);
        assert!(!msg.fields[1].repeated);
        assert!(msg.fields[2].optional);
    }

    #[test]
    fn test_parse_bidirectional_streaming() {
        let proto_content = r#"
syntax = "proto3";
service Chat {
    rpc StreamChat (stream ChatMessage) returns (stream ChatResponse);
}
message ChatMessage {
    string text = 1;
}
message ChatResponse {
    string reply = 1;
}
"#;
        let proto = parse_proto(proto_content).expect("should parse");
        let method = &proto.services[0].methods[0];
        assert_eq!(method.name, "StreamChat");
        assert!(method.client_streaming);
        assert!(method.server_streaming);
    }

    #[test]
    fn test_parse_multiple_services() {
        let proto_content = r#"
syntax = "proto3";
package api.v1;
service UserService {
    rpc GetUser (GetUserRequest) returns (GetUserResponse);
    rpc ListUsers (ListUsersRequest) returns (ListUsersResponse);
}
service AdminService {
    rpc DeleteUser (DeleteUserRequest) returns (Empty);
}
message GetUserRequest { string id = 1; }
message GetUserResponse { string name = 1; string email = 2; }
message ListUsersRequest { int32 page = 1; }
message ListUsersResponse { repeated string users = 1; }
message DeleteUserRequest { string id = 1; }
message Empty {}
"#;
        let proto = parse_proto(proto_content).expect("should parse");
        assert_eq!(proto.services.len(), 2);
        assert_eq!(proto.services[0].name, "UserService");
        assert_eq!(proto.services[0].methods.len(), 2);
        assert_eq!(proto.services[1].name, "AdminService");
        assert_eq!(proto.services[1].methods.len(), 1);
        assert_eq!(proto.messages.len(), 6);
    }
}
