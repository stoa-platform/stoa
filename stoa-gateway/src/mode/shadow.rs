//! Shadow Mode Implementation
//!
//! Passive traffic capture and analysis mode that auto-generates
//! UAC contracts from observed API traffic patterns.
//!
//! # STOA Killer Feature
//!
//! No competitor offers automatic contract generation from traffic.
//! This turns any existing API estate into an MCP-ready catalog
//! without manual onboarding.
//!
//! # Architecture
//!
//! ```text
//!                                    ┌──────────────────┐
//!    Production Traffic              │   Main Gateway   │
//!         ────────────────────────▶ │  (Kong/Envoy)   │
//!                │                   │                  │
//!                │ mirror            │                  │
//!                ▼                   └──────────────────┘
//!    ┌──────────────────┐
//!    │   STOA Shadow    │
//!    │                  │
//!    │ ┌──────────────┐ │
//!    │ │   Capture    │ │  ← Parse HTTP requests/responses
//!    │ └──────┬───────┘ │
//!    │        ▼         │
//!    │ ┌──────────────┐ │
//!    │ │   Analyze    │ │  ← Detect patterns, schemas
//!    │ └──────┬───────┘ │
//!    │        ▼         │
//!    │ ┌──────────────┐ │
//!    │ │  Generate    │ │  ← Create UAC YAML + MCP tools
//!    │ └──────┬───────┘ │
//!    │        ▼         │
//!    │ ┌──────────────┐ │
//!    │ │ GitLab MR    │ │  ← Submit for human review
//!    │ └──────────────┘ │
//!    └──────────────────┘
//! ```
//!
//! # Security
//!
//! - All generated contracts go through MR review (never auto-applied)
//! - Sensitive data (tokens, passwords) is automatically redacted
//! - PII detection flags potential privacy concerns

use super::ShadowSettings;
use crate::git::{FileAction, GitClient, GitError};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, instrument, warn};

/// Captured HTTP transaction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapturedTransaction {
    /// Unique transaction ID
    pub id: String,

    /// Capture timestamp
    pub timestamp: chrono::DateTime<chrono::Utc>,

    /// Request data
    pub request: CapturedRequest,

    /// Response data
    pub response: CapturedResponse,

    /// Latency in milliseconds
    pub latency_ms: u64,

    /// Source (envoy tap, port mirror, etc.)
    pub source: String,
}

/// Captured HTTP request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapturedRequest {
    /// HTTP method
    pub method: String,

    /// Request path
    pub path: String,

    /// Query parameters
    #[serde(default)]
    pub query_params: HashMap<String, String>,

    /// Request headers (sanitized)
    #[serde(default)]
    pub headers: HashMap<String, String>,

    /// Content type
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content_type: Option<String>,

    /// Request body (truncated for large payloads)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub body: Option<serde_json::Value>,

    /// Body size in bytes
    pub body_size: usize,
}

/// Captured HTTP response
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapturedResponse {
    /// HTTP status code
    pub status_code: u16,

    /// Response headers (sanitized)
    #[serde(default)]
    pub headers: HashMap<String, String>,

    /// Content type
    #[serde(skip_serializing_if = "Option::is_none")]
    pub content_type: Option<String>,

    /// Response body (truncated for large payloads)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub body: Option<serde_json::Value>,

    /// Body size in bytes
    pub body_size: usize,
}

/// Endpoint pattern detected from traffic
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EndpointPattern {
    /// HTTP method
    pub method: String,

    /// Path pattern (with parameter placeholders)
    /// e.g., /api/v1/users/{id}
    pub path_pattern: String,

    /// Query parameter patterns
    pub query_params: Vec<ParamPattern>,

    /// Request body schema (inferred)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_schema: Option<serde_json::Value>,

    /// Response schemas by status code
    pub response_schemas: HashMap<u16, serde_json::Value>,

    /// Observed content types
    pub content_types: Vec<String>,

    /// Sample count
    pub sample_count: u64,

    /// Average latency
    pub avg_latency_ms: u64,

    /// p95 latency
    pub p95_latency_ms: u64,

    /// Error rate (4xx + 5xx / total)
    pub error_rate: f64,

    /// Detected rate limit (if any)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detected_rate_limit: Option<RateLimitPattern>,

    /// Authentication type detected
    #[serde(skip_serializing_if = "Option::is_none")]
    pub auth_type: Option<String>,
}

/// Parameter pattern
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamPattern {
    /// Parameter name
    pub name: String,

    /// Inferred type (string, integer, boolean, etc.)
    pub param_type: String,

    /// Is required (seen in all requests)
    pub required: bool,

    /// Example values (up to 5)
    pub examples: Vec<String>,

    /// Description (if detected from docs)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

/// Rate limit pattern detected from traffic
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RateLimitPattern {
    /// Requests per window
    pub limit: u64,

    /// Window size in seconds
    pub window_secs: u64,

    /// Confidence (0.0 - 1.0)
    pub confidence: f64,
}

/// Generated UAC contract
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneratedUac {
    /// API identifier
    pub api_id: String,

    /// API name
    pub api_name: String,

    /// API version
    pub version: String,

    /// Base URL
    pub base_url: String,

    /// Description
    pub description: String,

    /// Endpoints
    pub endpoints: Vec<UacEndpoint>,

    /// Authentication configuration
    pub auth: UacAuth,

    /// Rate limits
    pub rate_limits: Vec<UacRateLimit>,

    /// Generation metadata
    pub metadata: UacMetadata,
}

/// UAC endpoint definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacEndpoint {
    /// Path
    pub path: String,

    /// Method
    pub method: String,

    /// Operation ID
    pub operation_id: String,

    /// Description
    pub description: String,

    /// Request schema
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_schema: Option<serde_json::Value>,

    /// Response schema
    #[serde(skip_serializing_if = "Option::is_none")]
    pub response_schema: Option<serde_json::Value>,

    /// Required scopes
    pub scopes: Vec<String>,
}

/// UAC authentication configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacAuth {
    /// Auth type (bearer, api_key, oauth2, etc.)
    #[serde(rename = "type")]
    pub auth_type: String,

    /// Header name for API key
    #[serde(skip_serializing_if = "Option::is_none")]
    pub header_name: Option<String>,

    /// OAuth2 scopes
    #[serde(default)]
    pub scopes: Vec<String>,
}

/// UAC rate limit configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacRateLimit {
    /// Endpoint pattern (or "*" for all)
    pub endpoint: String,

    /// Requests per window
    pub limit: u64,

    /// Window size
    pub window: String,
}

/// UAC generation metadata
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UacMetadata {
    /// Generation timestamp
    pub generated_at: chrono::DateTime<chrono::Utc>,

    /// Analysis window start
    pub analysis_start: chrono::DateTime<chrono::Utc>,

    /// Analysis window end
    pub analysis_end: chrono::DateTime<chrono::Utc>,

    /// Total transactions analyzed
    pub transactions_analyzed: u64,

    /// Unique endpoints detected
    pub endpoints_detected: u64,

    /// Generator version
    pub generator_version: String,

    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,
}

/// Request to submit a UAC to Git as a merge request
#[derive(Debug, Deserialize)]
pub struct SubmitUacRequest {
    /// Name of the API being analyzed
    pub api_name: String,
    /// Base URL of the API
    pub base_url: String,
    /// Pre-generated UAC YAML (if None, generate from captured patterns)
    pub uac_yaml: Option<String>,
    /// Tenant identifier
    pub tenant_id: String,
}

/// Result of submitting a UAC to Git
#[derive(Debug, Serialize)]
pub struct SubmitUacResult {
    /// Whether the submission succeeded
    pub success: bool,
    /// Commit ID (if successful)
    pub commit_id: Option<String>,
    /// Merge request URL (if successful)
    pub merge_request_url: Option<String>,
    /// Branch name used
    pub branch_name: String,
}

/// Shadow service state
pub struct ShadowService {
    /// Configuration
    settings: ShadowSettings,

    /// Captured transactions (in-memory buffer)
    transactions: Arc<RwLock<Vec<CapturedTransaction>>>,

    /// Detected patterns
    patterns: Arc<RwLock<HashMap<String, EndpointPattern>>>,

    /// Generated UACs
    generated_uacs: Arc<RwLock<Vec<GeneratedUac>>>,

    /// Git client for MR creation (None if GitLab not configured)
    git_client: Option<Arc<GitClient>>,
}

impl ShadowService {
    /// Create a new shadow service
    pub fn new(settings: ShadowSettings) -> Self {
        Self {
            settings,
            transactions: Arc::new(RwLock::new(Vec::new())),
            patterns: Arc::new(RwLock::new(HashMap::new())),
            generated_uacs: Arc::new(RwLock::new(Vec::new())),
            git_client: None,
        }
    }

    /// Create a new shadow service with a Git client for MR creation
    pub fn with_git_client(settings: ShadowSettings, git_client: Arc<GitClient>) -> Self {
        Self {
            settings,
            transactions: Arc::new(RwLock::new(Vec::new())),
            patterns: Arc::new(RwLock::new(HashMap::new())),
            generated_uacs: Arc::new(RwLock::new(Vec::new())),
            git_client: Some(git_client),
        }
    }

    /// Capture a transaction
    #[instrument(skip(self, transaction))]
    pub async fn capture(&self, transaction: CapturedTransaction) {
        debug!(
            id = %transaction.id,
            method = %transaction.request.method,
            path = %transaction.request.path,
            status = transaction.response.status_code,
            "Captured transaction"
        );

        let mut transactions = self.transactions.write().await;
        transactions.push(transaction);

        // Trigger analysis if threshold reached
        if transactions.len() as u64 >= self.settings.min_requests_for_uac {
            drop(transactions); // Release lock before analysis
            self.trigger_analysis().await;
        }
    }

    /// Trigger pattern analysis
    async fn trigger_analysis(&self) {
        info!("Triggering traffic pattern analysis");

        // Clone transactions for analysis
        let transactions = {
            let guard = self.transactions.read().await;
            guard.clone()
        };

        // Analyze patterns
        let patterns = self.analyze_patterns(&transactions).await;

        // Store patterns
        {
            let mut guard = self.patterns.write().await;
            for (key, pattern) in patterns {
                guard.insert(key, pattern);
            }
        }

        info!(
            patterns = self.patterns.read().await.len(),
            "Pattern analysis complete"
        );
    }

    /// Analyze traffic patterns
    async fn analyze_patterns(
        &self,
        transactions: &[CapturedTransaction],
    ) -> HashMap<String, EndpointPattern> {
        let mut patterns: HashMap<String, Vec<&CapturedTransaction>> = HashMap::new();

        // Group by normalized path
        for tx in transactions {
            let key = self.normalize_path(&tx.request.method, &tx.request.path);
            patterns.entry(key).or_default().push(tx);
        }

        // Convert to endpoint patterns
        let mut result = HashMap::new();
        for (key, txs) in patterns {
            if let Some(pattern) = self.build_endpoint_pattern(&key, &txs) {
                result.insert(key, pattern);
            }
        }

        result
    }

    /// Normalize path (replace IDs with placeholders)
    fn normalize_path(&self, method: &str, path: &str) -> String {
        // Simple heuristic: replace numeric segments with {id}
        let normalized: String = path
            .split('/')
            .map(|segment| {
                if segment.parse::<i64>().is_ok() {
                    "{id}".to_string()
                } else if uuid::Uuid::parse_str(segment).is_ok() {
                    "{uuid}".to_string()
                } else {
                    segment.to_string()
                }
            })
            .collect::<Vec<_>>()
            .join("/");

        format!("{} {}", method, normalized)
    }

    /// Build endpoint pattern from transactions
    fn build_endpoint_pattern(
        &self,
        key: &str,
        transactions: &[&CapturedTransaction],
    ) -> Option<EndpointPattern> {
        if transactions.is_empty() {
            return None;
        }

        let parts: Vec<&str> = key.splitn(2, ' ').collect();
        if parts.len() != 2 {
            return None;
        }

        let method = parts[0].to_string();
        let path_pattern = parts[1].to_string();

        // Calculate latency stats
        let mut latencies: Vec<u64> = transactions.iter().map(|t| t.latency_ms).collect();
        latencies.sort();

        let avg_latency = latencies.iter().sum::<u64>() / latencies.len() as u64;
        let p95_latency = latencies
            .get((latencies.len() as f64 * 0.95) as usize)
            .copied()
            .unwrap_or(0);

        // Calculate error rate
        let errors = transactions
            .iter()
            .filter(|t| t.response.status_code >= 400)
            .count();
        let error_rate = errors as f64 / transactions.len() as f64;

        // Detect auth type
        let auth_type = transactions.iter().find_map(|t| {
            if t.request.headers.contains_key("authorization") {
                let auth = t.request.headers.get("authorization")?;
                if auth.to_lowercase().starts_with("bearer") {
                    Some("bearer".to_string())
                } else if auth.to_lowercase().starts_with("basic") {
                    Some("basic".to_string())
                } else {
                    Some("unknown".to_string())
                }
            } else if t.request.headers.contains_key("x-api-key") {
                Some("api_key".to_string())
            } else {
                None
            }
        });

        // Collect content types
        let content_types: Vec<String> = transactions
            .iter()
            .filter_map(|t| t.request.content_type.clone())
            .collect::<std::collections::HashSet<_>>()
            .into_iter()
            .collect();

        // Build response schemas by status code
        let mut response_schemas: HashMap<u16, serde_json::Value> = HashMap::new();
        for tx in transactions {
            if let Some(body) = &tx.response.body {
                response_schemas
                    .entry(tx.response.status_code)
                    .or_insert_with(|| self.infer_schema(body));
            }
        }

        Some(EndpointPattern {
            method,
            path_pattern,
            query_params: Vec::new(), // TODO: Extract query param patterns
            request_schema: transactions
                .iter()
                .find_map(|t| t.request.body.as_ref())
                .map(|b| self.infer_schema(b)),
            response_schemas,
            content_types,
            sample_count: transactions.len() as u64,
            avg_latency_ms: avg_latency,
            p95_latency_ms: p95_latency,
            error_rate,
            detected_rate_limit: None, // TODO: Detect rate limits
            auth_type,
        })
    }

    /// Infer JSON schema from a value
    fn infer_schema(&self, value: &serde_json::Value) -> serde_json::Value {
        match value {
            serde_json::Value::Object(obj) => {
                let mut properties = serde_json::Map::new();
                for (key, val) in obj {
                    properties.insert(key.clone(), self.infer_schema(val));
                }
                serde_json::json!({
                    "type": "object",
                    "properties": properties
                })
            }
            serde_json::Value::Array(arr) => {
                let items = arr.first().map(|v| self.infer_schema(v));
                serde_json::json!({
                    "type": "array",
                    "items": items
                })
            }
            serde_json::Value::String(_) => serde_json::json!({"type": "string"}),
            serde_json::Value::Number(n) => {
                if n.is_i64() {
                    serde_json::json!({"type": "integer"})
                } else {
                    serde_json::json!({"type": "number"})
                }
            }
            serde_json::Value::Bool(_) => serde_json::json!({"type": "boolean"}),
            serde_json::Value::Null => serde_json::json!({"type": "null"}),
        }
    }

    /// Generate UAC contract from patterns
    #[instrument(skip(self))]
    pub async fn generate_uac(&self, api_name: &str, base_url: &str) -> Option<GeneratedUac> {
        let patterns = self.patterns.read().await;
        if patterns.is_empty() {
            warn!("No patterns to generate UAC from");
            return None;
        }

        let now = chrono::Utc::now();
        let endpoints: Vec<UacEndpoint> = patterns
            .values()
            .map(|p| UacEndpoint {
                path: p.path_pattern.clone(),
                method: p.method.clone(),
                operation_id: self.generate_operation_id(&p.method, &p.path_pattern),
                description: format!("{} {} endpoint", p.method, p.path_pattern),
                request_schema: p.request_schema.clone(),
                response_schema: p.response_schemas.get(&200).cloned(),
                scopes: vec!["stoa:read".to_string()], // Default scope
            })
            .collect();

        let uac = GeneratedUac {
            api_id: format!("{}-api", api_name.to_lowercase().replace(' ', "-")),
            api_name: api_name.to_string(),
            version: "v1".to_string(),
            base_url: base_url.to_string(),
            description: format!("Auto-generated UAC for {}", api_name),
            endpoints: endpoints.clone(),
            auth: UacAuth {
                auth_type: patterns
                    .values()
                    .find_map(|p| p.auth_type.clone())
                    .unwrap_or_else(|| "bearer".to_string()),
                header_name: None,
                scopes: vec!["stoa:read".to_string(), "stoa:write".to_string()],
            },
            rate_limits: vec![UacRateLimit {
                endpoint: "*".to_string(),
                limit: 1000,
                window: "1m".to_string(),
            }],
            metadata: UacMetadata {
                generated_at: now,
                analysis_start: now
                    - chrono::Duration::hours(self.settings.analysis_window_hours as i64),
                analysis_end: now,
                transactions_analyzed: self.transactions.read().await.len() as u64,
                endpoints_detected: endpoints.len() as u64,
                generator_version: env!("CARGO_PKG_VERSION").to_string(),
                confidence: 0.8, // TODO: Calculate based on sample size
            },
        };

        info!(
            api_name = %api_name,
            endpoints = uac.endpoints.len(),
            "Generated UAC contract"
        );

        // Store generated UAC
        self.generated_uacs.write().await.push(uac.clone());

        Some(uac)
    }

    /// Generate operation ID from method and path
    fn generate_operation_id(&self, method: &str, path: &str) -> String {
        let path_parts: Vec<&str> = path
            .split('/')
            .filter(|s| !s.is_empty() && !s.starts_with('{'))
            .collect();

        let method_upper = method.to_uppercase();
        let action = match method_upper.as_str() {
            "GET" => "get".to_string(),
            "POST" => "create".to_string(),
            "PUT" => "update".to_string(),
            "PATCH" => "patch".to_string(),
            "DELETE" => "delete".to_string(),
            _ => method.to_lowercase(),
        };

        if path_parts.is_empty() {
            action
        } else {
            format!("{}_{}", action, path_parts.join("_"))
        }
    }

    /// Export UAC as YAML
    pub async fn export_uac_yaml(&self, uac: &GeneratedUac) -> String {
        serde_yaml::to_string(uac).unwrap_or_default()
    }

    /// Submit a generated UAC to Git as a merge request (CAB-1109 Phase 5)
    #[instrument(skip(self, request))]
    pub async fn submit_uac_to_git(
        &self,
        request: SubmitUacRequest,
    ) -> Result<SubmitUacResult, GitError> {
        let git_client = self.git_client.as_ref().ok_or_else(|| {
            GitError::CommitFailed(
                "GitLab not configured (set STOA_GITLAB_API_URL, STOA_GITLAB_TOKEN, STOA_GITLAB_PROJECT_ID)".to_string(),
            )
        })?;

        let uac_yaml = if let Some(yaml) = request.uac_yaml {
            yaml
        } else {
            match self
                .generate_uac(&request.api_name, &request.base_url)
                .await
            {
                Some(uac) => self.export_uac_yaml(&uac).await,
                None => {
                    return Err(GitError::CommitFailed(
                        "Insufficient traffic data to generate UAC".to_string(),
                    ));
                }
            }
        };

        let timestamp = chrono::Utc::now().format("%Y%m%d-%H%M%S");
        let api_slug = request.api_name.to_lowercase().replace([' ', '/'], "-");
        let branch_name = format!(
            "shadow/uac/{}/{}-{}",
            request.tenant_id, api_slug, timestamp
        );
        let file_path = format!("uac/{}/{}.yaml", request.tenant_id, api_slug);

        info!(
            branch = %branch_name,
            file = %file_path,
            api = %request.api_name,
            "Submitting UAC to Git"
        );

        git_client.create_branch(&branch_name).await?;

        let commit_message = format!("[Shadow] Generated UAC for {}", request.api_name);
        let actions = vec![FileAction {
            action: "create".to_string(),
            file_path: file_path.clone(),
            content: uac_yaml,
        }];
        let commit = git_client
            .create_commit(&branch_name, &commit_message, actions)
            .await?;

        let mr_title = format!("[Shadow] UAC: {} ({})", request.api_name, request.tenant_id);
        let mr_description = format!(
            "## Shadow-Generated UAC\n\n\
             **API**: {}\n\
             **Tenant**: {}\n\
             **Base URL**: {}\n\
             **File**: `{}`\n\n\
             > **Warning**: This UAC was auto-generated by STOA Shadow mode \
             from observed traffic patterns. It requires human review before merging.\n\n\
             - [ ] Verify endpoint definitions\n\
             - [ ] Verify authentication requirements\n\
             - [ ] Verify rate limit settings\n\
             - [ ] Verify schema accuracy",
            request.api_name, request.tenant_id, request.base_url, file_path
        );

        let mr = git_client
            .create_merge_request(&branch_name, "main", &mr_title, &mr_description)
            .await?;

        info!(
            mr_url = %mr.web_url,
            commit_id = %commit.id,
            "UAC merge request created"
        );

        Ok(SubmitUacResult {
            success: true,
            commit_id: Some(commit.id),
            merge_request_url: Some(mr.web_url),
            branch_name,
        })
    }

    /// Get analysis status
    pub async fn status(&self) -> ShadowStatus {
        let transactions = self.transactions.read().await.len();
        let patterns = self.patterns.read().await.len();
        let uacs = self.generated_uacs.read().await.len();

        ShadowStatus {
            transactions_captured: transactions,
            patterns_detected: patterns,
            uacs_generated: uacs,
            min_requests_threshold: self.settings.min_requests_for_uac,
            ready_for_generation: transactions as u64 >= self.settings.min_requests_for_uac,
        }
    }
}

/// Shadow service status
#[derive(Debug, Serialize)]
pub struct ShadowStatus {
    /// Number of transactions captured
    pub transactions_captured: usize,

    /// Number of patterns detected
    pub patterns_detected: usize,

    /// Number of UACs generated
    pub uacs_generated: usize,

    /// Minimum requests before generation
    pub min_requests_threshold: u64,

    /// Whether enough data for generation
    pub ready_for_generation: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_path() {
        let settings = ShadowSettings::default();
        let service = ShadowService::new(settings);

        assert_eq!(
            service.normalize_path("GET", "/api/v1/users/123"),
            "GET /api/v1/users/{id}"
        );

        let uuid = "550e8400-e29b-41d4-a716-446655440000";
        assert_eq!(
            service.normalize_path("GET", &format!("/api/v1/users/{}", uuid)),
            "GET /api/v1/users/{uuid}"
        );
    }

    #[test]
    fn test_infer_schema() {
        let settings = ShadowSettings::default();
        let service = ShadowService::new(settings);

        let value = serde_json::json!({
            "name": "test",
            "count": 42,
            "active": true,
            "tags": ["a", "b"]
        });

        let schema = service.infer_schema(&value);
        assert_eq!(schema["type"], "object");
        assert_eq!(schema["properties"]["name"]["type"], "string");
        assert_eq!(schema["properties"]["count"]["type"], "integer");
        assert_eq!(schema["properties"]["active"]["type"], "boolean");
        assert_eq!(schema["properties"]["tags"]["type"], "array");
    }

    #[test]
    fn test_generate_operation_id() {
        let settings = ShadowSettings::default();
        let service = ShadowService::new(settings);

        assert_eq!(
            service.generate_operation_id("GET", "/api/v1/users"),
            "get_api_v1_users"
        );
        assert_eq!(
            service.generate_operation_id("POST", "/api/v1/users"),
            "create_api_v1_users"
        );
        assert_eq!(
            service.generate_operation_id("GET", "/api/v1/users/{id}"),
            "get_api_v1_users"
        );
    }

    #[tokio::test]
    async fn test_shadow_service_capture() {
        let settings = ShadowSettings {
            min_requests_for_uac: 10,
            ..Default::default()
        };
        let service = ShadowService::new(settings);

        let tx = CapturedTransaction {
            id: "tx-1".to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method: "GET".to_string(),
                path: "/api/v1/users".to_string(),
                query_params: HashMap::new(),
                headers: HashMap::new(),
                content_type: None,
                body: None,
                body_size: 0,
            },
            response: CapturedResponse {
                status_code: 200,
                headers: HashMap::new(),
                content_type: Some("application/json".to_string()),
                body: Some(serde_json::json!({"users": []})),
                body_size: 20,
            },
            latency_ms: 50,
            source: "test".to_string(),
        };

        service.capture(tx).await;

        let status = service.status().await;
        assert_eq!(status.transactions_captured, 1);
        assert!(!status.ready_for_generation);
    }
}
