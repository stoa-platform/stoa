//! Anti-Zombie Agent Detection
//!
//! Detects and terminates stale agent sessions (ADR-012).
//! Agents have a 10-minute TTL by default, with mandatory attestation.

use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

/// Zombie detection configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZombieConfig {
    /// Session TTL in seconds (default: 600 = 10 minutes per ADR-012)
    pub session_ttl_secs: u64,
    /// Grace period before marking as zombie (TTL * this factor)
    pub zombie_factor: f64,
    /// Require attestation every N requests
    pub attestation_interval: u64,
    /// Enable automatic token revocation
    pub auto_revoke: bool,
    /// Alert threshold (number of zombie sessions)
    pub alert_threshold: usize,
    /// Cleanup interval in seconds
    pub cleanup_interval_secs: u64,
}

impl Default for ZombieConfig {
    fn default() -> Self {
        Self {
            session_ttl_secs: 600, // 10 minutes (ADR-012)
            zombie_factor: 2.0,    // Mark as zombie after 2x TTL
            attestation_interval: 100,
            auto_revoke: true,
            alert_threshold: 10,
            cleanup_interval_secs: 60,
        }
    }
}

/// Session health status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SessionHealth {
    /// Active and healthy
    Healthy,
    /// Approaching TTL expiration
    Warning,
    /// TTL expired, pending cleanup
    Expired,
    /// Zombie session (no activity for 2x TTL)
    Zombie,
    /// Revoked by system
    Revoked,
}

/// Tracked session information
#[derive(Debug, Clone)]
pub struct TrackedSession {
    /// Session ID
    pub session_id: String,
    /// User/agent ID
    pub user_id: Option<String>,
    /// Tenant ID
    pub tenant_id: Option<String>,
    /// Session creation time
    pub created_at: DateTime<Utc>,
    /// Last activity time
    pub last_activity: DateTime<Utc>,
    /// Last attestation time
    pub last_attestation: DateTime<Utc>,
    /// Request count since creation
    pub request_count: u64,
    /// Request count since last attestation
    pub requests_since_attestation: u64,
    /// Current health status
    pub health: SessionHealth,
    /// Session metadata
    pub metadata: HashMap<String, String>,
}

impl TrackedSession {
    /// Create a new tracked session
    pub fn new(session_id: String) -> Self {
        let now = Utc::now();
        Self {
            session_id,
            user_id: None,
            tenant_id: None,
            created_at: now,
            last_activity: now,
            last_attestation: now,
            request_count: 0,
            requests_since_attestation: 0,
            health: SessionHealth::Healthy,
            metadata: HashMap::new(),
        }
    }

    /// Update last activity
    pub fn touch(&mut self) {
        self.last_activity = Utc::now();
        self.request_count += 1;
        self.requests_since_attestation += 1;
    }

    /// Record attestation
    pub fn attest(&mut self) {
        self.last_attestation = Utc::now();
        self.requests_since_attestation = 0;
    }

    /// Calculate time since last activity
    pub fn idle_duration(&self) -> Duration {
        Utc::now() - self.last_activity
    }

    /// Calculate session age
    pub fn age(&self) -> Duration {
        Utc::now() - self.created_at
    }
}

/// Zombie alert event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZombieAlert {
    /// Alert ID
    pub id: String,
    /// Alert timestamp
    pub timestamp: DateTime<Utc>,
    /// Alert severity
    pub severity: AlertSeverity,
    /// Session ID
    pub session_id: String,
    /// User/agent ID
    pub user_id: Option<String>,
    /// Tenant ID
    pub tenant_id: Option<String>,
    /// Idle duration in seconds
    pub idle_secs: i64,
    /// Action taken
    pub action: ZombieAction,
    /// Alert message
    pub message: String,
}

/// Alert severity levels
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AlertSeverity {
    /// Informational
    Info,
    /// Warning - approaching zombie state
    Warning,
    /// Critical - zombie detected
    Critical,
}

/// Action taken on zombie session
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ZombieAction {
    /// Logged only
    Logged,
    /// Alert sent
    Alerted,
    /// Session revoked
    Revoked,
    /// Token invalidated
    TokenInvalidated,
}

/// Zombie session detector
pub struct ZombieDetector {
    /// Configuration
    config: ZombieConfig,
    /// Tracked sessions
    sessions: Arc<RwLock<HashMap<String, TrackedSession>>>,
    /// Alert history
    alerts: Arc<RwLock<Vec<ZombieAlert>>>,
    /// Revoked session IDs
    revoked: Arc<RwLock<std::collections::HashSet<String>>>,
}

impl ZombieDetector {
    /// Create a new zombie detector
    pub fn new(config: ZombieConfig) -> Self {
        Self {
            config,
            sessions: Arc::new(RwLock::new(HashMap::new())),
            alerts: Arc::new(RwLock::new(Vec::new())),
            revoked: Arc::new(RwLock::new(std::collections::HashSet::new())),
        }
    }

    /// Start a new session
    pub async fn start_session(
        &self,
        session_id: &str,
        user_id: Option<String>,
        tenant_id: Option<String>,
    ) {
        let mut session = TrackedSession::new(session_id.to_string());
        session.user_id = user_id.clone();
        session.tenant_id = tenant_id.clone();

        let mut sessions = self.sessions.write().await;
        sessions.insert(session_id.to_string(), session);

        debug!(
            session_id = %session_id,
            user_id = ?user_id,
            tenant_id = ?tenant_id,
            ttl_secs = %self.config.session_ttl_secs,
            "Started tracking new session"
        );
    }

    /// Record session activity
    pub async fn record_activity(&self, session_id: &str) -> Result<SessionHealth, ZombieError> {
        // Check if session is revoked
        if self.revoked.read().await.contains(session_id) {
            return Err(ZombieError::SessionRevoked);
        }

        let mut sessions = self.sessions.write().await;

        if let Some(session) = sessions.get_mut(session_id) {
            // Check if attestation is required BEFORE recording activity
            if session.requests_since_attestation >= self.config.attestation_interval {
                return Err(ZombieError::AttestationRequired);
            }

            session.touch();

            // Update health based on idle time
            let idle_secs = session.idle_duration().num_seconds();
            let ttl = self.config.session_ttl_secs as i64;

            session.health = if idle_secs < ttl {
                SessionHealth::Healthy
            } else if idle_secs < (ttl as f64 * self.config.zombie_factor) as i64 {
                SessionHealth::Warning
            } else {
                SessionHealth::Expired
            };

            Ok(session.health)
        } else {
            Err(ZombieError::SessionNotFound)
        }
    }

    /// Record attestation for a session
    pub async fn record_attestation(&self, session_id: &str) -> Result<(), ZombieError> {
        if self.revoked.read().await.contains(session_id) {
            return Err(ZombieError::SessionRevoked);
        }

        let mut sessions = self.sessions.write().await;

        if let Some(session) = sessions.get_mut(session_id) {
            session.attest();
            info!(session_id = %session_id, "Session attestation recorded");
            Ok(())
        } else {
            Err(ZombieError::SessionNotFound)
        }
    }

    /// Check all sessions for zombies
    pub async fn check_zombies(&self) -> Vec<ZombieAlert> {
        let mut sessions = self.sessions.write().await;
        let mut new_alerts = Vec::new();

        let ttl_secs = self.config.session_ttl_secs as i64;
        let zombie_threshold = (ttl_secs as f64 * self.config.zombie_factor) as i64;

        for session in sessions.values_mut() {
            let idle_secs = session.idle_duration().num_seconds();

            // Check for zombie state
            if idle_secs >= zombie_threshold
                && session.health != SessionHealth::Zombie
                && session.health != SessionHealth::Revoked
            {
                session.health = SessionHealth::Zombie;

                let alert = ZombieAlert {
                    id: uuid::Uuid::new_v4().to_string(),
                    timestamp: Utc::now(),
                    severity: AlertSeverity::Critical,
                    session_id: session.session_id.clone(),
                    user_id: session.user_id.clone(),
                    tenant_id: session.tenant_id.clone(),
                    idle_secs,
                    action: if self.config.auto_revoke {
                        ZombieAction::Revoked
                    } else {
                        ZombieAction::Alerted
                    },
                    message: format!(
                        "Zombie session detected: {} idle for {}s (threshold: {}s)",
                        session.session_id, idle_secs, zombie_threshold
                    ),
                };

                warn!(
                    session_id = %session.session_id,
                    idle_secs = %idle_secs,
                    user_id = ?session.user_id,
                    "Zombie session detected"
                );

                new_alerts.push(alert);

                // Auto-revoke if enabled
                if self.config.auto_revoke {
                    session.health = SessionHealth::Revoked;
                }
            } else if idle_secs >= ttl_secs && session.health == SessionHealth::Healthy {
                // Warning state
                session.health = SessionHealth::Warning;

                let alert = ZombieAlert {
                    id: uuid::Uuid::new_v4().to_string(),
                    timestamp: Utc::now(),
                    severity: AlertSeverity::Warning,
                    session_id: session.session_id.clone(),
                    user_id: session.user_id.clone(),
                    tenant_id: session.tenant_id.clone(),
                    idle_secs,
                    action: ZombieAction::Logged,
                    message: format!(
                        "Session approaching zombie state: {} idle for {}s (TTL: {}s)",
                        session.session_id, idle_secs, ttl_secs
                    ),
                };

                debug!(
                    session_id = %session.session_id,
                    idle_secs = %idle_secs,
                    "Session approaching TTL"
                );

                new_alerts.push(alert);
            }
        }

        // Store alerts
        if !new_alerts.is_empty() {
            let mut alerts = self.alerts.write().await;
            alerts.extend(new_alerts.clone());
        }

        new_alerts
    }

    /// Revoke a session
    pub async fn revoke_session(&self, session_id: &str) -> Result<(), ZombieError> {
        let mut sessions = self.sessions.write().await;

        if let Some(session) = sessions.get_mut(session_id) {
            session.health = SessionHealth::Revoked;
            self.revoked.write().await.insert(session_id.to_string());

            info!(session_id = %session_id, "Session revoked");
            Ok(())
        } else {
            Err(ZombieError::SessionNotFound)
        }
    }

    /// Reap dead sessions (Revoked + Zombie) from the tracked map.
    /// Returns the IDs of reaped sessions for cross-removal from SessionManager.
    pub async fn reap_dead_sessions(&self) -> Vec<String> {
        let mut sessions = self.sessions.write().await;
        let reaped: Vec<String> = sessions
            .iter()
            .filter(|(_, s)| matches!(s.health, SessionHealth::Revoked | SessionHealth::Zombie))
            .map(|(id, _)| id.clone())
            .collect();
        for id in &reaped {
            sessions.remove(id);
        }
        if !reaped.is_empty() {
            info!(
                count = reaped.len(),
                "Reaped dead sessions (zombie/revoked)"
            );
        }
        reaped
    }

    /// End a session (normal termination)
    pub async fn end_session(&self, session_id: &str) {
        let mut sessions = self.sessions.write().await;
        if sessions.remove(session_id).is_some() {
            debug!(session_id = %session_id, "Session ended normally");
        }
    }

    /// Get session health
    pub async fn get_health(&self, session_id: &str) -> Option<SessionHealth> {
        if self.revoked.read().await.contains(session_id) {
            return Some(SessionHealth::Revoked);
        }

        self.sessions.read().await.get(session_id).map(|s| s.health)
    }

    /// Get session info
    pub async fn get_session(&self, session_id: &str) -> Option<TrackedSession> {
        self.sessions.read().await.get(session_id).cloned()
    }

    /// Cleanup expired sessions
    pub async fn cleanup(&self) -> usize {
        let mut sessions = self.sessions.write().await;
        let zombie_threshold =
            (self.config.session_ttl_secs as f64 * self.config.zombie_factor * 2.0) as i64;

        let before = sessions.len();
        sessions.retain(|_, session| {
            let idle_secs = session.idle_duration().num_seconds();
            // Keep sessions with recent activity only
            idle_secs < zombie_threshold
        });

        let removed = before - sessions.len();
        if removed > 0 {
            info!(removed = %removed, "Cleaned up expired sessions");
        }

        removed
    }

    /// Get statistics
    pub async fn stats(&self) -> ZombieStats {
        let sessions = self.sessions.read().await;

        let mut healthy = 0;
        let mut warning = 0;
        let mut expired = 0;
        let mut zombie = 0;
        let mut revoked = 0;

        for session in sessions.values() {
            match session.health {
                SessionHealth::Healthy => healthy += 1,
                SessionHealth::Warning => warning += 1,
                SessionHealth::Expired => expired += 1,
                SessionHealth::Zombie => zombie += 1,
                SessionHealth::Revoked => revoked += 1,
            }
        }

        ZombieStats {
            total_sessions: sessions.len(),
            healthy,
            warning,
            expired,
            zombie,
            revoked,
            alerts_total: self.alerts.read().await.len(),
        }
    }

    /// Get recent alerts
    pub async fn recent_alerts(&self, limit: usize) -> Vec<ZombieAlert> {
        let alerts = self.alerts.read().await;
        alerts.iter().rev().take(limit).cloned().collect()
    }

    /// Check if zombie threshold is exceeded
    pub async fn is_alert_threshold_exceeded(&self) -> bool {
        let sessions = self.sessions.read().await;
        let zombie_count = sessions
            .values()
            .filter(|s| s.health == SessionHealth::Zombie)
            .count();
        zombie_count >= self.config.alert_threshold
    }
}

/// Zombie detection statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ZombieStats {
    /// Total tracked sessions
    pub total_sessions: usize,
    /// Healthy sessions
    pub healthy: usize,
    /// Sessions in warning state
    pub warning: usize,
    /// Expired sessions
    pub expired: usize,
    /// Zombie sessions
    pub zombie: usize,
    /// Revoked sessions
    pub revoked: usize,
    /// Total alerts generated
    pub alerts_total: usize,
}

/// Zombie detection errors
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ZombieError {
    /// Session not found
    SessionNotFound,
    /// Session has been revoked
    SessionRevoked,
    /// Attestation required
    AttestationRequired,
}

impl std::fmt::Display for ZombieError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ZombieError::SessionNotFound => write!(f, "Session not found"),
            ZombieError::SessionRevoked => write!(f, "Session has been revoked"),
            ZombieError::AttestationRequired => write!(f, "Session attestation required"),
        }
    }
}

impl std::error::Error for ZombieError {}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::time::sleep;

    #[tokio::test]
    async fn test_session_lifecycle() {
        let detector = ZombieDetector::new(ZombieConfig::default());

        // Start session
        detector
            .start_session("test-session", Some("user-1".to_string()), None)
            .await;

        // Record activity
        let health = detector.record_activity("test-session").await.unwrap();
        assert_eq!(health, SessionHealth::Healthy);

        // Get session
        let session = detector.get_session("test-session").await.unwrap();
        assert_eq!(session.request_count, 1);

        // End session
        detector.end_session("test-session").await;
        assert!(detector.get_session("test-session").await.is_none());
    }

    #[tokio::test]
    async fn test_session_not_found() {
        let detector = ZombieDetector::new(ZombieConfig::default());

        let result = detector.record_activity("non-existent").await;
        assert_eq!(result, Err(ZombieError::SessionNotFound));
    }

    #[tokio::test]
    async fn test_attestation_required() {
        let detector = ZombieDetector::new(ZombieConfig {
            attestation_interval: 2,
            ..Default::default()
        });

        detector.start_session("test-session", None, None).await;

        // First two requests ok
        detector.record_activity("test-session").await.unwrap();
        detector.record_activity("test-session").await.unwrap();

        // Third request requires attestation
        let result = detector.record_activity("test-session").await;
        assert_eq!(result, Err(ZombieError::AttestationRequired));

        // After attestation, activity allowed again
        detector.record_attestation("test-session").await.unwrap();
        let health = detector.record_activity("test-session").await.unwrap();
        assert_eq!(health, SessionHealth::Healthy);
    }

    #[tokio::test]
    async fn test_session_revocation() {
        let detector = ZombieDetector::new(ZombieConfig::default());

        detector.start_session("test-session", None, None).await;
        detector.revoke_session("test-session").await.unwrap();

        // Activity should fail
        let result = detector.record_activity("test-session").await;
        assert_eq!(result, Err(ZombieError::SessionRevoked));

        // Health should show revoked
        let health = detector.get_health("test-session").await.unwrap();
        assert_eq!(health, SessionHealth::Revoked);
    }

    #[tokio::test]
    async fn test_zombie_detection() {
        let detector = ZombieDetector::new(ZombieConfig {
            session_ttl_secs: 1, // 1 second TTL for testing
            zombie_factor: 2.0,  // 2 seconds to zombie
            auto_revoke: false,  // Don't auto-revoke for this test
            ..Default::default()
        });

        detector.start_session("test-session", None, None).await;

        // Wait for zombie threshold
        sleep(tokio::time::Duration::from_secs(3)).await;

        // Check for zombies
        let alerts = detector.check_zombies().await;

        // Should have warning and/or zombie alerts
        assert!(!alerts.is_empty());

        let health = detector.get_health("test-session").await.unwrap();
        assert_eq!(health, SessionHealth::Zombie);
    }

    #[tokio::test]
    async fn test_stats() {
        let detector = ZombieDetector::new(ZombieConfig::default());

        detector.start_session("session-1", None, None).await;
        detector.start_session("session-2", None, None).await;
        detector.start_session("session-3", None, None).await;
        detector.revoke_session("session-3").await.unwrap();

        let stats = detector.stats().await;
        assert_eq!(stats.total_sessions, 3);
        assert_eq!(stats.healthy, 2);
        assert_eq!(stats.revoked, 1);
    }

    #[tokio::test]
    async fn test_cleanup() {
        let detector = ZombieDetector::new(ZombieConfig {
            session_ttl_secs: 1,
            zombie_factor: 1.0,
            ..Default::default()
        });

        detector.start_session("test-session", None, None).await;

        // Wait for cleanup threshold (2 * zombie_factor * TTL)
        sleep(tokio::time::Duration::from_secs(3)).await;

        let removed = detector.cleanup().await;
        assert_eq!(removed, 1);
    }

    #[test]
    fn test_session_touch() {
        let mut session = TrackedSession::new("test".to_string());
        assert_eq!(session.request_count, 0);

        session.touch();
        assert_eq!(session.request_count, 1);
        assert_eq!(session.requests_since_attestation, 1);

        session.attest();
        assert_eq!(session.requests_since_attestation, 0);
    }
}
