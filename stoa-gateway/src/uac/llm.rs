//! LLM Contract Types (CAB-709)
//!
//! Extends UAC with optional `LlmConfig` so LLM capabilities are
//! automatically exposed as REST endpoints and MCP tools via existing
//! binders — "Define Once, Expose Everywhere" applied to AI backends.

use serde::{Deserialize, Serialize};

use super::schema::UacEndpoint;

// =============================================================================
// LLM Capability Type
// =============================================================================

/// The kind of LLM operation a capability exposes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LlmCapabilityType {
    Summarize,
    Classify,
    Generate,
    Embed,
    Chat,
}

impl LlmCapabilityType {
    /// URL path suffix for the synthetic REST endpoint.
    pub fn path_suffix(&self) -> &'static str {
        match self {
            Self::Summarize => "/summarize",
            Self::Classify => "/classify",
            Self::Generate => "/generate",
            Self::Embed => "/embed",
            Self::Chat => "/chat",
        }
    }

    /// HTTP method for the synthetic endpoint (always POST for LLM ops).
    pub fn http_method(&self) -> &'static str {
        "POST"
    }

    /// OpenAPI operationId used for MCP tool naming.
    pub fn operation_id(&self) -> &'static str {
        match self {
            Self::Summarize => "llm_summarize",
            Self::Classify => "llm_classify",
            Self::Generate => "llm_generate",
            Self::Embed => "llm_embed",
            Self::Chat => "llm_chat",
        }
    }
}

// =============================================================================
// LLM Provider
// =============================================================================

/// A single LLM provider backend (e.g. Anthropic Claude, OpenAI GPT-4).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmProvider {
    /// Provider name (e.g. "anthropic", "openai")
    pub name: String,
    /// Model identifier (e.g. "claude-sonnet-4-5-20250929", "gpt-4o")
    pub model: String,
    /// Backend URL for the provider API
    pub backend_url: String,
    /// Priority (lower = higher priority). Primary provider = min priority.
    #[serde(default = "default_priority")]
    pub priority: u8,
}

fn default_priority() -> u8 {
    0
}

// =============================================================================
// LLM Capability
// =============================================================================

/// A single LLM capability with an ordered list of providers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmCapability {
    /// The type of LLM operation
    pub capability: LlmCapabilityType,
    /// Providers ordered by priority (fallback chain)
    pub providers: Vec<LlmProvider>,
}

// =============================================================================
// LLM Config
// =============================================================================

/// Optional LLM configuration on a UAC contract.
///
/// When present, `expand_endpoints()` generates synthetic `UacEndpoint`
/// entries (one per capability) so RestBinder and McpBinder work unchanged.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmConfig {
    /// LLM capabilities exposed by this contract
    pub capabilities: Vec<LlmCapability>,
    /// Default timeout in milliseconds for LLM calls
    #[serde(skip_serializing_if = "Option::is_none")]
    pub default_timeout_ms: Option<u64>,
}

impl LlmConfig {
    /// Validate the LLM configuration. Returns a list of errors (empty = valid).
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();

        if self.capabilities.is_empty() {
            errors.push("llm_config.capabilities must not be empty".to_string());
        }

        for (i, cap) in self.capabilities.iter().enumerate() {
            if cap.providers.is_empty() {
                errors.push(format!(
                    "llm_config.capabilities[{}].providers must not be empty",
                    i
                ));
            }
            for (j, provider) in cap.providers.iter().enumerate() {
                if provider.backend_url.is_empty() {
                    errors.push(format!(
                        "llm_config.capabilities[{}].providers[{}].backend_url must not be empty",
                        i, j
                    ));
                }
                if provider.model.is_empty() {
                    errors.push(format!(
                        "llm_config.capabilities[{}].providers[{}].model must not be empty",
                        i, j
                    ));
                }
            }
        }

        errors
    }

    /// Generate synthetic `UacEndpoint` entries from LLM capabilities.
    ///
    /// Each capability becomes one endpoint using the primary provider
    /// (lowest priority number) as the backend URL.
    pub fn expand_endpoints(&self) -> Vec<UacEndpoint> {
        self.capabilities
            .iter()
            .filter_map(|cap| {
                let primary = cap.providers.iter().min_by_key(|p| p.priority)?;
                Some(UacEndpoint {
                    path: cap.capability.path_suffix().to_string(),
                    methods: vec![cap.capability.http_method().to_string()],
                    backend_url: primary.backend_url.clone(),
                    operation_id: Some(cap.capability.operation_id().to_string()),
                    input_schema: None,
                    output_schema: None,
                })
            })
            .collect()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_provider(name: &str, priority: u8) -> LlmProvider {
        LlmProvider {
            name: name.to_string(),
            model: format!("{}-model", name),
            backend_url: format!("https://{}.example.com/v1", name),
            priority,
        }
    }

    fn sample_config() -> LlmConfig {
        LlmConfig {
            capabilities: vec![
                LlmCapability {
                    capability: LlmCapabilityType::Summarize,
                    providers: vec![
                        sample_provider("anthropic", 1),
                        sample_provider("openai", 2),
                    ],
                },
                LlmCapability {
                    capability: LlmCapabilityType::Embed,
                    providers: vec![sample_provider("openai", 1)],
                },
            ],
            default_timeout_ms: Some(30000),
        }
    }

    #[test]
    fn test_capability_type_path_suffix() {
        assert_eq!(LlmCapabilityType::Summarize.path_suffix(), "/summarize");
        assert_eq!(LlmCapabilityType::Classify.path_suffix(), "/classify");
        assert_eq!(LlmCapabilityType::Generate.path_suffix(), "/generate");
        assert_eq!(LlmCapabilityType::Embed.path_suffix(), "/embed");
        assert_eq!(LlmCapabilityType::Chat.path_suffix(), "/chat");
    }

    #[test]
    fn test_capability_type_operation_id() {
        assert_eq!(LlmCapabilityType::Summarize.operation_id(), "llm_summarize");
        assert_eq!(LlmCapabilityType::Chat.operation_id(), "llm_chat");
    }

    #[test]
    fn test_validate_valid_config() {
        let config = sample_config();
        assert!(config.validate().is_empty());
    }

    #[test]
    fn test_validate_empty_capabilities() {
        let config = LlmConfig {
            capabilities: vec![],
            default_timeout_ms: None,
        };
        let errors = config.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("capabilities must not be empty")));
    }

    #[test]
    fn test_validate_empty_providers() {
        let config = LlmConfig {
            capabilities: vec![LlmCapability {
                capability: LlmCapabilityType::Chat,
                providers: vec![],
            }],
            default_timeout_ms: None,
        };
        let errors = config.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("providers must not be empty")));
    }

    #[test]
    fn test_validate_empty_backend_url() {
        let config = LlmConfig {
            capabilities: vec![LlmCapability {
                capability: LlmCapabilityType::Chat,
                providers: vec![LlmProvider {
                    name: "test".to_string(),
                    model: "test-model".to_string(),
                    backend_url: String::new(),
                    priority: 0,
                }],
            }],
            default_timeout_ms: None,
        };
        let errors = config.validate();
        assert!(errors
            .iter()
            .any(|e| e.contains("backend_url must not be empty")));
    }

    #[test]
    fn test_expand_endpoints() {
        let config = sample_config();
        let endpoints = config.expand_endpoints();

        assert_eq!(endpoints.len(), 2);

        // First: summarize — primary is anthropic (priority 1)
        assert_eq!(endpoints[0].path, "/summarize");
        assert_eq!(endpoints[0].methods, vec!["POST"]);
        assert_eq!(endpoints[0].backend_url, "https://anthropic.example.com/v1");
        assert_eq!(endpoints[0].operation_id.as_deref(), Some("llm_summarize"));

        // Second: embed — primary is openai (priority 1)
        assert_eq!(endpoints[1].path, "/embed");
        assert_eq!(endpoints[1].methods, vec!["POST"]);
        assert_eq!(endpoints[1].backend_url, "https://openai.example.com/v1");
        assert_eq!(endpoints[1].operation_id.as_deref(), Some("llm_embed"));
    }

    #[test]
    fn test_serde_roundtrip() {
        let config = sample_config();
        let json = serde_json::to_string(&config).expect("serialize");
        let deserialized: LlmConfig = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(deserialized.capabilities.len(), 2);
        assert_eq!(
            deserialized.capabilities[0].capability,
            LlmCapabilityType::Summarize
        );
        assert_eq!(deserialized.capabilities[0].providers.len(), 2);
        assert_eq!(deserialized.default_timeout_ms, Some(30000));
    }
}
