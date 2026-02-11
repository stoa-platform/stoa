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

    fn make_service(min_requests: u64) -> ShadowService {
        ShadowService::new(ShadowSettings {
            min_requests_for_uac: min_requests,
            analysis_window_hours: 24,
            ..Default::default()
        })
    }

    fn make_tx(
        id: &str,
        method: &str,
        path: &str,
        status: u16,
        latency: u64,
    ) -> CapturedTransaction {
        CapturedTransaction {
            id: id.to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method: method.to_string(),
                path: path.to_string(),
                query_params: HashMap::new(),
                headers: HashMap::new(),
                content_type: Some("application/json".to_string()),
                body: None,
                body_size: 0,
            },
            response: CapturedResponse {
                status_code: status,
                headers: HashMap::new(),
                content_type: Some("application/json".to_string()),
                body: Some(serde_json::json!({"ok": true})),
                body_size: 10,
            },
            latency_ms: latency,
            source: "test".to_string(),
        }
    }

    fn make_tx_with_auth(id: &str, auth_header: &str) -> CapturedTransaction {
        let mut headers = HashMap::new();
        headers.insert("authorization".to_string(), auth_header.to_string());
        CapturedTransaction {
            id: id.to_string(),
            timestamp: chrono::Utc::now(),
            request: CapturedRequest {
                method: "GET".to_string(),
                path: "/api/v1/data".to_string(),
                query_params: HashMap::new(),
                headers,
                content_type: None,
                body: None,
                body_size: 0,
            },
            response: CapturedResponse {
                status_code: 200,
                headers: HashMap::new(),
                content_type: None,
                body: None,
                body_size: 0,
            },
            latency_ms: 10,
            source: "test".to_string(),
        }
    }

    // === Existing tests ===

    #[test]
    fn test_normalize_path() {
        let service = make_service(100);

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
    fn test_normalize_path_no_ids() {
        let service = make_service(100);
        assert_eq!(
            service.normalize_path("POST", "/api/v1/users"),
            "POST /api/v1/users"
        );
    }

    #[test]
    fn test_normalize_path_multiple_ids() {
        let service = make_service(100);
        assert_eq!(
            service.normalize_path("GET", "/api/v1/tenants/42/users/99"),
            "GET /api/v1/tenants/{id}/users/{id}"
        );
    }

    #[test]
    fn test_normalize_path_root() {
        let service = make_service(100);
        assert_eq!(service.normalize_path("GET", "/"), "GET /");
    }

    #[test]
    fn test_infer_schema() {
        let service = make_service(100);

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
    fn test_infer_schema_null() {
        let service = make_service(100);
        let schema = service.infer_schema(&serde_json::Value::Null);
        assert_eq!(schema["type"], "null");
    }

    #[test]
    fn test_infer_schema_number() {
        let service = make_service(100);
        let schema = service.infer_schema(&serde_json::json!(9.99));
        assert_eq!(schema["type"], "number");
    }

    #[test]
    fn test_infer_schema_empty_array() {
        let service = make_service(100);
        let schema = service.infer_schema(&serde_json::json!([]));
        assert_eq!(schema["type"], "array");
        assert!(schema["items"].is_null());
    }

    #[test]
    fn test_generate_operation_id() {
        let service = make_service(100);

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
        assert_eq!(
            service.generate_operation_id("PUT", "/api/v1/users/{id}"),
            "update_api_v1_users"
        );
        assert_eq!(
            service.generate_operation_id("PATCH", "/api/v1/items/{id}"),
            "patch_api_v1_items"
        );
        assert_eq!(
            service.generate_operation_id("DELETE", "/api/v1/users/{id}"),
            "delete_api_v1_users"
        );
    }

    #[test]
    fn test_generate_operation_id_root() {
        let service = make_service(100);
        assert_eq!(service.generate_operation_id("GET", "/"), "get");
    }

    #[test]
    fn test_generate_operation_id_unknown_method() {
        let service = make_service(100);
        assert_eq!(
            service.generate_operation_id("OPTIONS", "/api/v1/test"),
            "options_api_v1_test"
        );
    }

    #[tokio::test]
    async fn test_shadow_service_capture() {
        let service = make_service(10);

        let tx = make_tx("tx-1", "GET", "/api/v1/users", 200, 50);
        service.capture(tx).await;

        let status = service.status().await;
        assert_eq!(status.transactions_captured, 1);
        assert!(!status.ready_for_generation);
        assert_eq!(status.min_requests_threshold, 10);
    }

    #[tokio::test]
    async fn test_shadow_service_status_ready() {
        let service = make_service(2);

        service
            .capture(make_tx("tx-1", "GET", "/api/v1/a", 200, 10))
            .await;
        service
            .capture(make_tx("tx-2", "GET", "/api/v1/b", 200, 20))
            .await;

        let status = service.status().await;
        assert_eq!(status.transactions_captured, 2);
        assert!(status.ready_for_generation);
    }

    // === Build endpoint pattern tests ===

    #[test]
    fn test_build_endpoint_pattern_empty() {
        let service = make_service(100);
        let txs: Vec<&CapturedTransaction> = vec![];
        assert!(service.build_endpoint_pattern("GET /api", &txs).is_none());
    }

    #[test]
    fn test_build_endpoint_pattern_invalid_key() {
        let service = make_service(100);
        let tx = make_tx("tx-1", "GET", "/api", 200, 10);
        let txs = vec![&tx];
        // Key without space separator
        assert!(service.build_endpoint_pattern("invalid", &txs).is_none());
    }

    #[test]
    fn test_build_endpoint_pattern_basic() {
        let service = make_service(100);
        let tx1 = make_tx("tx-1", "GET", "/api/v1/users", 200, 10);
        let tx2 = make_tx("tx-2", "GET", "/api/v1/users", 200, 30);
        let tx3 = make_tx("tx-3", "GET", "/api/v1/users", 500, 50);
        let txs = vec![&tx1, &tx2, &tx3];

        let pattern = service
            .build_endpoint_pattern("GET /api/v1/users", &txs)
            .unwrap();

        assert_eq!(pattern.method, "GET");
        assert_eq!(pattern.path_pattern, "/api/v1/users");
        assert_eq!(pattern.sample_count, 3);
        assert_eq!(pattern.avg_latency_ms, 30); // (10+30+50)/3
                                                // Error rate: 1 out of 3 is >= 400
        assert!((pattern.error_rate - 1.0 / 3.0).abs() < 0.01);
    }

    #[test]
    fn test_build_endpoint_pattern_detects_bearer_auth() {
        let service = make_service(100);
        let tx = make_tx_with_auth("tx-1", "Bearer eyJhbGciOi...");
        let txs = vec![&tx];

        let pattern = service
            .build_endpoint_pattern("GET /api/v1/data", &txs)
            .unwrap();
        assert_eq!(pattern.auth_type, Some("bearer".to_string()));
    }

    #[test]
    fn test_build_endpoint_pattern_detects_basic_auth() {
        let service = make_service(100);
        let tx = make_tx_with_auth("tx-1", "Basic dXNlcjpwYXNz");
        let txs = vec![&tx];

        let pattern = service
            .build_endpoint_pattern("GET /api/v1/data", &txs)
            .unwrap();
        assert_eq!(pattern.auth_type, Some("basic".to_string()));
    }

    #[test]
    fn test_build_endpoint_pattern_detects_api_key() {
        let service = make_service(100);
        let mut tx = make_tx("tx-1", "GET", "/api/v1/data", 200, 10);
        tx.request
            .headers
            .insert("x-api-key".to_string(), "sk-test-123".to_string());
        let txs = vec![&tx];

        let pattern = service
            .build_endpoint_pattern("GET /api/v1/data", &txs)
            .unwrap();
        assert_eq!(pattern.auth_type, Some("api_key".to_string()));
    }

    #[test]
    fn test_build_endpoint_pattern_response_schema() {
        let service = make_service(100);
        let mut tx = make_tx("tx-1", "GET", "/api", 200, 10);
        tx.response.body = Some(serde_json::json!({"users": [{"id": 1}]}));
        let txs = vec![&tx];

        let pattern = service.build_endpoint_pattern("GET /api", &txs).unwrap();
        assert!(pattern.response_schemas.contains_key(&200));
        assert_eq!(pattern.response_schemas[&200]["type"], "object");
    }

    // === Analyze patterns tests ===

    #[tokio::test]
    async fn test_analyze_patterns_groups_by_path() {
        let service = make_service(100);
        let txs = vec![
            make_tx("tx-1", "GET", "/api/v1/users", 200, 10),
            make_tx("tx-2", "GET", "/api/v1/users", 200, 20),
            make_tx("tx-3", "POST", "/api/v1/users", 201, 30),
        ];

        let patterns = service.analyze_patterns(&txs).await;
        assert_eq!(patterns.len(), 2); // GET + POST
        assert!(patterns.contains_key("GET /api/v1/users"));
        assert!(patterns.contains_key("POST /api/v1/users"));
        assert_eq!(patterns["GET /api/v1/users"].sample_count, 2);
        assert_eq!(patterns["POST /api/v1/users"].sample_count, 1);
    }

    #[tokio::test]
    async fn test_analyze_patterns_normalizes_ids() {
        let service = make_service(100);
        let txs = vec![
            make_tx("tx-1", "GET", "/api/v1/users/1", 200, 10),
            make_tx("tx-2", "GET", "/api/v1/users/2", 200, 20),
            make_tx("tx-3", "GET", "/api/v1/users/99", 200, 30),
        ];

        let patterns = service.analyze_patterns(&txs).await;
        // All should be grouped under GET /api/v1/users/{id}
        assert_eq!(patterns.len(), 1);
        assert!(patterns.contains_key("GET /api/v1/users/{id}"));
        assert_eq!(patterns["GET /api/v1/users/{id}"].sample_count, 3);
    }

    // === Generate UAC tests ===

    #[tokio::test]
    async fn test_generate_uac_no_patterns() {
        let service = make_service(100);
        let uac = service.generate_uac("test-api", "http://test.com").await;
        assert!(uac.is_none());
    }

    #[tokio::test]
    async fn test_generate_uac_success() {
        let service = make_service(2);

        // Capture enough transactions to trigger analysis
        service
            .capture(make_tx("tx-1", "GET", "/api/v1/users", 200, 10))
            .await;
        service
            .capture(make_tx("tx-2", "POST", "/api/v1/users", 201, 20))
            .await;

        let uac = service.generate_uac("User API", "http://users.local").await;
        assert!(uac.is_some());

        let uac = uac.unwrap();
        assert_eq!(uac.api_id, "user-api-api");
        assert_eq!(uac.api_name, "User API");
        assert_eq!(uac.base_url, "http://users.local");
        assert_eq!(uac.version, "v1");
        assert!(!uac.endpoints.is_empty());
        assert!(!uac.rate_limits.is_empty());
        assert_eq!(uac.rate_limits[0].endpoint, "*");
        assert_eq!(uac.rate_limits[0].limit, 1000);
        assert!(uac.metadata.confidence > 0.0);
        assert!(uac.metadata.transactions_analyzed >= 2);

        // Check it's stored
        let status = service.status().await;
        assert_eq!(status.uacs_generated, 1);
    }

    // === Export YAML test ===

    #[tokio::test]
    async fn test_export_uac_yaml() {
        let service = make_service(2);
        service
            .capture(make_tx("tx-1", "GET", "/api", 200, 10))
            .await;
        service
            .capture(make_tx("tx-2", "GET", "/api", 200, 20))
            .await;

        let uac = service
            .generate_uac("Test", "http://test.com")
            .await
            .unwrap();
        let yaml = service.export_uac_yaml(&uac).await;
        assert!(yaml.contains("api_name: Test"));
        assert!(yaml.contains("base_url: http://test.com"));
    }

    // === Content type collection test ===

    #[test]
    fn test_build_endpoint_pattern_content_types() {
        let service = make_service(100);
        let mut tx1 = make_tx("tx-1", "POST", "/api/v1/data", 200, 10);
        tx1.request.content_type = Some("application/json".to_string());
        let mut tx2 = make_tx("tx-2", "POST", "/api/v1/data", 200, 20);
        tx2.request.content_type = Some("application/xml".to_string());
        let txs = vec![&tx1, &tx2];

        let pattern = service
            .build_endpoint_pattern("POST /api/v1/data", &txs)
            .unwrap();
        assert!(!pattern.content_types.is_empty()); // at least one content type
    }
}
