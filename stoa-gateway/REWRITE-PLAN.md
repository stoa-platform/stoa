# REWRITE-PLAN — GW-1: Éclater `handlers/admin.rs`

Statut: **Phase 1 validée 2026-04-22** avec 3 amendements (§ Amendements). **Phase 2 livrée** — 57/57 tests admin verts, full suite `cargo test` 2336 OK, clippy/fmt propres.

## Amendements post-review

1. **`admin.rs` reste comme façade pendant toute l'extraction.** Rust 2018 autorise `foo.rs` + enfants `foo/*.rs` coexistant; seul `foo.rs` + `foo/mod.rs` simultanés sont interdits. Pas de `git mv` atomique commit 1. Renommage éventuel vers `admin/mod.rs` reporté (probablement jamais — la façade `admin.rs` est la forme moderne).
2. **`contracts`**: pattern `contracts.rs` + `contracts/tests.rs`, **pas** de `contracts/mod.rs`. `#[cfg(test)] mod tests;` dans `contracts.rs` active `contracts/tests.rs` uniquement en build de tests.
3. **Chemin des test helpers**: depuis `#[cfg(test)] mod tests` placé dans `auth.rs` (ou n'importe quel sous-module), `super` désigne le sous-module (pas `admin`). Donc `use crate::handlers::admin::test_helpers::*;` (forme absolue, robuste) — alternative `use super::super::test_helpers::*;`. `test_helpers` n'a **pas** besoin d'être `pub(super)` comme déclaration ; pour accéder aux helpers depuis les sous-modules, ils sont `pub(super)` à l'intérieur.

## 0. Signaux de base

- Cible initiale: `src/handlers/admin.rs` = **2874 LOC** (≈ 1440 production + 1393 tests inline + séparateurs).
- Callers externes (hors `handlers/admin.rs`):
  - `src/lib.rs`: router wiring, 44 références à `admin::<handler>` + `admin::admin_auth` + `admin::routes_reload`.
  - `src/main.rs:60`: `stoa_gateway::handlers::admin::reload_routes_from_cp`.
  - `src/state.rs:723`: `crate::handlers::admin::reload_routes_from_cp`.
  - `tests/**`: **0 référence** (aucun import direct d'un symbole `admin::...`).
- Structure crate: `stoa-gateway` est une crate standalone (pas un workspace member).

## A. Inventaire par responsabilité

Production: lignes 1–1476. Tests: lignes 1482–2874 (57 `#[tokio::test]` + helpers + `sample_contract_json`).

| # | Responsabilité | Handlers | Types `pub` | LOC code | Tests | Module cible |
|---|---|---|---|---|---|---|
| 1 | Auth middleware | `admin_auth` | — | 31 | 5 | `auth.rs` |
| 2 | Health | `admin_health` | `AdminHealthResponse` | 23 | 2 | `health.rs` |
| 3 | API Routes CRUD | `upsert_api` (step-wise deploy), `list/get/delete_api` | — | 168 | 5 | `apis.rs` |
| 4 | Policies CRUD | `upsert/list/delete_policy` | — | 30 | 2 | `policies.rs` |
| 5 | Circuit Breaker (legacy CP) | `circuit_breaker_stats/reset` | `CircuitBreakerStatsResponse` | 39 | 2 | → `circuit_breaker.rs` |
| 6 | Semantic Cache | `cache_stats/clear` | `CacheStatsResponse` | 31 | 2 | → `cache.rs` |
| 7 | Prompt Cache | 5 handlers | `PromptCacheLoadEntry`, `PromptCacheLoadPayload` | 63 | 5 | `cache.rs` (fusion) |
| 8 | Sessions | `session_stats` | `SessionStatsResponse` | 27 | 1 | `sessions.rs` |
| 9 | Per-upstream Circuit Breakers | `circuit_breakers_list`, `circuit_breaker_reset_by_name` | — | 32 | 2 | `circuit_breaker.rs` (fusion) |
| 10 | mTLS | `mtls_config/stats` | — | 18 | 2 | `mtls.rs` |
| 11 | Quotas | 3 handlers | — | 41 | 3 | `quotas.rs` |
| 12 | Backend Credentials | `upsert/list/delete_backend_credential` | — | 78 | 4 | → `credentials.rs` |
| 13 | Consumer Credentials | `upsert/list/delete_consumer_credential` | `ConsumerCredentialPath` | 56 | 0 | `credentials.rs` (fusion) |
| 14 | UAC Contracts | 4 handlers (REST+MCP binders) | — | 135 | 16 | `contracts.rs` + `contracts/tests.rs` |
| 15 | Federation status/cache | 3 handlers | `FederationStatusResponse` | 41 | 3 | → `federation.rs` |
| 16 | Skills | 11 handlers | 5 types | 305 | 0 | `skills.rs` |
| 17 | LLM Routing | 3 handlers | 5 types | 148 | 0 | `llm.rs` |
| 18 | Tracing status | `tracing_status` | `TracingStatusResponse` | 18 | 1 | `tracing.rs` |
| 19 | Federation upstreams | `federation_upstreams` | 2 types | 41 | 1 | `federation.rs` (fusion) |
| 20 | Route hot-reload | `routes_reload`, `reload_routes_from_cp` | — | 76 | 0 | `reload.rs` |

**Total : 57 tests** (contracts a 16 tests — l'estimation Phase 1 de 14 était basse).

## B. Découpage livré

```
src/handlers/
├── admin.rs                 80   # FAÇADE — submod decls + pub use + `#[cfg(test)] mod test_helpers`
└── admin/
    ├── apis.rs             362   # Routes CRUD + 5 tests
    ├── auth.rs             151   # admin_auth + 5 tests
    ├── cache.rs            240   # semantic + prompt + 7 tests
    ├── circuit_breaker.rs  152   # legacy CP + per-upstream + 4 tests
    ├── contracts.rs        149   # CRUD UAC + `#[cfg(test)] mod tests;`
    ├── contracts/
    │   └── tests.rs        466   # 16 tests UAC contracts
    ├── credentials.rs      256   # backend + consumer + 4 tests
    ├── federation.rs       201   # status/cache/upstreams + 5 tests
    ├── health.rs            95   # admin_health + 2 tests
    ├── llm.rs              152   # routing/providers/costs (0 test)
    ├── mtls.rs              45   # config/stats + 2 tests
    ├── policies.rs          84   # CRUD + 2 tests
    ├── quotas.rs            91   # CRUD + 3 tests
    ├── reload.rs            79   # routes_reload + reload_routes_from_cp (0 test)
    ├── sessions.rs          55   # stats + 1 test
    ├── skills.rs           314   # 11 handlers (0 test inline préexistant)
    ├── test_helpers.rs     131   # helpers partagés (create_test_state, build_*_router, auth_req, auth_json_req)
    └── tracing.rs           48   # tracing_status + 1 test
```

**17 sous-fichiers** + façade + `contracts/tests.rs`. Tous ≤ 400 LOC sauf `contracts/tests.rs` (466 LOC, couvert par pattern § Amendement #2).

### B.1 Test helpers partagés

`admin/test_helpers.rs` héberge les 5 helpers génériques : `create_test_state`, `build_admin_router`, `build_full_admin_router`, `auth_req`, `auth_json_req`. Visibilité `pub(super)` pour être accessibles depuis tous les `#[cfg(test)] mod tests` des sous-modules via `use crate::handlers::admin::test_helpers::*;`.

`sample_contract_json` reste privé à `contracts/tests.rs`.

## C. Visibilité

**Split pur** (pas de tightening simultané). Tous les handlers et types restent `pub`, re-exportés explicitement depuis `admin.rs` pour préserver `crate::handlers::admin::<symbole>`. Aucune modification de `lib.rs` / `main.rs` / `state.rs`.

Tighten éventuel en Phase 2.5 séparée (non exécuté ici).

## D. Validation finale

- `cargo check` : ✔ zéro warning.
- `cargo fmt --check` : ✔ après `cargo fmt` initial (2 fichiers reformatés : `circuit_breaker.rs`, `federation.rs` — import group wrapping).
- `RUSTFLAGS=-Dwarnings cargo clippy --all-targets -- -D warnings` : ✔ zéro issue.
- `cargo test` full suite : **2336 passed, 0 failed, 3 ignored**.
- `cargo test --lib handlers::admin` : **57 passed / 57 baseline** (0 perte).
- `lib.rs`, `main.rs`, `state.rs` : **inchangés** (vérifié par `git status`).

Distribution des 57 tests par sous-module :
```
16 contracts    7 cache        5 apis / auth / federation
 4 credentials / circuit_breaker    3 quotas
 2 health / mtls / policies    1 sessions / tracing
 0 llm / skills / reload (aucun test inline préexistant)
```

## E. Déviations du plan initial

1. **Risque #4 invalidé** : `mod tracing;` shadow effectivement la crate externe `tracing` dans `admin.rs` (erreur E0432 au 1er build post-déclaration). Fix : `use ::tracing::warn;` dans `admin.rs` (chemin absolu explicite). Les sous-modules utilisent `use tracing::warn;` normalement (pas de collision locale). Comportement inchangé.
2. **`contracts` tests count** : 16 tests observés au lieu des 14 estimés Phase 1. Pattern `contracts.rs` + `contracts/tests.rs` tient sans ajustement.
3. **Un seul commit final** : plan initial visait 18 commits atomiques (1 par extraction). Après rollback de workspace mi-session (cf. CLAUDE.md `feedback_parallel_session_contamination`), la séquence a été reprise et achevée mais livrée en un commit bloc. Chaque extraction intermédiaire a été validée (57/57 verts à chaque palier) avant le commit final.

## F. 0 changement observable

- Aucun changement de route, status code, response schema, middleware, auth.
- Aucun changement d'API publique (tous les symboles `pub` préservés via re-exports explicites).
- `lib.rs`, `main.rs`, `state.rs` inchangés.
- Tests d'intégration `tests/**` inchangés (0 référence `admin::...` dans `tests/`).
