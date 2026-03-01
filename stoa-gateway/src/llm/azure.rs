//! Azure OpenAI Request Transformation (CAB-1610)
//!
//! Transforms standard OpenAI-format requests into Azure OpenAI format:
//! - URL: `{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={version}`
//! - Auth: `api-key: {key}` header instead of `Authorization: Bearer {key}`
//!
//! The subscriber sends a standard OpenAI chat/completions request with STOA
//! credentials. The gateway resolves the target Azure namespace from the
//! subscription mapping and transforms the request before proxying.

use super::providers::ProviderConfig;

/// Errors that can occur during Azure OpenAI request transformation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AzureTransformError {
    /// The provider config is missing the required `deployment` field.
    MissingDeployment,
    /// The provider config is missing the required `api_version` field.
    MissingApiVersion,
    /// The API key environment variable is not set or empty.
    MissingApiKey,
}

impl std::fmt::Display for AzureTransformError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AzureTransformError::MissingDeployment => {
                write!(f, "Azure OpenAI config missing 'deployment' field")
            }
            AzureTransformError::MissingApiVersion => {
                write!(f, "Azure OpenAI config missing 'api_version' field")
            }
            AzureTransformError::MissingApiKey => {
                write!(f, "Azure OpenAI API key not set")
            }
        }
    }
}

impl std::error::Error for AzureTransformError {}

/// Result of transforming a request for Azure OpenAI.
#[derive(Debug, Clone)]
pub struct AzureRequest {
    /// Full URL including deployment and api-version query parameter.
    pub url: String,
    /// Headers to set on the upstream request.
    pub headers: Vec<(String, String)>,
}

/// Build the Azure OpenAI chat completions URL from a provider config.
///
/// Format: `{base_url}/openai/deployments/{deployment}/chat/completions?api-version={version}`
pub fn build_chat_completions_url(config: &ProviderConfig) -> Result<String, AzureTransformError> {
    let deployment = config
        .deployment
        .as_deref()
        .ok_or(AzureTransformError::MissingDeployment)?;
    let api_version = config
        .api_version
        .as_deref()
        .ok_or(AzureTransformError::MissingApiVersion)?;

    let base = config.base_url.trim_end_matches('/');
    Ok(format!(
        "{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    ))
}

/// Build Azure OpenAI headers. Azure uses `api-key` instead of `Authorization: Bearer`.
pub fn build_headers(api_key: &str) -> Vec<(String, String)> {
    vec![
        ("api-key".to_string(), api_key.to_string()),
        ("Content-Type".to_string(), "application/json".to_string()),
    ]
}

/// Resolve the API key from the environment variable specified in the config.
pub fn resolve_api_key(config: &ProviderConfig) -> Result<String, AzureTransformError> {
    let env_name = config
        .api_key_env
        .as_deref()
        .ok_or(AzureTransformError::MissingApiKey)?;
    std::env::var(env_name).map_err(|_| AzureTransformError::MissingApiKey)
}

/// Transform a standard OpenAI request into Azure OpenAI format.
///
/// Resolves the API key from the environment, builds the Azure-specific URL,
/// and returns headers with `api-key` authentication.
pub fn transform_request(config: &ProviderConfig) -> Result<AzureRequest, AzureTransformError> {
    let url = build_chat_completions_url(config)?;
    let api_key = resolve_api_key(config)?;
    let headers = build_headers(&api_key);
    Ok(AzureRequest { url, headers })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::providers::{LlmProvider, ProviderConfig};

    fn make_azure_config(
        endpoint: &str,
        deployment: &str,
        api_version: &str,
        api_key_env: &str,
    ) -> ProviderConfig {
        ProviderConfig {
            provider: LlmProvider::AzureOpenAi,
            backend_id: Some("test-backend".to_string()),
            base_url: endpoint.to_string(),
            api_key_env: Some(api_key_env.to_string()),
            default_model: None,
            max_concurrent: 50,
            enabled: true,
            cost_per_1m_input: 5.0,
            cost_per_1m_output: 15.0,
            priority: 1,
            deployment: Some(deployment.to_string()),
            api_version: Some(api_version.to_string()),
        }
    }

    #[test]
    fn build_url_standard() {
        let config = make_azure_config(
            "https://projet-alpha.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "AZURE_ALPHA_KEY",
        );
        let url = build_chat_completions_url(&config).expect("should build URL");
        assert_eq!(
            url,
            "https://projet-alpha.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-12-01-preview"
        );
    }

    #[test]
    fn build_url_trailing_slash() {
        let config = make_azure_config(
            "https://projet-alpha.openai.azure.com/",
            "gpt-4o",
            "2024-12-01-preview",
            "AZURE_ALPHA_KEY",
        );
        let url = build_chat_completions_url(&config).expect("should build URL");
        assert_eq!(
            url,
            "https://projet-alpha.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-12-01-preview"
        );
    }

    #[test]
    fn build_url_missing_deployment() {
        let mut config = make_azure_config(
            "https://example.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "KEY",
        );
        config.deployment = None;
        let err = build_chat_completions_url(&config).unwrap_err();
        assert_eq!(err, AzureTransformError::MissingDeployment);
    }

    #[test]
    fn build_url_missing_api_version() {
        let mut config = make_azure_config(
            "https://example.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "KEY",
        );
        config.api_version = None;
        let err = build_chat_completions_url(&config).unwrap_err();
        assert_eq!(err, AzureTransformError::MissingApiVersion);
    }

    #[test]
    fn build_headers_uses_api_key() {
        let headers = build_headers("my-secret-key");
        assert_eq!(headers.len(), 2);
        assert_eq!(
            headers[0],
            ("api-key".to_string(), "my-secret-key".to_string())
        );
        assert_eq!(
            headers[1],
            ("Content-Type".to_string(), "application/json".to_string())
        );
    }

    #[test]
    fn resolve_api_key_from_env() {
        let config = make_azure_config(
            "https://test.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "STOA_TEST_AZURE_KEY_CAB1610",
        );

        // Set env var for this test
        std::env::set_var("STOA_TEST_AZURE_KEY_CAB1610", "test-key-value");
        let key = resolve_api_key(&config).expect("should resolve key");
        assert_eq!(key, "test-key-value");
        std::env::remove_var("STOA_TEST_AZURE_KEY_CAB1610");
    }

    #[test]
    fn resolve_api_key_missing_env() {
        let config = make_azure_config(
            "https://test.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "STOA_MISSING_KEY_CAB1610",
        );
        // Don't set the env var
        std::env::remove_var("STOA_MISSING_KEY_CAB1610");
        let err = resolve_api_key(&config).unwrap_err();
        assert_eq!(err, AzureTransformError::MissingApiKey);
    }

    #[test]
    fn resolve_api_key_no_env_name() {
        let mut config = make_azure_config(
            "https://test.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "KEY",
        );
        config.api_key_env = None;
        let err = resolve_api_key(&config).unwrap_err();
        assert_eq!(err, AzureTransformError::MissingApiKey);
    }

    #[test]
    fn transform_request_full_flow() {
        let config = make_azure_config(
            "https://projet-beta.openai.azure.com",
            "gpt-4o",
            "2024-12-01-preview",
            "STOA_TEST_BETA_KEY_CAB1610",
        );

        std::env::set_var("STOA_TEST_BETA_KEY_CAB1610", "beta-secret");
        let req = transform_request(&config).expect("should transform");
        assert_eq!(
            req.url,
            "https://projet-beta.openai.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2024-12-01-preview"
        );
        assert_eq!(req.headers[0].1, "beta-secret");
        std::env::remove_var("STOA_TEST_BETA_KEY_CAB1610");
    }

    #[test]
    fn error_display() {
        assert_eq!(
            AzureTransformError::MissingDeployment.to_string(),
            "Azure OpenAI config missing 'deployment' field"
        );
        assert_eq!(
            AzureTransformError::MissingApiVersion.to_string(),
            "Azure OpenAI config missing 'api_version' field"
        );
        assert_eq!(
            AzureTransformError::MissingApiKey.to_string(),
            "Azure OpenAI API key not set"
        );
    }
}
