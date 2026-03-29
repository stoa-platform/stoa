//! GitHub REST API Client
//!
//! CAB-1891: Client for GitHub API interactions (Wave 2 GitLab→GitHub migration).
//!
//! Operations:
//! - Get file content from a repository
//! - List files in a directory
//! - Get repository metadata
//! - Register webhooks

#![allow(dead_code)] // GitHub client infrastructure, wired incrementally

use base64::{engine::general_purpose::STANDARD, Engine};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use thiserror::Error;
use tracing::{debug, error, info};

const DEFAULT_BASE_URL: &str = "https://api.github.com";
const USER_AGENT: &str = concat!("stoa-gateway/", env!("CARGO_PKG_VERSION"));
const DEFAULT_TIMEOUT_SECS: u64 = 30;

// =============================================================================
// Error Types
// =============================================================================

#[derive(Debug, Error)]
pub enum GitHubError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),

    #[error("GitHub API error: {status} - {message}")]
    Api { status: u16, message: String },

    #[error("Failed to decode content from {path}: {reason}")]
    Decode { path: String, reason: String },
}

// =============================================================================
// GitHub API Types
// =============================================================================

/// Repository metadata returned by the GitHub API.
#[derive(Debug, Clone, Deserialize)]
pub struct RepoInfo {
    pub name: String,
    pub full_name: String,
    pub default_branch: String,
    pub private: bool,
}

/// Webhook registration response.
#[derive(Debug, Clone, Deserialize)]
pub struct WebhookInfo {
    pub id: u64,
    pub url: String,
    pub events: Vec<String>,
}

// Internal: GitHub contents endpoint entry (file or directory item).
#[derive(Debug, Deserialize)]
struct ContentsEntry {
    name: String,
    #[serde(rename = "type")]
    entry_type: String,
    /// Present for file entries; base64-encoded content (may contain newlines).
    content: Option<String>,
    encoding: Option<String>,
}

// Internal: webhook creation request body.
#[derive(Debug, Serialize)]
struct CreateWebhookRequest<'a> {
    name: &'static str, // always "web" per GitHub API
    config: WebhookConfig<'a>,
    events: &'a [&'a str],
    active: bool,
}

#[derive(Debug, Serialize)]
struct WebhookConfig<'a> {
    url: &'a str,
    content_type: &'static str,
    secret: &'a str,
    insecure_ssl: &'static str,
}

// =============================================================================
// GitHub Client
// =============================================================================

/// Client for GitHub REST API operations.
pub struct GitHubClient {
    client: Client,
    token: String,
    org: String,
    base_url: String,
}

impl GitHubClient {
    /// Create a new GitHub client targeting `api.github.com`.
    pub fn new(token: impl Into<String>, org: impl Into<String>) -> Result<Self, GitHubError> {
        Self::with_base_url(token, org, DEFAULT_BASE_URL)
    }

    /// Create a client with a custom base URL (useful for GitHub Enterprise or tests).
    pub fn with_base_url(
        token: impl Into<String>,
        org: impl Into<String>,
        base_url: impl Into<String>,
    ) -> Result<Self, GitHubError> {
        let client = Client::builder()
            .timeout(Duration::from_secs(DEFAULT_TIMEOUT_SECS))
            .build()?;

        Ok(Self {
            client,
            token: token.into(),
            org: org.into(),
            base_url: base_url.into().trim_end_matches('/').to_string(),
        })
    }

    /// Retrieve the decoded content of a single file.
    ///
    /// Uses `GET /repos/{org}/{repo}/contents/{path}?ref={ref_}`.
    pub async fn get_file_content(
        &self,
        repo: &str,
        path: &str,
        ref_: &str,
    ) -> Result<String, GitHubError> {
        let url = format!(
            "{}/repos/{}/{}/contents/{}",
            self.base_url, self.org, repo, path
        );
        debug!(url = %url, ref_ = %ref_, "Fetching file content from GitHub");

        let response = self
            .client
            .get(&url)
            .header("Authorization", self.auth_header())
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/vnd.github+json")
            .query(&[("ref", ref_)])
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, %message, "GitHub API error fetching file");
            return Err(GitHubError::Api { status, message });
        }

        let entry: ContentsEntry = response.json().await?;
        self.decode_content(&entry, path)
    }

    /// List file names in a directory (returns only direct children of type "file").
    ///
    /// Uses `GET /repos/{org}/{repo}/contents/{path}?ref={ref_}`.
    pub async fn list_files(
        &self,
        repo: &str,
        path: &str,
        ref_: &str,
    ) -> Result<Vec<String>, GitHubError> {
        let url = format!(
            "{}/repos/{}/{}/contents/{}",
            self.base_url, self.org, repo, path
        );
        debug!(url = %url, ref_ = %ref_, "Listing files from GitHub");

        let response = self
            .client
            .get(&url)
            .header("Authorization", self.auth_header())
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/vnd.github+json")
            .query(&[("ref", ref_)])
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, %message, "GitHub API error listing files");
            return Err(GitHubError::Api { status, message });
        }

        let entries: Vec<ContentsEntry> = response.json().await?;
        let files = entries
            .into_iter()
            .filter(|e| e.entry_type == "file")
            .map(|e| e.name)
            .collect();

        Ok(files)
    }

    /// Retrieve repository metadata.
    ///
    /// Uses `GET /repos/{org}/{repo}`.
    pub async fn get_repo_info(&self, repo: &str) -> Result<RepoInfo, GitHubError> {
        let url = format!("{}/repos/{}/{}", self.base_url, self.org, repo);
        debug!(url = %url, "Fetching repo info from GitHub");

        let response = self
            .client
            .get(&url)
            .header("Authorization", self.auth_header())
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, %message, "GitHub API error fetching repo info");
            return Err(GitHubError::Api { status, message });
        }

        let info: RepoInfo = response.json().await?;
        info!(repo = %info.full_name, default_branch = %info.default_branch, "Fetched repo info");

        Ok(info)
    }

    /// Register a webhook on a repository.
    ///
    /// Uses `POST /repos/{org}/{repo}/hooks`.
    pub async fn create_webhook(
        &self,
        repo: &str,
        url: &str,
        secret: &str,
        events: &[&str],
    ) -> Result<WebhookInfo, GitHubError> {
        let api_url = format!("{}/repos/{}/{}/hooks", self.base_url, self.org, repo);
        debug!(api_url = %api_url, "Creating GitHub webhook");

        let body = CreateWebhookRequest {
            name: "web",
            config: WebhookConfig {
                url,
                content_type: "json",
                secret,
                insecure_ssl: "0",
            },
            events,
            active: true,
        };

        let response = self
            .client
            .post(&api_url)
            .header("Authorization", self.auth_header())
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/vnd.github+json")
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, %message, "GitHub API error creating webhook");
            return Err(GitHubError::Api { status, message });
        }

        let hook: WebhookInfo = response.json().await?;
        info!(id = hook.id, "GitHub webhook created");

        Ok(hook)
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    fn auth_header(&self) -> String {
        format!("Bearer {}", self.token)
    }

    /// Decode a base64-encoded content field from the GitHub contents API.
    fn decode_content(&self, entry: &ContentsEntry, path: &str) -> Result<String, GitHubError> {
        let raw = entry.content.as_deref().unwrap_or("");
        // GitHub wraps lines at 60 chars with '\n'; strip all whitespace before decoding.
        let stripped: String = raw.chars().filter(|c| !c.is_whitespace()).collect();
        let bytes = STANDARD
            .decode(&stripped)
            .map_err(|e| GitHubError::Decode {
                path: path.to_string(),
                reason: e.to_string(),
            })?;
        String::from_utf8(bytes).map_err(|e| GitHubError::Decode {
            path: path.to_string(),
            reason: e.to_string(),
        })
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_new_strips_trailing_slash() {
        let client =
            GitHubClient::with_base_url("tok", "myorg", "https://api.github.com/").unwrap();
        assert_eq!(client.base_url, "https://api.github.com");
    }

    #[test]
    fn test_auth_header_format() {
        let client = GitHubClient::new("my-secret-token", "acme").unwrap();
        assert_eq!(client.auth_header(), "Bearer my-secret-token");
    }

    #[test]
    fn test_decode_content_valid_base64() {
        let client = GitHubClient::new("tok", "org").unwrap();
        // "hello\n" base64-encoded = "aGVsbG8K"
        let entry = ContentsEntry {
            name: "file.txt".into(),
            entry_type: "file".into(),
            content: Some("aGVsbG8K".into()),
            encoding: Some("base64".into()),
        };
        let result = client.decode_content(&entry, "file.txt").unwrap();
        assert_eq!(result, "hello\n");
    }

    #[test]
    fn test_decode_content_with_newlines_in_b64() {
        // GitHub wraps base64 output at 60 chars with '\n'.
        let client = GitHubClient::new("tok", "org").unwrap();
        let wrapped = "aGVs\nbG8K"; // "aGVsbG8K" with a newline injected
        let entry = ContentsEntry {
            name: "f".into(),
            entry_type: "file".into(),
            content: Some(wrapped.into()),
            encoding: Some("base64".into()),
        };
        let result = client.decode_content(&entry, "f").unwrap();
        assert_eq!(result, "hello\n");
    }

    #[test]
    fn test_decode_content_invalid_base64_returns_error() {
        let client = GitHubClient::new("tok", "org").unwrap();
        let entry = ContentsEntry {
            name: "x".into(),
            entry_type: "file".into(),
            content: Some("!!!not-base64!!!".into()),
            encoding: Some("base64".into()),
        };
        assert!(client.decode_content(&entry, "x").is_err());
    }

    #[test]
    fn test_webhook_request_serialization() {
        let body = CreateWebhookRequest {
            name: "web",
            config: WebhookConfig {
                url: "https://example.com/hook",
                content_type: "json",
                secret: "s3cr3t",
                insecure_ssl: "0",
            },
            events: &["push", "pull_request"],
            active: true,
        };
        let json = serde_json::to_string(&body).unwrap();
        assert!(json.contains("\"name\":\"web\""));
        assert!(json.contains("https://example.com/hook"));
        assert!(json.contains("s3cr3t"));
        assert!(json.contains("push"));
    }
}
