//! WSDL Parser (CAB-1762)
//!
//! Parses WSDL 1.1 documents to extract service operations.
//! Uses quick-xml for fast, zero-copy XML parsing.

use quick_xml::events::Event;
use quick_xml::Reader;
use serde::{Deserialize, Serialize};

/// A parsed SOAP service from a WSDL document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SoapService {
    /// Service name from WSDL
    pub name: String,
    /// Target namespace
    pub target_namespace: String,
    /// SOAP endpoint URL
    pub endpoint_url: Option<String>,
    /// Operations extracted from portType/binding
    pub operations: Vec<SoapOperation>,
}

/// A single SOAP operation parsed from WSDL.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SoapOperation {
    /// Operation name
    pub name: String,
    /// SOAPAction header value
    pub soap_action: String,
    /// Input message element name
    pub input_element: Option<String>,
    /// Output message element name
    pub output_element: Option<String>,
    /// Documentation from WSDL
    pub documentation: Option<String>,
}

/// Errors during WSDL parsing.
#[derive(Debug, thiserror::Error)]
pub enum WsdlError {
    #[error("XML parse error: {0}")]
    XmlParse(#[from] quick_xml::Error),
    #[error("invalid WSDL: {0}")]
    InvalidWsdl(String),
    #[error("HTTP fetch error: {0}")]
    HttpFetch(String),
}

/// Parse a WSDL 1.1 XML document and extract service operations.
///
/// Extracts:
/// - Service name and target namespace from `<definitions>`
/// - Operations from `<portType>` elements
/// - SOAPAction values from `<binding>` elements
/// - Endpoint URL from `<service><port><soap:address>` elements
pub fn parse_wsdl(xml: &str) -> Result<SoapService, WsdlError> {
    let mut reader = Reader::from_str(xml);

    let mut service_name = String::new();
    let mut target_namespace = String::new();
    let mut endpoint_url: Option<String> = None;
    let mut operations: Vec<SoapOperation> = Vec::new();
    let mut soap_actions: std::collections::HashMap<String, String> =
        std::collections::HashMap::new();

    // Parsing state
    let mut in_port_type = false;
    let mut in_binding = false;
    let mut in_operation = false;
    let mut in_documentation = false;
    let mut current_op_name = String::new();
    let mut current_input: Option<String> = None;
    let mut current_output: Option<String> = None;
    let mut current_doc: Option<String> = None;

    let mut buf = Vec::new();

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(ref e)) | Ok(Event::Empty(ref e)) => {
                let name = e.name();
                let name_bytes = name.as_ref();
                let local_name = local_name(name_bytes);

                match local_name {
                    b"definitions" => {
                        for attr in e.attributes().flatten() {
                            match attr.key.as_ref() {
                                b"name" => {
                                    service_name = String::from_utf8_lossy(&attr.value).to_string();
                                }
                                b"targetNamespace" => {
                                    target_namespace =
                                        String::from_utf8_lossy(&attr.value).to_string();
                                }
                                _ => {}
                            }
                        }
                    }
                    b"portType" => {
                        in_port_type = true;
                        // Use portType name as service name if definitions has no name
                        if service_name.is_empty() {
                            for attr in e.attributes().flatten() {
                                if attr.key.as_ref() == b"name" {
                                    service_name = String::from_utf8_lossy(&attr.value).to_string();
                                }
                            }
                        }
                    }
                    b"binding" => {
                        in_binding = true;
                    }
                    b"operation" => {
                        in_operation = true;
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"name" {
                                current_op_name = String::from_utf8_lossy(&attr.value).to_string();
                            }
                        }
                    }
                    b"input" if in_operation && in_port_type => {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"message" || attr.key.as_ref() == b"name" {
                                current_input =
                                    Some(String::from_utf8_lossy(&attr.value).to_string());
                            }
                        }
                    }
                    b"output" if in_operation && in_port_type => {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"message" || attr.key.as_ref() == b"name" {
                                current_output =
                                    Some(String::from_utf8_lossy(&attr.value).to_string());
                            }
                        }
                    }
                    b"documentation" if in_operation => {
                        in_documentation = true;
                    }
                    // Extract SOAPAction from binding/operation/soap:operation
                    _ if (local_name == b"operation" || local_name == b"soapOperation")
                        && in_binding
                        && in_operation =>
                    {
                        // This is the soap:operation element inside binding
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"soapAction" {
                                let action = String::from_utf8_lossy(&attr.value).to_string();
                                soap_actions.insert(current_op_name.clone(), action);
                            }
                        }
                    }
                    // Extract endpoint from service/port/soap:address
                    b"address" => {
                        for attr in e.attributes().flatten() {
                            if attr.key.as_ref() == b"location" {
                                endpoint_url =
                                    Some(String::from_utf8_lossy(&attr.value).to_string());
                            }
                        }
                    }
                    _ => {}
                }
            }
            Ok(Event::Text(ref e)) if in_documentation => {
                let text = e.unescape().unwrap_or_default().to_string();
                if !text.trim().is_empty() {
                    current_doc = Some(text.trim().to_string());
                }
            }
            Ok(Event::End(ref e)) => {
                let end_name = e.name();
                let end_bytes = end_name.as_ref();
                let local = local_name(end_bytes);
                match local {
                    b"portType" => {
                        in_port_type = false;
                    }
                    b"binding" => {
                        in_binding = false;
                    }
                    b"operation" if in_port_type => {
                        // End of operation in portType — save it
                        if !current_op_name.is_empty() {
                            operations.push(SoapOperation {
                                name: current_op_name.clone(),
                                soap_action: String::new(), // filled later from binding
                                input_element: current_input.take(),
                                output_element: current_output.take(),
                                documentation: current_doc.take(),
                            });
                        }
                        current_op_name.clear();
                        in_operation = false;
                    }
                    b"operation" if in_binding => {
                        current_op_name.clear();
                        in_operation = false;
                    }
                    b"documentation" => {
                        in_documentation = false;
                    }
                    _ => {}
                }
            }
            Ok(Event::Eof) => break,
            Err(e) => return Err(WsdlError::XmlParse(e)),
            _ => {}
        }
        buf.clear();
    }

    // Merge SOAPAction values from binding into operations
    for op in &mut operations {
        if let Some(action) = soap_actions.get(&op.name) {
            op.soap_action.clone_from(action);
        }
        // Default SOAPAction to targetNamespace/operationName
        if op.soap_action.is_empty() && !target_namespace.is_empty() {
            let ns = target_namespace.trim_end_matches('/');
            op.soap_action = format!("{}/{}", ns, op.name);
        }
    }

    if operations.is_empty() {
        return Err(WsdlError::InvalidWsdl(
            "no operations found in WSDL".to_string(),
        ));
    }

    Ok(SoapService {
        name: if service_name.is_empty() {
            "UnknownService".to_string()
        } else {
            service_name
        },
        target_namespace,
        endpoint_url,
        operations,
    })
}

/// Extract local name from a possibly-namespaced XML tag.
/// e.g. `{http://schemas.xmlsoap.org/wsdl/}definitions` → `definitions`
fn local_name(name: &[u8]) -> &[u8] {
    // quick-xml doesn't include the namespace prefix in the name by default,
    // but WSDL may use prefixed names like `wsdl:definitions` or `soap:operation`.
    // Strip everything before the last `:`.
    if let Some(pos) = name.iter().rposition(|&b| b == b':') {
        &name[pos + 1..]
    } else {
        name
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_WSDL: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<definitions name="CalculatorService"
             targetNamespace="http://example.com/calculator"
             xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             xmlns:tns="http://example.com/calculator">

  <portType name="CalculatorPortType">
    <operation name="Add">
      <documentation>Adds two numbers</documentation>
      <input message="tns:AddRequest"/>
      <output message="tns:AddResponse"/>
    </operation>
    <operation name="Subtract">
      <input message="tns:SubtractRequest"/>
      <output message="tns:SubtractResponse"/>
    </operation>
  </portType>

  <binding name="CalculatorBinding" type="tns:CalculatorPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <operation name="Add">
      <soap:operation soapAction="http://example.com/calculator/Add"/>
    </operation>
    <operation name="Subtract">
      <soap:operation soapAction="http://example.com/calculator/Subtract"/>
    </operation>
  </binding>

  <service name="CalculatorService">
    <port name="CalculatorPort" binding="tns:CalculatorBinding">
      <soap:address location="http://localhost:8080/calculator"/>
    </port>
  </service>
</definitions>"#;

    #[test]
    fn test_parse_wsdl_basic() {
        let service = parse_wsdl(SAMPLE_WSDL).expect("should parse");
        assert_eq!(service.name, "CalculatorService");
        assert_eq!(service.target_namespace, "http://example.com/calculator");
        assert_eq!(
            service.endpoint_url.as_deref(),
            Some("http://localhost:8080/calculator")
        );
        assert_eq!(service.operations.len(), 2);
    }

    #[test]
    fn test_parse_wsdl_operations() {
        let service = parse_wsdl(SAMPLE_WSDL).expect("should parse");
        let add = &service.operations[0];
        assert_eq!(add.name, "Add");
        assert_eq!(add.soap_action, "http://example.com/calculator/Add");
        assert_eq!(add.input_element.as_deref(), Some("tns:AddRequest"));
        assert_eq!(add.output_element.as_deref(), Some("tns:AddResponse"));
        assert_eq!(add.documentation.as_deref(), Some("Adds two numbers"));
    }

    #[test]
    fn test_parse_wsdl_soap_action_default() {
        // WSDL without explicit soapAction — should default to namespace/opName
        let wsdl = r#"<?xml version="1.0"?>
<definitions targetNamespace="http://example.com/svc"
             xmlns="http://schemas.xmlsoap.org/wsdl/">
  <portType name="SvcPortType">
    <operation name="GetStatus">
      <input message="GetStatusRequest"/>
      <output message="GetStatusResponse"/>
    </operation>
  </portType>
</definitions>"#;
        let service = parse_wsdl(wsdl).expect("should parse");
        assert_eq!(
            service.operations[0].soap_action,
            "http://example.com/svc/GetStatus"
        );
    }

    #[test]
    fn test_parse_wsdl_no_operations() {
        let wsdl = r#"<?xml version="1.0"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/">
</definitions>"#;
        let result = parse_wsdl(wsdl);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("no operations found"));
    }

    #[test]
    fn test_local_name() {
        assert_eq!(local_name(b"definitions"), b"definitions");
        assert_eq!(local_name(b"soap:operation"), b"operation");
        assert_eq!(local_name(b"wsdl:portType"), b"portType");
    }
}
