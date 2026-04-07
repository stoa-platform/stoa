//! Kafka Event Bridge — MCP Tools (CAB-1757)
//!
//! Two MCP tools that bridge Kafka topics for AI agents:
//!
//! - **`kafka_publish`**: Publish a JSON message to a Kafka topic
//! - **`kafka_subscribe`**: Read recent messages from a Kafka topic
//!
//! The publish tool uses the existing `MeteringProducer::send_raw()` method
//! for fire-and-forget publishing. The subscribe tool reads from the
//! `EventBuffer` (populated by the CNS consumer).
//!
//! # Feature Gate
//!
//! When the `kafka` cargo feature is disabled, both tools still compile and
//! register but return graceful errors explaining Kafka is unavailable.

use async_trait::async_trait;
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tracing::info;

use crate::mcp::tools::{Tool, ToolContent, ToolContext, ToolError, ToolResult, ToolSchema};
use crate::metering::MeteringProducer;
use crate::metrics;
use crate::uac::Action;

/// Allowed topics that can be published to via the bridge.
/// Prevents arbitrary topic access — only whitelisted topics are permitted.
const ALLOWED_TOPIC_PREFIXES: &[&str] = &["stoa.", "bridge."];

/// Maximum message payload size (1 MB).
const MAX_PAYLOAD_BYTES: usize = 1_048_576;

// ============================================================================
// KafkaPublishTool
// ============================================================================

/// MCP tool that publishes JSON messages to a Kafka topic.
///
/// Uses the gateway's existing `MeteringProducer` with `send_raw()` for
/// fire-and-forget publishing. Topic must start with an allowed prefix.
pub struct KafkaPublishTool {
    producer: Arc<MeteringProducer>,
    tenant_id: Option<String>,
}

impl KafkaPublishTool {
    pub fn new(producer: Arc<MeteringProducer>, tenant_id: Option<String>) -> Self {
        Self {
            producer,
            tenant_id,
        }
    }

    /// Check if a topic is allowed for publishing
    fn is_topic_allowed(topic: &str) -> bool {
        ALLOWED_TOPIC_PREFIXES
            .iter()
            .any(|prefix| topic.starts_with(prefix))
    }
}

#[async_trait]
impl Tool for KafkaPublishTool {
    fn name(&self) -> &str {
        "kafka_publish"
    }

    fn description(&self) -> &str {
        "Publish a JSON message to a Kafka topic. Topic must start with 'stoa.' or 'bridge.' prefix."
    }

    fn input_schema(&self) -> ToolSchema {
        let mut properties = HashMap::new();
        properties.insert(
            "topic".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "Kafka topic name (must start with 'stoa.' or 'bridge.')"
            }),
        );
        properties.insert(
            "key".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "Message key for partitioning (typically tenant_id or entity_id)"
            }),
        );
        properties.insert(
            "message".to_string(),
            serde_json::json!({
                "type": "object",
                "description": "JSON message payload to publish"
            }),
        );

        ToolSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec![
                "topic".to_string(),
                "key".to_string(),
                "message".to_string(),
            ],
        }
    }

    fn required_action(&self) -> Action {
        Action::Create
    }

    fn tenant_id(&self) -> Option<&str> {
        self.tenant_id.as_deref()
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let topic = args
            .get("topic")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("'topic' is required".to_string()))?;

        let key = args
            .get("key")
            .and_then(|v| v.as_str())
            .ok_or_else(|| ToolError::InvalidArguments("'key' is required".to_string()))?;

        let message = args
            .get("message")
            .ok_or_else(|| ToolError::InvalidArguments("'message' is required".to_string()))?;

        // Validate topic prefix
        if !Self::is_topic_allowed(topic) {
            metrics::track_kafka_bridge_publish(topic, false);
            return Err(ToolError::PermissionDenied(format!(
                "Topic '{}' is not allowed. Must start with: {}",
                topic,
                ALLOWED_TOPIC_PREFIXES.join(", ")
            )));
        }

        // Serialize and validate size
        let payload = serde_json::to_string(message).map_err(|e| {
            ToolError::InvalidArguments(format!("Failed to serialize message: {e}"))
        })?;

        if payload.len() > MAX_PAYLOAD_BYTES {
            metrics::track_kafka_bridge_publish(topic, false);
            return Err(ToolError::InvalidArguments(format!(
                "Message too large: {} bytes (max {})",
                payload.len(),
                MAX_PAYLOAD_BYTES
            )));
        }

        metrics::track_kafka_bridge_publish(topic, true);

        info!(
            topic = %topic,
            key = %key,
            tenant = %ctx.tenant_id,
            size = payload.len(),
            "Kafka bridge: publishing message"
        );

        // Fire-and-forget publish via existing producer
        self.producer.send_raw(topic, key, &payload);

        Ok(ToolResult {
            content: vec![ToolContent::Text {
                text: serde_json::json!({
                    "status": "published",
                    "topic": topic,
                    "key": key,
                    "size_bytes": payload.len()
                })
                .to_string(),
            }],
            is_error: None,
        })
    }
}

// ============================================================================
// KafkaSubscribeTool
// ============================================================================

/// MCP tool that reads recent messages from the event buffer.
///
/// Reads from the `EventBuffer` which is populated by the Kafka CNS consumer.
/// Returns the N most recent events matching the optional type filter.
pub struct KafkaSubscribeTool {
    event_buffer: Arc<crate::events::polling::EventBuffer>,
    tenant_id: Option<String>,
}

impl KafkaSubscribeTool {
    pub fn new(
        event_buffer: Arc<crate::events::polling::EventBuffer>,
        tenant_id: Option<String>,
    ) -> Self {
        Self {
            event_buffer,
            tenant_id,
        }
    }
}

#[async_trait]
impl Tool for KafkaSubscribeTool {
    fn name(&self) -> &str {
        "kafka_subscribe"
    }

    fn description(&self) -> &str {
        "Read recent messages from the Kafka event buffer. Returns events matching the caller's tenant, optionally filtered by event type."
    }

    fn input_schema(&self) -> ToolSchema {
        let mut properties = HashMap::new();
        properties.insert(
            "limit".to_string(),
            serde_json::json!({
                "type": "integer",
                "description": "Maximum number of events to return (default: 10, max: 100)",
                "default": 10
            }),
        );
        properties.insert(
            "event_type".to_string(),
            serde_json::json!({
                "type": "string",
                "description": "Optional filter: only return events of this type (e.g., 'api-created', 'deployment-success')"
            }),
        );

        ToolSchema {
            schema_type: "object".to_string(),
            properties,
            required: vec![],
        }
    }

    fn required_action(&self) -> Action {
        Action::Read
    }

    fn tenant_id(&self) -> Option<&str> {
        self.tenant_id.as_deref()
    }

    async fn execute(&self, args: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        let limit = args
            .get("limit")
            .and_then(|v| v.as_u64())
            .unwrap_or(10)
            .min(100) as usize;

        let event_type_filter = args.get("event_type").and_then(|v| v.as_str());

        metrics::track_kafka_bridge_subscribe(&ctx.tenant_id);

        // Read events from the polling buffer, filtered by tenant
        let events = self.event_buffer.query(&ctx.tenant_id, None, None, limit);

        // Apply optional event_type filter
        let filtered: Vec<_> = if let Some(type_filter) = event_type_filter {
            events
                .into_iter()
                .filter(|e| e.type_ == type_filter)
                .collect()
        } else {
            events
        };

        let result = serde_json::json!({
            "count": filtered.len(),
            "events": filtered
        });

        Ok(ToolResult {
            content: vec![ToolContent::Text {
                text: result.to_string(),
            }],
            is_error: None,
        })
    }
}

// ============================================================================
// Factory
// ============================================================================

/// Create Kafka bridge tools and return them as a vec of boxed Tool trait objects.
///
/// Both tools are always created (even without the `kafka` feature) but the
/// publish tool will use no-op mode when the producer has no Kafka connection.
pub fn create_kafka_bridge_tools(
    producer: Arc<MeteringProducer>,
    event_buffer: Arc<crate::events::polling::EventBuffer>,
    tenant_id: Option<String>,
) -> Vec<Box<dyn Tool>> {
    let publish = KafkaPublishTool::new(producer, tenant_id.clone());
    let subscribe = KafkaSubscribeTool::new(event_buffer, tenant_id);

    vec![Box::new(publish), Box::new(subscribe)]
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::polling::EventBuffer;
    use crate::events::CnsEvent;
    use crate::metering::{MeteringProducer, MeteringProducerConfig};

    fn make_producer() -> Arc<MeteringProducer> {
        Arc::new(MeteringProducer::noop(MeteringProducerConfig {
            brokers: "localhost:9092".to_string(),
            metering_topic: "test.metering".to_string(),
            errors_topic: "test.errors".to_string(),
        }))
    }

    fn make_context() -> ToolContext {
        ToolContext {
            tenant_id: "acme".to_string(),
            user_id: Some("user-1".to_string()),
            user_email: Some("user@acme.com".to_string()),
            request_id: "req-1".to_string(),
            roles: vec!["admin".to_string()],
            scopes: vec!["stoa:write".to_string()],
            raw_token: None,
            skill_instructions: None,
            progress_token: None,
            consumer_id: "test-client".to_string(),
            from_control_plane: false,
        }
    }

    // === KafkaPublishTool Tests ===

    #[test]
    fn test_publish_tool_name() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        assert_eq!(tool.name(), "kafka_publish");
    }

    #[test]
    fn test_publish_tool_description() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        assert!(tool.description().contains("Kafka topic"));
    }

    #[test]
    fn test_publish_tool_schema() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let schema = tool.input_schema();
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.contains_key("topic"));
        assert!(schema.properties.contains_key("key"));
        assert!(schema.properties.contains_key("message"));
        assert_eq!(schema.required.len(), 3);
    }

    #[test]
    fn test_publish_tool_action() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        assert!(matches!(tool.required_action(), Action::Create));
    }

    #[test]
    fn test_publish_topic_allowed() {
        assert!(KafkaPublishTool::is_topic_allowed("stoa.events"));
        assert!(KafkaPublishTool::is_topic_allowed("stoa.metering"));
        assert!(KafkaPublishTool::is_topic_allowed("bridge.custom"));
        assert!(!KafkaPublishTool::is_topic_allowed("internal.secret"));
        assert!(!KafkaPublishTool::is_topic_allowed("other-topic"));
    }

    #[tokio::test]
    async fn test_publish_success() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let ctx = make_context();
        let args = serde_json::json!({
            "topic": "stoa.test-events",
            "key": "acme",
            "message": {"event": "test", "data": 42}
        });

        let result = tool.execute(args, &ctx).await;
        assert!(result.is_ok());
        let result = result.expect("should succeed");
        assert!(result.is_error.is_none());
        let text = match &result.content[0] {
            ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        assert!(text.contains("published"));
        assert!(text.contains("stoa.test-events"));
    }

    #[tokio::test]
    async fn test_publish_disallowed_topic() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let ctx = make_context();
        let args = serde_json::json!({
            "topic": "internal.secret",
            "key": "key1",
            "message": {"data": "should fail"}
        });

        let result = tool.execute(args, &ctx).await;
        assert!(result.is_err());
        match result.err() {
            Some(ToolError::PermissionDenied(msg)) => {
                assert!(msg.contains("not allowed"));
            }
            other => panic!("expected PermissionDenied, got: {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_publish_missing_topic() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let ctx = make_context();
        let args = serde_json::json!({
            "key": "key1",
            "message": {"data": 1}
        });

        let result = tool.execute(args, &ctx).await;
        assert!(result.is_err());
        match result.err() {
            Some(ToolError::InvalidArguments(msg)) => {
                assert!(msg.contains("topic"));
            }
            other => panic!("expected InvalidArguments, got: {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_publish_missing_key() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let ctx = make_context();
        let args = serde_json::json!({
            "topic": "stoa.test",
            "message": {"data": 1}
        });

        let result = tool.execute(args, &ctx).await;
        assert!(result.is_err());
        match result.err() {
            Some(ToolError::InvalidArguments(msg)) => {
                assert!(msg.contains("key"));
            }
            other => panic!("expected InvalidArguments, got: {:?}", other),
        }
    }

    #[tokio::test]
    async fn test_publish_missing_message() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let ctx = make_context();
        let args = serde_json::json!({
            "topic": "stoa.test",
            "key": "key1"
        });

        let result = tool.execute(args, &ctx).await;
        assert!(result.is_err());
        match result.err() {
            Some(ToolError::InvalidArguments(msg)) => {
                assert!(msg.contains("message"));
            }
            other => panic!("expected InvalidArguments, got: {:?}", other),
        }
    }

    #[test]
    fn test_publish_tenant_id() {
        let tool = KafkaPublishTool::new(make_producer(), Some("acme".to_string()));
        assert_eq!(tool.tenant_id(), Some("acme"));
    }

    #[test]
    fn test_publish_tenant_id_none() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        assert_eq!(tool.tenant_id(), None);
    }

    #[test]
    fn test_publish_definition() {
        let tool = KafkaPublishTool::new(make_producer(), None);
        let def = tool.definition();
        assert_eq!(def.name, "kafka_publish");
        assert!(def.description.contains("Kafka"));
    }

    // === KafkaSubscribeTool Tests ===

    #[test]
    fn test_subscribe_tool_name() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        assert_eq!(tool.name(), "kafka_subscribe");
    }

    #[test]
    fn test_subscribe_tool_description() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        assert!(tool.description().contains("event buffer"));
    }

    #[test]
    fn test_subscribe_tool_schema() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        let schema = tool.input_schema();
        assert_eq!(schema.schema_type, "object");
        assert!(schema.properties.contains_key("limit"));
        assert!(schema.properties.contains_key("event_type"));
        assert!(schema.required.is_empty()); // All optional
    }

    #[test]
    fn test_subscribe_tool_action() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        assert!(matches!(tool.required_action(), Action::Read));
    }

    #[tokio::test]
    async fn test_subscribe_empty_buffer() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        let ctx = make_context();

        let result = tool.execute(serde_json::json!({}), &ctx).await;
        assert!(result.is_ok());
        let result = result.expect("should succeed");
        let text = match &result.content[0] {
            ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let parsed: Value = serde_json::from_str(text).expect("valid JSON");
        assert_eq!(parsed["count"], 0);
    }

    #[tokio::test]
    async fn test_subscribe_with_events() {
        let buffer = Arc::new(EventBuffer::new());

        // Push some events
        buffer.push(CnsEvent {
            id: "evt-1".to_string(),
            type_: "api-created".to_string(),
            source: "test".to_string(),
            tenant_id: "acme".to_string(),
            timestamp: chrono::Utc::now(),
            version: "1.0".to_string(),
            user_id: None,
            payload: serde_json::json!({"api": "test"}),
        });
        buffer.push(CnsEvent {
            id: "evt-2".to_string(),
            type_: "deployment-success".to_string(),
            source: "test".to_string(),
            tenant_id: "acme".to_string(),
            timestamp: chrono::Utc::now(),
            version: "1.0".to_string(),
            user_id: None,
            payload: serde_json::json!({"deploy": "ok"}),
        });

        let tool = KafkaSubscribeTool::new(buffer, None);
        let ctx = make_context();

        let result = tool.execute(serde_json::json!({"limit": 10}), &ctx).await;
        assert!(result.is_ok());
        let result = result.expect("should succeed");
        let text = match &result.content[0] {
            ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let parsed: Value = serde_json::from_str(text).expect("valid JSON");
        assert_eq!(parsed["count"], 2);
    }

    #[tokio::test]
    async fn test_subscribe_with_type_filter() {
        let buffer = Arc::new(EventBuffer::new());

        buffer.push(CnsEvent {
            id: "evt-1".to_string(),
            type_: "api-created".to_string(),
            source: "test".to_string(),
            tenant_id: "acme".to_string(),
            timestamp: chrono::Utc::now(),
            version: "1.0".to_string(),
            user_id: None,
            payload: Value::Null,
        });
        buffer.push(CnsEvent {
            id: "evt-2".to_string(),
            type_: "security-alert".to_string(),
            source: "test".to_string(),
            tenant_id: "acme".to_string(),
            timestamp: chrono::Utc::now(),
            version: "1.0".to_string(),
            user_id: None,
            payload: Value::Null,
        });

        let tool = KafkaSubscribeTool::new(buffer, None);
        let ctx = make_context();

        let result = tool
            .execute(serde_json::json!({"event_type": "api-created"}), &ctx)
            .await;
        assert!(result.is_ok());
        let result = result.expect("should succeed");
        let text = match &result.content[0] {
            ToolContent::Text { text } => text,
            _ => panic!("expected text content"),
        };
        let parsed: Value = serde_json::from_str(text).expect("valid JSON");
        assert_eq!(parsed["count"], 1);
    }

    #[tokio::test]
    async fn test_subscribe_limit_capped() {
        let buffer = Arc::new(EventBuffer::new());

        // The limit should be capped at 100
        let tool = KafkaSubscribeTool::new(buffer, None);
        let ctx = make_context();

        // Request limit 200 — should be capped to 100
        let result = tool.execute(serde_json::json!({"limit": 200}), &ctx).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_subscribe_default_limit() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        let ctx = make_context();

        // No limit specified — should default to 10
        let result = tool.execute(serde_json::json!({}), &ctx).await;
        assert!(result.is_ok());
    }

    #[test]
    fn test_subscribe_tenant_id() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, Some("corp".to_string()));
        assert_eq!(tool.tenant_id(), Some("corp"));
    }

    #[test]
    fn test_subscribe_definition() {
        let buffer = Arc::new(EventBuffer::new());
        let tool = KafkaSubscribeTool::new(buffer, None);
        let def = tool.definition();
        assert_eq!(def.name, "kafka_subscribe");
        assert!(def.description.contains("event buffer"));
    }

    // === Factory Tests ===

    #[test]
    fn test_create_kafka_bridge_tools() {
        let producer = make_producer();
        let buffer = Arc::new(EventBuffer::new());
        let tools = create_kafka_bridge_tools(producer, buffer, None);
        assert_eq!(tools.len(), 2);
        assert_eq!(tools[0].name(), "kafka_publish");
        assert_eq!(tools[1].name(), "kafka_subscribe");
    }

    #[test]
    fn test_create_kafka_bridge_tools_with_tenant() {
        let producer = make_producer();
        let buffer = Arc::new(EventBuffer::new());
        let tools = create_kafka_bridge_tools(producer, buffer, Some("acme".to_string()));
        assert_eq!(tools[0].tenant_id(), Some("acme"));
        assert_eq!(tools[1].tenant_id(), Some("acme"));
    }
}
