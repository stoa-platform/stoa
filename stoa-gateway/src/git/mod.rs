// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
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

pub use client::{
    CommitResponse, FileAction, GitClient, GitClientConfig, GitError, MergeRequestResponse,
};
pub use sync::{
    ApiDefinition, CircuitBreaker, CircuitBreakerConfig, CircuitBreakerStats, GitSyncService,
    SyncError, SyncResult,
};
