// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Git Sync with Circuit Breaker
//!
//! CAB-912: Write-through sync to Git with circuit breaker protection.
//!
//! Flow:
//! 1. Check circuit breaker state
//! 2. Attempt Git operation
//! 3. On success: reset failure count
//! 4. On failure: increment failure count, open circuit if threshold reached
//!
//! Circuit breaker: 3 failures → 30s cooldown

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::RwLock;
use thiserror::Error;
use tracing::{error, info, warn};

use super::client::{CommitResponse, FileAction, GitClient, GitError, MergeRequestResponse};
use crate::mcp::protocol::ApiState;
use crate::uac::Classification;

// =============================================================================
// Circuit Breaker Errors
// =============================================================================

#[derive(Debug, Error)]
pub enum SyncError {
    #[error("Circuit breaker is open - Git unavailable")]
    CircuitOpen {
        failures: u32,
        recovery_at: DateTime<Utc>,
    },

    #[error("Git operation failed: {0}")]
    GitError(#[from] GitError),

    #[error("Sync failed: {0}")]
    SyncFailed(String),
}

// =============================================================================
// Circuit Breaker State
// =============================================================================

/// Circuit breaker configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitBreakerConfig {
    /// Number of failures before opening the circuit
    pub failure_threshold: u32,

    /// Time to wait before attempting recovery (seconds)
    pub recovery_timeout_seconds: u64,
}

impl Default for CircuitBreakerConfig {
    fn default() -> Self {
        Self {
            failure_threshold: 3,
            recovery_timeout_seconds: 30,
        }
    }
}

/// Circuit breaker state.
#[derive(Debug)]
pub struct CircuitBreaker {
    /// Consecutive failure count
    failure_count: AtomicU32,

    /// Whether the circuit is open
    is_open: AtomicBool,

    /// When the circuit was opened
    opened_at: RwLock<Option<DateTime<Utc>>>,

    /// Configuration
    config: CircuitBreakerConfig,
}

impl CircuitBreaker {
    /// Create a new circuit breaker.
    pub fn new(config: CircuitBreakerConfig) -> Self {
        Self {
            failure_count: AtomicU32::new(0),
            is_open: AtomicBool::new(false),
            opened_at: RwLock::new(None),
            config,
        }
    }

    /// Check if the circuit is open (requests should be rejected).
    pub fn is_open(&self) -> bool {
        if !self.is_open.load(Ordering::Relaxed) {
            return false;
        }

        // Check if recovery timeout has passed
        let opened_at = self.opened_at.read().unwrap();
        if let Some(opened) = *opened_at {
            let recovery_at =
                opened + Duration::seconds(self.config.recovery_timeout_seconds as i64);
            if Utc::now() >= recovery_at {
                // Half-open: allow one request through to test
                return false;
            }
        }

        true
    }

    /// Get the time when recovery will be attempted.
    pub fn recovery_at(&self) -> Option<DateTime<Utc>> {
        let opened_at = self.opened_at.read().unwrap();
        opened_at.map(|t| t + Duration::seconds(self.config.recovery_timeout_seconds as i64))
    }

    /// Record a successful operation.
    pub fn record_success(&self) {
        self.failure_count.store(0, Ordering::Relaxed);
        self.is_open.store(false, Ordering::Relaxed);
        *self.opened_at.write().unwrap() = None;

        info!("Circuit breaker: success recorded, circuit closed");
    }

    /// Record a failed operation.
    pub fn record_failure(&self) {
        let failures = self.failure_count.fetch_add(1, Ordering::Relaxed) + 1;

        if failures >= self.config.failure_threshold {
            self.is_open.store(true, Ordering::Relaxed);
            *self.opened_at.write().unwrap() = Some(Utc::now());

            error!(
                failures,
                threshold = self.config.failure_threshold,
                recovery_seconds = self.config.recovery_timeout_seconds,
                "Circuit breaker: OPENED"
            );
        } else {
            warn!(
                failures,
                threshold = self.config.failure_threshold,
                "Circuit breaker: failure recorded"
            );
        }
    }

    /// Get current failure count.
    pub fn failure_count(&self) -> u32 {
        self.failure_count.load(Ordering::Relaxed)
    }

    /// Get circuit breaker stats.
    pub fn stats(&self) -> CircuitBreakerStats {
        CircuitBreakerStats {
            is_open: self.is_open.load(Ordering::Relaxed),
            failure_count: self.failure_count.load(Ordering::Relaxed),
            failure_threshold: self.config.failure_threshold,
            recovery_at: self.recovery_at(),
        }
    }
}

impl Default for CircuitBreaker {
    fn default() -> Self {
        Self::new(CircuitBreakerConfig::default())
    }
}

/// Circuit breaker statistics.
#[derive(Debug, Clone, Serialize)]
pub struct CircuitBreakerStats {
    pub is_open: bool,
    pub failure_count: u32,
    pub failure_threshold: u32,
    pub recovery_at: Option<DateTime<Utc>>,
}

// =============================================================================
// API Definition for Git Storage
// =============================================================================

/// API definition to be stored in Git.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiDefinition {
    /// API ID (UUID)
    pub id: String,

    /// Tenant ID
    pub tenant_id: String,

    /// API name
    pub name: String,

    /// API endpoint path
    pub endpoint: String,

    /// Classification (H/VH/VVH)
    pub classification: Classification,

    /// Applied policies
    pub policies: Vec<String>,

    /// Backend URL
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backend_url: Option<String>,

    /// Description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// Current state
    pub state: ApiState,

    /// Policy version used
    pub policy_version: String,

    /// Created at timestamp
    pub created_at: DateTime<Utc>,

    /// Created by user
    pub created_by: String,
}

impl ApiDefinition {
    /// Generate the Git file path for this API.
    pub fn git_path(&self) -> String {
        format!("apis/{}/{}.yaml", self.tenant_id, self.name)
    }

    /// Generate YAML content for Git.
    pub fn to_yaml(&self) -> Result<String, serde_yaml::Error> {
        // We don't have serde_yaml, so use a simple format
        Ok(format!(
            r#"# STOA API Definition
# Auto-generated by MCP Gateway
# DO NOT EDIT MANUALLY

apiVersion: gostoa.dev/v1alpha1
kind: Api
metadata:
  name: {}
  tenant: {}
  id: {}
spec:
  endpoint: {}
  classification: {}
  policies: {}
  backend_url: {}
  state: {}
  policy_version: {}
  created_at: {}
  created_by: {}
"#,
            self.name,
            self.tenant_id,
            self.id,
            self.endpoint,
            self.classification,
            serde_json::to_string(&self.policies).unwrap_or_default(),
            self.backend_url.as_deref().unwrap_or("null"),
            self.state,
            self.policy_version,
            self.created_at.to_rfc3339(),
            self.created_by
        ))
    }
}

// =============================================================================
// Git Sync Service
// =============================================================================

/// Result of a sync operation.
#[derive(Debug, Clone, Serialize)]
pub struct SyncResult {
    /// Whether sync was successful
    pub success: bool,

    /// Commit ID (if successful)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub commit_id: Option<String>,

    /// Merge request URL (for VH/VVH APIs)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub merge_request_url: Option<String>,

    /// Error message (if failed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// Git sync service with circuit breaker.
pub struct GitSyncService {
    client: GitClient,
    circuit_breaker: CircuitBreaker,
    gateway_url: String,
}

impl GitSyncService {
    /// Create a new sync service.
    pub fn new(client: GitClient, gateway_url: String) -> Self {
        Self {
            client,
            circuit_breaker: CircuitBreaker::default(),
            gateway_url,
        }
    }

    /// Create with custom circuit breaker config.
    pub fn with_circuit_breaker(mut self, config: CircuitBreakerConfig) -> Self {
        self.circuit_breaker = CircuitBreaker::new(config);
        self
    }

    /// Sync an API definition to Git.
    ///
    /// For H APIs: Direct commit to main branch
    /// For VH/VVH APIs: Create branch and merge request
    pub async fn sync_api(&self, api: &ApiDefinition) -> Result<SyncResult, SyncError> {
        // Check circuit breaker
        if self.circuit_breaker.is_open() {
            let stats = self.circuit_breaker.stats();
            return Err(SyncError::CircuitOpen {
                failures: stats.failure_count,
                recovery_at: stats.recovery_at.unwrap_or_else(Utc::now),
            });
        }

        let result = self.do_sync(api).await;

        match &result {
            Ok(_) => {
                self.circuit_breaker.record_success();
            }
            Err(_) => {
                self.circuit_breaker.record_failure();
            }
        }

        result
    }

    /// Internal sync implementation.
    async fn do_sync(&self, api: &ApiDefinition) -> Result<SyncResult, SyncError> {
        let content = api
            .to_yaml()
            .map_err(|e| SyncError::SyncFailed(format!("Failed to serialize API: {}", e)))?;

        let path = api.git_path();
        let message = format!(
            "[STOA] Add API: {} (tenant: {}, classification: {})\n\nCreated by: {}\nPolicy version: {}",
            api.name,
            api.tenant_id,
            api.classification,
            api.created_by,
            api.policy_version
        );

        if api.classification.auto_approve() {
            // H classification: direct commit to main
            info!(
                api = %api.name,
                tenant = %api.tenant_id,
                "Syncing H API directly to main"
            );

            let commit = self
                .client
                .create_file("main", &path, &content, &message)
                .await?;

            Ok(SyncResult {
                success: true,
                commit_id: Some(commit.id),
                merge_request_url: None,
                error: None,
            })
        } else {
            // VH/VVH: create branch and merge request
            let branch_name = format!("api/{}/{}", api.tenant_id, api.name);

            info!(
                api = %api.name,
                tenant = %api.tenant_id,
                classification = %api.classification,
                branch = %branch_name,
                "Creating branch for VH/VVH API"
            );

            // Create branch
            self.client.create_branch(&branch_name).await?;

            // Commit to branch
            let commit = self
                .client
                .create_file(&branch_name, &path, &content, &message)
                .await?;

            // Create merge request
            let mr_title = format!(
                "[{}] New API: {} ({})",
                api.classification, api.name, api.tenant_id
            );
            let mr_description = format!(
                r#"## New API Request

**API Name:** {}
**Tenant:** {}
**Classification:** {} (requires human review)
**Endpoint:** {}

### Policies Applied
{}

### Created By
- User: {}
- Policy Version: {}
- Timestamp: {}

---
*This merge request was auto-generated by STOA MCP Gateway.*
"#,
                api.name,
                api.tenant_id,
                api.classification,
                api.endpoint,
                api.policies.join("\n- "),
                api.created_by,
                api.policy_version,
                api.created_at.to_rfc3339()
            );

            let mr = self
                .client
                .create_merge_request(&branch_name, "main", &mr_title, &mr_description)
                .await?;

            Ok(SyncResult {
                success: true,
                commit_id: Some(commit.id),
                merge_request_url: Some(mr.web_url),
                error: None,
            })
        }
    }

    /// Get the current Git version.
    pub async fn get_version(&self) -> Result<String, SyncError> {
        if self.circuit_breaker.is_open() {
            let stats = self.circuit_breaker.stats();
            return Err(SyncError::CircuitOpen {
                failures: stats.failure_count,
                recovery_at: stats.recovery_at.unwrap_or_else(Utc::now),
            });
        }

        let result = self.client.get_current_version().await;

        match &result {
            Ok(_) => self.circuit_breaker.record_success(),
            Err(_) => self.circuit_breaker.record_failure(),
        }

        Ok(result?)
    }

    /// Get circuit breaker stats.
    pub fn circuit_breaker_stats(&self) -> CircuitBreakerStats {
        self.circuit_breaker.stats()
    }

    /// Get the gateway public URL.
    pub fn gateway_url(&self) -> &str {
        &self.gateway_url
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_circuit_breaker_closed_initially() {
        let cb = CircuitBreaker::default();
        assert!(!cb.is_open());
        assert_eq!(cb.failure_count(), 0);
    }

    #[test]
    fn test_circuit_breaker_opens_after_threshold() {
        let cb = CircuitBreaker::new(CircuitBreakerConfig {
            failure_threshold: 3,
            recovery_timeout_seconds: 30,
        });

        cb.record_failure();
        assert!(!cb.is_open());
        assert_eq!(cb.failure_count(), 1);

        cb.record_failure();
        assert!(!cb.is_open());
        assert_eq!(cb.failure_count(), 2);

        cb.record_failure();
        assert!(cb.is_open());
        assert_eq!(cb.failure_count(), 3);
    }

    #[test]
    fn test_circuit_breaker_resets_on_success() {
        let cb = CircuitBreaker::new(CircuitBreakerConfig {
            failure_threshold: 3,
            recovery_timeout_seconds: 30,
        });

        cb.record_failure();
        cb.record_failure();
        assert_eq!(cb.failure_count(), 2);

        cb.record_success();
        assert_eq!(cb.failure_count(), 0);
        assert!(!cb.is_open());
    }

    #[test]
    fn test_api_definition_git_path() {
        let api = ApiDefinition {
            id: "123".to_string(),
            tenant_id: "acme".to_string(),
            name: "weather".to_string(),
            endpoint: "/v1/weather".to_string(),
            classification: Classification::H,
            policies: vec!["rate-limit".to_string()],
            backend_url: None,
            description: None,
            state: ApiState::Active,
            policy_version: "abc123".to_string(),
            created_at: Utc::now(),
            created_by: "user@acme.com".to_string(),
        };

        assert_eq!(api.git_path(), "apis/acme/weather.yaml");
    }

    #[test]
    fn test_api_definition_to_yaml() {
        let api = ApiDefinition {
            id: "123".to_string(),
            tenant_id: "acme".to_string(),
            name: "weather".to_string(),
            endpoint: "/v1/weather".to_string(),
            classification: Classification::H,
            policies: vec!["rate-limit".to_string()],
            backend_url: Some("https://backend.example.com".to_string()),
            description: None,
            state: ApiState::Active,
            policy_version: "abc123".to_string(),
            created_at: Utc::now(),
            created_by: "user@acme.com".to_string(),
        };

        let yaml = api.to_yaml().unwrap();
        assert!(yaml.contains("name: weather"));
        assert!(yaml.contains("tenant: acme"));
        assert!(yaml.contains("classification: H"));
    }
}
