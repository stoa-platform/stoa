//! Event Polling Fallback (Phase 3: CAB-1179)
//!
//! In-memory ring buffer per tenant for HTTP polling.
//! `GET /mcp/events?since={iso}&types={comma}&limit={n}`
//! Fallback for MCP clients that don't support `notifications/send` via SSE.

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;

use axum::{extract::Query, extract::State, http::StatusCode, response::IntoResponse, Json};
use chrono::{DateTime, Duration, Utc};
use parking_lot::RwLock;
use serde::{Deserialize, Serialize};
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info};

use super::CnsEvent;
use crate::state::AppState;

/// Maximum events per tenant in the ring buffer
const MAX_EVENTS_PER_TENANT: usize = 1000;

/// Default TTL for buffered events (5 minutes)
const EVENT_TTL_SECS: i64 = 300;

/// Default limit for polling queries
const DEFAULT_POLL_LIMIT: usize = 100;

/// Per-tenant timestamped event ring buffer
type TenantBuffers = HashMap<String, VecDeque<(DateTime<Utc>, CnsEvent)>>;

/// In-memory event buffer for polling fallback
pub struct EventBuffer {
    buffers: Arc<RwLock<TenantBuffers>>,
}

impl Default for EventBuffer {
    fn default() -> Self {
        Self::new()
    }
}

impl EventBuffer {
    pub fn new() -> Self {
        Self {
            buffers: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Push an event to the tenant's ring buffer
    pub fn push(&self, event: CnsEvent) {
        let mut buffers = self.buffers.write();
        let buffer = buffers.entry(event.tenant_id.clone()).or_default();

        if buffer.len() >= MAX_EVENTS_PER_TENANT {
            buffer.pop_front();
        }

        buffer.push_back((Utc::now(), event));
    }

    /// Query events for a tenant with optional filters
    pub fn query(
        &self,
        tenant_id: &str,
        since: Option<DateTime<Utc>>,
        types: Option<&[String]>,
        limit: usize,
    ) -> Vec<CnsEvent> {
        let buffers = self.buffers.read();
        let Some(buffer) = buffers.get(tenant_id) else {
            return Vec::new();
        };

        buffer
            .iter()
            .filter(|(ts, _)| since.is_none_or(|s| *ts > s))
            .filter(|(_, evt)| {
                types.is_none_or(|t| t.iter().any(|prefix| evt.type_.starts_with(prefix)))
            })
            .take(limit)
            .map(|(_, evt)| evt.clone())
            .collect()
    }

    /// Remove events older than TTL
    pub fn cleanup_expired(&self) {
        let cutoff = Utc::now() - Duration::seconds(EVENT_TTL_SECS);
        let mut buffers = self.buffers.write();
        let mut total_removed = 0;

        for buffer in buffers.values_mut() {
            let before = buffer.len();
            buffer.retain(|(ts, _)| *ts > cutoff);
            total_removed += before - buffer.len();
        }

        buffers.retain(|_, buf| !buf.is_empty());

        if total_removed > 0 {
            debug!(
                removed = total_removed,
                "EventBuffer: cleaned expired events"
            );
        }
    }

    /// Start background cleanup task (every 60 seconds)
    pub fn start_cleanup_task(self: Arc<Self>) {
        let buffer = self.clone();
        tokio::spawn(async move {
            let mut cleanup_interval = interval(TokioDuration::from_secs(60));
            loop {
                cleanup_interval.tick().await;
                buffer.cleanup_expired();
            }
        });
        info!("EventBuffer cleanup task started (60s interval, {EVENT_TTL_SECS}s TTL)");
    }

    /// Get total event count across all tenants (for metrics)
    #[allow(dead_code)]
    pub fn count(&self) -> usize {
        self.buffers.read().values().map(|b| b.len()).sum()
    }
}

impl Clone for EventBuffer {
    fn clone(&self) -> Self {
        Self {
            buffers: self.buffers.clone(),
        }
    }
}

/// Query parameters for GET /mcp/events
#[derive(Debug, Deserialize)]
pub struct PollQuery {
    /// ISO-8601 timestamp — return events after this time
    pub since: Option<String>,
    /// Comma-separated event type prefixes to filter
    pub types: Option<String>,
    /// Maximum number of events to return (default: 100)
    pub limit: Option<usize>,
    /// Tenant ID (extracted from JWT in production, query param for dev)
    pub tenant_id: Option<String>,
}

/// Response for GET /mcp/events
#[derive(Debug, Serialize)]
pub struct PollResponse {
    pub events: Vec<CnsEvent>,
    pub count: usize,
    pub server_time: String,
}

/// GET /mcp/events — Polling fallback for MCP clients without SSE support
pub async fn poll_events(
    State(state): State<AppState>,
    Query(query): Query<PollQuery>,
) -> impl IntoResponse {
    let tenant_id = query.tenant_id.as_deref().unwrap_or("default");

    let since = query.since.as_ref().and_then(|s| {
        DateTime::parse_from_rfc3339(s)
            .ok()
            .map(|dt| dt.with_timezone(&Utc))
    });

    let types: Option<Vec<String>> = query
        .types
        .as_ref()
        .map(|t| t.split(',').map(|s| s.trim().to_string()).collect());

    let limit = query.limit.unwrap_or(DEFAULT_POLL_LIMIT).min(1000);

    let events = state
        .event_buffer
        .query(tenant_id, since, types.as_deref(), limit);

    let count = events.len();

    (
        StatusCode::OK,
        Json(PollResponse {
            events,
            count,
            server_time: Utc::now().to_rfc3339(),
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    fn make_event(id: &str, type_: &str, tenant: &str) -> CnsEvent {
        CnsEvent {
            id: id.into(),
            type_: type_.into(),
            source: "test".into(),
            tenant_id: tenant.into(),
            timestamp: Utc::now(),
            version: "1.0".into(),
            user_id: None,
            payload: Value::Null,
        }
    }

    #[test]
    fn test_push_and_query() {
        let buffer = EventBuffer::new();
        buffer.push(make_event("e1", "api-created", "acme"));
        buffer.push(make_event("e2", "api-deleted", "acme"));

        let events = buffer.query("acme", None, None, 100);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].id, "e1");
        assert_eq!(events[1].id, "e2");
    }

    #[test]
    fn test_query_tenant_isolation() {
        let buffer = EventBuffer::new();
        buffer.push(make_event("e1", "api-created", "acme"));
        buffer.push(make_event("e2", "api-created", "other"));

        assert_eq!(buffer.query("acme", None, None, 100).len(), 1);
        assert_eq!(buffer.query("other", None, None, 100).len(), 1);
    }

    #[test]
    fn test_query_type_filter() {
        let buffer = EventBuffer::new();
        buffer.push(make_event("e1", "api-created", "acme"));
        buffer.push(make_event("e2", "security-alert", "acme"));
        buffer.push(make_event("e3", "api-deleted", "acme"));

        let types = vec!["api".to_string()];
        let events = buffer.query("acme", None, Some(&types), 100);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].id, "e1");
        assert_eq!(events[1].id, "e3");
    }

    #[test]
    fn test_query_limit() {
        let buffer = EventBuffer::new();
        for i in 0..10 {
            buffer.push(make_event(&format!("e{i}"), "api-created", "acme"));
        }

        let events = buffer.query("acme", None, None, 3);
        assert_eq!(events.len(), 3);
    }

    #[test]
    fn test_ring_buffer_eviction() {
        let buffer = EventBuffer::new();
        for i in 0..MAX_EVENTS_PER_TENANT + 10 {
            buffer.push(make_event(&format!("e{i}"), "api-created", "acme"));
        }

        let events = buffer.query("acme", None, None, MAX_EVENTS_PER_TENANT + 100);
        assert_eq!(events.len(), MAX_EVENTS_PER_TENANT);
        assert_eq!(events[0].id, "e10");
    }

    #[test]
    fn test_query_nonexistent_tenant() {
        let buffer = EventBuffer::new();
        assert!(buffer.query("nonexistent", None, None, 100).is_empty());
    }

    #[test]
    fn test_count() {
        let buffer = EventBuffer::new();
        assert_eq!(buffer.count(), 0);

        buffer.push(make_event("e1", "api-created", "acme"));
        buffer.push(make_event("e2", "api-created", "other"));
        assert_eq!(buffer.count(), 2);
    }

    #[test]
    fn test_cleanup_keeps_fresh_events() {
        let buffer = EventBuffer::new();
        buffer.push(make_event("e1", "api-created", "acme"));

        buffer.cleanup_expired();
        assert_eq!(buffer.count(), 1);
    }

    #[test]
    fn test_clone_shares_state() {
        let buffer = EventBuffer::new();
        let clone = buffer.clone();

        buffer.push(make_event("e1", "api-created", "acme"));
        assert_eq!(clone.count(), 1);
    }
}
