//! Git Module
//!
//! CAB-912: GitLab API client and sync service with circuit breaker.
//! CAB-1891: GitHub REST API client (Wave 2 migration).
//!
//! This module provides:
//! - GitLab API client for commits and merge requests (client.rs)
//! - GitHub REST API client for file content and webhooks (github_client.rs)
//! - Circuit breaker for resilience (sync.rs)
//! - Write-through sync for API definitions (sync.rs)

pub mod client;
pub mod github_client;
pub mod sync;

pub use client::{FileAction, GitClient, GitClientConfig, GitError};
pub use github_client::{GitHubClient, GitHubError, RepoInfo, WebhookInfo};
