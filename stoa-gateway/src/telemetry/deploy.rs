//! Deploy Progress Telemetry (CAB-1421)
//!
//! Emits structured progress events during API sync operations to
//! the `stoa.deployment.progress` Kafka topic. The CP API (CAB-1420)
//! consumes these events and fans them out via SSE to the Console UI.
//!
//! Each sync operation reports step-level granularity:
//! `validating → applying-routes → applying-policies → activating → done`
//!
//! Uses the same Kafka producer infrastructure as metering (fire-and-forget,
//! non-blocking). When Kafka is unavailable, events are logged via tracing.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::debug;
use uuid::Uuid;

use crate::metering::MeteringProducer;

/// Deployment progress step identifiers.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum DeployStep {
    /// Validating the API route payload
    Validating,
    /// Applying route changes to the registry
    ApplyingRoutes,
    /// Applying policy changes
    ApplyingPolicies,
    /// Activating the route (making it live)
    Activating,
    /// Sync operation complete
    Done,
}

impl std::fmt::Display for DeployStep {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DeployStep::Validating => write!(f, "validating"),
            DeployStep::ApplyingRoutes => write!(f, "applying-routes"),
            DeployStep::ApplyingPolicies => write!(f, "applying-policies"),
            DeployStep::Activating => write!(f, "activating"),
            DeployStep::Done => write!(f, "done"),
        }
    }
}

/// Status of a deployment step.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum DeployStepStatus {
    /// Step has started
    Started,
    /// Step completed successfully
    Completed,
    /// Step failed
    Failed,
}

impl std::fmt::Display for DeployStepStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DeployStepStatus::Started => write!(f, "started"),
            DeployStepStatus::Completed => write!(f, "completed"),
            DeployStepStatus::Failed => write!(f, "failed"),
        }
    }
}

/// A structured deployment progress event.
///
/// Published to `stoa.deployment.progress` for each step of an API sync operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeployProgressEvent {
    /// Unique deployment identifier (UUID, same across all steps of one sync)
    pub deployment_id: Uuid,

    /// Current step in the deployment pipeline
    pub step: DeployStep,

    /// Status of this step
    pub status: DeployStepStatus,

    /// Human-readable progress message
    pub message: String,

    /// ISO 8601 timestamp
    pub timestamp: DateTime<Utc>,

    /// API route ID being deployed (for correlation)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_id: Option<String>,

    /// Tenant ID (for topic partitioning / routing)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,
}

impl DeployProgressEvent {
    /// Create a new progress event for the given deployment + step + status.
    pub fn new(
        deployment_id: Uuid,
        step: DeployStep,
        status: DeployStepStatus,
        message: impl Into<String>,
    ) -> Self {
        Self {
            deployment_id,
            step,
            status,
            message: message.into(),
            timestamp: Utc::now(),
            api_id: None,
            tenant_id: None,
        }
    }

    /// Attach the API route ID for correlation.
    pub fn with_api_id(mut self, api_id: impl Into<String>) -> Self {
        self.api_id = Some(api_id.into());
        self
    }

    /// Attach the tenant ID for routing.
    pub fn with_tenant_id(mut self, tenant_id: impl Into<String>) -> Self {
        self.tenant_id = Some(tenant_id.into());
        self
    }
}

/// Emitter for deployment progress events.
///
/// Wraps the existing Kafka metering producer infrastructure.
/// When `metering_producer` is `None`, events are logged but not sent.
#[derive(Clone)]
pub struct DeployProgressEmitter {
    /// Kafka topic for deployment progress events
    topic: String,
    /// Reuses the metering producer for Kafka access (fire-and-forget)
    producer: Option<Arc<MeteringProducer>>,
}

impl DeployProgressEmitter {
    /// Create a new emitter.
    ///
    /// - `topic`: Kafka topic name (default: `stoa.deployment.progress`)
    /// - `producer`: shared metering producer (None = log-only mode)
    pub fn new(topic: String, producer: Option<Arc<MeteringProducer>>) -> Self {
        Self { topic, producer }
    }

    /// Emit a single deploy progress event (fire-and-forget, non-blocking).
    ///
    /// In log-only mode (no Kafka producer), events are emitted via `tracing::debug`.
    /// When the `kafka` feature is enabled and a producer is present, events are
    /// serialized and sent to the configured Kafka topic.
    pub fn emit(&self, event: &DeployProgressEvent) {
        // Log every event at debug level regardless of Kafka availability
        debug!(
            deployment_id = %event.deployment_id,
            step = %event.step,
            status = %event.status,
            message = %event.message,
            api_id = ?event.api_id,
            tenant_id = ?event.tenant_id,
            topic = %self.topic,
            "Deploy progress event"
        );

        // Attempt Kafka send when the feature is compiled in and producer exists
        #[cfg(feature = "kafka")]
        if self.producer.is_some() {
            match serde_json::to_string(event) {
                Ok(payload) => {
                    let key = event.deployment_id.to_string();
                    self.send_to_kafka(&key, &payload);
                }
                Err(e) => {
                    tracing::error!(error = %e, "Failed to serialize deploy progress event");
                }
            }
        }
    }

    /// Internal: send payload to Kafka topic via the metering producer's `send_raw`.
    #[cfg(feature = "kafka")]
    fn send_to_kafka(&self, key: &str, payload: &str) {
        if let Some(ref producer) = self.producer {
            producer.send_raw(&self.topic, key, payload);
        }
    }

    /// Convenience: emit a "started" event for a step.
    pub fn step_started(
        &self,
        deployment_id: Uuid,
        step: DeployStep,
        message: impl Into<String>,
        api_id: Option<&str>,
        tenant_id: Option<&str>,
    ) {
        let mut event =
            DeployProgressEvent::new(deployment_id, step, DeployStepStatus::Started, message);
        if let Some(id) = api_id {
            event = event.with_api_id(id);
        }
        if let Some(tid) = tenant_id {
            event = event.with_tenant_id(tid);
        }
        self.emit(&event);
    }

    /// Convenience: emit a "completed" event for a step.
    pub fn step_completed(
        &self,
        deployment_id: Uuid,
        step: DeployStep,
        message: impl Into<String>,
        api_id: Option<&str>,
        tenant_id: Option<&str>,
    ) {
        let mut event =
            DeployProgressEvent::new(deployment_id, step, DeployStepStatus::Completed, message);
        if let Some(id) = api_id {
            event = event.with_api_id(id);
        }
        if let Some(tid) = tenant_id {
            event = event.with_tenant_id(tid);
        }
        self.emit(&event);
    }

    /// Convenience: emit a "failed" event for a step.
    pub fn step_failed(
        &self,
        deployment_id: Uuid,
        step: DeployStep,
        message: impl Into<String>,
        api_id: Option<&str>,
        tenant_id: Option<&str>,
    ) {
        let mut event =
            DeployProgressEvent::new(deployment_id, step, DeployStepStatus::Failed, message);
        if let Some(id) = api_id {
            event = event.with_api_id(id);
        }
        if let Some(tid) = tenant_id {
            event = event.with_tenant_id(tid);
        }
        self.emit(&event);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deploy_step_serialization() {
        let json = serde_json::to_string(&DeployStep::ApplyingRoutes).unwrap();
        assert_eq!(json, "\"applying-routes\"");

        let json = serde_json::to_string(&DeployStep::Done).unwrap();
        assert_eq!(json, "\"done\"");
    }

    #[test]
    fn test_deploy_step_display() {
        assert_eq!(DeployStep::Validating.to_string(), "validating");
        assert_eq!(DeployStep::ApplyingRoutes.to_string(), "applying-routes");
        assert_eq!(
            DeployStep::ApplyingPolicies.to_string(),
            "applying-policies"
        );
        assert_eq!(DeployStep::Activating.to_string(), "activating");
        assert_eq!(DeployStep::Done.to_string(), "done");
    }

    #[test]
    fn test_deploy_step_status_serialization() {
        let json = serde_json::to_string(&DeployStepStatus::Started).unwrap();
        assert_eq!(json, "\"started\"");

        let json = serde_json::to_string(&DeployStepStatus::Completed).unwrap();
        assert_eq!(json, "\"completed\"");

        let json = serde_json::to_string(&DeployStepStatus::Failed).unwrap();
        assert_eq!(json, "\"failed\"");
    }

    #[test]
    fn test_deploy_step_status_display() {
        assert_eq!(DeployStepStatus::Started.to_string(), "started");
        assert_eq!(DeployStepStatus::Completed.to_string(), "completed");
        assert_eq!(DeployStepStatus::Failed.to_string(), "failed");
    }

    #[test]
    fn test_progress_event_new() {
        let id = Uuid::new_v4();
        let event = DeployProgressEvent::new(
            id,
            DeployStep::Validating,
            DeployStepStatus::Started,
            "Validating API route payload",
        );

        assert_eq!(event.deployment_id, id);
        assert_eq!(event.step, DeployStep::Validating);
        assert_eq!(event.status, DeployStepStatus::Started);
        assert_eq!(event.message, "Validating API route payload");
        assert!(event.api_id.is_none());
        assert!(event.tenant_id.is_none());
    }

    #[test]
    fn test_progress_event_with_context() {
        let id = Uuid::new_v4();
        let event = DeployProgressEvent::new(
            id,
            DeployStep::Done,
            DeployStepStatus::Completed,
            "API sync complete",
        )
        .with_api_id("r1")
        .with_tenant_id("acme");

        assert_eq!(event.api_id.as_deref(), Some("r1"));
        assert_eq!(event.tenant_id.as_deref(), Some("acme"));
    }

    #[test]
    fn test_progress_event_json_roundtrip() {
        let id = Uuid::new_v4();
        let event = DeployProgressEvent::new(
            id,
            DeployStep::ApplyingPolicies,
            DeployStepStatus::Completed,
            "All policies applied",
        )
        .with_api_id("api-42")
        .with_tenant_id("tenant-1");

        let json = serde_json::to_string(&event).unwrap();
        let parsed: DeployProgressEvent = serde_json::from_str(&json).unwrap();

        assert_eq!(parsed.deployment_id, id);
        assert_eq!(parsed.step, DeployStep::ApplyingPolicies);
        assert_eq!(parsed.status, DeployStepStatus::Completed);
        assert_eq!(parsed.message, "All policies applied");
        assert_eq!(parsed.api_id.as_deref(), Some("api-42"));
        assert_eq!(parsed.tenant_id.as_deref(), Some("tenant-1"));
    }

    #[test]
    fn test_progress_event_optional_fields_absent_in_json() {
        let id = Uuid::new_v4();
        let event = DeployProgressEvent::new(
            id,
            DeployStep::Validating,
            DeployStepStatus::Started,
            "Starting validation",
        );

        let json = serde_json::to_string(&event).unwrap();
        // Optional fields with skip_serializing_if should be absent
        assert!(!json.contains("api_id"));
        assert!(!json.contains("tenant_id"));
    }

    #[test]
    fn test_emitter_log_only_mode() {
        let emitter = DeployProgressEmitter::new("stoa.deployment.progress".to_string(), None);
        let id = Uuid::new_v4();

        // Should not panic in log-only mode
        emitter.step_started(
            id,
            DeployStep::Validating,
            "Validating",
            Some("r1"),
            Some("acme"),
        );
        emitter.step_completed(
            id,
            DeployStep::Validating,
            "Validation complete",
            Some("r1"),
            Some("acme"),
        );
        emitter.step_failed(
            id,
            DeployStep::ApplyingRoutes,
            "Route apply failed",
            Some("r1"),
            Some("acme"),
        );
    }

    #[test]
    fn test_emitter_full_sync_sequence() {
        let emitter = DeployProgressEmitter::new("stoa.deployment.progress".to_string(), None);
        let deployment_id = Uuid::new_v4();
        let api_id = Some("r1");
        let tenant_id = Some("acme");

        // Simulate a full sync lifecycle — none should panic
        let steps = [
            DeployStep::Validating,
            DeployStep::ApplyingRoutes,
            DeployStep::ApplyingPolicies,
            DeployStep::Activating,
            DeployStep::Done,
        ];

        for step in &steps {
            emitter.step_started(deployment_id, *step, "started", api_id, tenant_id);
            emitter.step_completed(deployment_id, *step, "completed", api_id, tenant_id);
        }
    }

    #[test]
    fn test_deploy_step_deserialization() {
        let step: DeployStep = serde_json::from_str("\"applying-routes\"").unwrap();
        assert_eq!(step, DeployStep::ApplyingRoutes);

        let step: DeployStep = serde_json::from_str("\"done\"").unwrap();
        assert_eq!(step, DeployStep::Done);
    }

    #[test]
    fn test_deploy_step_status_deserialization() {
        let status: DeployStepStatus = serde_json::from_str("\"started\"").unwrap();
        assert_eq!(status, DeployStepStatus::Started);

        let status: DeployStepStatus = serde_json::from_str("\"failed\"").unwrap();
        assert_eq!(status, DeployStepStatus::Failed);
    }
}
