//! Git Module
//!
//! CAB-912: Git API client and sync service with circuit breaker.
//!
//! This module provides:
//! - GitLab API client for commits and merge requests
//! - Circuit breaker for resilience
//! - Write-through sync for API definitions

pub mod client;
pub mod sync;

pub use client::{FileAction, GitClient, GitClientConfig, GitError};
