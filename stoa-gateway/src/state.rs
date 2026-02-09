//! Application State
//!
//! Shared state across all handlers.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use parking_lot::RwLock;
use tracing::info;

use crate::auth::api_key::ApiKeyValidator;
use crate::auth::jwt::{JwtValidator, JwtValidatorConfig};
use crate::auth::oidc::{OidcProvider, OidcProviderConfig};
use crate::cache::{SemanticCache, SemanticCacheConfig};
use crate::config::Config;
use crate::control_plane::{OidcConfig, ToolProxyClient};
use crate::governance::zombie::{ZombieConfig, ZombieDetector};
use crate::mcp::session::SessionManager;
use crate::mcp::tools::ToolRegistry;
use crate::metering::{KafkaConfig, MeteringProducer, MeteringProducerConfig};
use crate::policy::{PolicyDecision, PolicyEngine, PolicyEngineConfig, PolicyInput};
use crate::quota::{ConsumerRateLimiter, QuotaManager, QuotaManagerConfig, RateLimiterConfig};
use crate::rate_limit::RateLimiter;
use crate::resilience::{CircuitBreaker, CircuitBreakerConfig};
use crate::routes::{PolicyRegistry, RouteRegistry};
use crate::uac::Action;

/// Application state shared across all handlers
#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    pub tool_registry: Arc<ToolRegistry>,
    pub session_manager: Arc<SessionManager>,
    pub rate_limiter: Arc<RateLimiter>,
    #[allow(dead_code)]
    pub api_key_validator: Arc<ApiKeyValidator>,
    pub uac_enforcer: Arc<UacEnforcer>,
    pub control_plane: Arc<ToolProxyClient>,
    pub route_registry: Arc<RouteRegistry>,
    pub policy_registry: Arc<PolicyRegistry>,
    /// JWT validator for user token authentication (None if Keycloak not configured)
    pub jwt_validator: Option<Arc<JwtValidator>>,
    /// Semantic cache for read-only tool responses (Phase 6)
    pub semantic_cache: Arc<SemanticCache>,
    /// Per-upstream circuit breakers (CAB-362). Key = upstream ID.
    /// The "cp-api" entry is the default for Control Plane API calls.
    pub circuit_breakers: Arc<RwLock<HashMap<String, Arc<CircuitBreaker>>>>,
    /// Circuit breaker config used when creating new per-upstream CBs
    pub cb_config: CircuitBreakerConfig,
    /// Kafka metering producer (Phase 3: CAB-1105)
    /// None if Kafka metering is disabled or unavailable.
    pub metering_producer: Option<Arc<MeteringProducer>>,
    /// Zombie session detector (CAB-362, ADR-012)
    pub zombie_detector: Arc<ZombieDetector>,
    /// Per-consumer rate limiter based on plan quotas (Phase 4: CAB-1121)
    pub consumer_rate_limiter: Arc<ConsumerRateLimiter>,
    /// Daily/monthly quota manager (Phase 4: CAB-1121)
    pub quota_manager: Arc<QuotaManager>,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let tool_registry = Arc::new(ToolRegistry::new());
        let mut session_mgr = SessionManager::new(config.mcp_session_ttl_minutes);
        // Zombie detector is set below after initialization
        let rate_limiter = Arc::new(RateLimiter::new(&config));
        let api_key_validator = Arc::new(ApiKeyValidator::new(&config));

        // Initialize Policy Engine (OPA)
        let policy_config = PolicyEngineConfig {
            policy_path: config.policy_path.clone(),
            enabled: config.policy_enabled,
            ..PolicyEngineConfig::default()
        };
        let policy_engine = match PolicyEngine::new(policy_config) {
            Ok(engine) => Arc::new(engine),
            Err(e) => {
                tracing::error!(error = %e, "Failed to initialize policy engine — using permissive fallback");
                // Create disabled engine as fallback
                Arc::new(
                    PolicyEngine::new(PolicyEngineConfig {
                        enabled: false,
                        ..PolicyEngineConfig::default()
                    })
                    .expect("Fallback policy engine"),
                )
            }
        };
        let uac_enforcer = Arc::new(UacEnforcer::new(policy_engine));

        let cp_url = config
            .control_plane_url
            .as_deref()
            .unwrap_or("http://localhost:8000");

        // Build OIDC config if Keycloak credentials are provided
        let oidc = match (
            &config.keycloak_url,
            &config.keycloak_client_id,
            &config.keycloak_client_secret,
        ) {
            (Some(url), Some(client_id), Some(client_secret)) => {
                let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
                let token_url = format!(
                    "{}/realms/{}/protocol/openid-connect/token",
                    url.trim_end_matches('/'),
                    realm
                );
                Some(OidcConfig {
                    token_url,
                    client_id: client_id.clone(),
                    client_secret: client_secret.clone(),
                })
            }
            _ => None,
        };

        let control_plane = Arc::new(ToolProxyClient::new(cp_url, oidc));
        let route_registry = Arc::new(RouteRegistry::new());
        let policy_registry = Arc::new(PolicyRegistry::new());

        // Build JWT validator if Keycloak is configured (for user token validation)
        let jwt_validator = if let Some(url) = &config.keycloak_url {
            let realm = config.keycloak_realm.as_deref().unwrap_or("stoa");
            let issuer_url = format!("{}/realms/{}", url.trim_end_matches('/'), realm);
            let client_id = config
                .keycloak_client_id
                .as_deref()
                .unwrap_or("stoa-mcp-gateway");

            let oidc_config = OidcProviderConfig {
                issuer_url,
                audience: client_id.to_string(),
                ..OidcProviderConfig::default()
            };
            let oidc_provider = Arc::new(OidcProvider::new(oidc_config));
            // Disable audience validation: user tokens come from various clients
            // (control-plane-ui, Claude.ai DCR, etc.) and won't have the gateway
            // client_id in their aud claim unless a Keycloak audience mapper is added.
            // Issuer + RS256 signature validation is sufficient.
            let jwt_config = JwtValidatorConfig {
                validate_audience: false,
                ..JwtValidatorConfig::default()
            };
            let validator = JwtValidator::with_config(oidc_provider, jwt_config);
            tracing::info!("JWT validator initialized for user token authentication");
            Some(Arc::new(validator))
        } else {
            tracing::warn!("Keycloak not configured — JWT user auth disabled");
            None
        };

        // Initialize semantic cache for tool responses (Phase 6)
        let semantic_cache = Arc::new(SemanticCache::new(SemanticCacheConfig::default()));
        tracing::info!("Semantic cache initialized");

        // Initialize per-upstream circuit breakers (CAB-362)
        let cb_config = CircuitBreakerConfig {
            failure_threshold: config.circuit_breaker_failure_threshold,
            reset_timeout: Duration::from_secs(config.circuit_breaker_reset_timeout_secs),
            success_threshold: config.circuit_breaker_success_threshold,
            window_size: Duration::from_secs(60),
        };
        let cp_circuit_breaker = CircuitBreaker::new("cp-api", cb_config.clone());
        let mut breakers = HashMap::new();
        breakers.insert("cp-api".to_string(), cp_circuit_breaker);
        let circuit_breakers = Arc::new(RwLock::new(breakers));
        info!(
            per_upstream = config.circuit_breaker_per_upstream,
            failure_threshold = config.circuit_breaker_failure_threshold,
            "Circuit breakers initialized (CAB-362)"
        );

        // Initialize zombie detector (CAB-362, ADR-012)
        let zombie_config = ZombieConfig {
            session_ttl_secs: config.agent_session_ttl_secs,
            zombie_factor: 2.0,
            attestation_interval: config.attestation_interval,
            auto_revoke: config.zombie_auto_revoke,
            alert_threshold: 10,
            cleanup_interval_secs: config.zombie_reaper_interval_secs,
        };
        let zombie_detector = Arc::new(ZombieDetector::new(zombie_config));
        if config.zombie_detection_enabled {
            // Wire zombie detector into session manager (CAB-362)
            session_mgr.set_zombie_detector(zombie_detector.clone());
            info!(
                ttl_secs = config.agent_session_ttl_secs,
                auto_revoke = config.zombie_auto_revoke,
                reaper_interval = config.zombie_reaper_interval_secs,
                "Zombie detector initialized (CAB-362)"
            );
        }
        let session_manager = Arc::new(session_mgr);

        // Initialize Kafka metering producer (Phase 3: CAB-1105)
        let metering_producer = if config.kafka_enabled {
            let kafka_config = KafkaConfig {
                brokers: config.kafka_brokers.clone(),
                metering_topic: config.kafka_metering_topic.clone(),
                errors_topic: config.kafka_errors_topic.clone(),
                enabled: true,
            };
            let producer_config = MeteringProducerConfig::from(&kafka_config);
            match MeteringProducer::new(producer_config) {
                Ok(producer) => {
                    tracing::info!(
                        brokers = %config.kafka_brokers,
                        "Kafka metering producer initialized"
                    );
                    Some(Arc::new(producer))
                }
                Err(e) => {
                    tracing::warn!(error = %e, "Kafka metering initialization failed");
                    None
                }
            }
        } else {
            tracing::info!("Kafka metering disabled (STOA_KAFKA_ENABLED=false)");
            None
        };

        // Initialize per-consumer quota enforcement (Phase 4: CAB-1121)
        let rate_limiter_config = RateLimiterConfig {
            default_rate_per_minute: config.quota_default_rate_per_minute,
            ..RateLimiterConfig::default()
        };
        let consumer_rate_limiter = Arc::new(ConsumerRateLimiter::new(rate_limiter_config));

        let quota_manager_config = QuotaManagerConfig {
            default_daily_limit: config.quota_default_daily_limit,
            ..QuotaManagerConfig::default()
        };
        let quota_manager = Arc::new(QuotaManager::new(quota_manager_config));

        if config.quota_enforcement_enabled {
            info!(
                default_rate_per_minute = config.quota_default_rate_per_minute,
                default_daily_limit = config.quota_default_daily_limit,
                "Quota enforcement enabled (CAB-1121)"
            );
        } else {
            info!("Quota enforcement disabled (STOA_QUOTA_ENFORCEMENT_ENABLED=false)");
        }

        Self {
            config,
            tool_registry,
            session_manager,
            rate_limiter,
            api_key_validator,
            uac_enforcer,
            control_plane,
            route_registry,
            policy_registry,
            jwt_validator,
            semantic_cache,
            circuit_breakers,
            cb_config,
            metering_producer,
            zombie_detector,
            consumer_rate_limiter,
            quota_manager,
        }
    }

    /// Get or create a circuit breaker for the given upstream ID.
    ///
    /// When `circuit_breaker_per_upstream` is true, each upstream gets its own CB.
    /// When false, all upstreams share the "cp-api" global CB.
    pub fn get_or_create_cb(&self, upstream_id: &str) -> Arc<CircuitBreaker> {
        // If per-upstream is disabled, always return the global "cp-api" CB
        let key = if self.config.circuit_breaker_per_upstream {
            upstream_id
        } else {
            "cp-api"
        };

        // Fast path: check if CB already exists (read lock)
        {
            let breakers = self.circuit_breakers.read();
            if let Some(cb) = breakers.get(key) {
                return cb.clone();
            }
        }

        // Slow path: create new CB (write lock)
        let mut breakers = self.circuit_breakers.write();
        // Double-check after acquiring write lock
        if let Some(cb) = breakers.get(key) {
            return cb.clone();
        }

        let cb = CircuitBreaker::new(key, self.cb_config.clone());
        breakers.insert(key.to_string(), cb.clone());
        tracing::debug!(upstream = %key, "Created new per-upstream circuit breaker");
        cb
    }

    /// Start background tasks
    pub fn start_background_tasks(&self) {
        // Start session cleanup
        self.session_manager.clone().start_cleanup_task();

        // Start rate limiter cleanup
        self.rate_limiter.clone().start_cleanup_task();

        // Start consumer rate limiter cleanup (Phase 4: CAB-1121)
        if self.config.quota_enforcement_enabled {
            self.consumer_rate_limiter.clone().start_cleanup_task();
            self.quota_manager.clone().start_reset_task();
        }

        // Start zombie reaper sweep (CAB-362)
        if self.config.zombie_detection_enabled {
            let detector = self.zombie_detector.clone();
            let session_manager = self.session_manager.clone();
            let interval_secs = self.config.zombie_reaper_interval_secs;
            let auto_revoke = self.config.zombie_auto_revoke;

            tokio::spawn(async move {
                let mut interval =
                    tokio::time::interval(tokio::time::Duration::from_secs(interval_secs));
                loop {
                    interval.tick().await;

                    let alerts = detector.check_zombies().await;
                    for alert in &alerts {
                        if alert.severity == crate::governance::zombie::AlertSeverity::Critical
                            && auto_revoke
                        {
                            // Revoke zombie session and remove from session manager
                            if let Err(e) = detector.revoke_session(&alert.session_id).await {
                                tracing::warn!(
                                    session_id = %alert.session_id,
                                    error = %e,
                                    "Failed to revoke zombie session"
                                );
                            } else {
                                session_manager.remove(&alert.session_id).await;
                                tracing::info!(
                                    session_id = %alert.session_id,
                                    "Zombie session revoked and removed"
                                );
                            }
                        }
                    }

                    // Cleanup very old sessions from zombie detector
                    let cleaned = detector.cleanup().await;
                    if cleaned > 0 {
                        tracing::debug!(cleaned, "Zombie detector cleanup completed");
                    }
                }
            });
            info!(
                interval_secs,
                "Zombie reaper background task started (CAB-362)"
            );
        }
    }
}

/// UAC Enforcer using OPA Policy Engine
///
/// Evaluates scope-based access control policies for tool invocations.
/// Implements ADR-012 12-Scope Model.
pub struct UacEnforcer {
    policy_engine: Arc<PolicyEngine>,
}

impl UacEnforcer {
    /// Create a new UAC enforcer with the given policy engine
    pub fn new(policy_engine: Arc<PolicyEngine>) -> Self {
        Self { policy_engine }
    }

    /// Get a reference to the policy engine (for SIGHUP reload)
    pub fn policy_engine(&self) -> &Arc<PolicyEngine> {
        &self.policy_engine
    }

    /// Check if a tool invocation is allowed (legacy signature for compatibility)
    #[allow(dead_code)]
    pub async fn check(&self, tenant_id: &str, action: Action) -> Result<(), String> {
        // Legacy check with empty context — allows all by default for backwards compat
        // New code should use check_with_context() for proper policy evaluation
        self.check_with_context(
            None,
            None,
            tenant_id,
            "unknown",
            action,
            vec!["stoa:read".to_string()], // Default read scope
            vec![],
        )
    }

    /// Check if a tool invocation is allowed with full context
    ///
    /// This is the primary method for policy evaluation. It builds a PolicyInput
    /// from the provided context and evaluates it against the OPA policy.
    #[allow(clippy::too_many_arguments)]
    pub fn check_with_context(
        &self,
        user_id: Option<String>,
        user_email: Option<String>,
        tenant_id: &str,
        tool_name: &str,
        action: Action,
        scopes: Vec<String>,
        roles: Vec<String>,
    ) -> Result<(), String> {
        let input = PolicyInput::new(
            user_id,
            user_email,
            tenant_id.to_string(),
            tool_name.to_string(),
            action,
            scopes,
            roles,
        );

        match self.policy_engine.evaluate(&input) {
            PolicyDecision::Allow => Ok(()),
            PolicyDecision::Deny { reason } => Err(reason),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::resilience::CircuitState;

    fn test_state() -> AppState {
        AppState::new(Config::default())
    }

    fn test_state_global_cb() -> AppState {
        let config = Config {
            circuit_breaker_per_upstream: false,
            ..Config::default()
        };
        AppState::new(config)
    }

    #[test]
    fn test_get_or_create_cb_returns_existing() {
        let state = test_state();
        // "cp-api" is created during AppState::new
        let cb1 = state.get_or_create_cb("cp-api");
        let cb2 = state.get_or_create_cb("cp-api");
        assert_eq!(cb1.name(), cb2.name());
        assert_eq!(cb1.name(), "cp-api");
    }

    #[test]
    fn test_get_or_create_cb_creates_new() {
        let state = test_state();
        let cb = state.get_or_create_cb("upstream-payments");
        assert_eq!(cb.name(), "upstream-payments");
        assert_eq!(cb.state(), CircuitState::Closed);

        // Verify it's now in the map
        let breakers = state.circuit_breakers.read();
        assert!(breakers.contains_key("upstream-payments"));
    }

    #[test]
    fn test_per_upstream_isolation() {
        let state = test_state();

        let cb_a = state.get_or_create_cb("upstream-A");
        let cb_b = state.get_or_create_cb("upstream-B");

        // Trip upstream-A
        for _ in 0..5 {
            cb_a.record_failure();
        }

        // upstream-A should be open, upstream-B still closed
        assert_eq!(cb_a.state(), CircuitState::Open);
        assert_eq!(cb_b.state(), CircuitState::Closed);
        assert!(cb_b.allow_request());
        assert!(!cb_a.allow_request());
    }

    #[test]
    fn test_global_cb_mode_shares_single_cb() {
        let state = test_state_global_cb();

        let cb_a = state.get_or_create_cb("upstream-A");
        let cb_b = state.get_or_create_cb("upstream-B");

        // Both should be the same "cp-api" CB
        assert_eq!(cb_a.name(), "cp-api");
        assert_eq!(cb_b.name(), "cp-api");

        // Trip via cb_a, cb_b should also see it
        for _ in 0..5 {
            cb_a.record_failure();
        }
        assert_eq!(cb_b.state(), CircuitState::Open);
    }

    #[test]
    fn test_cb_uses_config_thresholds() {
        let config = Config {
            circuit_breaker_failure_threshold: 2,
            circuit_breaker_success_threshold: 1,
            ..Config::default()
        };
        let state = AppState::new(config);

        let cb = state.get_or_create_cb("test-upstream");

        // Should trip after 2 failures (not default 5)
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Closed);
        cb.record_failure();
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_zombie_detector_initialized() {
        let state = test_state();
        // zombie_detector should be set
        assert!(Arc::strong_count(&state.zombie_detector) >= 1);
    }

    #[tokio::test]
    async fn test_zombie_detector_tracks_sessions() {
        let state = test_state();

        state
            .zombie_detector
            .start_session("sess-1", Some("user-1".to_string()), None)
            .await;

        let stats = state.zombie_detector.stats().await;
        assert_eq!(stats.total_sessions, 1);
        assert_eq!(stats.healthy, 1);
    }
}
