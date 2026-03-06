//! HEGEMON Agent Lifecycle Events — Centralized metering via Kafka.
//!
//! Captures all agent lifecycle events in an in-memory ring buffer and
//! optionally publishes to Kafka topic `hegemon.agent_events`.
//!
//! Part of CAB-1709 Phase 5a (CAB-1720).

use std::collections::VecDeque;
use std::sync::Arc;

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

use crate::metering::MeteringProducer;

// =============================================================================
// Configuration
// =============================================================================

/// Maximum events retained in the ring buffer.
const DEFAULT_BUFFER_CAPACITY: usize = 1000;

/// Kafka topic for HEGEMON lifecycle events.
const KAFKA_TOPIC: &str = "hegemon.agent_events";

// =============================================================================
// Event Types
// =============================================================================

/// All possible HEGEMON lifecycle event types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    AgentAuthenticated,
    DispatchStarted,
    DispatchCompleted,
    ClaimReserved,
    ClaimReleased,
    BudgetChecked,
    BudgetRecorded,
    SupervisionBlocked,
}

impl EventType {
    fn as_str(&self) -> &'static str {
        match self {
            Self::AgentAuthenticated => "agent_authenticated",
            Self::DispatchStarted => "dispatch_started",
            Self::DispatchCompleted => "dispatch_completed",
            Self::ClaimReserved => "claim_reserved",
            Self::ClaimReleased => "claim_released",
            Self::BudgetChecked => "budget_checked",
            Self::BudgetRecorded => "budget_recorded",
            Self::SupervisionBlocked => "supervision_blocked",
        }
    }
}

/// A single lifecycle event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LifecycleEvent {
    pub event_type: EventType,
    pub agent_name: String,
    pub timestamp: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dispatch_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ticket_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mega_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub phase_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cost_usd: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

impl LifecycleEvent {
    pub fn new(event_type: EventType, agent_name: &str) -> Self {
        Self {
            event_type,
            agent_name: agent_name.to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            dispatch_id: None,
            ticket_id: None,
            mega_id: None,
            phase_id: None,
            cost_usd: None,
            detail: None,
        }
    }

    pub fn with_dispatch(mut self, dispatch_id: &str, ticket_id: &str) -> Self {
        self.dispatch_id = Some(dispatch_id.to_string());
        self.ticket_id = Some(ticket_id.to_string());
        self
    }

    pub fn with_claim(mut self, mega_id: &str, phase_id: &str) -> Self {
        self.mega_id = Some(mega_id.to_string());
        self.phase_id = Some(phase_id.to_string());
        self
    }

    pub fn with_cost(mut self, cost_usd: f64) -> Self {
        self.cost_usd = Some(cost_usd);
        self
    }

    pub fn with_detail(mut self, detail: &str) -> Self {
        self.detail = Some(detail.to_string());
        self
    }
}

// =============================================================================
// Event Buffer (Ring Buffer)
// =============================================================================

/// Thread-safe ring buffer for lifecycle events.
pub struct EventBuffer {
    events: RwLock<VecDeque<LifecycleEvent>>,
    capacity: usize,
}

impl Default for EventBuffer {
    fn default() -> Self {
        Self::new()
    }
}

impl EventBuffer {
    pub fn new() -> Self {
        Self {
            events: RwLock::new(VecDeque::with_capacity(DEFAULT_BUFFER_CAPACITY)),
            capacity: DEFAULT_BUFFER_CAPACITY,
        }
    }

    #[cfg(test)]
    pub fn with_capacity(capacity: usize) -> Self {
        Self {
            events: RwLock::new(VecDeque::with_capacity(capacity)),
            capacity,
        }
    }

    /// Push an event into the buffer, evicting oldest if at capacity.
    pub fn push(&self, event: LifecycleEvent) {
        let mut events = self.events.write();
        if events.len() >= self.capacity {
            events.pop_front();
        }
        events.push_back(event);
    }

    /// Get events since a given ISO timestamp, up to `limit`.
    pub fn since(&self, since: Option<&str>, limit: usize) -> Vec<LifecycleEvent> {
        let events = self.events.read();
        let iter = events.iter();

        let filtered: Box<dyn Iterator<Item = &LifecycleEvent> + '_> = if let Some(since_ts) = since
        {
            Box::new(iter.filter(move |e| e.timestamp.as_str() >= since_ts))
        } else {
            Box::new(iter)
        };

        // Return most recent events (tail of buffer)
        let collected: Vec<_> = filtered.cloned().collect();
        let start = if collected.len() > limit {
            collected.len() - limit
        } else {
            0
        };
        collected[start..].to_vec()
    }

    /// Get total event count in buffer.
    pub fn len(&self) -> usize {
        self.events.read().len()
    }

    /// Check if buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.events.read().is_empty()
    }

    /// Get all events (for dashboard aggregation).
    pub fn all(&self) -> Vec<LifecycleEvent> {
        self.events.read().iter().cloned().collect()
    }
}

// =============================================================================
// Metering Service
// =============================================================================

/// Centralized service for recording and publishing lifecycle events.
pub struct HegemonMetering {
    buffer: Arc<EventBuffer>,
    producer: Option<Arc<MeteringProducer>>,
}

impl HegemonMetering {
    pub fn new(producer: Option<Arc<MeteringProducer>>) -> Self {
        Self {
            buffer: Arc::new(EventBuffer::new()),
            producer,
        }
    }

    /// Record an event: buffer it and optionally publish to Kafka.
    pub fn record(&self, event: LifecycleEvent) {
        // Publish to Kafka (fire-and-forget)
        if let Some(ref producer) = self.producer {
            if let Ok(payload) = serde_json::to_string(&event) {
                producer.send_raw(KAFKA_TOPIC, event.event_type.as_str(), &payload);
            }
        }

        // Buffer for admin API
        self.buffer.push(event);
    }

    /// Get the event buffer (for admin endpoints).
    pub fn buffer(&self) -> &Arc<EventBuffer> {
        &self.buffer
    }
}

// =============================================================================
// Admin Handlers
// =============================================================================

use axum::extract::{Query, State};
use axum::response::IntoResponse;
use axum::Json;

#[derive(Deserialize)]
pub struct EventsQuery {
    since: Option<String>,
    limit: Option<usize>,
}

/// GET /admin/hegemon/events?since=&limit= — recent lifecycle events from buffer.
pub async fn list_events(
    State(state): State<crate::state::AppState>,
    Query(query): Query<EventsQuery>,
) -> impl IntoResponse {
    let Some(ref heg) = state.hegemon else {
        return Json(serde_json::json!({
            "error": "hegemon_disabled",
            "message": "HEGEMON module is not enabled"
        }))
        .into_response();
    };

    let limit = query.limit.unwrap_or(100).min(1000);
    let events = heg.metering.buffer().since(query.since.as_deref(), limit);

    Json(serde_json::json!({
        "events": events,
        "count": events.len(),
        "buffer_total": heg.metering.buffer().len(),
    }))
    .into_response()
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn make_event(event_type: EventType, agent: &str) -> LifecycleEvent {
        LifecycleEvent::new(event_type, agent)
    }

    #[test]
    fn test_event_buffer_push_and_retrieve() {
        let buffer = EventBuffer::new();
        buffer.push(make_event(EventType::AgentAuthenticated, "worker-1"));
        buffer.push(make_event(EventType::DispatchStarted, "worker-2"));

        assert_eq!(buffer.len(), 2);
        let events = buffer.since(None, 100);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].agent_name, "worker-1");
        assert_eq!(events[1].agent_name, "worker-2");
    }

    #[test]
    fn test_event_buffer_capacity_eviction() {
        let buffer = EventBuffer::with_capacity(3);
        for i in 0..5 {
            buffer.push(make_event(
                EventType::AgentAuthenticated,
                &format!("worker-{i}"),
            ));
        }

        assert_eq!(buffer.len(), 3);
        let events = buffer.all();
        // Oldest 2 evicted, remaining: worker-2, worker-3, worker-4
        assert_eq!(events[0].agent_name, "worker-2");
        assert_eq!(events[2].agent_name, "worker-4");
    }

    #[test]
    fn test_event_buffer_since_filter() {
        let buffer = EventBuffer::new();

        let mut e1 = make_event(EventType::AgentAuthenticated, "worker-1");
        e1.timestamp = "2026-03-06T10:00:00+00:00".to_string();
        buffer.push(e1);

        let mut e2 = make_event(EventType::DispatchStarted, "worker-2");
        e2.timestamp = "2026-03-06T12:00:00+00:00".to_string();
        buffer.push(e2);

        let mut e3 = make_event(EventType::DispatchCompleted, "worker-3");
        e3.timestamp = "2026-03-06T14:00:00+00:00".to_string();
        buffer.push(e3);

        let events = buffer.since(Some("2026-03-06T11:00:00+00:00"), 100);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].agent_name, "worker-2");
    }

    #[test]
    fn test_event_buffer_limit() {
        let buffer = EventBuffer::new();
        for i in 0..10 {
            buffer.push(make_event(EventType::BudgetChecked, &format!("worker-{i}")));
        }

        let events = buffer.since(None, 3);
        assert_eq!(events.len(), 3);
        // Should return the most recent 3
        assert_eq!(events[0].agent_name, "worker-7");
        assert_eq!(events[2].agent_name, "worker-9");
    }

    #[test]
    fn test_lifecycle_event_builder() {
        let event = LifecycleEvent::new(EventType::DispatchStarted, "worker-1")
            .with_dispatch("d-123", "CAB-100")
            .with_cost(1.5)
            .with_detail("starting phase 1");

        assert_eq!(event.agent_name, "worker-1");
        assert_eq!(event.dispatch_id, Some("d-123".to_string()));
        assert_eq!(event.ticket_id, Some("CAB-100".to_string()));
        assert_eq!(event.cost_usd, Some(1.5));
        assert_eq!(event.detail, Some("starting phase 1".to_string()));
        assert!(event.mega_id.is_none());
    }

    #[test]
    fn test_lifecycle_event_with_claim() {
        let event = LifecycleEvent::new(EventType::ClaimReserved, "worker-3")
            .with_claim("CAB-1709", "phase-2");

        assert_eq!(event.mega_id, Some("CAB-1709".to_string()));
        assert_eq!(event.phase_id, Some("phase-2".to_string()));
    }

    #[test]
    fn test_event_serialization() {
        let event = LifecycleEvent::new(EventType::SupervisionBlocked, "worker-5")
            .with_detail("tier=manual, action blocked");

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains("\"supervision_blocked\""));
        assert!(json.contains("\"worker-5\""));
        assert!(json.contains("tier=manual"));
        // Optional fields that are None should not appear
        assert!(!json.contains("dispatch_id"));
        assert!(!json.contains("mega_id"));
    }

    #[test]
    fn test_event_type_as_str() {
        assert_eq!(
            EventType::AgentAuthenticated.as_str(),
            "agent_authenticated"
        );
        assert_eq!(EventType::DispatchStarted.as_str(), "dispatch_started");
        assert_eq!(EventType::ClaimReserved.as_str(), "claim_reserved");
        assert_eq!(EventType::BudgetRecorded.as_str(), "budget_recorded");
    }

    #[test]
    fn test_metering_service_records_to_buffer() {
        let metering = HegemonMetering::new(None);
        metering.record(make_event(EventType::AgentAuthenticated, "worker-1"));
        metering.record(make_event(EventType::DispatchStarted, "worker-2"));

        assert_eq!(metering.buffer().len(), 2);
    }

    #[test]
    fn test_metering_service_no_kafka_graceful() {
        // No Kafka producer — should not panic
        let metering = HegemonMetering::new(None);
        metering.record(make_event(EventType::BudgetChecked, "worker-1"));
        assert_eq!(metering.buffer().len(), 1);
    }

    #[test]
    fn test_concurrent_buffer_writes() {
        let buffer = Arc::new(EventBuffer::new());
        let mut handles = vec![];

        for i in 0..10 {
            let buf = buffer.clone();
            handles.push(std::thread::spawn(move || {
                for j in 0..50 {
                    buf.push(make_event(
                        EventType::AgentAuthenticated,
                        &format!("worker-{i}-{j}"),
                    ));
                }
            }));
        }

        for h in handles {
            h.join().expect("thread join");
        }

        assert_eq!(buffer.len(), 500);
    }

    #[test]
    fn test_concurrent_buffer_at_capacity() {
        let buffer = Arc::new(EventBuffer::with_capacity(100));
        let mut handles = vec![];

        for i in 0..10 {
            let buf = buffer.clone();
            handles.push(std::thread::spawn(move || {
                for j in 0..50 {
                    buf.push(make_event(
                        EventType::DispatchStarted,
                        &format!("worker-{i}-{j}"),
                    ));
                }
            }));
        }

        for h in handles {
            h.join().expect("thread join");
        }

        // 500 writes, capacity 100 — should have exactly 100
        assert_eq!(buffer.len(), 100);
    }
}
