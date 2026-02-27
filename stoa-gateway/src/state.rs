//! Application State
//!
//! Shared state across all handlers.

use std::sync::Arc;
use std::time::Instant;

use crate::auth::api_key::ApiKeyValidator;
use crate::auth::jwt::{JwtValidator, JwtValidatorConfig};
use crate::auth::mtls::MtlsStats;
use crate::auth::oidc::{OidcProvider, OidcProviderConfig};
use crate::cache::{PromptCache, PromptCacheConfig, SemanticCache, SemanticCacheConfig};
use crate::config::Config;
use crate::control_plane::{OidcConfig, ToolProxyClient};
use crate::diagnostics::DiagnosticEngine;
use crate::events::polling::EventBuffer;
use crate::federation::FederationCache;
use crate::governance::zombie::{ZombieConfig, ZombieDetector};
use crate::guardrails::{GuardrailPolicyStore, TokenBudgetTracker};
use crate::mcp::pending_requests::PendingRequestTracker;
use crate::mcp::session::SessionManager;
use crate::mcp::tools::ToolRegistry;
use crate::metering::{KafkaConfig, MeteringProducer, MeteringProducerConfig};
use crate::policy::{PolicyDecision, PolicyEngine, PolicyEngineConfig, PolicyInput};
use crate::proxy::{ConsumerCredentialStore, CredentialStore};
use crate::quota::{
    BudgetCache, BudgetCacheConfig, ConsumerRateLimiter, QuotaManager, QuotaManagerConfig,
    RateLimiterConfig,
};
use crate::rate_limit::RateLimiter;
use crate::resilience::{
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerRegistry, FallbackChain,
};
use crate::routes::{PolicyRegistry, RouteRegistry};
use crate::skills::health::SkillHealthTracker;
use crate::skills::resolver::SkillResolver;
use crate::telemetry::deploy::DeployProgressEmitter;
use crate::uac::cache::VersionedPolicyCache;
use crate::uac::enforcer::ClassificationEnforcer;
use crate::uac::{Action, ContractRegistry};

/// Application state shared across all handlers
#[derive(Clone)]
pub struct AppState {
    pub config: Config,
    /// Timestamp when the gateway process started (for uptime tracking)
    pub start_time: Instant,
    pub tool_registry: Arc<ToolRegistry>,
    pub session_manager: Arc<SessionManager>,
    /// Tracks pending server-initiated requests (sampling, roots/list) across WS sessions.
    pub pending_requests: Arc<PendingRequestTracker>,
    pub rate_limiter: Arc<RateLimiter>,
    pub api_key_validator: Arc<ApiKeyValidator>,
    pub uac_enforcer: Arc<UacEnforcer>,
    pub control_plane: Arc<ToolProxyClient>,
    pub route_registry: Arc<RouteRegistry>,
    pub policy_registry: Arc<PolicyRegistry>,
    /// JWT validator for user token authentication (None if Keycloak not configured)
    pub jwt_validator: Option<Arc<JwtValidator>>,
    /// Semantic cache for read-only tool responses (Phase 6)
    pub semantic_cache: Arc<SemanticCache>,
    /// Circuit breaker for Control Plane API calls (Phase 6)
    pub cp_circuit_breaker: Arc<CircuitBreaker>,
    /// Kafka metering producer (Phase 3: CAB-1105)
    /// None if Kafka metering is disabled or unavailable.
    pub metering_producer: Option<Arc<MeteringProducer>>,
    /// Zombie session detector (CAB-362)
    /// None if zombie detection is disabled.
    pub zombie_detector: Option<Arc<ZombieDetector>>,
    /// Per-upstream circuit breaker registry (CAB-362)
    pub circuit_breakers: Arc<CircuitBreakerRegistry>,
    /// Fallback chain config for tool execution (CAB-708)
    pub fallback_chain: FallbackChain,
    /// mTLS validation stats (CAB-864)
    pub mtls_stats: Arc<MtlsStats>,
    /// Per-consumer rate limiter (CAB-1121 P4)
    pub consumer_rate_limiter: Arc<ConsumerRateLimiter>,
    /// Daily/monthly quota manager (CAB-1121 P4)
    pub quota_manager: Arc<QuotaManager>,
    /// BYOK credential store for backend API auth (CAB-1250)
    pub credential_store: Arc<CredentialStore>,
    /// Per-consumer credential store for backend API auth (CAB-1432)
    pub consumer_credential_store: Arc<ConsumerCredentialStore>,
    /// Event buffer for polling fallback (CAB-1179)
    pub event_buffer: Arc<EventBuffer>,
    /// UAC contract registry (CAB-1299)
    pub contract_registry: Arc<ContractRegistry>,
    /// Classification-based enforcer for contract routes (CAB-1299)
    /// None when classification enforcement is disabled.
    pub classification_enforcer: Option<Arc<ClassificationEnforcer>>,
    /// Skill resolver for CSS cascade context injection (CAB-1314)
    pub skill_resolver: Arc<SkillResolver>,
    /// Per-skill health tracker with circuit breaker (CAB-1551)
    pub skill_health: Arc<SkillHealthTracker>,
    /// Federation allow-list cache for sub-account routing (CAB-1362)
    pub federation_cache: Arc<FederationCache>,
    /// Per-tenant token budget tracker (CAB-1337 Phase 2)
    /// None when token budget tracking is disabled.
    pub token_budget: Option<Arc<TokenBudgetTracker>>,
    /// Per-tenant guardrail policy store (CAB-1337 Phase 3)
    /// Populated by K8s CRD watcher; empty store = all tenants use global defaults.
    pub guardrail_policy_store: Arc<GuardrailPolicyStore>,
    /// Deploy progress emitter for structured telemetry during API sync (CAB-1421)
    pub deploy_progress: DeployProgressEmitter,
    /// Prompt cache for reusable patterns across agent sessions (CAB-1123)
    pub prompt_cache: Arc<PromptCache>,
    /// Self-diagnostic engine for auto-RCA and hop detection (CAB-1316)
    pub diagnostic_engine: Arc<DiagnosticEngine>,
    /// Pull-based budget cache for department chargeback enforcement (CAB-1456)
    /// None when budget enforcement is disabled.
    pub budget_cache: Option<Arc<BudgetCache>>,
    /// Shared HTTP client with connection pooling (CAB-1542)
    /// Replaces per-request client creation in OAuth proxy and readiness check.
    pub http_client: reqwest::Client,
    /// TTL-cached Keycloak admin tokens keyed by "admin:{realm}" (CAB-1542)
    pub admin_token_cache: moka::sync::Cache<String, String>,
    /// Lazy MCP discovery with cache-first upstream probing (CAB-1552)
    pub mcp_discovery: Arc<crate::mcp::lazy_discovery::LazyMcpDiscovery>,
}

impl AppState {
    pub fn new(config: Config) -> Self {
        let tool_registry = Arc::new(ToolRegistry::new());
        let session_manager = Arc::new(SessionManager::new(config.mcp_session_ttl_minutes));
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

        // Initialize per-upstream circuit breaker registry (CAB-362, wired in CAB-1542 Phase 2)
        let cb_config = CircuitBreakerConfig {
            failure_threshold: config.cb_failure_threshold,
            reset_timeout: std::time::Duration::from_secs(config.cb_reset_timeout_secs),
            success_threshold: config.cb_success_threshold,
            ..CircuitBreakerConfig::default()
        };
        let circuit_breakers = Arc::new(CircuitBreakerRegistry::new(cb_config));
        tracing::info!("Per-upstream circuit breaker registry initialized");

        let control_plane = Arc::new(
            ToolProxyClient::new(cp_url, oidc).with_circuit_breakers(circuit_breakers.clone()),
        );
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
                internal_base_url: config.keycloak_internal_url.clone(),
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

        // Initialize circuit breaker for CP API (Phase 6)
        let cp_circuit_breaker = CircuitBreaker::new("cp-api", CircuitBreakerConfig::default());
        tracing::info!("Circuit breaker initialized for CP API");

        // Initialize zombie detector (CAB-362)
        let zombie_detector = if config.zombie_detection_enabled {
            let zd = Arc::new(ZombieDetector::new(ZombieConfig {
                session_ttl_secs: config.agent_session_ttl_secs,
                attestation_interval: config.attestation_interval,
                ..ZombieConfig::default()
            }));
            tracing::info!("Zombie session detector initialized");
            Some(zd)
        } else {
            tracing::info!("Zombie detection disabled");
            None
        };

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

        // Initialize per-consumer rate limiter (CAB-1121 P4)
        let consumer_rate_limiter = Arc::new(ConsumerRateLimiter::new(RateLimiterConfig {
            default_rate_per_minute: config.quota_default_rate_per_minute,
            ..RateLimiterConfig::default()
        }));
        if config.quota_enforcement_enabled {
            tracing::info!(
                rate_per_minute = config.quota_default_rate_per_minute,
                daily_limit = config.quota_default_daily_limit,
                "Consumer quota enforcement enabled"
            );
        } else {
            tracing::info!(
                "Consumer quota enforcement disabled (STOA_QUOTA_ENFORCEMENT_ENABLED=false)"
            );
        }

        // Initialize daily/monthly quota manager (CAB-1121 P4)
        let quota_manager = Arc::new(QuotaManager::new(QuotaManagerConfig {
            default_daily_limit: config.quota_default_daily_limit,
            reset_check_interval_secs: config.quota_sync_interval_secs,
        }));

        // Initialize fallback chain (CAB-708)
        let fallback_chain = FallbackChain::new(
            config.fallback_enabled,
            config.fallback_chains.as_deref(),
            config.fallback_timeout_ms,
        );

        // Initialize BYOK credential store (CAB-1250)
        let credential_store = Arc::new(CredentialStore::new());

        // Initialize per-consumer credential store (CAB-1432)
        let consumer_credential_store = Arc::new(ConsumerCredentialStore::new());

        // Initialize event buffer for polling fallback (CAB-1179)
        let event_buffer = Arc::new(EventBuffer::new());

        // Initialize UAC contract registry (CAB-1299)
        let contract_registry = Arc::new(ContractRegistry::new());

        // Initialize classification enforcer (CAB-1299) — soft mode
        let classification_enforcer = if config.classification_enforcement_enabled {
            let policy_cache = Arc::new(VersionedPolicyCache::new(3600));
            let enforcer = ClassificationEnforcer::new(policy_cache);
            tracing::info!("Classification enforcement enabled (soft mode — log only)");
            Some(Arc::new(enforcer))
        } else {
            tracing::info!("Classification enforcement disabled");
            None
        };

        // Initialize skill resolver (CAB-1314)
        let skill_resolver = Arc::new(SkillResolver::new(config.skill_cache_ttl_secs));
        tracing::info!(
            cache_ttl_secs = config.skill_cache_ttl_secs,
            "Skill resolver initialized"
        );

        // Initialize skill health tracker with circuit breaker (CAB-1551)
        let skill_cb_config = CircuitBreakerConfig {
            failure_threshold: config.cb_failure_threshold,
            reset_timeout: std::time::Duration::from_secs(config.cb_reset_timeout_secs),
            success_threshold: config.cb_success_threshold,
            ..CircuitBreakerConfig::default()
        };
        let skill_health = Arc::new(SkillHealthTracker::new(skill_cb_config));

        // Initialize federation cache (CAB-1362)
        let federation_cache = Arc::new(FederationCache::new(
            config.federation_cache_ttl_secs,
            config.federation_cache_max_entries,
            control_plane.clone(),
        ));
        if config.federation_enabled {
            tracing::info!(
                ttl_secs = config.federation_cache_ttl_secs,
                max_entries = config.federation_cache_max_entries,
                "Federation routing enabled"
            );
        } else {
            tracing::info!("Federation routing disabled (STOA_FEDERATION_ENABLED=false)");
        }

        // Initialize token budget tracker (CAB-1337 Phase 2)
        let token_budget = if config.token_budget_enabled {
            let window_secs = config.token_budget_window_hours * 3600;
            let tracker = Arc::new(TokenBudgetTracker::new(
                config.token_budget_default_limit,
                window_secs,
            ));
            tracing::info!(
                default_limit = config.token_budget_default_limit,
                window_hours = config.token_budget_window_hours,
                "Token budget tracker initialized"
            );
            Some(tracker)
        } else {
            tracing::info!("Token budget tracking disabled (STOA_TOKEN_BUDGET_ENABLED=false)");
            None
        };

        // Initialize mTLS stats (CAB-864)
        let mtls_stats = Arc::new(MtlsStats::new());
        if config.mtls.enabled {
            tracing::info!(
                require_binding = config.mtls.require_binding,
                trusted_proxies = config.mtls.trusted_proxies.len(),
                allowed_issuers = config.mtls.allowed_issuers.len(),
                "mTLS certificate validation enabled"
            );
        } else {
            tracing::info!("mTLS disabled (STOA_MTLS_ENABLED=false)");
        }

        // Initialize prompt cache (CAB-1123)
        let prompt_cache = Arc::new(PromptCache::new(PromptCacheConfig {
            max_entries: config.prompt_cache_max_entries,
            default_ttl: std::time::Duration::from_secs(config.prompt_cache_ttl_secs),
        }));

        // Initialize deploy progress emitter (CAB-1421)
        let deploy_progress = DeployProgressEmitter::new(
            config.kafka_deploy_progress_topic.clone(),
            metering_producer.clone(),
        );
        tracing::info!(
            topic = %config.kafka_deploy_progress_topic,
            kafka_enabled = config.kafka_enabled,
            "Deploy progress emitter initialized"
        );

        // Initialize budget cache (CAB-1456)
        let budget_cache = if config.budget_enforcement_enabled {
            let billing_url = config
                .billing_api_url
                .clone()
                .or_else(|| config.control_plane_url.clone())
                .unwrap_or_else(|| "http://localhost:8000".to_string());
            let cache = Arc::new(BudgetCache::new(BudgetCacheConfig {
                billing_api_url: billing_url.clone(),
                cache_ttl_secs: config.budget_cache_ttl_secs,
            }));
            tracing::info!(
                billing_api_url = %billing_url,
                cache_ttl_secs = config.budget_cache_ttl_secs,
                "Budget enforcement enabled"
            );
            Some(cache)
        } else {
            tracing::info!("Budget enforcement disabled (STOA_BUDGET_ENFORCEMENT_ENABLED=false)");
            None
        };

        // Initialize diagnostic engine (CAB-1316)
        let diagnostic_engine = Arc::new(DiagnosticEngine::new(1000));
        tracing::info!("Diagnostic engine initialized (buffer: 1000 reports)");

        // Shared HTTP client with connection pooling (CAB-1542)
        let http_client = reqwest::Client::builder()
            .pool_max_idle_per_host(20)
            .timeout(std::time::Duration::from_secs(15))
            .build()
            .unwrap_or_default();

        // Keycloak admin token cache: 4-min TTL, max 64 entries (CAB-1542)
        let admin_token_cache = moka::sync::Cache::builder()
            .max_capacity(64)
            .time_to_live(std::time::Duration::from_secs(240))
            .build();

        // Lazy MCP discovery: cache-first upstream probing (CAB-1552)
        let mcp_discovery = Arc::new(crate::mcp::lazy_discovery::LazyMcpDiscovery::new(
            &config,
            http_client.clone(),
            circuit_breakers.clone(),
        ));

        let start_time = Instant::now();

        Self {
            config,
            start_time,
            tool_registry,
            session_manager,
            pending_requests: Arc::new(PendingRequestTracker::new()),
            rate_limiter,
            api_key_validator,
            uac_enforcer,
            control_plane,
            route_registry,
            policy_registry,
            jwt_validator,
            semantic_cache,
            cp_circuit_breaker,
            metering_producer,
            zombie_detector,
            circuit_breakers,
            fallback_chain,
            mtls_stats,
            consumer_rate_limiter,
            quota_manager,
            credential_store,
            consumer_credential_store,
            event_buffer,
            contract_registry,
            classification_enforcer,
            skill_resolver,
            skill_health,
            federation_cache,
            token_budget,
            guardrail_policy_store: Arc::new(GuardrailPolicyStore::new()),
            deploy_progress,
            prompt_cache,
            diagnostic_engine,
            budget_cache,
            http_client,
            admin_token_cache,
            mcp_discovery,
        }
    }

    /// Start background tasks
    pub fn start_background_tasks(&self) {
        // Start prompt cache file watcher (CAB-1123)
        if let Some(ref watch_dir) = self.config.prompt_cache_watch_dir {
            crate::cache::watcher::spawn_cache_file_watcher(
                watch_dir.clone(),
                self.prompt_cache.clone(),
            );
        }

        // Start session cleanup
        self.session_manager.clone().start_cleanup_task();

        // Start rate limiter cleanup
        self.rate_limiter.clone().start_cleanup_task();

        // Start consumer rate limiter cleanup (CAB-1121 P4)
        if self.config.quota_enforcement_enabled {
            self.consumer_rate_limiter.clone().start_cleanup_task();
            self.quota_manager.clone().start_reset_task();
        }

        // Start event buffer cleanup (CAB-1179)
        self.event_buffer.clone().start_cleanup_task();

        // Start token budget sync task (CAB-1337 Phase 2)
        if let Some(ref tracker) = self.token_budget {
            TokenBudgetTracker::spawn_sync_task(tracker.clone());
        }

        // Start budget cache refresh task (CAB-1456)
        if let Some(ref cache) = self.budget_cache {
            cache.clone().start_refresh_task();
        }

        // Start zombie reaper (CAB-362)
        if let Some(ref zd) = self.zombie_detector {
            let zombie_detector = zd.clone();
            let session_manager = self.session_manager.clone();
            tokio::spawn(async move {
                let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(60));
                loop {
                    interval.tick().await;
                    // Mark zombies first
                    zombie_detector.check_zombies().await;
                    // Reap dead sessions and cross-remove from SessionManager
                    let reaped = zombie_detector.reap_dead_sessions().await;
                    for id in &reaped {
                        session_manager.remove(id).await;
                    }
                }
            });
            tracing::info!("Zombie reaper background task started (60s interval)");
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

/// Caller identity context for UAC policy evaluation.
#[derive(Debug, Clone)]
pub struct PolicyCallerCtx {
    pub user_id: Option<String>,
    pub user_email: Option<String>,
    pub scopes: Vec<String>,
    pub roles: Vec<String>,
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
    pub async fn check(&self, tenant_id: &str, action: Action) -> Result<(), String> {
        // Legacy check with empty context — allows all by default for backwards compat
        // New code should use check_with_context() for proper policy evaluation
        self.check_with_context(
            PolicyCallerCtx {
                user_id: None,
                user_email: None,
                scopes: vec!["stoa:read".to_string()],
                roles: vec![],
            },
            tenant_id,
            "unknown",
            action,
        )
    }

    /// Check if a tool invocation is allowed with full context
    ///
    /// This is the primary method for policy evaluation. It builds a PolicyInput
    /// from the provided context and evaluates it against the OPA policy.
    pub fn check_with_context(
        &self,
        caller: PolicyCallerCtx,
        tenant_id: &str,
        tool_name: &str,
        action: Action,
    ) -> Result<(), String> {
        let input = PolicyInput::new(
            caller.user_id,
            caller.user_email,
            tenant_id.to_string(),
            tool_name.to_string(),
            action,
            caller.scopes,
            caller.roles,
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

    fn make_disabled_enforcer() -> UacEnforcer {
        let engine = PolicyEngine::new(PolicyEngineConfig {
            enabled: false,
            ..PolicyEngineConfig::default()
        })
        .expect("disabled engine");
        UacEnforcer::new(Arc::new(engine))
    }

    fn make_enabled_enforcer() -> UacEnforcer {
        let engine = PolicyEngine::new(PolicyEngineConfig {
            enabled: true,
            ..PolicyEngineConfig::default()
        })
        .expect("enabled engine");
        UacEnforcer::new(Arc::new(engine))
    }

    #[test]
    fn disabled_enforcer_constructs() {
        let enforcer = make_disabled_enforcer();
        let _engine = enforcer.policy_engine();
    }

    #[test]
    fn enabled_enforcer_constructs() {
        let enforcer = make_enabled_enforcer();
        let _engine = enforcer.policy_engine();
    }

    #[test]
    fn disabled_engine_allows_read() {
        let enforcer = make_disabled_enforcer();
        let result = enforcer.check_with_context(
            PolicyCallerCtx {
                user_id: Some("user-1".into()),
                user_email: None,
                scopes: vec!["stoa:read".into()],
                roles: vec!["viewer".into()],
            },
            "tenant-1",
            "stoa_catalog",
            Action::Read,
        );
        assert!(result.is_ok());
    }

    #[test]
    fn disabled_engine_allows_admin() {
        let enforcer = make_disabled_enforcer();
        let result = enforcer.check_with_context(
            PolicyCallerCtx {
                user_id: Some("admin".into()),
                user_email: Some("admin@test.com".into()),
                scopes: vec!["stoa:admin".into()],
                roles: vec!["cpi-admin".into()],
            },
            "tenant-1",
            "stoa_security",
            Action::ManageContracts,
        );
        assert!(result.is_ok());
    }

    #[test]
    fn disabled_engine_allows_write() {
        let enforcer = make_disabled_enforcer();
        let result = enforcer.check_with_context(
            PolicyCallerCtx {
                user_id: None,
                user_email: None,
                scopes: vec![],
                roles: vec![],
            },
            "tenant-1",
            "stoa_subscription",
            Action::Create,
        );
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn legacy_check_disabled_engine_allows() {
        let enforcer = make_disabled_enforcer();
        let result = enforcer.check("tenant-1", Action::Read).await;
        assert!(result.is_ok());
    }

    #[test]
    fn start_time_tracks_uptime() {
        let before = Instant::now();
        std::thread::sleep(std::time::Duration::from_millis(10));
        let state = AppState::new(Config::default());
        let elapsed = state.start_time.elapsed();
        // start_time should have been set during AppState::new,
        // so elapsed should be small (well under 1 second)
        assert!(elapsed.as_secs() < 1);
        assert!(state.start_time >= before);
    }
}
