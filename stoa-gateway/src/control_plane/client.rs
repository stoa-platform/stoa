// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! Control Plane API Client
//!
//! CAB-912: HTTP client for interacting with the FastAPI control plane.
//!
//! Operations:
//! - Create API record in database
//! - Update API state
//! - Rollback API creation on Git failure

use reqwest::Client;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tracing::{debug, error, info};

use crate::mcp::protocol::ApiState;
use crate::uac::Classification;

// =============================================================================
// Error Types
// =============================================================================

#[derive(Debug, Error)]
pub enum ControlPlaneError {
    #[error("HTTP request failed: {0}")]
    Http(#[from] reqwest::Error),

    #[error("API error: {status} - {message}")]
    Api { status: u16, message: String },

    #[error("API not found: {id}")]
    NotFound { id: String },

    #[error("API already exists: {name} in tenant {tenant}")]
    AlreadyExists { tenant: String, name: String },

    #[error("Rollback failed: {0}")]
    RollbackFailed(String),
}

// =============================================================================
// API Types
// =============================================================================

/// Request to create an API in the control plane.
#[derive(Debug, Clone, Serialize)]
pub struct CreateApiRequest {
    /// Tenant ID
    pub tenant_id: String,

    /// API name
    pub name: String,

    /// API endpoint
    pub endpoint: String,

    /// Classification
    pub classification: String,

    /// Applied policies
    pub policies: Vec<String>,

    /// Backend URL
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backend_url: Option<String>,

    /// Description
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,

    /// Initial state
    pub state: String,

    /// Policy version used for creation
    pub policy_version: String,

    /// User who created the API
    pub created_by: String,
}

/// Response from creating an API.
#[derive(Debug, Clone, Deserialize)]
pub struct CreateApiResponse {
    /// Created API ID
    pub id: String,

    /// API name
    pub name: String,

    /// Current state
    pub state: String,

    /// Public URL (if active)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub public_url: Option<String>,

    /// Created timestamp
    pub created_at: String,
}

/// Request to update API state.
#[derive(Debug, Clone, Serialize)]
pub struct UpdateStateRequest {
    /// New state
    pub state: String,

    /// Reason for state change
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,

    /// Git commit ID (if applicable)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub git_commit_id: Option<String>,

    /// Merge request URL (if applicable)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub merge_request_url: Option<String>,
}

/// API record from the control plane.
#[derive(Debug, Clone, Deserialize)]
pub struct ApiRecord {
    pub id: String,
    pub tenant_id: String,
    pub name: String,
    pub endpoint: String,
    pub classification: String,
    pub state: String,
    pub policies: Vec<String>,
    pub policy_version: String,
    pub created_at: String,
    pub created_by: String,
}

// =============================================================================
// Client Configuration
// =============================================================================

/// Configuration for control plane client.
#[derive(Debug, Clone)]
pub struct ControlPlaneConfig {
    /// Control plane API URL
    pub api_url: String,

    /// Request timeout in seconds
    pub timeout_seconds: u64,
}

impl Default for ControlPlaneConfig {
    fn default() -> Self {
        Self {
            api_url: "https://api.gostoa.dev".to_string(),
            timeout_seconds: 30,
        }
    }
}

// =============================================================================
// Control Plane Client
// =============================================================================

/// Client for the FastAPI control plane.
pub struct ControlPlaneClient {
    client: Client,
    config: ControlPlaneConfig,
}

impl ControlPlaneClient {
    /// Create a new control plane client.
    pub fn new(config: ControlPlaneConfig) -> Result<Self, ControlPlaneError> {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(config.timeout_seconds))
            .build()?;

        Ok(Self { client, config })
    }

    /// Create an API in the control plane database.
    pub async fn create_api(
        &self,
        request: CreateApiRequest,
    ) -> Result<CreateApiResponse, ControlPlaneError> {
        let url = format!("{}/api/v1/apis", self.config.api_url);

        debug!(
            url = %url,
            tenant = %request.tenant_id,
            name = %request.name,
            "Creating API in control plane"
        );

        let response = self.client.post(&url).json(&request).send().await?;

        if response.status() == reqwest::StatusCode::CONFLICT {
            return Err(ControlPlaneError::AlreadyExists {
                tenant: request.tenant_id,
                name: request.name,
            });
        }

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Control plane API error");
            return Err(ControlPlaneError::Api { status, message });
        }

        let created: CreateApiResponse = response.json().await?;
        info!(
            id = %created.id,
            name = %created.name,
            state = %created.state,
            "API created in control plane"
        );

        Ok(created)
    }

    /// Update API state.
    pub async fn update_state(
        &self,
        api_id: &str,
        request: UpdateStateRequest,
    ) -> Result<ApiRecord, ControlPlaneError> {
        let url = format!("{}/api/v1/apis/{}/state", self.config.api_url, api_id);

        debug!(
            url = %url,
            api_id = %api_id,
            new_state = %request.state,
            "Updating API state"
        );

        let response = self.client.patch(&url).json(&request).send().await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Err(ControlPlaneError::NotFound {
                id: api_id.to_string(),
            });
        }

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "State update failed");
            return Err(ControlPlaneError::Api { status, message });
        }

        let record: ApiRecord = response.json().await?;
        info!(
            id = %record.id,
            state = %record.state,
            "API state updated"
        );

        Ok(record)
    }

    /// Delete an API (rollback).
    pub async fn delete_api(&self, api_id: &str) -> Result<(), ControlPlaneError> {
        let url = format!("{}/api/v1/apis/{}", self.config.api_url, api_id);

        debug!(url = %url, api_id = %api_id, "Deleting API (rollback)");

        let response = self.client.delete(&url).send().await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            // Already deleted, that's fine
            return Ok(());
        }

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            error!(status, message = %message, "Delete failed");
            return Err(ControlPlaneError::RollbackFailed(message));
        }

        info!(api_id = %api_id, "API deleted (rollback successful)");
        Ok(())
    }

    /// Check if an API already exists.
    pub async fn api_exists(&self, tenant_id: &str, name: &str) -> Result<bool, ControlPlaneError> {
        let url = format!(
            "{}/api/v1/tenants/{}/apis/{}",
            self.config.api_url, tenant_id, name
        );

        let response = self.client.head(&url).send().await?;

        Ok(response.status().is_success())
    }

    /// Get an API by ID.
    pub async fn get_api(&self, api_id: &str) -> Result<ApiRecord, ControlPlaneError> {
        let url = format!("{}/api/v1/apis/{}", self.config.api_url, api_id);

        let response = self.client.get(&url).send().await?;

        if response.status() == reqwest::StatusCode::NOT_FOUND {
            return Err(ControlPlaneError::NotFound {
                id: api_id.to_string(),
            });
        }

        if !response.status().is_success() {
            let status = response.status().as_u16();
            let message = response.text().await.unwrap_or_default();
            return Err(ControlPlaneError::Api { status, message });
        }

        Ok(response.json().await?)
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
        let config = ControlPlaneConfig::default();
        assert_eq!(config.api_url, "https://api.gostoa.dev");
        assert_eq!(config.timeout_seconds, 30);
    }

    #[test]
    fn test_create_request_serialization() {
        let request = CreateApiRequest {
            tenant_id: "acme".to_string(),
            name: "weather".to_string(),
            endpoint: "/v1/weather".to_string(),
            classification: "H".to_string(),
            policies: vec!["rate-limit".to_string()],
            backend_url: None,
            description: None,
            state: "pending_sync".to_string(),
            policy_version: "abc123".to_string(),
            created_by: "user@acme.com".to_string(),
        };

        let json = serde_json::to_string(&request).unwrap();
        assert!(json.contains("\"tenant_id\":\"acme\""));
        assert!(json.contains("\"classification\":\"H\""));
    }
}
