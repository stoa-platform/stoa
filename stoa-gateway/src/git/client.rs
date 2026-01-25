//! Git API Client
//!
//! CAB-912: Client for GitLab API interactions.
//!
//! Operations:
//! - Get current commit hash (for version checking)
//! - Create file commits (for API definitions)
//! - Create merge requests (for VH/VVH APIs)

use reqwest::Client;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tracing::{debug, error, info};

// =============================================================================
// Error Types
// =============================================================================

#[derive(Debug, Error)]
pub enum GitError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),

    #[error("Git API error: {status} - {message}")]
    Api { status: u16, message: String },

    #[error("File already exists: {path}")]
    FileExists { path: String },

    #[error("Branch not found: {branch}")]
    BranchNotFound { branch: String },

    #[error("Commit failed: {0}")]
    CommitFailed(String),

    #[error("Merge request creation failed: {0}")]
    MergeRequestFailed(String),
}

// =============================================================================
// GitLab API Types
// =============================================================================

/// GitLab branch information
#[derive(Debug, Clone, Deserialize)]
pub struct Branch {
    pub name: String,
    pub commit: Commit,
}

/// GitLab commit information
#[derive(Debug, Clone, Deserialize)]
pub struct Commit {
    pub id: String,
    pub short_id: String,
    pub message: String,
}

/// Create file action for commits
#[derive(Debug, Clone, Serialize)]
pub struct FileAction {
    pub action: String, // "create", "update", "delete"
    pub file_path: String,
    pub content: String,
}

/// Create commit request
#[derive(Debug, Clone, Serialize)]
struct CreateCommitRequest {
    branch: String,
    commit_message: String,
    actions: Vec<FileAction>,
}

/// Create commit response
#[derive(Debug, Clone, Deserialize)]
pub struct CommitResponse {
    pub id: String,
    pub short_id: String,
    pub message: String,
    pub web_url: String,
}

/// Create merge request
#[derive(Debug, Clone, Serialize)]
struct CreateMergeRequestRequest {
    source_branch: String,
    target_branch: String,
    title: String,
    description: String,
}

/// Merge request response
#[derive(Debug, Clone, Deserialize)]
pub struct MergeRequestResponse {
    pub iid: u64,
    pub title: String,
    pub web_url: String,
    pub state: String,
}

// =============================================================================
// Git Client Configuration
// =============================================================================

/// Configuration for Git client.
#[derive(Debug, Clone)]
pub struct GitClientConfig {
    /// GitLab API URL (e.g., https://gitlab.com/api/v4)
    pub api_url: String,

    /// GitLab project ID
    pub project_id: String,

    /// Private token for authentication
    pub token: String,

    /// Default branch (usually "main")
    pub default_branch: String,

    /// Request timeout in seconds
    pub timeout_seconds: u64,
}

impl Default for GitClientConfig {
    fn default() -> Self {
        Self {
            api_url: "https://gitlab.com/api/v4".to_string(),
            project_id: String::new(),
            token: String::new(),
            default_branch: "main".to_string(),
            timeout_seconds: 30,
        }
    }
}

// =============================================================================
// Git Client
// =============================================================================

/// Client for Git (GitLab) API operations.
pub struct GitClient {
    client: Client,
    config: GitClientConfig,
}

impl GitClient {
    /// Create a new Git client.
    pub fn new(config: GitClientConfig) -> Result<Self, GitError> {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(config.timeout_seconds))
            .build()?;

        Ok(Self { client, config })
    }

    /// Get the current commit hash of the default branch.
    pub async fn get_current_version(&self) -> Result<String, GitError> {
        let url = format!(
            "{}/projects/{}/repository/branches/{}",
            self.config.api_url,
            urlencoding::encode(&self.config.project_id),
            urlencoding::encode(&self.config.default_branch)
        );

        debug!(url = %url, "Fetching current Git version");

        let response = self
            .client
            .get(&url)
            .header("PRIVATE-TOKEN", &self.config.token)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Git API error");
            return Err(GitError::Api { status, message });
        }

        let branch: Branch = response.json().await?;
        info!(
            commit_id = %branch.commit.id,
            short_id = %branch.commit.short_id,
            "Got current Git version"
        );

        Ok(branch.commit.id)
    }

    /// Create a commit with file changes.
    pub async fn create_commit(
        &self,
        branch: &str,
        message: &str,
        actions: Vec<FileAction>,
    ) -> Result<CommitResponse, GitError> {
        let url = format!(
            "{}/projects/{}/repository/commits",
            self.config.api_url,
            urlencoding::encode(&self.config.project_id)
        );

        let request = CreateCommitRequest {
            branch: branch.to_string(),
            commit_message: message.to_string(),
            actions,
        };

        debug!(
            url = %url,
            branch = %branch,
            message = %message,
            "Creating Git commit"
        );

        let response = self
            .client
            .post(&url)
            .header("PRIVATE-TOKEN", &self.config.token)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Commit failed");
            return Err(GitError::CommitFailed(message));
        }

        let commit: CommitResponse = response.json().await?;
        info!(
            commit_id = %commit.id,
            short_id = %commit.short_id,
            "Commit created successfully"
        );

        Ok(commit)
    }

    /// Create a new branch from the default branch.
    pub async fn create_branch(&self, branch_name: &str) -> Result<Branch, GitError> {
        let url = format!(
            "{}/projects/{}/repository/branches",
            self.config.api_url,
            urlencoding::encode(&self.config.project_id)
        );

        let response = self
            .client
            .post(&url)
            .header("PRIVATE-TOKEN", &self.config.token)
            .query(&[
                ("branch", branch_name),
                ("ref", &self.config.default_branch),
            ])
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Branch creation failed");
            return Err(GitError::Api { status, message });
        }

        let branch: Branch = response.json().await?;
        info!(branch = %branch.name, "Branch created");

        Ok(branch)
    }

    /// Create a merge request.
    pub async fn create_merge_request(
        &self,
        source_branch: &str,
        target_branch: &str,
        title: &str,
        description: &str,
    ) -> Result<MergeRequestResponse, GitError> {
        let url = format!(
            "{}/projects/{}/merge_requests",
            self.config.api_url,
            urlencoding::encode(&self.config.project_id)
        );

        let request = CreateMergeRequestRequest {
            source_branch: source_branch.to_string(),
            target_branch: target_branch.to_string(),
            title: title.to_string(),
            description: description.to_string(),
        };

        debug!(
            source = %source_branch,
            target = %target_branch,
            title = %title,
            "Creating merge request"
        );

        let response = self
            .client
            .post(&url)
            .header("PRIVATE-TOKEN", &self.config.token)
            .json(&request)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Merge request creation failed");
            return Err(GitError::MergeRequestFailed(message));
        }

        let mr: MergeRequestResponse = response.json().await?;
        info!(
            iid = mr.iid,
            url = %mr.web_url,
            "Merge request created"
        );

        Ok(mr)
    }

    /// Create a file in the repository (convenience method).
    pub async fn create_file(
        &self,
        branch: &str,
        path: &str,
        content: &str,
        message: &str,
    ) -> Result<CommitResponse, GitError> {
        let actions = vec![FileAction {
            action: "create".to_string(),
            file_path: path.to_string(),
            content: content.to_string(),
        }];

        self.create_commit(branch, message, actions).await
    }

    /// Update a file in the repository.
    pub async fn update_file(
        &self,
        branch: &str,
        path: &str,
        content: &str,
        message: &str,
    ) -> Result<CommitResponse, GitError> {
        let actions = vec![FileAction {
            action: "update".to_string(),
            file_path: path.to_string(),
            content: content.to_string(),
        }];

        self.create_commit(branch, message, actions).await
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_default() {
        let config = GitClientConfig::default();
        assert_eq!(config.api_url, "https://gitlab.com/api/v4");
        assert_eq!(config.default_branch, "main");
        assert_eq!(config.timeout_seconds, 30);
    }

    #[test]
    fn test_file_action_serialization() {
        let action = FileAction {
            action: "create".to_string(),
            file_path: "apis/tenant-acme/weather.yaml".to_string(),
            content: "openapi: 3.0.0".to_string(),
        };

        let json = serde_json::to_string(&action).unwrap();
        assert!(json.contains("create"));
        assert!(json.contains("weather.yaml"));
    }
}
