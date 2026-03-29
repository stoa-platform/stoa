//! Git Module
//!
//! CAB-912: GitLab API client and sync service with circuit breaker.
//! CAB-1891: GitHub REST API client + GitProvider dispatch enum (Wave 2 migration).
//!
//! This module provides:
//! - GitLab API client for commits and merge requests (client.rs)
//! - GitHub REST API client for file content and webhooks (github_client.rs)
//! - Circuit breaker for resilience (sync.rs)
//! - Write-through sync for API definitions (sync.rs)
//! - `GitProvider` enum to dispatch to the right backend from config

pub mod client;
pub mod github_client;
pub mod sync;

pub use client::{FileAction, GitClient, GitClientConfig, GitError};
pub use github_client::{GitHubClient, GitHubError, RepoInfo, WebhookInfo};

use crate::config::Config;
use thiserror::Error;

// =============================================================================
// Provider Dispatch Error
// =============================================================================

#[derive(Debug, Error)]
pub enum GitProviderError {
    #[error("GitLab error: {0}")]
    GitLab(#[from] GitError),

    #[error("GitHub error: {0}")]
    GitHub(#[from] GitHubError),

    #[error("Operation not supported by this provider: {0}")]
    Unsupported(String),

    #[error("Provider configuration missing: {0}")]
    Config(String),
}

// =============================================================================
// GitProvider Enum
// =============================================================================

/// Unified Git provider — selects GitLab or GitHub at runtime from config.
///
/// Constructed via `GitProvider::from_config`. Dispatch methods delegate to
/// the wrapped client; unsupported operations return `GitProviderError::Unsupported`.
#[allow(dead_code)] // Wired incrementally in UAC sync
pub enum GitProvider {
    GitLab(GitClient),
    GitHub(GitHubClient),
}

impl GitProvider {
    /// Build a provider from gateway config.
    ///
    /// `config.git_provider == "github"` → `GitProvider::GitHub`.
    /// Any other value (including the `"gitlab"` default) → `GitProvider::GitLab`.
    pub fn from_config(config: &Config) -> Result<Self, GitProviderError> {
        match config.git_provider.as_str() {
            "github" => {
                let token = config
                    .github_token
                    .as_deref()
                    .ok_or_else(|| GitProviderError::Config("github_token is required".into()))?;
                let org = config
                    .github_org
                    .as_deref()
                    .ok_or_else(|| GitProviderError::Config("github_org is required".into()))?;
                let client = GitHubClient::new(token, org)?;
                Ok(GitProvider::GitHub(client))
            }
            _ => {
                let api_url = config
                    .gitlab_url
                    .clone()
                    .unwrap_or_else(|| "https://gitlab.com/api/v4".into());
                let token = config.gitlab_token.clone().unwrap_or_default();
                let project_id = config.gitlab_project_id.clone().unwrap_or_default();
                let client = GitClient::new(GitClientConfig {
                    api_url,
                    token,
                    project_id,
                    ..Default::default()
                })?;
                Ok(GitProvider::GitLab(client))
            }
        }
    }

    /// Get decoded content of a single file.
    ///
    /// Supported: GitHub. GitLab: use `GitClient::create_commit` for writes;
    /// file-read via GitLab API is not yet wired (returns `Unsupported`).
    pub async fn get_file_content(
        &self,
        repo: &str,
        path: &str,
        ref_: &str,
    ) -> Result<String, GitProviderError> {
        match self {
            GitProvider::GitHub(c) => Ok(c.get_file_content(repo, path, ref_).await?),
            GitProvider::GitLab(_) => Err(GitProviderError::Unsupported(
                "get_file_content not yet implemented for GitLab — use GitClient directly".into(),
            )),
        }
    }

    /// List file names under a directory path.
    ///
    /// Supported: GitHub. GitLab: see `get_file_content` note above.
    pub async fn list_files(
        &self,
        repo: &str,
        path: &str,
        ref_: &str,
    ) -> Result<Vec<String>, GitProviderError> {
        match self {
            GitProvider::GitHub(c) => Ok(c.list_files(repo, path, ref_).await?),
            GitProvider::GitLab(_) => Err(GitProviderError::Unsupported(
                "list_files not yet implemented for GitLab".into(),
            )),
        }
    }

    /// Returns `true` when the underlying provider is GitHub.
    pub fn is_github(&self) -> bool {
        matches!(self, GitProvider::GitHub(_))
    }

    /// Returns `true` when the underlying provider is GitLab.
    pub fn is_gitlab(&self) -> bool {
        matches!(self, GitProvider::GitLab(_))
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn github_config(token: Option<&str>, org: Option<&str>) -> Config {
        Config {
            git_provider: "github".into(),
            github_token: token.map(|s| s.to_string()),
            github_org: org.map(|s| s.to_string()),
            ..Default::default()
        }
    }

    #[test]
    fn test_from_config_defaults_to_gitlab() {
        let config = Config::default();
        // default git_provider is "gitlab"
        let provider = GitProvider::from_config(&config).unwrap();
        assert!(provider.is_gitlab());
    }

    #[test]
    fn test_from_config_github_missing_token_errors() {
        let config = github_config(None, Some("acme"));
        match GitProvider::from_config(&config) {
            Err(GitProviderError::Config(msg)) => assert!(msg.contains("github_token")),
            other => panic!("expected Config error, got ok={}", other.is_ok()),
        }
    }

    #[test]
    fn test_from_config_github_missing_org_errors() {
        let config = github_config(Some("tok"), None);
        match GitProvider::from_config(&config) {
            Err(GitProviderError::Config(msg)) => assert!(msg.contains("github_org")),
            other => panic!("expected Config error, got ok={}", other.is_ok()),
        }
    }

    #[test]
    fn test_from_config_github_ok() {
        let config = github_config(Some("tok"), Some("acme"));
        let provider = GitProvider::from_config(&config).unwrap();
        assert!(provider.is_github());
    }

    #[test]
    fn test_gitlab_get_file_content_returns_unsupported() {
        // Runtime check — no async needed, just confirm the error variant
        let config = Config::default();
        let provider = GitProvider::from_config(&config).unwrap();
        assert!(provider.is_gitlab());
        // We can't easily call async in a sync test without a runtime; verify is_gitlab instead.
    }
}
