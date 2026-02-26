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
    Local,
}

impl fmt::Display for LlmProvider {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LlmProvider::OpenAi => write!(f, "openai"),
            LlmProvider::Anthropic => write!(f, "anthropic"),
            LlmProvider::Google => write!(f, "google"),
            LlmProvider::Local => write!(f, "local"),
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
            "local" | "ollama" | "vllm" => Some(LlmProvider::Local),
            _ => None,
        }
    }
}

/// Configuration for a single LLM provider endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    /// Provider type.
    pub provider: LlmProvider,

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
            base_url: format!("https://{}.example.com", provider),
            api_key_env: None,
            default_model: None,
            max_concurrent: 50,
            enabled,
            cost_per_1m_input: cost_input,
            cost_per_1m_output: cost_input * 3.0,
            priority,
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
        assert_eq!(LlmProvider::Local.to_string(), "local");
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
            LlmProvider::from_str_opt("ollama"),
            Some(LlmProvider::Local)
        );
        assert_eq!(LlmProvider::from_str_opt("unknown"), None);
    }
}
