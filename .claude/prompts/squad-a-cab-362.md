CAB-362 — Circuit Breaker per-upstream + Zombie Session Reaper (stoa-gateway Rust).

Branch: `feat/cab-362-circuit-breaker-session`

## Etat actuel (code existant — NE PAS recréer)

### CircuitBreaker (`src/resilience/circuit_breaker.rs`, 335 lignes, 13 tests)
- Hystrix-style state machine complet: Closed → Open → HalfOpen
- Thread-safe: `RwLock` + `AtomicU64`
- Config: `failure_threshold`, `reset_timeout`, `success_threshold`, `window_size`
- Methods: `allow_request()`, `record_success()`, `record_failure()`, `call()`, `reset()`
- Stats: success/failure counts, consecutive_failures, open_count, rejected_count

### ZombieDetector (`src/governance/zombie.rs`, 648 lignes, 10 tests)
- Session tracking, TTL, attestation, ADR-012
- `ZombieConfig`: session_ttl_secs (600), zombie_factor (2.0), attestation_interval (100), auto_revoke
- `TrackedSession`: session_id, user_id, tenant_id, created/last_activity/last_attestation, request_count
- `SessionHealth`: Healthy → Warning → Expired → Zombie → Revoked
- `ZombieAlert` avec severity (Info/Warning/Critical) + action (Logged/Alerted/Revoked)

### SessionManager (`src/mcp/session.rs`, 200 lignes)
- Gere les sessions MCP SSE avec TTL (default 30 min)
- Background cleanup task toutes les 60s (`start_cleanup_task()`)
- Methods: `create()`, `get()`, `remove()`, `cleanup_expired()`
- DEJA dans AppState (`state.rs` ligne 49)

### AppState (`src/state.rs`)
- `cp_circuit_breaker: Arc<CircuitBreaker>` — UN SEUL CB global (ligne 40)
- `session_manager: Arc<SessionManager>` — (ligne 49)
- PAS de ZombieDetector dans AppState
- `start_background_tasks()` lance session cleanup (ligne 192)

### Admin endpoints (`src/handlers/admin.rs`)
- `GET /admin/circuit-breaker/stats` — stats du CB global
- `POST /admin/circuit-breaker/reset` — reset du CB global

### Config (`src/config.rs`)
- CB: AUCUN champ — utilise `CircuitBreakerConfig::default()` en dur
- Zombie: `zombie_detection_enabled` (true), `agent_session_ttl_secs` (600), `attestation_interval` (100)
- PAS de: zombie_factor, auto_revoke, cleanup_interval dans Config

## Ce qui manque (= tes taches)

### Tache 1: Per-upstream Circuit Breakers
Le CB actuel est global — un upstream lent trippe le CB pour TOUS les backends.

1. Dans `state.rs`: remplacer `cp_circuit_breaker: Arc<CircuitBreaker>` par:
   ```rust
   circuit_breakers: Arc<RwLock<HashMap<String, Arc<CircuitBreaker>>>>
   ```
   Avec une methode `get_or_create_cb(upstream_id: &str) -> Arc<CircuitBreaker>`

2. Dans `config.rs` ajouter:
   ```rust
   pub circuit_breaker_failure_threshold: u32,     // default 5
   pub circuit_breaker_reset_timeout_secs: u64,    // default 30
   pub circuit_breaker_success_threshold: u32,     // default 3
   pub circuit_breaker_per_upstream: bool,          // default true
   ```

3. Dans `handlers/admin.rs`:
   - `GET /admin/circuit-breakers` → liste tous les CBs avec stats par upstream
   - `POST /admin/circuit-breakers/:upstream_id/reset` → reset un CB specifique
   - Garder les anciens endpoints pour backward compat (deleguer au global)

4. Wire dans le request path: chercher ou `cp_circuit_breaker` est utilise et wrapper l'appel avec le CB per-upstream.

### Tache 2: Zombie Reaper Integration

1. Dans `state.rs`: ajouter `zombie_detector: Arc<ZombieDetector>` dans AppState
   - Init avec `ZombieConfig` depuis les champs config existants

2. Hook dans `session.rs`:
   - `SessionManager::create()` → appeler `zombie_detector.start_session()`
   - `SessionManager::get()` → appeler `zombie_detector.record_activity()`
   - Gerer `SessionHealth::Zombie` → log warn + close session

3. Background zombie sweep dans `start_background_tasks()`:
   - `tokio::spawn` loop: `check_zombies()` toutes les 60s
   - Sur alert Critical + auto_revoke: `revoke_session()` + log

4. Config: ajouter les champs manquants:
   ```rust
   pub zombie_reaper_interval_secs: u64,  // default 60
   pub zombie_auto_revoke: bool,           // default false
   ```

5. Admin endpoints:
   - `GET /admin/zombies/stats` → stats zombie detector
   - `GET /admin/zombies/alerts` → recent alerts (limit param)

### Tache 3: Tests

- Test per-upstream CB: upstream-A tripped, upstream-B still closed
- Test zombie reaper: session expiree detectee + nettoyee
- Test admin endpoints: GET stats retourne JSON correct
- Garder TOUS les tests existants verts (13 CB + 10 zombie)

## Regles

- Lis TOUT le code existant AVANT de coder: circuit_breaker.rs, zombie.rs, session.rs, config.rs, state.rs, handlers/admin.rs
- `cargo fmt --check` clean
- `RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings` zero warning
- `cargo test --all-features` tous les tests passent
- PAS de `todo!()`, `unimplemented!()`, `dbg!()` (SAST bloque)
- PAS de `.unwrap()` dans le code production (ok dans tests)
- Prefer `?` operator + `anyhow::Context` pour error handling
- Commit: `feat(gateway): per-upstream circuit breaker + zombie session reaper (CAB-362)`
