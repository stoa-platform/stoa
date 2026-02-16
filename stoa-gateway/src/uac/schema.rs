//! UAC Contract Schema Types
//!
//! Core types for the Universal API Contract v1 specification.
//! "Define Once, Expose Everywhere" — a single contract generates
//! REST routes, MCP tools, and protocol bindings automatically.
//!
//! These types mirror `uac-contract-v1.schema.json` (cross-language parity).

use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::classifications::Classification;

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
    pub methods: Vec<String>,
    /// Backend URL to proxy requests to
    pub backend_url: String,
    /// OpenAPI operationId — used for MCP tool naming
    #[serde(skip_serializing_if = "Option::is_none")]
    pub operation_id: Option<String>,
    /// JSON Schema for request body validation
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input_schema: Option<Value>,
    /// JSON Schema for response body
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<Value>,
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
    /// Semantic version (e.g. "1.0.0")
    pub version: String,
    /// Owning tenant identifier
    pub tenant_id: String,
    /// Human-readable display name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub display_name: Option<String>,
    /// Contract description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    /// ICT risk classification (H/VH/VVH, DORA-aligned)
    pub classification: Classification,
    /// API endpoints exposed by this contract
    pub endpoints: Vec<UacEndpoint>,
    /// Required policies derived from classification (auto-populated)
    #[serde(default)]
    pub required_policies: Vec<String>,
    /// Lifecycle status
    pub status: ContractStatus,
    /// URL of the source OpenAPI spec
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_spec_url: Option<String>,
    /// SHA-256 hash of the source spec for drift detection
    #[serde(skip_serializing_if = "Option::is_none")]
    pub spec_hash: Option<String>,
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
        if self.endpoints.is_empty() && self.status == ContractStatus::Published {
            errors.push("published contract must have at least one endpoint".to_string());
        }

        // Validate each endpoint
        for (i, ep) in self.endpoints.iter().enumerate() {
            if ep.path.is_empty() {
                errors.push(format!("endpoints[{}].path must not be empty", i));
            }
            if ep.methods.is_empty() {
                errors.push(format!("endpoints[{}].methods must not be empty", i));
            }
            if ep.backend_url.is_empty() {
                errors.push(format!("endpoints[{}].backend_url must not be empty", i));
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
            operation_id: Some("get_payment".to_string()),
            input_schema: None,
            output_schema: None,
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
            operation_id: None,
            input_schema: None,
            output_schema: None,
        };

        let json = serde_json::to_value(&endpoint).expect("serialize");
        assert!(json.get("operation_id").is_none());
        assert!(json.get("input_schema").is_none());
        assert!(json.get("output_schema").is_none());
    }
}
