//! RAG Injector — Enriches prompts with context from external sources (CAB-1761)
//!
//! Supports pluggable context sources:
//! - **REST API**: fetches context from an HTTP endpoint (JSON body)
//! - **VectorDB**: queries a vector database for similar documents (Qdrant/pgvector)
//! - **Static**: injects a fixed system prompt or knowledge base snippet
//!
//! Each route can be configured with a different RAG source and parameters.
//! Context is injected as a system message or prepended to the user prompt.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::time::Duration;
use tracing::{info, warn};

/// Configuration for the RAG injector.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagInjectorConfig {
    /// Maximum context length in characters (prevents prompt bloat)
    #[serde(default = "default_max_context_len")]
    pub max_context_length: usize,
    /// Timeout for external context source requests
    #[serde(default = "default_source_timeout_ms")]
    pub source_timeout_ms: u64,
    /// Maximum number of context chunks to include
    #[serde(default = "default_max_chunks")]
    pub max_chunks: usize,
}

fn default_max_context_len() -> usize {
    4096
}
fn default_source_timeout_ms() -> u64 {
    3000
}
fn default_max_chunks() -> usize {
    5
}

impl Default for RagInjectorConfig {
    fn default() -> Self {
        Self {
            max_context_length: default_max_context_len(),
            source_timeout_ms: default_source_timeout_ms(),
            max_chunks: default_max_chunks(),
        }
    }
}

/// Type of RAG context source.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RagSourceType {
    /// HTTP REST API endpoint that returns context JSON
    RestApi,
    /// Vector database (Qdrant, pgvector, Milvus)
    VectorDb,
    /// Static text (injected as-is, no external call)
    Static,
}

/// A configured RAG context source.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagSource {
    /// Unique identifier for this source
    pub id: String,
    /// Source type
    pub source_type: RagSourceType,
    /// Endpoint URL (for rest_api and vector_db types)
    pub url: Option<String>,
    /// Static content (for static type)
    pub content: Option<String>,
    /// API key or bearer token for the source
    pub api_key: Option<String>,
    /// Collection/index name (for vector_db type)
    pub collection: Option<String>,
    /// Number of results to retrieve (for vector_db type)
    #[serde(default = "default_top_k")]
    pub top_k: usize,
}

fn default_top_k() -> usize {
    3
}

/// A chunk of retrieved context.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RagContext {
    /// Source identifier
    pub source_id: String,
    /// Retrieved text content
    pub text: String,
    /// Relevance score (0.0-1.0, from vector search)
    pub score: Option<f64>,
    /// Optional metadata (document title, URL, etc.)
    pub metadata: Option<Value>,
}

/// RAG Injector — fetches and injects context into prompts.
pub struct RagInjector {
    config: RagInjectorConfig,
    http_client: reqwest::Client,
}

impl RagInjector {
    /// Create a new RAG injector with the given configuration.
    pub fn new(config: RagInjectorConfig) -> Self {
        let http_client = reqwest::Client::builder()
            .timeout(Duration::from_millis(config.source_timeout_ms))
            .build()
            .unwrap_or_default();

        Self {
            config,
            http_client,
        }
    }

    /// Fetch context from a source for a given query.
    ///
    /// Returns a list of context chunks, truncated to `max_chunks` and
    /// `max_context_length` limits.
    pub async fn fetch_context(
        &self,
        source: &RagSource,
        query: &str,
    ) -> Result<Vec<RagContext>, String> {
        match source.source_type {
            RagSourceType::Static => self.fetch_static(source),
            RagSourceType::RestApi => self.fetch_rest_api(source, query).await,
            RagSourceType::VectorDb => self.fetch_vector_db(source, query).await,
        }
    }

    /// Inject context into tool call arguments.
    ///
    /// Prepends retrieved context as a `_rag_context` field in the arguments JSON.
    /// The LLM or tool handler can use this additional context.
    pub fn inject_context(&self, args: &Value, contexts: &[RagContext]) -> Value {
        if contexts.is_empty() {
            return args.clone();
        }

        // Build context string from chunks
        let mut context_text = String::new();
        let mut total_len = 0;

        for (i, ctx) in contexts.iter().enumerate() {
            if i >= self.config.max_chunks {
                break;
            }
            let chunk = format!("[Source: {}] {}\n", ctx.source_id, ctx.text);
            if total_len + chunk.len() > self.config.max_context_length {
                // Truncate to fit within limit
                let remaining = self.config.max_context_length.saturating_sub(total_len);
                if remaining > 20 {
                    context_text.push_str(&chunk[..remaining]);
                }
                break;
            }
            context_text.push_str(&chunk);
            total_len += chunk.len();
        }

        // Inject as _rag_context field
        let mut result = args.clone();
        if let Value::Object(ref mut map) = result {
            map.insert("_rag_context".to_string(), Value::String(context_text));
        }
        result
    }

    /// Static source: return the configured content directly.
    fn fetch_static(&self, source: &RagSource) -> Result<Vec<RagContext>, String> {
        match &source.content {
            Some(text) => Ok(vec![RagContext {
                source_id: source.id.clone(),
                text: text.clone(),
                score: Some(1.0),
                metadata: None,
            }]),
            None => Err("Static source has no content configured".to_string()),
        }
    }

    /// REST API source: POST query to endpoint, parse response.
    ///
    /// Expected response format:
    /// ```json
    /// {
    ///   "results": [
    ///     {"text": "...", "score": 0.95, "metadata": {...}},
    ///     {"text": "...", "score": 0.87}
    ///   ]
    /// }
    /// ```
    async fn fetch_rest_api(
        &self,
        source: &RagSource,
        query: &str,
    ) -> Result<Vec<RagContext>, String> {
        let url = source
            .url
            .as_deref()
            .ok_or("REST API source has no URL configured")?;

        let body = serde_json::json!({
            "query": query,
            "top_k": source.top_k,
        });

        let mut request = self.http_client.post(url).json(&body);

        if let Some(api_key) = &source.api_key {
            request = request.bearer_auth(api_key);
        }

        info!(source = %source.id, url = %url, "RAG: fetching context from REST API");

        let response = request
            .send()
            .await
            .map_err(|e| format!("RAG REST API request failed: {e}"))?;

        if !response.status().is_success() {
            let status = response.status();
            return Err(format!("RAG REST API returned HTTP {status}"));
        }

        let json: Value = response
            .json()
            .await
            .map_err(|e| format!("RAG REST API response parse error: {e}"))?;

        Self::parse_results(&source.id, &json)
    }

    /// Vector DB source: query for similar documents.
    ///
    /// Sends a search request to the vector DB HTTP API.
    /// Supports Qdrant-style API: POST /collections/{collection}/points/search
    async fn fetch_vector_db(
        &self,
        source: &RagSource,
        query: &str,
    ) -> Result<Vec<RagContext>, String> {
        let base_url = source
            .url
            .as_deref()
            .ok_or("Vector DB source has no URL configured")?;

        let collection = source
            .collection
            .as_deref()
            .ok_or("Vector DB source has no collection configured")?;

        // For vector DB, we send the raw query text.
        // The vector DB service is expected to handle embedding internally
        // (e.g., Qdrant with FastEmbed, or a proxy that embeds before search).
        let url = format!(
            "{}/collections/{}/points/search",
            base_url.trim_end_matches('/'),
            collection
        );

        let body = serde_json::json!({
            "query": query,
            "limit": source.top_k,
            "with_payload": true,
        });

        let mut request = self.http_client.post(&url).json(&body);

        if let Some(api_key) = &source.api_key {
            request = request.header("api-key", api_key);
        }

        info!(source = %source.id, collection = %collection, "RAG: querying vector DB");

        let response = request
            .send()
            .await
            .map_err(|e| format!("RAG vector DB request failed: {e}"))?;

        if !response.status().is_success() {
            let status = response.status();
            warn!(source = %source.id, status = %status, "RAG vector DB error");
            return Err(format!("RAG vector DB returned HTTP {status}"));
        }

        let json: Value = response
            .json()
            .await
            .map_err(|e| format!("RAG vector DB response parse error: {e}"))?;

        // Qdrant response: { "result": [{ "score": 0.95, "payload": { "text": "..." } }] }
        if let Some(results) = json.get("result").and_then(|r| r.as_array()) {
            let contexts: Vec<RagContext> = results
                .iter()
                .filter_map(|r| {
                    let text = r
                        .get("payload")
                        .and_then(|p| p.get("text"))
                        .and_then(|t| t.as_str())
                        .map(String::from)?;
                    let score = r.get("score").and_then(|s| s.as_f64());
                    Some(RagContext {
                        source_id: source.id.clone(),
                        text,
                        score,
                        metadata: r.get("payload").cloned(),
                    })
                })
                .take(self.config.max_chunks)
                .collect();
            return Ok(contexts);
        }

        // Fallback: try generic "results" array format
        Self::parse_results(&source.id, &json)
    }

    /// Parse a generic results array from a context source response.
    fn parse_results(source_id: &str, json: &Value) -> Result<Vec<RagContext>, String> {
        let results = json
            .get("results")
            .and_then(|r| r.as_array())
            .ok_or("Response missing 'results' array")?;

        Ok(results
            .iter()
            .filter_map(|r| {
                let text = r.get("text").and_then(|t| t.as_str()).map(String::from)?;
                let score = r.get("score").and_then(|s| s.as_f64());
                let metadata = r.get("metadata").cloned();
                Some(RagContext {
                    source_id: source_id.to_string(),
                    text,
                    score,
                    metadata,
                })
            })
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn default_injector() -> RagInjector {
        RagInjector::new(RagInjectorConfig::default())
    }

    // --- Static source tests ---

    #[test]
    fn test_fetch_static_returns_content() {
        let injector = default_injector();
        let source = RagSource {
            id: "static-1".to_string(),
            source_type: RagSourceType::Static,
            url: None,
            content: Some("You are a helpful API assistant.".to_string()),
            api_key: None,
            collection: None,
            top_k: default_top_k(),
        };

        let result = injector.fetch_static(&source).expect("should succeed");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].text, "You are a helpful API assistant.");
        assert_eq!(result[0].score, Some(1.0));
    }

    #[test]
    fn test_fetch_static_no_content_errors() {
        let injector = default_injector();
        let source = RagSource {
            id: "static-empty".to_string(),
            source_type: RagSourceType::Static,
            url: None,
            content: None,
            api_key: None,
            collection: None,
            top_k: default_top_k(),
        };

        let result = injector.fetch_static(&source);
        assert!(result.is_err());
    }

    // --- Context injection tests ---

    #[test]
    fn test_inject_context_adds_field() {
        let injector = default_injector();
        let args = json!({"query": "What APIs are available?"});
        let contexts = vec![RagContext {
            source_id: "kb".to_string(),
            text: "STOA provides REST, GraphQL, and MCP APIs.".to_string(),
            score: Some(0.92),
            metadata: None,
        }];

        let result = injector.inject_context(&args, &contexts);
        assert!(result.get("_rag_context").is_some());
        let ctx = result["_rag_context"].as_str().unwrap();
        assert!(ctx.contains("STOA provides REST"));
        assert!(ctx.contains("[Source: kb]"));
        // Original args preserved
        assert_eq!(result["query"], "What APIs are available?");
    }

    #[test]
    fn test_inject_context_empty_contexts_returns_original() {
        let injector = default_injector();
        let args = json!({"query": "hello"});
        let result = injector.inject_context(&args, &[]);
        assert_eq!(result, args);
    }

    #[test]
    fn test_inject_context_respects_max_chunks() {
        let config = RagInjectorConfig {
            max_chunks: 2,
            ..Default::default()
        };
        let injector = RagInjector::new(config);
        let args = json!({"query": "test"});
        let contexts = vec![
            RagContext {
                source_id: "a".to_string(),
                text: "chunk 1".to_string(),
                score: None,
                metadata: None,
            },
            RagContext {
                source_id: "b".to_string(),
                text: "chunk 2".to_string(),
                score: None,
                metadata: None,
            },
            RagContext {
                source_id: "c".to_string(),
                text: "chunk 3 should be excluded".to_string(),
                score: None,
                metadata: None,
            },
        ];

        let result = injector.inject_context(&args, &contexts);
        let ctx = result["_rag_context"].as_str().unwrap();
        assert!(ctx.contains("chunk 1"));
        assert!(ctx.contains("chunk 2"));
        assert!(!ctx.contains("chunk 3"));
    }

    #[test]
    fn test_inject_context_respects_max_length() {
        let config = RagInjectorConfig {
            max_context_length: 50,
            max_chunks: 10,
            ..Default::default()
        };
        let injector = RagInjector::new(config);
        let args = json!({"query": "test"});
        let contexts = vec![
            RagContext {
                source_id: "s".to_string(),
                text: "A".repeat(30),
                score: None,
                metadata: None,
            },
            RagContext {
                source_id: "s".to_string(),
                text: "B".repeat(30),
                score: None,
                metadata: None,
            },
        ];

        let result = injector.inject_context(&args, &contexts);
        let ctx = result["_rag_context"].as_str().unwrap();
        assert!(ctx.len() <= 50);
    }

    // --- Parse results tests ---

    #[test]
    fn test_parse_results_valid() {
        let json = json!({
            "results": [
                {"text": "API docs here", "score": 0.95, "metadata": {"source": "wiki"}},
                {"text": "Configuration guide", "score": 0.87}
            ]
        });

        let results = RagInjector::parse_results("test", &json).expect("should parse");
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].text, "API docs here");
        assert_eq!(results[0].score, Some(0.95));
        assert!(results[0].metadata.is_some());
        assert_eq!(results[1].text, "Configuration guide");
    }

    #[test]
    fn test_parse_results_missing_results_array() {
        let json = json!({"data": "wrong format"});
        let result = RagInjector::parse_results("test", &json);
        assert!(result.is_err());
    }

    #[test]
    fn test_parse_results_skips_entries_without_text() {
        let json = json!({
            "results": [
                {"text": "valid", "score": 0.9},
                {"score": 0.8},
                {"text": "also valid"}
            ]
        });

        let results = RagInjector::parse_results("test", &json).expect("should parse");
        assert_eq!(results.len(), 2);
    }

    // --- Config serialization ---

    #[test]
    fn test_rag_source_serialization() {
        let source = RagSource {
            id: "my-kb".to_string(),
            source_type: RagSourceType::VectorDb,
            url: Some("http://qdrant:6333".to_string()),
            content: None,
            api_key: None,
            collection: Some("stoa-docs".to_string()),
            top_k: 5,
        };

        let json = serde_json::to_value(&source).expect("should serialize");
        assert_eq!(json["source_type"], "vector_db");
        assert_eq!(json["collection"], "stoa-docs");
    }

    #[test]
    fn test_rag_config_defaults() {
        let config = RagInjectorConfig::default();
        assert_eq!(config.max_context_length, 4096);
        assert_eq!(config.source_timeout_ms, 3000);
        assert_eq!(config.max_chunks, 5);
    }
}
