//! SOAP↔JSON Bridge (CAB-1762)
//!
//! Transforms between JSON and SOAP XML envelopes:
//! - `json_to_soap_envelope`: wraps JSON parameters in a SOAP envelope
//! - `soap_response_to_json`: extracts SOAP Body content to JSON
//! - `SoapBridgeTool`: MCP tool that calls a SOAP backend via the bridge

use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;

use crate::mcp::tools::{
    Tool, ToolAnnotations, ToolContent, ToolContext, ToolDefinition, ToolError, ToolResult,
    ToolSchema,
};
use crate::metrics;
use crate::uac::Action;

use super::wsdl::SoapOperation;

/// Build a SOAP 1.1 envelope from JSON parameters.
///
/// Wraps the JSON key-value pairs as XML elements inside `<soap:Body>`.
/// Example: `{"a": 1, "b": 2}` with operation "Add" in namespace "http://example.com" →
/// ```xml
/// <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
///                xmlns:ns="http://example.com">
///   <soap:Body>
///     <ns:Add>
///       <a>1</a>
///       <b>2</b>
///     </ns:Add>
///   </soap:Body>
/// </soap:Envelope>
/// ```
pub fn json_to_soap_envelope(operation_name: &str, namespace: &str, params: &Value) -> String {
    let mut body_elements = String::new();
    if let Value::Object(map) = params {
        for (key, val) in map {
            let text = match val {
                Value::String(s) => s.clone(),
                Value::Null => String::new(),
                other => other.to_string(),
            };
            // Escape XML special characters
            let escaped = escape_xml(&text);
            body_elements.push_str(&format!("      <{key}>{escaped}</{key}>\n"));
        }
    }

    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:ns="{namespace}">
  <soap:Body>
    <ns:{operation_name}>
{body_elements}    </ns:{operation_name}>
  </soap:Body>
</soap:Envelope>"#
    )
}

/// Extract the SOAP Body content from a SOAP response and convert to JSON.
///
/// Parses the XML response, finds `<soap:Body>`, and converts child elements
/// to a flat JSON object. Detects SOAP faults and returns them as errors.
pub fn soap_response_to_json(xml: &str) -> Result<Value, String> {
    use quick_xml::escape::unescape;
    use quick_xml::events::Event;
    use quick_xml::Reader;

    let mut reader = Reader::from_str(xml);
    let mut buf = Vec::new();

    let mut in_body = false;
    let mut in_fault = false;
    let mut depth: usize = 0;
    let mut result: HashMap<String, Value> = HashMap::new();
    let mut current_element: Option<String> = None;
    let mut fault_string: Option<String> = None;
    let mut fault_code: Option<String> = None;
    let mut in_fault_string = false;
    let mut in_fault_code = false;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) => {
                let local = local_name_str(e.name().as_ref());

                if local.eq_ignore_ascii_case("body") {
                    in_body = true;
                    depth = 0;
                    continue;
                }

                if in_body {
                    depth += 1;
                    if local.eq_ignore_ascii_case("fault") {
                        in_fault = true;
                    }
                    if in_fault && local.eq_ignore_ascii_case("faultstring") {
                        in_fault_string = true;
                    }
                    if in_fault && local.eq_ignore_ascii_case("faultcode") {
                        in_fault_code = true;
                    }
                    // Capture leaf element names at depth 2 (inside operation response wrapper)
                    if depth >= 2 && !in_fault {
                        current_element = Some(local.to_string());
                    }
                }
            }
            Ok(Event::Text(ref e)) if in_body => {
                let decoded = e.decode().unwrap_or_default();
                let text = unescape(&decoded).unwrap_or_default().to_string();
                let text = text.trim().to_string();
                if text.is_empty() {
                    continue;
                }

                if in_fault_string {
                    fault_string = Some(text);
                } else if in_fault_code {
                    fault_code = Some(text);
                } else if let Some(ref elem) = current_element {
                    // Try to parse as number or boolean
                    let val = if let Ok(n) = text.parse::<i64>() {
                        Value::Number(n.into())
                    } else if let Ok(f) = text.parse::<f64>() {
                        serde_json::Number::from_f64(f)
                            .map(Value::Number)
                            .unwrap_or(Value::String(text.clone()))
                    } else if text == "true" || text == "false" {
                        Value::Bool(text == "true")
                    } else {
                        Value::String(text)
                    };
                    result.insert(elem.clone(), val);
                }
            }
            Ok(Event::End(ref e)) if in_body => {
                let local = local_name_str(e.name().as_ref());

                if local.eq_ignore_ascii_case("body") {
                    in_body = false;
                    continue;
                }

                if in_fault && local.eq_ignore_ascii_case("faultstring") {
                    in_fault_string = false;
                }
                if in_fault && local.eq_ignore_ascii_case("faultcode") {
                    in_fault_code = false;
                }
                if local.eq_ignore_ascii_case("fault") {
                    in_fault = false;
                }

                current_element = None;
                depth = depth.saturating_sub(1);
            }
            Ok(Event::Eof) => break,
            Err(e) => return Err(format!("XML parse error: {e}")),
            _ => {}
        }
        buf.clear();
    }

    // Check for SOAP fault
    if let Some(fault_str) = fault_string {
        let code = fault_code.unwrap_or_else(|| "Server".to_string());
        return Err(format!("SOAP Fault [{code}]: {fault_str}"));
    }

    Ok(Value::Object(result.into_iter().collect()))
}

/// MCP tool that bridges a SOAP operation.
///
/// When called via MCP, converts JSON arguments to a SOAP envelope,
/// sends the request to the backend, and converts the response back to JSON.
pub struct SoapBridgeTool {
    /// Tool name (derived from service + operation)
    tool_name: String,
    /// Human-readable description
    tool_description: String,
    /// SOAP operation metadata
    operation: SoapOperation,
    /// Target namespace for the SOAP envelope
    namespace: String,
    /// Backend SOAP endpoint URL
    endpoint_url: String,
    /// HTTP client for making requests
    http_client: reqwest::Client,
    /// Tenant that owns this tool (None = global)
    tenant_id: Option<String>,
}

impl SoapBridgeTool {
    /// Create a new SOAP bridge tool for a specific operation.
    pub fn new(
        service_name: &str,
        operation: SoapOperation,
        namespace: &str,
        endpoint_url: &str,
        http_client: reqwest::Client,
        tenant_id: Option<String>,
    ) -> Self {
        let tool_name = format!("soap_{}_{}", service_name.to_lowercase(), operation.name);
        let doc = operation
            .documentation
            .as_deref()
            .unwrap_or("SOAP operation");
        let tool_description =
            format!("SOAP bridge: {}.{} — {}", service_name, operation.name, doc);

        Self {
            tool_name,
            tool_description,
            operation,
            namespace: namespace.to_string(),
            endpoint_url: endpoint_url.to_string(),
            http_client,
            tenant_id,
        }
    }
}

#[async_trait]
impl Tool for SoapBridgeTool {
    fn name(&self) -> &str {
        &self.tool_name
    }

    fn description(&self) -> &str {
        &self.tool_description
    }

    fn input_schema(&self) -> ToolSchema {
        // Generic schema — accepts any JSON object as SOAP parameters
        ToolSchema {
            schema_type: "object".to_string(),
            properties: HashMap::from([(
                "parameters".to_string(),
                serde_json::json!({
                    "type": "object",
                    "description": "SOAP operation parameters as key-value pairs"
                }),
            )]),
            required: vec!["parameters".to_string()],
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
        let params = args
            .get("parameters")
            .cloned()
            .unwrap_or(Value::Object(serde_json::Map::new()));

        // Build SOAP envelope
        let envelope = json_to_soap_envelope(&self.operation.name, &self.namespace, &params);

        metrics::track_soap_bridge_request(&self.operation.name);

        // Send SOAP request
        let response = self
            .http_client
            .post(&self.endpoint_url)
            .header("Content-Type", "text/xml; charset=utf-8")
            .header("SOAPAction", &self.operation.soap_action)
            .body(envelope)
            .send()
            .await
            .map_err(|e| ToolError::ExecutionFailed(format!("SOAP request failed: {e}")))?;

        let status = response.status();
        let body = response.text().await.map_err(|e| {
            ToolError::ExecutionFailed(format!("Failed to read SOAP response: {e}"))
        })?;

        if !status.is_success() && !body.contains("soap:Envelope") && !body.contains("Envelope") {
            return Err(ToolError::ExecutionFailed(format!(
                "SOAP endpoint returned HTTP {status}"
            )));
        }

        // Parse SOAP response to JSON
        match soap_response_to_json(&body) {
            Ok(json) => {
                metrics::track_soap_bridge_response(&self.operation.name, true);
                Ok(ToolResult {
                    content: vec![ToolContent::Text {
                        text: serde_json::to_string_pretty(&json)
                            .unwrap_or_else(|_| json.to_string()),
                    }],
                    is_error: None,
                })
            }
            Err(fault) => {
                metrics::track_soap_bridge_response(&self.operation.name, false);
                Ok(ToolResult {
                    content: vec![ToolContent::Text { text: fault }],
                    is_error: Some(true),
                })
            }
        }
    }

    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.tool_name.clone(),
            description: self.tool_description.clone(),
            input_schema: self.input_schema(),
            output_schema: self.output_schema(),
            annotations: Some(
                ToolAnnotations::from_action(Action::Read)
                    .with_title(format!("SOAP: {}", self.operation.name)),
            ),
            tenant_id: self.tenant_id.clone(),
        }
    }
}

/// Escape XML special characters.
fn escape_xml(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// Extract local name from namespaced XML tag as string.
fn local_name_str(name: &[u8]) -> String {
    let name_str = String::from_utf8_lossy(name);
    if let Some(pos) = name_str.rfind(':') {
        name_str[pos + 1..].to_string()
    } else {
        name_str.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_json_to_soap_envelope() {
        let params = serde_json::json!({"a": 1, "b": 2});
        let envelope = json_to_soap_envelope("Add", "http://example.com", &params);
        assert!(envelope.contains("soap:Envelope"));
        assert!(envelope.contains("ns:Add"));
        assert!(envelope.contains("<a>1</a>") || envelope.contains("<b>2</b>"));
        assert!(envelope.contains(r#"xmlns:ns="http://example.com""#));
    }

    #[test]
    fn test_json_to_soap_envelope_string_params() {
        let params = serde_json::json!({"name": "John", "city": "Paris"});
        let envelope = json_to_soap_envelope("GetUser", "http://example.com/users", &params);
        assert!(envelope.contains("<name>John</name>"));
        assert!(envelope.contains("<city>Paris</city>"));
    }

    #[test]
    fn test_json_to_soap_envelope_xml_escaping() {
        let params = serde_json::json!({"query": "<script>alert('xss')</script>"});
        let envelope = json_to_soap_envelope("Search", "http://example.com", &params);
        assert!(envelope.contains("&lt;script&gt;"));
        assert!(!envelope.contains("<script>"));
    }

    #[test]
    fn test_soap_response_to_json_success() {
        let xml = r#"<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <AddResponse>
      <Result>42</Result>
      <Status>OK</Status>
    </AddResponse>
  </soap:Body>
</soap:Envelope>"#;
        let result = soap_response_to_json(xml).expect("should parse");
        assert_eq!(result["Result"], 42);
        assert_eq!(result["Status"], "OK");
    }

    #[test]
    fn test_soap_response_to_json_fault() {
        let xml = r#"<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Invalid operation</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>"#;
        let result = soap_response_to_json(xml);
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(err.contains("SOAP Fault"));
        assert!(err.contains("Invalid operation"));
    }

    #[test]
    fn test_soap_response_to_json_boolean() {
        let xml = r#"<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <CheckResponse>
      <available>true</available>
      <count>5</count>
    </CheckResponse>
  </soap:Body>
</soap:Envelope>"#;
        let result = soap_response_to_json(xml).expect("should parse");
        assert_eq!(result["available"], true);
        assert_eq!(result["count"], 5);
    }

    #[test]
    fn test_escape_xml() {
        assert_eq!(escape_xml("<b>test</b>"), "&lt;b&gt;test&lt;/b&gt;");
        assert_eq!(escape_xml("a & b"), "a &amp; b");
        assert_eq!(escape_xml(r#""quoted""#), "&quot;quoted&quot;");
    }
}
