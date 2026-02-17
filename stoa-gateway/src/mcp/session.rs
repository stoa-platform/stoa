//! MCP Session Manager
//!
//! Manages stateful SSE sessions with automatic TTL expiration.
//! Includes NotificationBus for pushing events to connected SSE clients (CAB-1178).

use axum::response::sse::Event;
use chrono::{DateTime, Duration, Utc};
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info, warn};

/// MCP Session
#[derive(Debug, Clone)]
pub struct Session {
    pub id: String,
    #[allow(dead_code)]
    pub tenant_id: String,
    #[allow(dead_code)]
    pub created_at: DateTime<Utc>,
    pub last_activity: DateTime<Utc>,
    #[allow(dead_code)]
    pub metadata: HashMap<String, String>,
}

impl Session {
    pub fn new(id: String, tenant_id: String) -> Self {
        let now = Utc::now();
        Self {
            id,
            tenant_id,
            created_at: now,
            last_activity: now,
            metadata: HashMap::new(),
        }
    }

    pub fn touch(&mut self) {
        self.last_activity = Utc::now();
    }

    pub fn is_expired(&self, ttl: Duration) -> bool {
        Utc::now() - self.last_activity > ttl
    }
}

/// Session Manager with TTL-based expiration and NotificationBus
pub struct SessionManager {
    sessions: Arc<RwLock<HashMap<String, Session>>>,
    /// NotificationBus: maps session_id -> SSE event sender (CAB-1178)
    channels: Arc<RwLock<HashMap<String, mpsc::Sender<Event>>>>,
    ttl: Duration,
}

impl SessionManager {
    pub fn new(ttl_minutes: i64) -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            channels: Arc::new(RwLock::new(HashMap::new())),
            ttl: Duration::minutes(ttl_minutes),
        }
    }

    /// Create a new session
    pub async fn create(&self, session: Session) {
        let id = session.id.clone();
        self.sessions.write().insert(id.clone(), session);
        debug!(session_id = %id, "Session created");
    }

    /// Get session by ID (and touch it)
    pub async fn get(&self, id: &str) -> Option<Session> {
        let mut sessions = self.sessions.write();
        if let Some(session) = sessions.get_mut(id) {
            session.touch();
            Some(session.clone())
        } else {
            None
        }
    }

    /// Remove session and its notification channel
    pub async fn remove(&self, id: &str) -> bool {
        self.channels.write().remove(id);
        self.sessions.write().remove(id).is_some()
    }

    /// Update session metadata
    pub async fn update_metadata(&self, id: &str, key: String, value: String) -> bool {
        let mut sessions = self.sessions.write();
        if let Some(session) = sessions.get_mut(id) {
            session.metadata.insert(key, value);
            session.touch();
            true
        } else {
            false
        }
    }

    /// Get session metadata value
    pub async fn get_metadata(&self, id: &str, key: &str) -> Option<String> {
        let sessions = self.sessions.read();
        sessions.get(id).and_then(|s| s.metadata.get(key).cloned())
    }

    // === NotificationBus (CAB-1178) ===

    /// Register an SSE event channel for a session.
    /// Called from handle_sse_get when a new SSE connection is established.
    pub fn register_channel(&self, session_id: &str, tx: mpsc::Sender<Event>) {
        self.channels.write().insert(session_id.to_string(), tx);
        debug!(session_id = %session_id, "NotificationBus: channel registered");
    }

    /// Unregister an SSE event channel (on disconnect or session cleanup).
    pub fn unregister_channel(&self, session_id: &str) {
        if self.channels.write().remove(session_id).is_some() {
            debug!(session_id = %session_id, "NotificationBus: channel unregistered");
        }
    }

    /// Broadcast an SSE event to all sessions belonging to a tenant.
    /// Uses try_send() for non-blocking delivery — slow consumers get events dropped.
    /// Returns the number of sessions that received the event.
    pub fn broadcast_to_tenant(&self, tenant_id: &str, event_type: &str, data: &str) -> usize {
        // Phase 1: collect matching session IDs (read lock on sessions)
        let matching_ids: Vec<String> = {
            let sessions = self.sessions.read();
            sessions
                .iter()
                .filter(|(_, s)| s.tenant_id == tenant_id)
                .map(|(id, _)| id.clone())
                .collect()
        };

        if matching_ids.is_empty() {
            return 0;
        }

        // Phase 2: send to matching channels (read lock on channels)
        let channels = self.channels.read();
        let mut sent = 0;
        for id in &matching_ids {
            if let Some(tx) = channels.get(id) {
                let evt = Event::default().event(event_type).data(data);
                match tx.try_send(evt) {
                    Ok(()) => sent += 1,
                    Err(mpsc::error::TrySendError::Full(_)) => {
                        warn!(
                            session_id = %id,
                            tenant_id = %tenant_id,
                            "NotificationBus: channel full, event dropped"
                        );
                    }
                    Err(mpsc::error::TrySendError::Closed(_)) => {
                        debug!(
                            session_id = %id,
                            "NotificationBus: channel closed (client disconnected)"
                        );
                    }
                }
            }
        }
        sent
    }

    /// Cleanup expired sessions and their channels
    pub fn cleanup_expired(&self) {
        // Phase 1: collect expired IDs (read lock)
        let expired_ids: Vec<String> = {
            let sessions = self.sessions.read();
            sessions
                .iter()
                .filter(|(_, session)| session.is_expired(self.ttl))
                .map(|(id, _)| id.clone())
                .collect()
        };

        if expired_ids.is_empty() {
            return;
        }

        // Phase 2: remove expired (write locks)
        {
            let mut sessions = self.sessions.write();
            let mut channels = self.channels.write();
            for id in &expired_ids {
                sessions.remove(id);
                channels.remove(id);
                debug!(session_id = %id, "Session expired");
            }
        }

        info!(removed = expired_ids.len(), "Cleaned up expired sessions");
    }

    /// Start background cleanup task
    pub fn start_cleanup_task(self: Arc<Self>) {
        let manager = self.clone();
        tokio::spawn(async move {
            // Cleanup every minute
            let mut cleanup_interval = interval(TokioDuration::from_secs(60));
            loop {
                cleanup_interval.tick().await;
                manager.cleanup_expired();
            }
        });
        info!(
            ttl_minutes = self.ttl.num_minutes(),
            "Session cleanup task started"
        );
    }

    /// Get active session count (for metrics)
    pub fn count(&self) -> usize {
        self.sessions.read().len()
    }
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new(30) // 30 min default TTL
    }
}

impl Clone for SessionManager {
    fn clone(&self) -> Self {
        Self {
            sessions: self.sessions.clone(),
            channels: self.channels.clone(),
            ttl: self.ttl,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_create_and_get() {
        let manager = SessionManager::new(30);
        let session = Session::new("test-1".into(), "tenant-1".into());

        manager.create(session).await;

        let retrieved = manager.get("test-1").await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().tenant_id, "tenant-1");
    }

    #[tokio::test]
    async fn test_remove() {
        let manager = SessionManager::new(30);
        let session = Session::new("test-1".into(), "tenant-1".into());

        manager.create(session).await;
        assert!(manager.remove("test-1").await);
        assert!(manager.get("test-1").await.is_none());
    }

    #[test]
    fn test_session_expiry() {
        let mut session = Session::new("test".into(), "tenant".into());
        let short_ttl = Duration::seconds(1);

        assert!(!session.is_expired(short_ttl));

        // Simulate old activity
        session.last_activity = Utc::now() - Duration::seconds(10);
        assert!(session.is_expired(short_ttl));
    }

    #[tokio::test]
    async fn test_update_metadata() {
        let manager = SessionManager::new(30);
        let session = Session::new("m-1".into(), "t-1".into());
        manager.create(session).await;

        assert!(
            manager
                .update_metadata("m-1", "key".into(), "val".into())
                .await
        );
        assert!(
            !manager
                .update_metadata("nonexistent", "k".into(), "v".into())
                .await
        );
    }

    #[tokio::test]
    async fn test_get_metadata() {
        let manager = SessionManager::new(30);
        let session = Session::new("m-2".into(), "t-1".into());
        manager.create(session).await;

        manager
            .update_metadata("m-2", "proto".into(), "2025-03-26".into())
            .await;
        assert_eq!(
            manager.get_metadata("m-2", "proto").await,
            Some("2025-03-26".to_string())
        );
        assert_eq!(manager.get_metadata("m-2", "missing").await, None);
        assert_eq!(manager.get_metadata("nonexistent", "proto").await, None);
    }

    #[test]
    fn test_cleanup_expired_sessions() {
        let manager = SessionManager::new(30);
        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            manager
                .create(Session::new("fresh".into(), "t".into()))
                .await;
            let mut old = Session::new("old".into(), "t".into());
            old.last_activity = Utc::now() - Duration::hours(1);
            manager.create(old).await;

            assert_eq!(manager.count(), 2);
            manager.cleanup_expired();
            assert_eq!(manager.count(), 1);
            assert!(manager.get("fresh").await.is_some());
            assert!(manager.get("old").await.is_none());
        });
    }

    #[test]
    fn test_count() {
        let manager = SessionManager::new(30);
        assert_eq!(manager.count(), 0);

        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            manager.create(Session::new("a".into(), "t".into())).await;
            assert_eq!(manager.count(), 1);
            manager.create(Session::new("b".into(), "t".into())).await;
            assert_eq!(manager.count(), 2);
            manager.remove("a").await;
            assert_eq!(manager.count(), 1);
        });
    }

    #[test]
    fn test_default_ttl() {
        let manager = SessionManager::default();
        assert_eq!(manager.ttl, Duration::minutes(30));
    }

    #[test]
    fn test_clone_shares_state() {
        let manager = SessionManager::new(30);
        let clone = manager.clone();

        let rt = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap();

        rt.block_on(async {
            manager
                .create(Session::new("shared".into(), "t".into()))
                .await;
            assert!(clone.get("shared").await.is_some());
        });
    }

    #[tokio::test]
    async fn test_get_nonexistent_session() {
        let manager = SessionManager::new(30);
        assert!(manager.get("does-not-exist").await.is_none());
    }

    // === NotificationBus Tests (CAB-1178) ===

    #[tokio::test]
    async fn test_register_and_unregister_channel() {
        let manager = SessionManager::new(30);
        let (tx, _rx) = mpsc::channel::<Event>(32);

        manager
            .create(Session::new("ch-1".into(), "t-1".into()))
            .await;
        manager.register_channel("ch-1", tx);
        assert_eq!(manager.channels.read().len(), 1);

        manager.unregister_channel("ch-1");
        assert_eq!(manager.channels.read().len(), 0);
    }

    #[tokio::test]
    async fn test_remove_also_removes_channel() {
        let manager = SessionManager::new(30);
        let (tx, _rx) = mpsc::channel::<Event>(32);

        manager
            .create(Session::new("ch-2".into(), "t-1".into()))
            .await;
        manager.register_channel("ch-2", tx);

        manager.remove("ch-2").await;
        assert_eq!(manager.channels.read().len(), 0);
    }

    #[tokio::test]
    async fn test_broadcast_to_tenant_sends_to_matching() {
        let manager = SessionManager::new(30);

        // Create sessions for two tenants
        manager
            .create(Session::new("s1".into(), "acme".into()))
            .await;
        manager
            .create(Session::new("s2".into(), "acme".into()))
            .await;
        manager
            .create(Session::new("s3".into(), "other".into()))
            .await;

        let (tx1, mut rx1) = mpsc::channel::<Event>(32);
        let (tx2, mut rx2) = mpsc::channel::<Event>(32);
        let (tx3, mut rx3) = mpsc::channel::<Event>(32);

        manager.register_channel("s1", tx1);
        manager.register_channel("s2", tx2);
        manager.register_channel("s3", tx3);

        let sent = manager.broadcast_to_tenant("acme", "test", "hello");

        assert_eq!(sent, 2);
        assert!(rx1.try_recv().is_ok());
        assert!(rx2.try_recv().is_ok());
        assert!(rx3.try_recv().is_err()); // "other" tenant — no event
    }

    #[tokio::test]
    async fn test_broadcast_no_matching_tenant() {
        let manager = SessionManager::new(30);
        manager
            .create(Session::new("s1".into(), "acme".into()))
            .await;

        let sent = manager.broadcast_to_tenant("nonexistent", "test", "hello");
        assert_eq!(sent, 0);
    }

    #[tokio::test]
    async fn test_cleanup_also_removes_channels() {
        let manager = SessionManager::new(30);

        let mut old = Session::new("old-ch".into(), "t".into());
        old.last_activity = Utc::now() - Duration::hours(1);
        manager.create(old).await;

        let (tx, _rx) = mpsc::channel::<Event>(32);
        manager.register_channel("old-ch", tx);

        manager.cleanup_expired();
        assert_eq!(manager.count(), 0);
        assert_eq!(manager.channels.read().len(), 0);
    }

    #[tokio::test]
    async fn test_broadcast_drops_for_full_channel() {
        let manager = SessionManager::new(30);
        manager
            .create(Session::new("full".into(), "t".into()))
            .await;

        // Create channel with capacity 1
        let (tx, _rx) = mpsc::channel::<Event>(1);
        manager.register_channel("full", tx);

        // Fill the channel
        manager.broadcast_to_tenant("t", "e1", "d1");

        // This should drop (channel full) but not panic
        let sent = manager.broadcast_to_tenant("t", "e2", "d2");
        // First call sent 1, second call: channel full → 0
        assert_eq!(sent, 0);
    }
}
