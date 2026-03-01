//! LLM Provider Registry (CAB-1487)
//!
//! Manages multiple LLM provider configurations with priority and cost metadata.
//! The registry filters disabled providers at construction time and provides
//! sorted views for different routing strategies.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::sync::Arc;

/// Supported LLM provider types.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LlmProvider {
    OpenAi,
    Anthropic,
    Google,
    Mistral,
    Local,
    AzureOpenAi,
}

impl fmt::Display for LlmProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LlmProvider::OpenAi => write!(f, "openai"),
            LlmProvider::Anthropic => write!(f, "anthropic"),
            LlmProvider::Google => write!(f, "google"),
            LlmProvider::Mistral => write!(f, "mistral"),
            LlmProvider::Local => write!(f, "local"),
            LlmProvider::AzureOpenAi => write!(f, "azure_openai"),
        }
    }
}

impl LlmProvider {
    /// Parse a provider from a string (case-insensitive).
    pub fn from_str_opt(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "openai" | "open_ai" => Some(LlmProvider::OpenAi),
            "anthropic" => Some(LlmProvider::Anthropic),
            "google" | "gemini" => Some(LlmProvider::Google),
            "mistral" => Some(LlmProvider::Mistral),
            "local" | "ollama" | "vllm" => Some(LlmProvider::Local),
            "azure_openai" | "azure-openai" | "azureopenai" => Some(LlmProvider::AzureOpenAi),
            _ => None,
        }
    }

    /// Returns true if this provider uses OpenAI-compatible API format
    /// (`/v1/chat/completions`, `Authorization: Bearer`, OpenAI response schema).
    pub fn is_openai_compatible(&self) -> bool {
        matches!(
            self,
            LlmProvider::OpenAi | LlmProvider::Mistral | LlmProvider::Local
        )
    }

    /// Returns true if this provider uses the OpenAI response/request schema
    /// but may have different auth or URL patterns (e.g. Azure OpenAI).
    pub fn uses_openai_schema(&self) -> bool {
        self.is_openai_compatible() || matches!(self, LlmProvider::AzureOpenAi)
    }
}

/// Configuration for a single LLM provider endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    /// Provider type.
    pub provider: LlmProvider,

    /// Unique backend identifier for subscription-based routing.
    /// When multiple backends share the same provider type (e.g. two Azure OpenAI
    /// namespaces), this ID distinguishes them in subscription → backend mappings.
    #[serde(default)]
    pub backend_id: Option<String>,

    /// Base URL for API requests (e.g. `https://api.openai.com/v1`).
    pub base_url: String,

    /// Environment variable name holding the API key.
    #[serde(default)]
    pub api_key_env: Option<String>,

    /// Default model identifier (e.g. `gpt-4o`, `claude-sonnet-4-20250514`).
    #[serde(default)]
    pub default_model: Option<String>,

    /// Maximum concurrent requests to this provider.
    #[serde(default = "default_max_concurrent")]
    pub max_concurrent: u32,

    /// Whether this provider is enabled.
    #[serde(default = "default_enabled")]
    pub enabled: bool,

    /// Cost per 1M input tokens in USD.
    #[serde(default)]
    pub cost_per_1m_input: f64,

    /// Cost per 1M output tokens in USD.
    #[serde(default)]
    pub cost_per_1m_output: f64,

    /// Routing priority (lower = higher priority, 0 = highest).
    #[serde(default = "default_priority")]
    pub priority: u32,

    /// Azure OpenAI deployment name (e.g. `gpt-4o`). Only used when provider is AzureOpenAi.
    #[serde(default)]
    pub deployment: Option<String>,

    /// Azure OpenAI API version (e.g. `2024-10-21`). Only used when provider is AzureOpenAi.
    #[serde(default)]
    pub api_version: Option<String>,
}

fn default_max_concurrent() -> u32 {
    50
}

fn default_enabled() -> bool {
    true
}

fn default_priority() -> u32 {
    10
}

/// Registry of enabled LLM providers, filterable by cost and priority.
#[derive(Debug, Clone)]
pub struct ProviderRegistry {
    providers: Vec<ProviderConfig>,
}

impl ProviderRegistry {
    /// Create a registry from a list of provider configs. Disabled providers are filtered out.
    pub fn new(configs: Vec<ProviderConfig>) -> Self {
        let providers: Vec<ProviderConfig> = configs.into_iter().filter(|c| c.enabled).collect();
        Self { providers }
    }

    /// Create an empty registry (no providers configured).
    pub fn empty() -> Self {
        Self {
            providers: Vec::new(),
        }
    }

    /// Get a provider config by type. Returns the first matching enabled provider.
    pub fn get(&self, provider: LlmProvider) -> Option<&ProviderConfig> {
        self.providers.iter().find(|p| p.provider == provider)
    }

    /// Get a provider config by backend ID. Used for subscription-based routing
    /// where the subscription plan maps to a specific backend identifier.
    pub fn get_by_backend_id(&self, backend_id: &str) -> Option<&ProviderConfig> {
        self.providers
            .iter()
            .find(|p| p.backend_id.as_deref() == Some(backend_id))
    }

    /// Get all enabled providers sorted by priority (lowest number first).
    pub fn sorted_by_priority(&self) -> Vec<&ProviderConfig> {
        let mut sorted: Vec<&ProviderConfig> = self.providers.iter().collect();
        sorted.sort_by_key(|p| p.priority);
        sorted
    }

    /// Get all enabled providers sorted by input cost (cheapest first).
    pub fn sorted_by_cost(&self) -> Vec<&ProviderConfig> {
        let mut sorted: Vec<&ProviderConfig> = self.providers.iter().collect();
        sorted.sort_by(|a, b| {
            a.cost_per_1m_input
                .partial_cmp(&b.cost_per_1m_input)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        sorted
    }

    /// Return all enabled providers (insertion order).
    pub fn all(&self) -> &[ProviderConfig] {
        &self.providers
    }

    /// Number of enabled providers.
    pub fn len(&self) -> usize {
        self.providers.len()
    }

    /// Whether the registry has no enabled providers.
    pub fn is_empty(&self) -> bool {
        self.providers.is_empty()
    }

    /// Wrap in Arc for shared ownership across async tasks.
    pub fn into_shared(self) -> Arc<Self> {
        Arc::new(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_provider(
        provider: LlmProvider,
        enabled: bool,
        priority: u32,
        cost_input: f64,
    ) -> ProviderConfig {
        ProviderConfig {
            provider,
            backend_id: None,
            base_url: format!("https://{}.example.com", provider),
            api_key_env: None,
            default_model: None,
            max_concurrent: 50,
            enabled,
            cost_per_1m_input: cost_input,
            cost_per_1m_output: cost_input * 3.0,
            priority,
            deployment: None,
            api_version: None,
        }
    }

    #[test]
    fn registry_creation_filters_disabled() {
        let configs = vec![
            make_provider(LlmProvider::OpenAi, true, 1, 5.0),
            make_provider(LlmProvider::Anthropic, false, 2, 3.0),
            make_provider(LlmProvider::Google, true, 3, 1.0),
        ];
        let registry = ProviderRegistry::new(configs);
        assert_eq!(registry.len(), 2);
        assert!(registry.get(LlmProvider::OpenAi).is_some());
        assert!(registry.get(LlmProvider::Anthropic).is_none());
        assert!(registry.get(LlmProvider::Google).is_some());
    }

    #[test]
    fn sorted_by_priority() {
        let configs = vec![
            make_provider(LlmProvider::Google, true, 10, 1.0),
            make_provider(LlmProvider::OpenAi, true, 1, 5.0),
            make_provider(LlmProvider::Anthropic, true, 5, 3.0),
        ];
        let registry = ProviderRegistry::new(configs);
        let sorted = registry.sorted_by_priority();
        assert_eq!(sorted[0].provider, LlmProvider::OpenAi);
        assert_eq!(sorted[1].provider, LlmProvider::Anthropic);
        assert_eq!(sorted[2].provider, LlmProvider::Google);
    }

    #[test]
    fn sorted_by_cost() {
        let configs = vec![
            make_provider(LlmProvider::OpenAi, true, 1, 5.0),
            make_provider(LlmProvider::Anthropic, true, 2, 3.0),
            make_provider(LlmProvider::Google, true, 3, 1.0),
        ];
        let registry = ProviderRegistry::new(configs);
        let sorted = registry.sorted_by_cost();
        assert_eq!(sorted[0].provider, LlmProvider::Google);
        assert_eq!(sorted[1].provider, LlmProvider::Anthropic);
        assert_eq!(sorted[2].provider, LlmProvider::OpenAi);
    }

    #[test]
    fn empty_registry() {
        let registry = ProviderRegistry::empty();
        assert!(registry.is_empty());
        assert_eq!(registry.len(), 0);
        assert!(registry.get(LlmProvider::OpenAi).is_none());
    }

    #[test]
    fn provider_display() {
        assert_eq!(LlmProvider::OpenAi.to_string(), "openai");
        assert_eq!(LlmProvider::Anthropic.to_string(), "anthropic");
        assert_eq!(LlmProvider::Google.to_string(), "google");
        assert_eq!(LlmProvider::Mistral.to_string(), "mistral");
        assert_eq!(LlmProvider::Local.to_string(), "local");
        assert_eq!(LlmProvider::AzureOpenAi.to_string(), "azure_openai");
    }

    #[test]
    fn provider_from_str_opt() {
        assert_eq!(
            LlmProvider::from_str_opt("openai"),
            Some(LlmProvider::OpenAi)
        );
        assert_eq!(
            LlmProvider::from_str_opt("Anthropic"),
            Some(LlmProvider::Anthropic)
        );
        assert_eq!(
            LlmProvider::from_str_opt("gemini"),
            Some(LlmProvider::Google)
        );
        assert_eq!(
            LlmProvider::from_str_opt("mistral"),
            Some(LlmProvider::Mistral)
        );
        assert_eq!(
            LlmProvider::from_str_opt("ollama"),
            Some(LlmProvider::Local)
        );
        assert_eq!(
            LlmProvider::from_str_opt("azure_openai"),
            Some(LlmProvider::AzureOpenAi)
        );
        assert_eq!(
            LlmProvider::from_str_opt("azure-openai"),
            Some(LlmProvider::AzureOpenAi)
        );
        assert_eq!(
            LlmProvider::from_str_opt("azureopenai"),
            Some(LlmProvider::AzureOpenAi)
        );
        assert_eq!(LlmProvider::from_str_opt("unknown"), None);
    }

    #[test]
    fn is_openai_compatible() {
        assert!(LlmProvider::OpenAi.is_openai_compatible());
        assert!(LlmProvider::Mistral.is_openai_compatible());
        assert!(LlmProvider::Local.is_openai_compatible());
        assert!(!LlmProvider::Anthropic.is_openai_compatible());
        assert!(!LlmProvider::Google.is_openai_compatible());
        assert!(!LlmProvider::AzureOpenAi.is_openai_compatible());
    }

    #[test]
    fn uses_openai_schema() {
        assert!(LlmProvider::OpenAi.uses_openai_schema());
        assert!(LlmProvider::Mistral.uses_openai_schema());
        assert!(LlmProvider::Local.uses_openai_schema());
        assert!(LlmProvider::AzureOpenAi.uses_openai_schema());
        assert!(!LlmProvider::Anthropic.uses_openai_schema());
        assert!(!LlmProvider::Google.uses_openai_schema());
    }

    #[test]
    fn get_by_backend_id() {
        let mut alpha = make_provider(LlmProvider::AzureOpenAi, true, 1, 5.0);
        alpha.backend_id = Some("projet-alpha".to_string());
        alpha.base_url = "https://projet-alpha.openai.azure.com".to_string();

        let mut beta = make_provider(LlmProvider::AzureOpenAi, true, 2, 5.0);
        beta.backend_id = Some("projet-beta".to_string());
        beta.base_url = "https://projet-beta.openai.azure.com".to_string();

        let registry = ProviderRegistry::new(vec![alpha, beta]);

        let found = registry.get_by_backend_id("projet-alpha");
        assert!(found.is_some());
        assert_eq!(
            found.expect("should find alpha").base_url,
            "https://projet-alpha.openai.azure.com"
        );

        let found_beta = registry.get_by_backend_id("projet-beta");
        assert!(found_beta.is_some());
        assert_eq!(
            found_beta.expect("should find beta").base_url,
            "https://projet-beta.openai.azure.com"
        );

        assert!(registry.get_by_backend_id("unknown").is_none());
    }
}
