use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

fn new_idempotency_key() -> Uuid {
    Uuid::new_v4()
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AuditDecision {
    Allow,
    Deny,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct AuditEvent {
    #[serde(skip, default = "new_idempotency_key")]
    pub idempotency_key: Uuid,
    pub source: String,
    pub event_type: String,
    pub decision: AuditDecision,
    pub reason: String,
    pub tenant_id: Uuid,
    pub actor_id: Option<Uuid>,
    pub session_id: Option<String>,
    pub resource_type: String,
    pub resource_id: String,
    pub tool_call_id: Uuid,
    pub approval_id: Option<Uuid>,
    pub policy_version: Option<String>,
    pub correlation_id: Uuid,
    pub occurred_at: DateTime<Utc>,
    pub details: Value,
}
