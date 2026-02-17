//! Kafka CNS Event Bridge (Phase 2: CAB-1178)
//!
//! Bridges Kafka CNS (Cloud Native Services) events to MCP clients via SSE.
//! Events are consumed from `stoa.*` topics and pushed to connected sessions
//! matching the event's `tenant_id`.
//!
//! # Feature Gate
//!
//! - `kafka`: Enables rdkafka StreamConsumer for real Kafka consumption
//! - Without `kafka`: Module compiles but consumer is a no-op

pub mod consumer;
pub mod notifications;
pub mod polling;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// CNS Event envelope (matches CP API `stoa.*` topic schema from CAB-1177)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CnsEvent {
    /// Unique event ID (UUID)
    pub id: String,

    /// Event type (e.g., "api-created", "deployment-success", "security-alert")
    #[serde(rename = "type")]
    pub type_: String,

    /// Source component (e.g., "control-plane-api", "gateway")
    pub source: String,

    /// Tenant ID for routing (events only delivered to matching tenant sessions)
    pub tenant_id: String,

    /// Event timestamp
    pub timestamp: DateTime<Utc>,

    /// Schema version (e.g., "1.0")
    #[serde(default = "default_version")]
    pub version: String,

    /// User who triggered the event (optional)
    #[serde(default)]
    pub user_id: Option<String>,

    /// Event payload (opaque JSON — forwarded as-is to MCP clients)
    #[serde(default)]
    pub payload: Value,
}

fn default_version() -> String {
    "1.0".to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cns_event_deserialize() {
        let json = r#"{
            "id": "evt-001",
            "type": "api-created",
            "source": "control-plane-api",
            "tenant_id": "acme",
            "timestamp": "2026-02-17T10:00:00Z",
            "version": "1.0",
            "user_id": "user-123",
            "payload": {"api_id": "api-42", "name": "Weather API"}
        }"#;

        let event: CnsEvent = serde_json::from_str(json).expect("deserialize");
        assert_eq!(event.id, "evt-001");
        assert_eq!(event.type_, "api-created");
        assert_eq!(event.tenant_id, "acme");
        assert_eq!(event.payload["api_id"], "api-42");
    }

    #[test]
    fn test_cns_event_deserialize_minimal() {
        let json = r#"{
            "id": "evt-002",
            "type": "security-alert",
            "source": "gateway",
            "tenant_id": "corp",
            "timestamp": "2026-02-17T12:00:00Z"
        }"#;

        let event: CnsEvent = serde_json::from_str(json).expect("deserialize");
        assert_eq!(event.version, "1.0");
        assert!(event.user_id.is_none());
        assert_eq!(event.payload, Value::Null);
    }

    #[test]
    fn test_cns_event_roundtrip() {
        let event = CnsEvent {
            id: "evt-003".to_string(),
            type_: "deploy-request".to_string(),
            source: "control-plane-api".to_string(),
            tenant_id: "beta".to_string(),
            timestamp: Utc::now(),
            version: "1.0".to_string(),
            user_id: Some("admin".to_string()),
            payload: serde_json::json!({"deployment_id": "dep-99"}),
        };

        let serialized = serde_json::to_string(&event).expect("serialize");
        let deserialized: CnsEvent = serde_json::from_str(&serialized).expect("deserialize");
        assert_eq!(deserialized.id, "evt-003");
        assert_eq!(deserialized.type_, "deploy-request");
    }
}
