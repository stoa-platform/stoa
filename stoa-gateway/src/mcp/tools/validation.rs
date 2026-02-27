//! Tool Schema Validation (CAB-1551)
//!
//! Validates MCP tool definitions at registration time.
//! Rejects malformed tools with descriptive errors before they enter the registry.

use serde_json::Value;
use std::fmt;

const MAX_TOOL_NAME_LEN: usize = 128;
const MAX_DESCRIPTION_LEN: usize = 4096;

/// A single validation error on a specific field.
#[derive(Debug, Clone)]
pub struct ValidationError {
    pub field: String,
    pub message: String,
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.field, self.message)
    }
}

/// Collection of validation errors for a tool.
#[derive(Debug, Clone)]
pub struct ValidationErrors {
    pub tool_name: String,
    pub errors: Vec<ValidationError>,
}

impl fmt::Display for ValidationErrors {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let n = self.errors.len();
        let plural = if n == 1 { "" } else { "s" };
        write!(
            f,
            "Tool '{}' failed validation ({} error{}): ",
            self.tool_name, n, plural
        )?;
        for (i, e) in self.errors.iter().enumerate() {
            if i > 0 {
                write!(f, "; ")?;
            }
            write!(f, "{}", e)?;
        }
        Ok(())
    }
}

impl std::error::Error for ValidationErrors {}

// ---------------------------------------------------------------------------
// Validators
// ---------------------------------------------------------------------------

fn validate_name(name: &str, errors: &mut Vec<ValidationError>) {
    if name.is_empty() {
        errors.push(ValidationError {
            field: "name".into(),
            message: "must not be empty".into(),
        });
        return;
    }
    if name.len() > MAX_TOOL_NAME_LEN {
        errors.push(ValidationError {
            field: "name".into(),
            message: format!("exceeds max length of {} chars", MAX_TOOL_NAME_LEN),
        });
    }
    if !name
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-' || c == '.' || c == ':')
    {
        errors.push(ValidationError {
            field: "name".into(),
            message: "must contain only ASCII alphanumeric, underscore, hyphen, dot, or colon"
                .into(),
        });
    }
}

fn validate_description(desc: &str, errors: &mut Vec<ValidationError>) {
    if desc.is_empty() {
        errors.push(ValidationError {
            field: "description".into(),
            message: "must not be empty".into(),
        });
        return;
    }
    if desc.len() > MAX_DESCRIPTION_LEN {
        errors.push(ValidationError {
            field: "description".into(),
            message: format!("exceeds max length of {} chars", MAX_DESCRIPTION_LEN),
        });
    }
}

fn validate_input_schema(schema: &super::ToolSchema, errors: &mut Vec<ValidationError>) {
    if schema.schema_type != "object" {
        errors.push(ValidationError {
            field: "inputSchema.type".into(),
            message: format!("must be \"object\", got \"{}\"", schema.schema_type),
        });
    }
    for (prop_name, prop_val) in &schema.properties {
        if !prop_val.is_object() {
            errors.push(ValidationError {
                field: format!("inputSchema.properties.{}", prop_name),
                message: "property definition must be a JSON object".into(),
            });
        }
    }
    // Note: we intentionally do NOT validate that `required` entries exist in
    // `properties`. JSON Schema allows `required` to reference properties from
    // composed schemas (`allOf`, `$ref`, etc.), and proxy/remote tools may relay
    // schemas whose properties are defined at a higher level.
}

fn validate_output_schema(schema: &Value, errors: &mut Vec<ValidationError>) {
    if !schema.is_object() {
        errors.push(ValidationError {
            field: "outputSchema".into(),
            message: "must be a JSON object".into(),
        });
        return;
    }
    if schema.get("type").is_none() {
        errors.push(ValidationError {
            field: "outputSchema".into(),
            message: "must contain a \"type\" field".into(),
        });
    }
}

// ---------------------------------------------------------------------------
// Public entry point
// ---------------------------------------------------------------------------

/// Validate a tool definition. Returns `Ok(())` if valid, or `Err` with all errors.
pub fn validate_tool(tool: &dyn super::Tool) -> Result<(), ValidationErrors> {
    let mut errors = Vec::new();
    let name = tool.name().to_string();

    validate_name(&name, &mut errors);
    validate_description(tool.description(), &mut errors);
    validate_input_schema(&tool.input_schema(), &mut errors);

    if let Some(ref out_schema) = tool.output_schema() {
        validate_output_schema(out_schema, &mut errors);
    }

    if errors.is_empty() {
        Ok(())
    } else {
        Err(ValidationErrors {
            tool_name: name,
            errors,
        })
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::mcp::tools::{Tool, ToolSchema};
    use crate::uac::Action;
    use async_trait::async_trait;
    use serde_json::json;
    use std::collections::HashMap;

    /// Minimal mock tool for validation testing.
    struct MockTool {
        name: String,
        description: String,
        input_schema: ToolSchema,
        output_schema: Option<Value>,
    }

    impl MockTool {
        fn valid() -> Self {
            let mut props = HashMap::new();
            props.insert("query".to_string(), json!({"type": "string"}));
            Self {
                name: "test_tool".into(),
                description: "A test tool".into(),
                input_schema: ToolSchema {
                    schema_type: "object".into(),
                    properties: props,
                    required: vec!["query".into()],
                },
                output_schema: None,
            }
        }
    }

    #[async_trait]
    impl Tool for MockTool {
        fn name(&self) -> &str {
            &self.name
        }
        fn description(&self) -> &str {
            &self.description
        }
        fn input_schema(&self) -> ToolSchema {
            self.input_schema.clone()
        }
        fn output_schema(&self) -> Option<Value> {
            self.output_schema.clone()
        }
        fn required_action(&self) -> Action {
            Action::Read
        }
        fn tenant_id(&self) -> Option<&str> {
            None
        }
        async fn execute(
            &self,
            _args: Value,
            _ctx: &super::super::ToolContext,
        ) -> Result<super::super::ToolResult, super::super::ToolError> {
            Ok(super::super::ToolResult::text("ok"))
        }
    }

    #[test]
    fn valid_tool_passes() {
        let tool = MockTool::valid();
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn valid_tool_with_output_schema() {
        let mut tool = MockTool::valid();
        tool.output_schema = Some(json!({"type": "object", "properties": {}}));
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn valid_tool_empty_properties() {
        let mut tool = MockTool::valid();
        tool.input_schema.properties.clear();
        tool.input_schema.required.clear();
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn valid_name_with_dots_and_hyphens() {
        let mut tool = MockTool::valid();
        tool.name = "org.example.my-tool_v2".into();
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn empty_name_rejected() {
        let mut tool = MockTool::valid();
        tool.name = "".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.field == "name"));
    }

    #[test]
    fn name_too_long_rejected() {
        let mut tool = MockTool::valid();
        tool.name = "a".repeat(MAX_TOOL_NAME_LEN + 1);
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.message.contains("max length")));
    }

    #[test]
    fn name_with_spaces_rejected() {
        let mut tool = MockTool::valid();
        tool.name = "bad name".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err
            .errors
            .iter()
            .any(|e| e.message.contains("alphanumeric")));
    }

    #[test]
    fn name_with_unicode_rejected() {
        let mut tool = MockTool::valid();
        tool.name = "outil_météo".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err
            .errors
            .iter()
            .any(|e| e.message.contains("alphanumeric")));
    }

    #[test]
    fn empty_description_rejected() {
        let mut tool = MockTool::valid();
        tool.description = "".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.field == "description"));
    }

    #[test]
    fn description_too_long_rejected() {
        let mut tool = MockTool::valid();
        tool.description = "x".repeat(MAX_DESCRIPTION_LEN + 1);
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.field == "description"));
    }

    #[test]
    fn schema_type_not_object_rejected() {
        let mut tool = MockTool::valid();
        tool.input_schema.schema_type = "array".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.field == "inputSchema.type"));
    }

    #[test]
    fn property_not_object_rejected() {
        let mut tool = MockTool::valid();
        tool.input_schema
            .properties
            .insert("bad".into(), json!("not-an-object"));
        let err = validate_tool(&tool).unwrap_err();
        assert!(err
            .errors
            .iter()
            .any(|e| e.field.contains("properties.bad")));
    }

    #[test]
    fn required_references_missing_property_allowed() {
        // JSON Schema allows `required` to reference properties from composed schemas
        // (allOf, $ref, etc.), so we intentionally do NOT reject this case.
        let mut tool = MockTool::valid();
        tool.input_schema.required.push("nonexistent".into());
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn valid_name_with_colons() {
        // STOA uses colons as namespace separators: uac:tenant:contract:operation
        let mut tool = MockTool::valid();
        tool.name = "uac:acme:payments:list_payments".into();
        assert!(validate_tool(&tool).is_ok());
    }

    #[test]
    fn output_schema_not_object_rejected() {
        let mut tool = MockTool::valid();
        tool.output_schema = Some(json!("string"));
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.iter().any(|e| e.field == "outputSchema"));
    }

    #[test]
    fn output_schema_missing_type_rejected() {
        let mut tool = MockTool::valid();
        tool.output_schema = Some(json!({"properties": {}}));
        let err = validate_tool(&tool).unwrap_err();
        assert!(err
            .errors
            .iter()
            .any(|e| e.message.contains("\"type\" field")));
    }

    #[test]
    fn multiple_errors_collected() {
        let mut tool = MockTool::valid();
        tool.name = "".into();
        tool.description = "".into();
        tool.input_schema.schema_type = "array".into();
        let err = validate_tool(&tool).unwrap_err();
        assert!(err.errors.len() >= 3);
    }

    #[test]
    fn validation_errors_display() {
        let errs = ValidationErrors {
            tool_name: "bad_tool".into(),
            errors: vec![
                ValidationError {
                    field: "name".into(),
                    message: "too short".into(),
                },
                ValidationError {
                    field: "desc".into(),
                    message: "empty".into(),
                },
            ],
        };
        let msg = errs.to_string();
        assert!(msg.contains("bad_tool"));
        assert!(msg.contains("2 errors"));
        assert!(msg.contains("too short"));
        assert!(msg.contains("empty"));
    }

    #[test]
    fn single_error_no_plural() {
        let errs = ValidationErrors {
            tool_name: "x".into(),
            errors: vec![ValidationError {
                field: "name".into(),
                message: "bad".into(),
            }],
        };
        let msg = errs.to_string();
        assert!(msg.contains("1 error)"));
        assert!(!msg.contains("errors)"));
    }
}
