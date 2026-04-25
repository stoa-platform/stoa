//! UAC Contract Schema Types
//!
//! Core types for the Universal API Contract v1 specification.
//! "Define Once, Expose Everywhere" — a single contract generates
//! REST routes, MCP tools, and protocol bindings automatically.
//!
//! These types mirror `uac-contract-v1.schema.json` (cross-language parity).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

use super::classifications::Classification;
use super::llm::LlmConfig;

fn default_tenant_id() -> String {
    "default".to_string()
}

// =============================================================================
// Endpoint LLM Metadata
// =============================================================================

/// Effect level for LLM-facing endpoint metadata.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EndpointSideEffects {
    None,
    Read,
    Write,
    Destructive,
}

/// Example input for an LLM-facing endpoint tool.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EndpointLlmExample {
    /// Example input object for the projected MCP tool
    pub input: Value,
    /// Optional explanation for the example
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// LLM-facing metadata for a UAC endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EndpointLlm {
    /// Short human-readable tool summary
    pub summary: String,
    /// Agent-facing intent describing when to use this endpoint
    pub intent: String,
    /// Stable MCP tool name to expose for this endpoint
    pub tool_name: String,
    /// Effect level of invoking this endpoint
    pub side_effects: EndpointSideEffects,
    /// Whether autonomous agents may use this endpoint
    pub safe_for_agents: bool,
    /// Whether a human approval step is required before invocation
    pub requires_human_approval: bool,
    /// Example inputs for MCP clients and smoke validation
    pub examples: Vec<EndpointLlmExample>,
}

// =============================================================================
// Contract Status
// =============================================================================

/// Lifecycle status of a UAC contract.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum ContractStatus {
    /// Contract is being defined, not yet active
    #[default]
    Draft,
    /// Contract is live and generating bindings
    Published,
    /// Contract is marked for removal
    Deprecated,
}

impl std::fmt::Display for ContractStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ContractStatus::Draft => write!(f, "draft"),
            ContractStatus::Published => write!(f, "published"),
            ContractStatus::Deprecated => write!(f, "deprecated"),
        }
    }
}

// =============================================================================
// UAC Endpoint
// =============================================================================

/// A single API endpoint within a UAC contract.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacEndpoint {
    /// URL path pattern (e.g. "/payments/{id}")
    pub path: String,
    /// Allowed HTTP methods (e.g. ["GET", "POST"])
    #[serde(default)]
    pub methods: Vec<String>,
    /// Backend URL to proxy requests to
    #[serde(default)]
    pub backend_url: String,
    /// Single method shorthand — merged into `methods` during deserialization
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
    /// Human-readable description of this endpoint
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// OpenAPI operationId — used for MCP tool naming
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operation_id: Option<String>,
    /// JSON Schema for request body validation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input_schema: Option<Value>,
    /// JSON Schema for response body
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<Value>,
    /// Optional LLM-facing metadata for MCP tool projection
    #[serde(skip_serializing_if = "Option::is_none")]
    pub llm: Option<EndpointLlm>,
}

// =============================================================================
// UAC Contract Spec
// =============================================================================

/// The Universal API Contract specification.
///
/// A UAC contract defines an API surface that can be automatically
/// exposed via multiple protocols (REST, MCP, GraphQL, gRPC, Kafka).
/// Classification determines security requirements (DORA ICT risk aligned).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacContractSpec {
    /// Unique contract name within tenant (kebab-case)
    pub name: String,
    /// Optional explicit key override (default: `tenant_id:name`)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub key: Option<String>,
    /// Semantic version (e.g. "1.0.0")
    pub version: String,
    /// Owning tenant identifier
    #[serde(default = "default_tenant_id")]
    pub tenant_id: String,
    /// Human-readable display name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
    /// Contract description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// ICT risk classification (H/VH/VVH, DORA-aligned)
    #[serde(default)]
    pub classification: Classification,
    /// API endpoints exposed by this contract
    #[serde(default)]
    pub endpoints: Vec<UacEndpoint>,
    /// Required policies derived from classification (auto-populated)
    #[serde(default)]
    pub required_policies: Vec<String>,
    /// Lifecycle status
    #[serde(default)]
    pub status: ContractStatus,
    /// URL of the source OpenAPI spec
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_spec_url: Option<String>,
    /// SHA-256 hash of the source spec for drift detection
    #[serde(skip_serializing_if = "Option::is_none")]
    pub spec_hash: Option<String>,
    /// Optional LLM backend configuration (CAB-709).
    /// When present, `expand_endpoints()` generates synthetic REST/MCP endpoints.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub llm_config: Option<LlmConfig>,
}

impl UacContractSpec {
    /// Create a minimal contract spec for testing or quick creation.
    pub fn new(name: impl Into<String>, tenant_id: impl Into<String>) -> Self {
        let classification = Classification::default(); // H
        let required_policies = classification
            .required_policies()
            .into_iter()
            .map(|s| s.to_string())
            .collect();

        Self {
            name: name.into(),
            key: None,
            version: "1.0.0".to_string(),
            tenant_id: tenant_id.into(),
            display_name: None,
            description: None,
            classification,
            endpoints: vec![],
            required_policies,
            status: ContractStatus::Draft,
            source_spec_url: None,
            spec_hash: None,
            llm_config: None,
        }
    }

    /// Recompute required_policies from the current classification.
    pub fn refresh_policies(&mut self) {
        self.required_policies = self
            .classification
            .required_policies()
            .into_iter()
            .map(|s| s.to_string())
            .collect();
    }

    /// Validate the contract spec.
    ///
    /// Returns a list of validation errors (empty = valid).
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();

        if self.name.is_empty() {
            errors.push("name must not be empty".to_string());
        }
        if self.version.is_empty() {
            errors.push("version must not be empty".to_string());
        }
        if self.tenant_id.is_empty() {
            errors.push("tenant_id must not be empty".to_string());
        }
        if self.endpoints.is_empty()
            && self.llm_config.is_none()
            && self.status == ContractStatus::Published
        {
            errors.push("published contract must have at least one endpoint".to_string());
        }

        // Validate LLM config if present
        if let Some(ref llm) = self.llm_config {
            errors.extend(llm.validate());
        }

        // Validate each endpoint
        let mut llm_tool_names: HashMap<&str, usize> = HashMap::new();
        for (i, ep) in self.endpoints.iter().enumerate() {
            if ep.path.is_empty() {
                errors.push(format!("endpoints[{}].path must not be empty", i));
            }
            if ep.methods.is_empty() {
                errors.push(format!("endpoints[{}].methods must not be empty", i));
            }
            // backend_url only required for Published contracts — Draft/Deprecated can omit it
            if ep.backend_url.is_empty() && self.status == ContractStatus::Published {
                errors.push(format!("endpoints[{}].backend_url must not be empty", i));
            }
            if let Some(llm) = &ep.llm {
                if llm.summary.is_empty() {
                    errors.push(format!("endpoints[{}].llm.summary must not be empty", i));
                }
                if llm.intent.is_empty() {
                    errors.push(format!("endpoints[{}].llm.intent must not be empty", i));
                }
                if llm.tool_name.is_empty() {
                    errors.push(format!("endpoints[{}].llm.tool_name must not be empty", i));
                } else if let Some(previous_index) =
                    llm_tool_names.insert(llm.tool_name.as_str(), i)
                {
                    errors.push(format!(
                        "endpoints[{}].llm.tool_name duplicate tool_name '{}' already used by endpoints[{}]",
                        i, llm.tool_name, previous_index
                    ));
                }
                if llm.side_effects == EndpointSideEffects::Destructive
                    && !llm.requires_human_approval
                {
                    errors.push(format!(
                        "endpoints[{}].llm destructive side_effects requires requires_human_approval=true",
                        i
                    ));
                }
            }
        }

        errors
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_endpoint() -> UacEndpoint {
        UacEndpoint {
            path: "/payments/{id}".to_string(),
            methods: vec!["GET".to_string(), "POST".to_string()],
            backend_url: "https://backend.acme.com/v1/payments".to_string(),
            method: None,
            description: None,
            operation_id: Some("get_payment".to_string()),
            input_schema: None,
            output_schema: None,
            llm: None,
        }
    }

    fn sample_contract() -> UacContractSpec {
        let mut spec = UacContractSpec::new("payment-service", "acme");
        spec.display_name = Some("Payment Service".to_string());
        spec.description = Some("Process payments".to_string());
        spec.endpoints = vec![sample_endpoint()];
        spec
    }

    #[test]
    fn test_serde_roundtrip() {
        let spec = sample_contract();
        let json = serde_json::to_string(&spec).expect("serialize");
        let deserialized: UacContractSpec = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(deserialized.name, "payment-service");
        assert_eq!(deserialized.tenant_id, "acme");
        assert_eq!(deserialized.classification, Classification::H);
        assert_eq!(deserialized.status, ContractStatus::Draft);
        assert_eq!(deserialized.endpoints.len(), 1);
        assert_eq!(deserialized.endpoints[0].path, "/payments/{id}");
    }

    #[test]
    fn test_default_classification_is_h() {
        let spec = UacContractSpec::new("test-api", "tenant-1");
        assert_eq!(spec.classification, Classification::H);
    }

    #[test]
    fn test_required_policies_auto_populated() {
        let spec = UacContractSpec::new("test-api", "tenant-1");
        assert!(spec.required_policies.contains(&"rate-limit".to_string()));
        assert!(spec.required_policies.contains(&"auth-jwt".to_string()));
    }

    #[test]
    fn test_refresh_policies_vvh() {
        let mut spec = UacContractSpec::new("critical-api", "tenant-1");
        spec.classification = Classification::Vvh;
        spec.refresh_policies();

        assert!(spec.required_policies.contains(&"rate-limit".to_string()));
        assert!(spec.required_policies.contains(&"auth-jwt".to_string()));
        assert!(spec.required_policies.contains(&"mtls".to_string()));
        assert!(spec
            .required_policies
            .contains(&"audit-logging".to_string()));
        assert!(spec
            .required_policies
            .contains(&"data-encryption".to_string()));
        assert!(spec
            .required_policies
            .contains(&"geo-restriction".to_string()));
    }

    #[test]
    fn test_validate_empty_name() {
        let mut spec = sample_contract();
        spec.name = String::new();
        let errors = spec.validate();
        assert!(errors.iter().any(|e| e.contains("name")));
    }

    #[test]
    fn test_validate_published_without_endpoints() {
        let mut spec = UacContractSpec::new("test", "t1");
        spec.status = ContractStatus::Published;
        let errors = spec.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("published contract must have at least one endpoint")));
    }

    #[test]
    fn test_validate_endpoint_empty_path() {
        let mut spec = sample_contract();
        spec.endpoints[0].path = String::new();
        let errors = spec.validate();
        assert!(errors.iter().any(|e| e.contains("path must not be empty")));
    }

    #[test]
    fn test_validate_valid_contract() {
        let spec = sample_contract();
        let errors = spec.validate();
        assert!(errors.is_empty(), "Expected no errors, got: {:?}", errors);
    }

    #[test]
    fn test_contract_status_serde() {
        let json = serde_json::to_string(&ContractStatus::Published).expect("serialize");
        assert_eq!(json, "\"published\"");

        let status: ContractStatus = serde_json::from_str("\"deprecated\"").expect("deserialize");
        assert_eq!(status, ContractStatus::Deprecated);
    }

    #[test]
    fn test_contract_status_display() {
        assert_eq!(format!("{}", ContractStatus::Draft), "draft");
        assert_eq!(format!("{}", ContractStatus::Published), "published");
        assert_eq!(format!("{}", ContractStatus::Deprecated), "deprecated");
    }

    #[test]
    fn test_endpoint_with_schemas() {
        let endpoint = UacEndpoint {
            path: "/users".to_string(),
            methods: vec!["POST".to_string()],
            backend_url: "https://api.example.com/users".to_string(),
            method: None,
            description: None,
            operation_id: Some("create_user".to_string()),
            input_schema: Some(serde_json::json!({
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"}
                },
                "required": ["name", "email"]
            })),
            output_schema: Some(serde_json::json!({
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"}
                }
            })),
            llm: None,
        };

        let json = serde_json::to_value(&endpoint).expect("serialize");
        assert!(json.get("input_schema").is_some());
        assert!(json.get("output_schema").is_some());
    }

    #[test]
    fn test_endpoint_optional_fields_omitted() {
        let endpoint = UacEndpoint {
            path: "/health".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: "https://api.example.com/health".to_string(),
            method: None,
            description: None,
            operation_id: None,
            input_schema: None,
            output_schema: None,
            llm: None,
        };

        let json = serde_json::to_value(&endpoint).expect("serialize");
        assert!(json.get("operation_id").is_none());
        assert!(json.get("input_schema").is_none());
        assert!(json.get("output_schema").is_none());
        assert!(json.get("llm").is_none());
    }

    #[test]
    fn test_endpoint_with_llm_metadata() {
        let endpoint = UacEndpoint {
            path: "/health".to_string(),
            methods: vec!["GET".to_string()],
            backend_url: "https://api.example.com/health".to_string(),
            method: None,
            description: None,
            operation_id: Some("health".to_string()),
            input_schema: None,
            output_schema: None,
            llm: Some(EndpointLlm {
                summary: "Read health".to_string(),
                intent: "Let agents inspect service health.".to_string(),
                tool_name: "health_read".to_string(),
                side_effects: EndpointSideEffects::Read,
                safe_for_agents: true,
                requires_human_approval: false,
                examples: vec![EndpointLlmExample {
                    input: serde_json::json!({"verbose": false}),
                    description: None,
                }],
            }),
        };

        let json = serde_json::to_value(&endpoint).expect("serialize");
        assert_eq!(json["llm"]["tool_name"], "health_read");

        let roundtrip: UacEndpoint = serde_json::from_value(json).expect("deserialize");
        let llm = roundtrip.llm.expect("llm metadata");
        assert_eq!(llm.side_effects, EndpointSideEffects::Read);
        assert_eq!(llm.examples.len(), 1);
    }

    #[test]
    fn test_validate_duplicate_llm_tool_name() {
        let mut spec = sample_contract();
        spec.endpoints.push(sample_endpoint());
        spec.endpoints[0].llm = Some(EndpointLlm {
            summary: "Read one".to_string(),
            intent: "Read one payment.".to_string(),
            tool_name: "payments_read".to_string(),
            side_effects: EndpointSideEffects::Read,
            safe_for_agents: true,
            requires_human_approval: false,
            examples: vec![],
        });
        spec.endpoints[1].llm = Some(EndpointLlm {
            summary: "Read two".to_string(),
            intent: "Read another payment.".to_string(),
            tool_name: "payments_read".to_string(),
            side_effects: EndpointSideEffects::Read,
            safe_for_agents: true,
            requires_human_approval: false,
            examples: vec![],
        });

        let errors = spec.validate();
        assert!(errors.iter().any(|e| e.contains("duplicate tool_name")));
    }

    #[test]
    fn test_validate_destructive_llm_requires_approval() {
        let mut spec = sample_contract();
        spec.endpoints[0].llm = Some(EndpointLlm {
            summary: "Delete payment".to_string(),
            intent: "Delete a payment permanently.".to_string(),
            tool_name: "payment_delete".to_string(),
            side_effects: EndpointSideEffects::Destructive,
            safe_for_agents: false,
            requires_human_approval: false,
            examples: vec![],
        });

        let errors = spec.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("destructive") && e.contains("requires_human_approval")));
    }

    // === LLM Config integration tests (CAB-709) ===

    #[test]
    fn test_published_contract_with_llm_config_valid() {
        use crate::uac::llm::{LlmCapability, LlmCapabilityType, LlmConfig, LlmProvider};

        let mut spec = UacContractSpec::new("ai-service", "acme");
        spec.status = ContractStatus::Published;
        // No explicit endpoints, but has llm_config
        spec.llm_config = Some(LlmConfig {
            capabilities: vec![LlmCapability {
                capability: LlmCapabilityType::Summarize,
                providers: vec![LlmProvider {
                    name: "anthropic".to_string(),
                    model: "claude-sonnet-4-5-20250929".to_string(),
                    backend_url: "https://api.anthropic.com/v1".to_string(),
                    priority: 1,
                }],
            }],
            default_timeout_ms: Some(30000),
        });

        let errors = spec.validate();
        assert!(errors.is_empty(), "Expected no errors, got: {:?}", errors);
    }

    #[test]
    fn test_llm_validation_errors_propagate() {
        use crate::uac::llm::{LlmCapability, LlmCapabilityType, LlmConfig, LlmProvider};

        let mut spec = UacContractSpec::new("ai-service", "acme");
        spec.llm_config = Some(LlmConfig {
            capabilities: vec![LlmCapability {
                capability: LlmCapabilityType::Chat,
                providers: vec![LlmProvider {
                    name: "test".to_string(),
                    model: String::new(),       // invalid
                    backend_url: String::new(), // invalid
                    priority: 0,
                }],
            }],
            default_timeout_ms: None,
        });

        let errors = spec.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("backend_url must not be empty")));
        assert!(errors.iter().any(|e| e.contains("model must not be empty")));
    }

    #[test]
    fn test_serde_roundtrip_with_llm_config() {
        use crate::uac::llm::{LlmCapability, LlmCapabilityType, LlmConfig, LlmProvider};

        let mut spec = sample_contract();
        spec.llm_config = Some(LlmConfig {
            capabilities: vec![LlmCapability {
                capability: LlmCapabilityType::Embed,
                providers: vec![LlmProvider {
                    name: "openai".to_string(),
                    model: "text-embedding-3-small".to_string(),
                    backend_url: "https://api.openai.com/v1".to_string(),
                    priority: 1,
                }],
            }],
            default_timeout_ms: None,
        });

        let json = serde_json::to_string(&spec).expect("serialize");
        let deserialized: UacContractSpec = serde_json::from_str(&json).expect("deserialize");

        assert!(deserialized.llm_config.is_some());
        let llm = deserialized.llm_config.as_ref().expect("llm_config");
        assert_eq!(llm.capabilities.len(), 1);
        assert_eq!(llm.capabilities[0].capability, LlmCapabilityType::Embed);
    }
}
