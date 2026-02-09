//! MCP Session Manager
//!
//! Manages stateful SSE sessions with automatic TTL expiration.
//! CAB-362: Integrates with ZombieDetector for session governance.

use chrono::{DateTime, Duration, Utc};
use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info, warn};

use crate::governance::zombie::{SessionHealth, ZombieDetector};

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
    /// Optional zombie detector for session governance (CAB-362)
    zombie_detector: Option<Arc<ZombieDetector>>,
}

impl SessionManager {
    pub fn new(ttl_minutes: i64) -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            ttl: Duration::minutes(ttl_minutes),
            zombie_detector: None,
        }
    }

    /// Set the zombie detector for session governance (CAB-362)
    pub fn set_zombie_detector(&mut self, detector: Arc<ZombieDetector>) {
        self.zombie_detector = Some(detector);
    }

    /// Create a new session (CAB-362: also starts zombie tracking)
    pub async fn create(&self, session: Session) {
        let id = session.id.clone();
        let tenant_id = session.tenant_id.clone();
        self.sessions.write().insert(id.clone(), session);
        debug!(session_id = %id, "Session created");

        // Register with zombie detector for tracking
        if let Some(ref detector) = self.zombie_detector {
            detector.start_session(&id, None, Some(tenant_id)).await;
        }
    }

    /// Get session by ID (and touch it)
    /// CAB-362: Also records activity with zombie detector.
    /// Returns None if session is zombie/revoked.
    pub async fn get(&self, id: &str) -> Option<Session> {
        // Check zombie health first
        if let Some(ref detector) = self.zombie_detector {
            match detector.record_activity(id).await {
                Ok(SessionHealth::Zombie) => {
                    warn!(session_id = %id, "Session is zombie — removing");
                    self.sessions.write().remove(id);
                    return None;
                }
                Ok(SessionHealth::Revoked) => {
                    warn!(session_id = %id, "Session is revoked — removing");
                    self.sessions.write().remove(id);
                    return None;
                }
                Err(crate::governance::zombie::ZombieError::SessionRevoked) => {
                    warn!(session_id = %id, "Session revoked by zombie detector");
                    self.sessions.write().remove(id);
                    return None;
                }
                // AttestationRequired and SessionNotFound are non-fatal for get()
                _ => {}
            }
        }

        let mut sessions = self.sessions.write();
        if let Some(session) = sessions.get_mut(id) {
            session.touch();
            Some(session.clone())
        } else {
            None
        }
    }

    /// Remove session (CAB-362: also ends zombie tracking)
    pub async fn remove(&self, id: &str) -> bool {
        let removed = self.sessions.write().remove(id).is_some();
        if removed {
            if let Some(ref detector) = self.zombie_detector {
                detector.end_session(id).await;
            }
        }
        removed
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
            zombie_detector: self.zombie_detector.clone(),
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

    // =========================================================================
    // Zombie Integration Tests (CAB-362)
    // =========================================================================

    #[tokio::test]
    async fn test_session_create_registers_with_zombie_detector() {
        use crate::governance::zombie::{ZombieConfig, ZombieDetector};

        let detector = Arc::new(ZombieDetector::new(ZombieConfig::default()));
        let mut manager = SessionManager::new(30);
        manager.set_zombie_detector(detector.clone());

        let session = Session::new("test-z1".into(), "tenant-1".into());
        manager.create(session).await;

        // Zombie detector should track the session
        let stats = detector.stats().await;
        assert_eq!(stats.total_sessions, 1);
    }

    #[tokio::test]
    async fn test_session_remove_ends_zombie_tracking() {
        use crate::governance::zombie::{ZombieConfig, ZombieDetector};

        let detector = Arc::new(ZombieDetector::new(ZombieConfig::default()));
        let mut manager = SessionManager::new(30);
        manager.set_zombie_detector(detector.clone());

        let session = Session::new("test-z2".into(), "tenant-1".into());
        manager.create(session).await;

        assert!(manager.remove("test-z2").await);

        // Zombie detector should no longer track the session
        let session_info = detector.get_session("test-z2").await;
        assert!(session_info.is_none());
    }

    #[tokio::test]
    async fn test_session_get_checks_zombie_health() {
        use crate::governance::zombie::{ZombieConfig, ZombieDetector};

        let detector = Arc::new(ZombieDetector::new(ZombieConfig {
            session_ttl_secs: 1,
            zombie_factor: 1.0,
            auto_revoke: true,
            ..ZombieConfig::default()
        }));
        let mut manager = SessionManager::new(30);
        manager.set_zombie_detector(detector.clone());

        let session = Session::new("test-z3".into(), "tenant-1".into());
        manager.create(session).await;

        // Wait for zombie threshold (1s * 1.0 = 1s), then run check + revoke
        // (simulates the background reaper task)
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        let alerts = detector.check_zombies().await;
        assert!(!alerts.is_empty());

        // Explicitly revoke (as the background sweep would do for Critical + auto_revoke)
        for alert in &alerts {
            let _ = detector.revoke_session(&alert.session_id).await;
        }

        // Now get() should detect the revoked session and remove it
        let result = manager.get("test-z3").await;
        assert!(result.is_none());
    }
}
