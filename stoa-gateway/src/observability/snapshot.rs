//! Error Snapshot — In-memory ring buffer with TTL (CAB-1645)
//!
//! Stores PII-masked request/response data for 5xx errors.
//! Ring buffer wraps at capacity; TTL eviction runs periodically.

use std::collections::HashMap;
use std::time::Instant;

use parking_lot::RwLock;
use serde::{Deserialize, Serialize};

/// A captured error snapshot with PII-masked data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ErrorSnapshot {
    pub request_id: String,
    /// Monotonic instant for TTL eviction (not serialized).
    #[serde(skip)]
    pub captured_at: Option<Instant>,
    /// RFC 3339 timestamp for API consumers.
    pub timestamp: String,
    pub method: String,
    pub path: String,
    pub status_code: u16,
    pub error_category: String,
    pub duration_ms: f64,
    /// Sanitized request headers (sensitive values redacted).
    pub request_headers: HashMap<String, String>,
    /// PII-masked request body excerpt (None if body was empty or not captured).
    pub request_body_excerpt: Option<String>,
    /// Sanitized response headers.
    pub response_headers: HashMap<String, String>,
    /// PII-masked response body excerpt.
    pub response_body_excerpt: Option<String>,
    /// Whether PII was found and redacted during capture.
    pub pii_found: bool,
}

/// In-memory ring buffer for error snapshots with TTL eviction.
pub struct SnapshotStore {
    inner: RwLock<StoreInner>,
    max_age_secs: u64,
    is_enabled: bool,
}

struct StoreInner {
    snapshots: Vec<ErrorSnapshot>,
    capacity: usize,
    next_index: usize,
}

impl StoreInner {
    fn new(capacity: usize) -> Self {
        Self {
            snapshots: Vec::with_capacity(capacity),
            capacity,
            next_index: 0,
        }
    }

    fn push(&mut self, snapshot: ErrorSnapshot) -> usize {
        let evicted = if self.snapshots.len() < self.capacity {
            self.snapshots.push(snapshot);
            0
        } else {
            self.snapshots[self.next_index] = snapshot;
            1 // overwrote an existing entry
        };
        self.next_index = (self.next_index + 1) % self.capacity;
        evicted
    }

    fn get(&self, request_id: &str) -> Option<&ErrorSnapshot> {
        self.snapshots.iter().find(|s| s.request_id == request_id)
    }

    fn list(&self, limit: usize, offset: usize) -> (Vec<&ErrorSnapshot>, usize) {
        let total = self.snapshots.len();
        if total == 0 || offset >= total {
            return (Vec::new(), total);
        }

        // Return newest first (same pattern as ReportBuffer::recent)
        let mut result = Vec::with_capacity(limit.min(total));
        let mut idx = if self.next_index == 0 {
            total.saturating_sub(1)
        } else {
            self.next_index - 1
        };

        // Skip `offset` entries
        for _ in 0..offset.min(total) {
            if idx == 0 {
                idx = total.saturating_sub(1);
            } else {
                idx -= 1;
            }
        }

        // Collect `limit` entries
        let remaining = total.saturating_sub(offset);
        for _ in 0..limit.min(remaining) {
            result.push(&self.snapshots[idx]);
            if idx == 0 {
                idx = total.saturating_sub(1);
            } else {
                idx -= 1;
            }
        }

        (result, total)
    }

    fn clear(&mut self) -> usize {
        let count = self.snapshots.len();
        self.snapshots.clear();
        self.next_index = 0;
        count
    }

    fn evict_expired(&mut self, max_age_secs: u64) -> usize {
        let now = Instant::now();
        let max_age = std::time::Duration::from_secs(max_age_secs);
        let before = self.snapshots.len();

        self.snapshots.retain(|s| {
            s.captured_at
                .map(|t| now.duration_since(t) < max_age)
                .unwrap_or(true)
        });

        let evicted = before - self.snapshots.len();
        // Reset next_index if we evicted entries
        if evicted > 0 {
            self.next_index = self.snapshots.len() % self.capacity.max(1);
        }
        evicted
    }

    fn len(&self) -> usize {
        self.snapshots.len()
    }
}

impl SnapshotStore {
    /// Create a new enabled store with the given capacity and TTL.
    pub fn new(capacity: usize, max_age_secs: u64) -> Self {
        Self {
            inner: RwLock::new(StoreInner::new(capacity)),
            max_age_secs,
            is_enabled: true,
        }
    }

    /// Create a disabled (no-op) store.
    pub fn disabled() -> Self {
        Self {
            inner: RwLock::new(StoreInner::new(0)),
            max_age_secs: 0,
            is_enabled: false,
        }
    }

    /// Whether the store is enabled.
    pub fn is_enabled(&self) -> bool {
        self.is_enabled
    }

    /// Push a snapshot into the store. Returns silently if disabled.
    pub fn push(&self, snapshot: ErrorSnapshot) {
        if !self.is_enabled {
            return;
        }
        let evicted = self.inner.write().push(snapshot);
        super::record_snapshot_captured();
        if evicted > 0 {
            super::record_evictions(evicted);
        }
        super::update_store_size(self.inner.read().len());
    }

    /// Look up a snapshot by request ID.
    pub fn get(&self, request_id: &str) -> Option<ErrorSnapshot> {
        self.inner.read().get(request_id).cloned()
    }

    /// List snapshots with pagination (newest first).
    pub fn list(&self, limit: usize, offset: usize) -> (Vec<ErrorSnapshot>, usize) {
        let guard = self.inner.read();
        let (refs, total) = guard.list(limit, offset);
        (refs.into_iter().cloned().collect(), total)
    }

    /// Clear all snapshots. Returns the number cleared.
    pub fn clear(&self) -> usize {
        let count = self.inner.write().clear();
        super::update_store_size(0);
        count
    }

    /// Evict snapshots older than max_age_secs.
    pub fn evict_expired(&self) {
        if !self.is_enabled {
            return;
        }
        let evicted = self.inner.write().evict_expired(self.max_age_secs);
        if evicted > 0 {
            super::record_evictions(evicted);
            super::update_store_size(self.inner.read().len());
        }
    }

    /// Current number of snapshots.
    pub fn len(&self) -> usize {
        self.inner.read().len()
    }

    /// Whether the store is empty.
    pub fn is_empty(&self) -> bool {
        self.inner.read().len() == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_snapshot(id: &str, status: u16) -> ErrorSnapshot {
        ErrorSnapshot {
            request_id: id.to_string(),
            captured_at: Some(Instant::now()),
            timestamp: "2026-03-18T12:00:00Z".to_string(),
            method: "POST".to_string(),
            path: "/api/test".to_string(),
            status_code: status,
            error_category: "backend".to_string(),
            duration_ms: 42.0,
            request_headers: HashMap::new(),
            request_body_excerpt: Some("masked body".to_string()),
            response_headers: HashMap::new(),
            response_body_excerpt: Some("error response".to_string()),
            pii_found: false,
        }
    }

    #[test]
    fn push_and_get() {
        let store = SnapshotStore::new(10, 3600);
        store.push(make_snapshot("req-1", 500));
        let snap = store.get("req-1");
        assert!(snap.is_some());
        assert_eq!(snap.as_ref().unwrap().status_code, 500);
    }

    #[test]
    fn get_not_found() {
        let store = SnapshotStore::new(10, 3600);
        assert!(store.get("nonexistent").is_none());
    }

    #[test]
    fn ring_buffer_wraps() {
        let store = SnapshotStore::new(3, 3600);
        for i in 0..5 {
            store.push(make_snapshot(&format!("req-{}", i), 500));
        }
        // Only last 3 should be present
        assert!(store.get("req-0").is_none());
        assert!(store.get("req-1").is_none());
        assert!(store.get("req-2").is_some());
        assert!(store.get("req-3").is_some());
        assert!(store.get("req-4").is_some());
    }

    #[test]
    fn ttl_eviction() {
        let store = SnapshotStore::new(10, 0); // 0 second TTL = everything expired
        let mut snap = make_snapshot("old", 500);
        snap.captured_at = Some(Instant::now() - std::time::Duration::from_secs(1));
        store.push(snap);

        assert_eq!(store.len(), 1);
        store.evict_expired();
        assert_eq!(store.len(), 0);
    }

    #[test]
    fn list_empty() {
        let store = SnapshotStore::new(10, 3600);
        let (items, total) = store.list(20, 0);
        assert!(items.is_empty());
        assert_eq!(total, 0);
    }

    #[test]
    fn list_with_pagination() {
        let store = SnapshotStore::new(10, 3600);
        for i in 0..5 {
            store.push(make_snapshot(&format!("req-{}", i), 500));
        }

        let (items, total) = store.list(2, 0);
        assert_eq!(total, 5);
        assert_eq!(items.len(), 2);
        // Newest first
        assert_eq!(items[0].request_id, "req-4");
        assert_eq!(items[1].request_id, "req-3");

        let (items2, _) = store.list(2, 2);
        assert_eq!(items2.len(), 2);
        assert_eq!(items2[0].request_id, "req-2");
        assert_eq!(items2[1].request_id, "req-1");
    }

    #[test]
    fn list_offset_beyond_total() {
        let store = SnapshotStore::new(10, 3600);
        store.push(make_snapshot("req-1", 500));
        let (items, total) = store.list(10, 100);
        assert!(items.is_empty());
        assert_eq!(total, 1);
    }

    #[test]
    fn clear_returns_count() {
        let store = SnapshotStore::new(10, 3600);
        store.push(make_snapshot("req-1", 500));
        store.push(make_snapshot("req-2", 502));
        let cleared = store.clear();
        assert_eq!(cleared, 2);
        assert!(store.is_empty());
    }

    #[test]
    fn disabled_store_noop() {
        let store = SnapshotStore::disabled();
        assert!(!store.is_enabled());
        store.push(make_snapshot("req-1", 500));
        assert!(store.get("req-1").is_none());
        assert!(store.is_empty());
    }

    #[test]
    fn serde_roundtrip() {
        let snap = make_snapshot("req-1", 503);
        let json = serde_json::to_string(&snap).expect("serialize");
        let back: ErrorSnapshot = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.request_id, "req-1");
        assert_eq!(back.status_code, 503);
        // captured_at is skipped in serde
        assert!(back.captured_at.is_none());
    }
}
