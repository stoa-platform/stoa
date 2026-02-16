//! MCP Session Manager
//!
//! Manages stateful SSE sessions with automatic TTL expiration.

use chrono::{DateTime, Duration, Utc};
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info};

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

/// Session Manager with TTL-based expiration
pub struct SessionManager {
    sessions: Arc<RwLock<HashMap<String, Session>>>,
    ttl: Duration,
}

impl SessionManager {
    pub fn new(ttl_minutes: i64) -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
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

    /// Remove session
    pub async fn remove(&self, id: &str) -> bool {
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

    /// Cleanup expired sessions
    pub fn cleanup_expired(&self) {
        let mut sessions = self.sessions.write();
        let before = sessions.len();

        sessions.retain(|id, session| {
            let keep = !session.is_expired(self.ttl);
            if !keep {
                debug!(session_id = %id, "Session expired");
            }
            keep
        });

        let removed = before - sessions.len();
        if removed > 0 {
            info!(
                removed = removed,
                remaining = sessions.len(),
                "Cleaned up expired sessions"
            );
        }
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
}
