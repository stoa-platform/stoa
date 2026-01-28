// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
//! stoa_create_api Tool
//!
//! CAB-912: Main MCP tool for creating APIs in the STOA platform.
//!
//! Flow:
//! 1. Validate input arguments
//! 2. Check rate limits (per tenant, per classification)
//! 3. Enforce UAC policies (version check, required policies)
//! 4. Create API in control plane (state=pending_sync)
//! 5. Sync to Git (commit or MR based on classification)
//! 6. Update state (active or pending_review)
//! 7. Rollback on failure

use async_trait::async_trait;
use chrono::Utc;
use serde_json::json;
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{error, info, warn};
use uuid::Uuid;

use super::registry::Tool;
use crate::control_plane::{ControlPlaneClient, CreateApiRequest, UpdateStateRequest};
use crate::git::{ApiDefinition, GitSyncService, SyncError};
use crate::mcp::protocol::{ApiState, CreateApiArgs, CreateApiResult, ToolCallResponse};
use crate::rate_limit::RateLimiter;
use crate::uac::{Classification, EnforcementContext, EnforcementDecision, UacEnforcer};

// =============================================================================
// Tool Implementation
// =============================================================================

/// stoa_create_api tool for creating APIs.
pub struct StoaCreateApiTool {
    /// Rate limiter
    rate_limiter: Arc<RateLimiter>,

    /// UAC enforcer
    uac_enforcer: Arc<UacEnforcer>,

    /// Git sync service
    git_sync: Arc<GitSyncService>,

    /// Control plane client
    control_plane: Arc<ControlPlaneClient>,
}

impl StoaCreateApiTool {
    /// Create a new stoa_create_api tool.
    pub fn new(
        rate_limiter: Arc<RateLimiter>,
        uac_enforcer: Arc<UacEnforcer>,
        git_sync: Arc<GitSyncService>,
        control_plane: Arc<ControlPlaneClient>,
    ) -> Self {
        Self {
            rate_limiter,
            uac_enforcer,
            git_sync,
            control_plane,
        }
    }
}

#[async_trait]
impl Tool for StoaCreateApiTool {
    fn name(&self) -> &str {
        "stoa_create_api"
    }

    fn description(&self) -> &str {
        "Create a new API in the STOA platform. Validates policies, syncs to Git, and registers in the control plane."
    }

    fn input_schema(&self) -> serde_json::Value {
        json!({
            "type": "object",
            "properties": {
                "tenant": {
                    "type": "string",
                    "description": "Tenant identifier (e.g., 'acme')"
                },
                "name": {
                    "type": "string",
                    "description": "API name (e.g., 'weather-api')"
                },
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint path (e.g., '/v1/weather')"
                },
                "classification": {
                    "type": "string",
                    "enum": ["H", "VH", "VVH"],
                    "description": "Security classification: H (standard), VH (sensitive), VVH (critical)"
                },
                "policies": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of policies to apply (e.g., ['rate-limit', 'auth-jwt'])"
                },
                "backend_url": {
                    "type": "string",
                    "description": "Backend URL to proxy to (optional)"
                },
                "description": {
                    "type": "string",
                    "description": "API description (optional)"
                }
            },
            "required": ["tenant", "name", "endpoint", "classification", "policies"]
        })
    }

    async fn execute(
        &self,
        args: HashMap<String, serde_json::Value>,
        ctx: EnforcementContext,
    ) -> ToolCallResponse {
        // Parse arguments
        let parsed_args = match parse_args(&args) {
            Ok(args) => args,
            Err(e) => return ToolCallResponse::error(format!("Invalid arguments: {}", e)),
        };

        // Parse classification
        let classification = match Classification::from_str(&parsed_args.classification) {
            Some(c) => c,
            None => {
                return ToolCallResponse::error(format!(
                    "Invalid classification '{}'. Must be H, VH, or VVH.",
                    parsed_args.classification
                ))
            }
        };

        info!(
            tenant = %parsed_args.tenant,
            name = %parsed_args.name,
            classification = %classification,
            user = %ctx.user_id,
            "Starting API creation"
        );

        // Step 1: Check rate limits
        let rate_result = self.rate_limiter.check(&parsed_args.tenant, classification);
        if !rate_result.allowed {
            warn!(
                tenant = %parsed_args.tenant,
                classification = %classification,
                current = rate_result.current,
                limit = rate_result.limit,
                "Rate limit exceeded"
            );
            return ToolCallResponse::error(format!(
                "Rate limit exceeded for {} classification: {}/{} per hour. Retry after {} seconds.",
                classification, rate_result.current, rate_result.limit, rate_result.retry_after_seconds
            ));
        }

        // Step 2: Enforce UAC policies
        let decision = self
            .uac_enforcer
            .enforce(classification, &parsed_args.policies, &ctx);

        let (target_state, policy_version) = match decision {
            EnforcementDecision::Allow {
                state,
                policy_version,
            } => (state, policy_version),
            EnforcementDecision::Deny {
                reason,
                missing_policies,
                ..
            } => {
                warn!(
                    tenant = %parsed_args.tenant,
                    name = %parsed_args.name,
                    reason = %reason,
                    missing = ?missing_policies,
                    "Policy enforcement denied"
                );
                return ToolCallResponse::error(format!(
                    "Policy violation: {}. Missing policies: {:?}",
                    reason, missing_policies
                ));
            }
        };

        info!(
            tenant = %parsed_args.tenant,
            name = %parsed_args.name,
            target_state = %target_state,
            policy_version = %policy_version,
            "UAC enforcement passed"
        );

        // Step 3: Create API in control plane (state=pending_sync)
        let api_id = Uuid::new_v4().to_string();
        let create_request = CreateApiRequest {
            tenant_id: parsed_args.tenant.clone(),
            name: parsed_args.name.clone(),
            endpoint: parsed_args.endpoint.clone(),
            classification: classification.to_string(),
            policies: parsed_args.policies.clone(),
            backend_url: parsed_args.backend_url.clone(),
            description: parsed_args.description.clone(),
            state: ApiState::PendingSync.to_string(),
            policy_version: policy_version.clone(),
            created_by: ctx.user_id.clone(),
        };

        let created = match self.control_plane.create_api(create_request).await {
            Ok(c) => c,
            Err(e) => {
                error!(error = %e, "Failed to create API in control plane");
                return ToolCallResponse::error(format!(
                    "Failed to create API in control plane: {}",
                    e
                ));
            }
        };

        info!(
            api_id = %created.id,
            "API created in control plane (pending_sync)"
        );

        // Step 4: Sync to Git
        let api_definition = ApiDefinition {
            id: created.id.clone(),
            tenant_id: parsed_args.tenant.clone(),
            name: parsed_args.name.clone(),
            endpoint: parsed_args.endpoint.clone(),
            classification,
            policies: parsed_args.policies.clone(),
            backend_url: parsed_args.backend_url.clone(),
            description: parsed_args.description.clone(),
            state: target_state,
            policy_version: policy_version.clone(),
            created_at: Utc::now(),
            created_by: ctx.user_id.clone(),
        };

        let sync_result = match self.git_sync.sync_api(&api_definition).await {
            Ok(r) => r,
            Err(e) => {
                error!(error = %e, api_id = %created.id, "Git sync failed - rolling back");

                // Rollback: delete from control plane
                if let Err(rollback_err) = self.control_plane.delete_api(&created.id).await {
                    error!(error = %rollback_err, "Rollback failed");
                }

                let error_msg = match e {
                    SyncError::CircuitOpen {
                        failures,
                        recovery_at,
                    } => {
                        format!(
                            "Git service unavailable (circuit breaker open after {} failures). Retry after {:?}.",
                            failures, recovery_at
                        )
                    }
                    SyncError::GitError(ge) => format!("Git error: {}", ge),
                    SyncError::SyncFailed(msg) => format!("Sync failed: {}", msg),
                };

                return ToolCallResponse::error(error_msg);
            }
        };

        info!(
            api_id = %created.id,
            commit_id = ?sync_result.commit_id,
            merge_request = ?sync_result.merge_request_url,
            "Git sync successful"
        );

        // Step 5: Update state in control plane
        let update_request = UpdateStateRequest {
            state: target_state.to_string(),
            reason: Some("Git sync completed".to_string()),
            git_commit_id: sync_result.commit_id.clone(),
            merge_request_url: sync_result.merge_request_url.clone(),
        };

        if let Err(e) = self
            .control_plane
            .update_state(&created.id, update_request)
            .await
        {
            error!(error = %e, "Failed to update state - API created but state may be stale");
            // Don't rollback here - the API exists in Git
        }

        // Build result
        let public_url = if target_state == ApiState::Active {
            Some(format!(
                "{}/{}{}",
                self.git_sync.gateway_url(),
                parsed_args.tenant,
                parsed_args.endpoint
            ))
        } else {
            None
        };

        let result = CreateApiResult {
            success: true,
            api_id: Some(created.id),
            state: target_state,
            policy_version,
            message: match target_state {
                ApiState::Active => format!(
                    "API '{}' created and activated. Available at {}",
                    parsed_args.name,
                    public_url.as_deref().unwrap_or("N/A")
                ),
                ApiState::PendingReview => format!(
                    "API '{}' created and awaiting human review. MR: {}",
                    parsed_args.name,
                    sync_result.merge_request_url.as_deref().unwrap_or("N/A")
                ),
                _ => format!(
                    "API '{}' created with state: {}",
                    parsed_args.name, target_state
                ),
            },
            public_url,
            merge_request_url: sync_result.merge_request_url,
        };

        ToolCallResponse::json(&result).unwrap_or_else(|e| {
            ToolCallResponse::error(format!("Failed to serialize result: {}", e))
        })
    }
}

/// Parse tool arguments from JSON values.
fn parse_args(args: &HashMap<String, serde_json::Value>) -> Result<CreateApiArgs, String> {
    let tenant = args
        .get("tenant")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or("Missing required argument: tenant")?;

    let name = args
        .get("name")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or("Missing required argument: name")?;

    let endpoint = args
        .get("endpoint")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or("Missing required argument: endpoint")?;

    let classification = args
        .get("classification")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or("Missing required argument: classification")?;

    let policies = args
        .get("policies")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let backend_url = args
        .get("backend_url")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let description = args
        .get("description")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    Ok(CreateApiArgs {
        tenant,
        name,
        endpoint,
        classification,
        policies,
        backend_url,
        description,
    })
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_args_success() {
        let mut args = HashMap::new();
        args.insert("tenant".to_string(), json!("acme"));
        args.insert("name".to_string(), json!("weather"));
        args.insert("endpoint".to_string(), json!("/v1/weather"));
        args.insert("classification".to_string(), json!("H"));
        args.insert("policies".to_string(), json!(["rate-limit", "auth-jwt"]));

        let parsed = parse_args(&args).unwrap();
        assert_eq!(parsed.tenant, "acme");
        assert_eq!(parsed.name, "weather");
        assert_eq!(parsed.classification, "H");
        assert_eq!(parsed.policies.len(), 2);
    }

    #[test]
    fn test_parse_args_missing_required() {
        let mut args = HashMap::new();
        args.insert("tenant".to_string(), json!("acme"));
        // Missing name

        let result = parse_args(&args);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("name"));
    }

    // Note: Full tool tests require mock services (GitSync, ControlPlane)
    // Integration tests should be added in tests/ directory
}
