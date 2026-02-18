//! Daily/Monthly Quota Manager (Phase 4: CAB-1121)
//!
//! Tracks per-consumer request counts against daily and monthly limits.
//! Counters reset automatically at midnight (daily) and month start (monthly).
//!
//! Thread-safe via `parking_lot::RwLock` (non-poisoning).

use chrono::{Datelike, Utc};
use parking_lot::RwLock;
use serde::Serialize;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::time::{interval, Duration as TokioDuration};
use tracing::{debug, info};

use super::rate_limiter::PlanQuota;
use super::QuotaError;

/// Configuration for the quota manager.
#[derive(Debug, Clone)]
pub struct QuotaManagerConfig {
    /// Default daily request limit when no plan quota is set.
    pub default_daily_limit: u32,

    /// Background reset check interval in seconds.
    pub reset_check_interval_secs: u64,
}

impl Default for QuotaManagerConfig {
    fn default() -> Self {
        Self {
            default_daily_limit: 10_000,
            reset_check_interval_secs: 60,
        }
    }
}

/// Per-consumer quota state.
#[derive(Debug, Clone, Serialize)]
pub struct QuotaState {
    /// Number of requests today.
    pub daily_count: u64,
    /// Number of requests this month.
    pub monthly_count: u64,
    /// Day of year when daily counter was last reset.
    pub last_reset_day: u32,
    /// Month when monthly counter was last reset.
    pub last_reset_month: u32,
    /// Year of last reset (to handle year transitions).
    pub last_reset_year: i32,
}

impl QuotaState {
    fn new() -> Self {
        let now = Utc::now();
        Self {
            daily_count: 0,
            monthly_count: 0,
            last_reset_day: now.ordinal(),
            last_reset_month: now.month(),
            last_reset_year: now.year(),
        }
    }

    /// Check if daily counter needs reset.
    fn maybe_reset_daily(&mut self) {
        let now = Utc::now();
        if now.ordinal() != self.last_reset_day || now.year() != self.last_reset_year {
            debug!(
                old_day = self.last_reset_day,
                new_day = now.ordinal(),
                count = self.daily_count,
                "Resetting daily quota counter"
            );
            self.daily_count = 0;
            self.last_reset_day = now.ordinal();
            self.last_reset_year = now.year();
        }
    }

    /// Check if monthly counter needs reset.
    fn maybe_reset_monthly(&mut self) {
        let now = Utc::now();
        if now.month() != self.last_reset_month || now.year() != self.last_reset_year {
            debug!(
                old_month = self.last_reset_month,
                new_month = now.month(),
                count = self.monthly_count,
                "Resetting monthly quota counter"
            );
            self.monthly_count = 0;
            self.last_reset_month = now.month();
            self.last_reset_year = now.year();
        }
    }
}

/// Aggregated quota statistics for a consumer.
#[derive(Debug, Clone, Serialize)]
pub struct QuotaStats {
    pub consumer_id: String,
    pub daily_count: u64,
    pub daily_limit: u32,
    pub monthly_count: u64,
    pub monthly_limit: u32,
    pub daily_remaining: u64,
    pub monthly_remaining: u64,
}

/// Manages daily and monthly request quotas per consumer.
pub struct QuotaManager {
    states: Arc<RwLock<HashMap<String, QuotaState>>>,
    plan_quotas: Arc<RwLock<HashMap<String, PlanQuota>>>,
    config: QuotaManagerConfig,
}

impl QuotaManager {
    /// Create a new quota manager.
    pub fn new(config: QuotaManagerConfig) -> Self {
        Self {
            states: Arc::new(RwLock::new(HashMap::new())),
            plan_quotas: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }

    /// Set the plan quota for a consumer (shared with rate limiter).
    /// Called by admin API when CP pushes plan context via `upsert_policy`.
    pub fn set_plan_quota(&self, consumer_id: &str, quota: PlanQuota) {
        self.plan_quotas
            .write()
            .insert(consumer_id.to_string(), quota);
    }

    /// Check if the consumer has remaining quota.
    ///
    /// Does NOT increment the counter — call `record_request` after the
    /// request succeeds to avoid counting failed requests.
    pub fn check_quota(&self, consumer_id: &str) -> Result<(), QuotaError> {
        let quotas = self.plan_quotas.read();
        let default_quota = PlanQuota {
            daily_request_limit: self.config.default_daily_limit,
            ..PlanQuota::default()
        };
        let quota = quotas.get(consumer_id).unwrap_or(&default_quota);

        let mut states = self.states.write();
        let state = states
            .entry(consumer_id.to_string())
            .or_insert_with(QuotaState::new);

        // Auto-reset if day/month changed
        state.maybe_reset_daily();
        state.maybe_reset_monthly();

        // Check daily limit
        if quota.daily_request_limit > 0 && state.daily_count >= quota.daily_request_limit as u64 {
            return Err(QuotaError::DailyQuota {
                used: state.daily_count,
                limit: quota.daily_request_limit,
            });
        }

        // Check monthly limit
        if quota.monthly_request_limit > 0
            && state.monthly_count >= quota.monthly_request_limit as u64
        {
            return Err(QuotaError::MonthlyQuota {
                used: state.monthly_count,
                limit: quota.monthly_request_limit,
            });
        }

        Ok(())
    }

    /// Record a successful request (increment counters).
    pub fn record_request(&self, consumer_id: &str) {
        let mut states = self.states.write();
        let state = states
            .entry(consumer_id.to_string())
            .or_insert_with(QuotaState::new);

        state.maybe_reset_daily();
        state.maybe_reset_monthly();

        state.daily_count += 1;
        state.monthly_count += 1;
    }

    /// Get quota stats for a specific consumer.
    pub fn get_stats(&self, consumer_id: &str) -> Option<QuotaStats> {
        let quotas = self.plan_quotas.read();
        let default_quota = PlanQuota {
            daily_request_limit: self.config.default_daily_limit,
            ..PlanQuota::default()
        };
        let quota = quotas.get(consumer_id).unwrap_or(&default_quota);

        let mut states = self.states.write();
        let state = states.get_mut(consumer_id)?;

        state.maybe_reset_daily();
        state.maybe_reset_monthly();

        let daily_remaining = if quota.daily_request_limit > 0 {
            (quota.daily_request_limit as u64).saturating_sub(state.daily_count)
        } else {
            u64::MAX
        };
        let monthly_remaining = if quota.monthly_request_limit > 0 {
            (quota.monthly_request_limit as u64).saturating_sub(state.monthly_count)
        } else {
            u64::MAX
        };

        Some(QuotaStats {
            consumer_id: consumer_id.to_string(),
            daily_count: state.daily_count,
            daily_limit: quota.daily_request_limit,
            monthly_count: state.monthly_count,
            monthly_limit: quota.monthly_request_limit,
            daily_remaining,
            monthly_remaining,
        })
    }

    /// List all consumer quota states.
    pub fn list_all_stats(&self) -> Vec<QuotaStats> {
        let quotas = self.plan_quotas.read();
        let default_quota = PlanQuota {
            daily_request_limit: self.config.default_daily_limit,
            ..PlanQuota::default()
        };

        let mut states = self.states.write();
        states
            .iter_mut()
            .map(|(consumer_id, state)| {
                state.maybe_reset_daily();
                state.maybe_reset_monthly();

                let quota = quotas.get(consumer_id).unwrap_or(&default_quota);
                let daily_remaining = if quota.daily_request_limit > 0 {
                    (quota.daily_request_limit as u64).saturating_sub(state.daily_count)
                } else {
                    u64::MAX
                };
                let monthly_remaining = if quota.monthly_request_limit > 0 {
                    (quota.monthly_request_limit as u64).saturating_sub(state.monthly_count)
                } else {
                    u64::MAX
                };

                QuotaStats {
                    consumer_id: consumer_id.clone(),
                    daily_count: state.daily_count,
                    daily_limit: quota.daily_request_limit,
                    monthly_count: state.monthly_count,
                    monthly_limit: quota.monthly_request_limit,
                    daily_remaining,
                    monthly_remaining,
                }
            })
            .collect()
    }

    /// Reset quota counters for a consumer.
    pub fn reset_consumer(&self, consumer_id: &str) -> bool {
        let mut states = self.states.write();
        if let Some(state) = states.get_mut(consumer_id) {
            state.daily_count = 0;
            state.monthly_count = 0;
            let now = Utc::now();
            state.last_reset_day = now.ordinal();
            state.last_reset_month = now.month();
            state.last_reset_year = now.year();
            info!(consumer_id = %consumer_id, "Quota counters reset");
            true
        } else {
            false
        }
    }

    /// Run periodic reset check (called by background task).
    pub fn check_and_reset_expired(&self) {
        let mut states = self.states.write();
        for (consumer_id, state) in states.iter_mut() {
            let old_daily = state.daily_count;
            let old_monthly = state.monthly_count;
            state.maybe_reset_daily();
            state.maybe_reset_monthly();
            if state.daily_count != old_daily || state.monthly_count != old_monthly {
                debug!(
                    consumer_id = %consumer_id,
                    "Quota counters auto-reset by background task"
                );
            }
        }
    }

    /// Start background reset check task.
    pub fn start_reset_task(self: Arc<Self>) {
        let manager = self.clone();
        let interval_secs = self.config.reset_check_interval_secs;
        tokio::spawn(async move {
            let mut check_interval = interval(TokioDuration::from_secs(interval_secs));
            loop {
                check_interval.tick().await;
                manager.check_and_reset_expired();
            }
        });
        info!(
            interval_secs = interval_secs,
            "Quota manager reset task started"
        );
    }

    /// Get consumer count (for metrics).
    pub fn consumer_count(&self) -> usize {
        self.states.read().len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> QuotaManagerConfig {
        QuotaManagerConfig {
            default_daily_limit: 100,
            reset_check_interval_secs: 60,
        }
    }

    #[test]
    fn test_quota_allows_within_limit() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 5,
                monthly_request_limit: 100,
                ..Default::default()
            },
        );

        for _ in 0..5 {
            assert!(manager.check_quota("consumer-1").is_ok());
            manager.record_request("consumer-1");
        }
    }

    #[test]
    fn test_daily_quota_exceeded() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 3,
                monthly_request_limit: 0,
                ..Default::default()
            },
        );

        for _ in 0..3 {
            assert!(manager.check_quota("consumer-1").is_ok());
            manager.record_request("consumer-1");
        }

        let result = manager.check_quota("consumer-1");
        assert!(result.is_err());
        match result.unwrap_err() {
            QuotaError::DailyQuota { used, limit } => {
                assert_eq!(used, 3);
                assert_eq!(limit, 3);
            }
            other => panic!("Expected DailyQuota, got {:?}", other),
        }
    }

    #[test]
    fn test_monthly_quota_exceeded() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 0,
                monthly_request_limit: 2,
                ..Default::default()
            },
        );

        for _ in 0..2 {
            assert!(manager.check_quota("consumer-1").is_ok());
            manager.record_request("consumer-1");
        }

        let result = manager.check_quota("consumer-1");
        assert!(result.is_err());
        match result.unwrap_err() {
            QuotaError::MonthlyQuota { used, limit } => {
                assert_eq!(used, 2);
                assert_eq!(limit, 2);
            }
            other => panic!("Expected MonthlyQuota, got {:?}", other),
        }
    }

    #[test]
    fn test_separate_consumers() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 2,
                ..Default::default()
            },
        );
        manager.set_plan_quota(
            "consumer-2",
            PlanQuota {
                daily_request_limit: 2,
                ..Default::default()
            },
        );

        // Exhaust consumer-1
        for _ in 0..2 {
            manager.check_quota("consumer-1").unwrap();
            manager.record_request("consumer-1");
        }
        assert!(manager.check_quota("consumer-1").is_err());

        // consumer-2 should still be fine
        assert!(manager.check_quota("consumer-2").is_ok());
    }

    #[test]
    fn test_reset_consumer() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 2,
                ..Default::default()
            },
        );

        // Exhaust quota
        for _ in 0..2 {
            manager.check_quota("consumer-1").unwrap();
            manager.record_request("consumer-1");
        }
        assert!(manager.check_quota("consumer-1").is_err());

        // Reset
        assert!(manager.reset_consumer("consumer-1"));

        // Should be allowed again
        assert!(manager.check_quota("consumer-1").is_ok());
    }

    #[test]
    fn test_reset_nonexistent_consumer() {
        let manager = QuotaManager::new(test_config());
        assert!(!manager.reset_consumer("nonexistent"));
    }

    #[test]
    fn test_get_stats() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 100,
                monthly_request_limit: 1000,
                ..Default::default()
            },
        );

        // Record some requests
        for _ in 0..5 {
            manager.check_quota("consumer-1").unwrap();
            manager.record_request("consumer-1");
        }

        let stats = manager.get_stats("consumer-1").unwrap();
        assert_eq!(stats.consumer_id, "consumer-1");
        assert_eq!(stats.daily_count, 5);
        assert_eq!(stats.daily_limit, 100);
        assert_eq!(stats.daily_remaining, 95);
        assert_eq!(stats.monthly_count, 5);
        assert_eq!(stats.monthly_limit, 1000);
        assert_eq!(stats.monthly_remaining, 995);
    }

    #[test]
    fn test_list_all_stats() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 100,
                ..Default::default()
            },
        );
        manager.set_plan_quota(
            "consumer-2",
            PlanQuota {
                daily_request_limit: 200,
                ..Default::default()
            },
        );

        manager.record_request("consumer-1");
        manager.record_request("consumer-2");
        manager.record_request("consumer-2");

        let stats = manager.list_all_stats();
        assert_eq!(stats.len(), 2);
    }

    #[test]
    fn test_unlimited_quota() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 0,
                monthly_request_limit: 0,
                ..Default::default()
            },
        );

        // Should always pass
        for _ in 0..100 {
            assert!(manager.check_quota("consumer-1").is_ok());
            manager.record_request("consumer-1");
        }
    }

    #[test]
    fn test_default_quota_for_unknown_consumer() {
        let config = QuotaManagerConfig {
            default_daily_limit: 5,
            ..Default::default()
        };
        let manager = QuotaManager::new(config);

        // No explicit quota — uses default daily limit
        for _ in 0..5 {
            assert!(manager.check_quota("unknown").is_ok());
            manager.record_request("unknown");
        }
        assert!(manager.check_quota("unknown").is_err());
    }

    #[test]
    fn test_consumer_count() {
        let manager = QuotaManager::new(test_config());
        assert_eq!(manager.consumer_count(), 0);

        manager.record_request("consumer-1");
        assert_eq!(manager.consumer_count(), 1);

        manager.record_request("consumer-2");
        assert_eq!(manager.consumer_count(), 2);
    }

    #[test]
    fn test_check_and_reset_expired() {
        let manager = QuotaManager::new(test_config());
        manager.set_plan_quota(
            "consumer-1",
            PlanQuota {
                daily_request_limit: 100,
                ..Default::default()
            },
        );

        manager.record_request("consumer-1");

        // Running check — nothing should be reset (same day)
        manager.check_and_reset_expired();

        let stats = manager.get_stats("consumer-1").unwrap();
        assert_eq!(stats.daily_count, 1);
    }
}
