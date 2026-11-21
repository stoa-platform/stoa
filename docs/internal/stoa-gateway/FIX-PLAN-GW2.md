# FIX-PLAN-GW2 — Batch all-in-one (11 in-scope + 2 deferred)

> Reference audit: `BUG-REPORT-GW-2.md` (13 findings total).
> Target: 1 commit atomique sur `fix/gw-2-bug-hunt-batch` (from `main`).
> Scope: 3 P0 + 4 P1 + 5 P2 = 11 items traités. 2 P3 backlog + 1 P2 déféré en ticket GW-3.

---

## Context critique découvert en Phase 1

**Production expose des env vars actuellement silencieuses.**

`stoa-gateway/k8s/deployment.yaml` (manifest ArgoCD prod, `stoa.dev/environment: prod`) définit ~50 env vars avec single-underscore :
- `STOA_API_PROXY_ENABLED=true` + `STOA_API_PROXY_REQUIRE_AUTH=true`
- `STOA_API_PROXY_BACKENDS_PUSHGATEWAY_*` (6 vars)
- `STOA_API_PROXY_BACKENDS_HEALTHCHECKS_*` (5 vars)
- `STOA_API_PROXY_BACKENDS_N8N_*` (6 vars)
- `STOA_API_PROXY_BACKENDS_CLOUDFLARE_*` (5 vars)
- `STOA_API_PROXY_BACKENDS_LINEAR_*` (3+ vars)
- Probablement GitHub/Slack/Infisical similaire

**Toutes silencieusement ignorées** → `config.api_proxy.enabled = false` en prod. La feature API Proxy (CAB-1722/1728/1729) est donc **inactive en prod** malgré l'intention apparente du manifest.

**Autres repos** : `stoa-signed-commits-policy/docs/CAB-864-MTLS-DESIGN.md` documente 15+ env vars single-underscore (STOA_MTLS_*). Hors scope de ce commit (cross-repo).

### Implication sur le plan

Appliquer Option 1 (`.split("__")`) :
- ✅ **Backward compat stricte** : single-underscore reste ignoré (inchangé, déjà no-op).
- ✅ **Double-underscore s'active** : nouveaux déploiements peuvent utiliser `STOA_MTLS__ENABLED` et ça marche.
- ⚠️ **Ne migre PAS le manifest prod automatiquement** : l'API Proxy reste désactivée tant qu'un humain n'a pas sed'é le fichier.

**Arbitrage** : on NE migre PAS `k8s/deployment.yaml` dans ce commit. Activer l'API Proxy pour la première fois en prod = changement comportemental séparé, nécessite Council (Impact Score HIGH), out of scope. On **documente** le gap dans `REWRITE-BUGS.md` avec ticket de suivi.

---

## A. Ordre d'exécution (commit atomique, 11 étapes)

Ordre choisi selon les dépendances (P1-5 avant P1-6 pour que ConfigError puisse utiliser Debug custom sans leak).

### Bloc 1 — Infrastructure (redact + errors)
1. **P1-5a** : créer `src/config/redact.rs` avec wrapper `Redacted<T>` (String + Option<String>) `impl Debug` qui print `<redacted>` si Some, `None` si None.
2. **P1-5b** : custom `impl Debug for Config` qui redacte les 10 champs secrets (liste exhaustive). Supprime `Debug` du `#[derive]`.
3. **P1-5c** : appliquer Debug custom à `FederationUpstreamConfig.auth_token` et `UpstreamMcpConfig` (`src/federation/upstream.rs:20`) via Redacted.
4. **P1-6a** : créer `enum ConfigError` dans `src/config/loader.rs` avec `thiserror`. Variants : `PortZero`, `MtlsEnabledWithoutTrustedProxies`, `FederationEnabledWithoutUpstreams`, `SenderConstraintWithoutBacking`, `TcpRateLimitNotFinite`. `Display` format humain + actionnable.

### Bloc 2 — Loader fix (P0-1 + P0-2)
5. **P0-1** : modifier `src/config/loader.rs:48` → `Env::prefixed("STOA_").split("__")`. Vérifier que les flat fields root ne contiennent pas de `__` (grep : aucun).
6. **P0-2** : créer `fn deserialize_string_list<'de, D>(...)` dans `src/config/loader.rs` (ou sous-module `deserializers.rs`) qui accepte CSV ET JSON array. Appliquer via `#[serde(deserialize_with = "...")]` sur `snapshot_extra_pii_patterns` (config.rs:824), `mtls.trusted_proxies`, `mtls.allowed_issuers`, `mtls.required_routes` (mtls.rs:23, 28, 33).

### Bloc 3 — Defaults alignment (P1-4)
7. **P1-4** : transformer les 4 `#[serde(default)]` en `#[serde(default = "default_*")]` avec fn retournant `Some(...)`. Fichiers :
   - `rate_limit_default` → `default_rate_limit_default() -> Option<usize> { Some(1000) }`
   - `rate_limit_window_seconds` → `default_rate_limit_window() -> Option<u64> { Some(60) }`
   - `log_level` → `default_log_level() -> Option<String> { Some("info".to_string()) }`
   - `log_format` → `default_log_format() -> Option<String> { Some("json".to_string()) }`
   - Déclarer dans `defaults.rs` en `pub(super) fn`.

### Bloc 4 — Validator (P1-6 + P2-10)
8. **P1-6b** : changer `Config::validate(&self)` → `Config::validate(&self) -> Result<(), ConfigError>` (`src/config/loader.rs:81`). Implémenter les 5 invariants :
   - `port > 0`
   - `mtls.enabled ⇒ !mtls.trusted_proxies.is_empty()`
   - `federation_enabled ⇒ !federation_upstreams.is_empty()`
   - `sender_constraint.enabled ⇒ mtls.enabled || dpop.enabled`
   - `tcp_rate_limit_per_ip.map(|r| r.is_finite() && r > 0.0).unwrap_or(true)` ← absorbe P2-10
   - Garder `warn!` pour `control_plane_url` absent et JWT absent (non-critiques).
9. **main.rs:23** : remplacer `config.validate();` par `config.validate()?;`.

### Bloc 5 — Cosmetic + tracking (P2-8 + P2-11 + P2-12)
10. **P2-8** : supprimer `default_circuit_breaker_enabled` de `src/config/api_proxy.rs:95-97`. Remplacer l'attr serde par `#[serde(default = "crate::config::defaults::default_true")]` à la ligne 66.
11. **P2-11** : ajouter `fn validate_path(&self) -> Result<(), ConfigError>` helper dans validate ou skip — décision low priority. **Scope** : si `STOA_CONFIG_ALLOWED_PATHS` est défini, vérifier que `policy_path`, `ip_blocklist_file`, `prompt_cache_watch_dir` commencent par un préfixe autorisé. Sinon pas d'allow-list (soft behavior, backward compat).
12. **P2-12** : ajouter `// TODO(CAB-XXXX): remove 'per_operation' alias after release post-2026-05-15 doc-drift window` au-dessus de `#[serde(alias = "per_operation")]` dans `src/config/expansion.rs:17`. Créer un Linear ticket tracking séparé en Phase 3.

### Bloc 6 — Tests (P1-7) + docs (P0-3)
13. **P1-7** : créer `tests/fixtures/config_minimal.yaml`, `tests/fixtures/config_production.yaml` (sans secrets), `tests/fixtures/config_federation.yaml`. Ajouter tests dans `src/config/tests.rs` listés §C.
14. **P0-3** : créer `stoa-gateway/REWRITE-BUGS.md` (court, ~60 lignes) avec : résumé exécutif + pointeur vers `BUG-REPORT-GW-2.md` + section "Known migration gap: k8s/deployment.yaml single-underscore vars" avec la liste et ticket de suivi.
15. **Doc-comments** : mettre à jour les 30+ doc-comments `Env: STOA_MTLS_ENABLED` → `Env: STOA_MTLS__ENABLED` (double underscore). Fichiers impactés : `src/config.rs`, `src/config/mtls.rs`, `src/config/api_proxy.rs`, `src/config/llm_router.rs`, `src/config/sender_constraint.rs`. NE PAS toucher `DpopConfig` (hors scope `src/config/`, dans `src/auth/dpop.rs`) mais l'ajouter à `REWRITE-BUGS.md`.

---

## B. Arbitrages résolus

### B.1 — P0-1 stratégie de fix : **Option 1 (`.split("__")`) RETENUE**

Vérifié via grep : aucun flat field Config contient `__` dans son nom, aucune collision possible. Backward compat stricte : single-underscore existant reste no-op (inchangé).

**Migration path** :
- Doc-comments passent à double-underscore (étape 15).
- `k8s/deployment.yaml` prod **NOT migrated in this commit** → ticket de suivi séparé + Council (car active pour la 1ère fois une feature prod).
- `CHANGELOG.md` : entrée dédiée "Config env var fix for nested structs".

### B.2 — P0-2 format accepté : **Option A (custom deserializer) RETENUE**

Custom deserializer `deserialize_string_list` accepte :
- String `"a,b,c"` → `vec!["a", "b", "c"]`
- JSON array `'["a","b"]'` → `vec!["a", "b"]`
- Seq de strings directement (YAML list) → vec

Appliqué à 4 champs : `snapshot_extra_pii_patterns` + `mtls.{trusted_proxies, allowed_issuers, required_routes}`. Les champs `mtls.*` sont invisibles tant que P0-1 pas appliqué, mais on fixe les deux en même temps pour éviter crash post-fix de P0-1.

### B.3 — P1-5 Debug redact : **Option a + b combinées**

- **Option a** : `impl Debug for Config` custom (explicite, lisible dans le codebase — une méthode qu'on relit).
- **Option b** : helper réutilisable `Redacted<String>` wrapper dans `src/config/redact.rs` pour les structs annexes (`FederationUpstreamConfig`, `UpstreamMcpConfig`).

Pas de crate `secrecy` (ajoute une dep, pas justifié pour 10 champs).

**CI lock test** (§C) : pour chaque secret sensible, assert `!format!("{:?}", config).contains("SECRET_VALUE")` → la régression future (quelqu'un qui re-dérive Debug) casse ce test immédiatement.

### B.4 — P1-6 scope invariants : **minimum obligatoire**

Les 5 invariants listés (port, mtls+trusted_proxies, federation+upstreams, sender_constraint+backing, tcp_rate_limit finite). Tout le reste (`hegemon_budget_warn_pct` range, `rate_limit_default > 0`) part en backlog — pas de crash loop prod.

**Garde-fou** : tester Config::validate() sur `tests/fixtures/config_production.yaml` avant merge pour éviter breaking change prod.

### B.5 — P2-9 String → enum : **DÉFÉRÉ ticket GW-3**

Scope trop large (7 micro-PRs estimés) pour un commit batch. Créer en Phase 3 le ticket Linear `GW-3: Type config strings to enums` avec liste des 7 champs (git_provider, log_level, log_format, environment, shadow_capture_source, supervision_default_tier, llm_proxy_provider).

### B.6 — P0-3 docs : **Option Y (deux fichiers)**

- `BUG-REPORT-GW-2.md` : rapport d'audit exhaustif (existant, 438 lignes).
- `REWRITE-BUGS.md` : nouveau fichier court (~60 lignes) qui ferme la dette documentaire du REWRITE-PLAN.md. Résumé exécutif + cross-ref vers BUG-REPORT + section "Known gap: k8s/deployment.yaml migration pending".

---

## C. Régression guards (12 nouveaux tests)

Tous dans `src/config/tests.rs` ou submodule tests dédiés.

### Env var split (P0-1)
1. **`test_env_var_nested_mtls_double_underscore`** : set `STOA_MTLS__ENABLED=true` → `config.mtls.enabled == true`. Cleanup remove_var.
2. **`test_env_var_single_underscore_stays_flat`** (régression lock) : set `STOA_MTLS_ENABLED=true` (single) → `config.mtls.enabled == false` (confirmé no-op).
3. **`test_env_var_nested_api_proxy_double_underscore`** : set `STOA_API_PROXY__ENABLED=true` + `STOA_API_PROXY__REQUIRE_AUTH=false` → `config.api_proxy.enabled == true && config.api_proxy.require_auth == false`.

### CSV deserializer (P0-2)
4. **`test_snapshot_extra_pii_patterns_csv`** : `STOA_SNAPSHOT_EXTRA_PII_PATTERNS=card_number,ssn_us` → `vec!["card_number", "ssn_us"]`.
5. **`test_snapshot_extra_pii_patterns_json_array`** : `'["card_number","ssn_us"]'` → `vec!["card_number", "ssn_us"]`.
6. **`test_mtls_trusted_proxies_csv_via_double_underscore`** : `STOA_MTLS__TRUSTED_PROXIES=10.0.0.0/8,192.168.0.0/16` → `vec!["10.0.0.0/8", "192.168.0.0/16"]`.

### Defaults alignment (P1-4)
7. **`test_config_default_matches_empty_yaml_deserialize`** : `Config::default() == serde_yaml::from_str::<Config>("").unwrap()` (assert les 4 fields + 2-3 random autres pour couvrir).

### Debug redact (P1-5)
8. **`test_debug_does_not_leak_secrets`** : pour chaque champ parmi {jwt_secret, keycloak_client_secret, keycloak_admin_password, control_plane_api_key, admin_api_token, gitlab_token, github_token, github_webhook_secret, llm_proxy_api_key, llm_proxy_mistral_api_key}, assigner valeur sentinelle `"SECRET_DO_NOT_LEAK_XYZ"`, asserter `!format!("{:?}", config).contains("SECRET_DO_NOT_LEAK_XYZ")`.
9. **`test_federation_upstream_debug_redacts_token`** : même test sur `FederationUpstreamConfig.auth_token`.

### Validator (P1-6)
10. **`test_validate_rejects_port_zero`** : `config.port = 0` → `Err(ConfigError::PortZero)`.
11. **`test_validate_rejects_mtls_without_trusted_proxies`** : `mtls.enabled=true, trusted_proxies=[]` → `Err(ConfigError::MtlsEnabledWithoutTrustedProxies)`.
12. **`test_validate_rejects_federation_without_upstreams`** : `federation_enabled=true, upstreams=[]` → `Err`.
13. **`test_validate_rejects_sender_constraint_without_backing`** : `sender_constraint.enabled=true, mtls.enabled=false, dpop.enabled=false` → `Err`.
14. **`test_validate_rejects_tcp_rate_limit_infinity`** : `tcp_rate_limit_per_ip = Some(f64::INFINITY)` → `Err(ConfigError::TcpRateLimitNotFinite)`.
15. **`test_validate_accepts_default_config`** : `Config::default().validate().is_ok()` (régression lock).
16. **`test_validate_accepts_production_fixture`** : charge `tests/fixtures/config_production.yaml` + asserter validate OK.

### Roundtrip + fixtures (P1-7)
17. **`test_config_roundtrip_default`** : `serde_json::from_value(serde_json::to_value(&Config::default())) == Config::default()` (équiv Eq via comparaison de JSON).
18. **`test_fixture_minimal_parses`** : `Config::load_from(minimal.yaml)` OK.
19. **`test_fixture_production_parses`** : `Config::load_from(production.yaml)` OK + asserts sur 5-6 champs critiques.

### Pas de test dédié
- P0-3 (docs only)
- P2-8 (couvert par tests existants de circuit_breaker_enabled default)
- P2-11 (low priority, soft behavior)
- P2-12 (tracking ticket suffit)

**Total** : 19 nouveaux tests (plus large que la liste user car on duplique mtls/api_proxy pour le split env).

---

## D. Risques identifiés

| Risque | Mitigation | Verif |
|---|---|---|
| **P0-1** active pour la 1ère fois `STOA_API_PROXY_*` si un dev local/staging utilise `k8s/deployment.yaml` avec double-underscore | NE PAS migrer le YAML prod dans ce commit. `REWRITE-BUGS.md` trace le gap. | Grep `k8s/deployment.yaml` inchangé post-commit. |
| **P0-2** custom deserializer ne gère pas correctement les chaînes vides ou whitespace | Tests `""` → `vec![]`, `" a , b "` → `vec!["a", "b"]` (trim). Gestion explicite dans le deserializer. | Tests 4-6 + edge cases. |
| **P1-5** Debug custom casse tests existants qui font `format!("{:?}", config)` avec match | Grep en pré-commit : aucun match `format!.*{:?}.*config` détecté (grep déjà fait en audit). | Re-grep avant merge. |
| **P1-6** invariant rejette un YAML prod légitime → crash loop | Test `test_validate_accepts_production_fixture` + fixture = copie sanitized du prod actuel. | Test obligatoire avant merge. |
| **P1-4** snapshot insta diverge post-alignement | Alignement préserve Some(1000) → Some(1000), pas de divergence snapshot attendue. | `cargo test snapshot_default_config` green. |
| **main.rs:23** `config.validate()?` change type de retour de main | main retourne déjà `Result<(), Box<dyn Error>>`. ConfigError doit impl `Error` (via thiserror). | Compile check. |
| **Custom deserializer** appliqué à 4 champs, risque de casser round-trip sérialization (serialize en JSON array mais accepte CSV) | `Serialize` reste dérivé par défaut (serialize en array). `deserialize_with` uniquement sur le parsing. Roundtrip YAML array → Vec<String> → array. | Test 17 roundtrip. |
| **Redacted<String>** dans `FederationUpstreamConfig` change la forme JSON sérialisée | Implémenter `Serialize` pass-through sur Redacted (délègue au inner String). Ou appliquer uniquement à Debug. | Test 8 + snapshot insta inchangé. |

---

## E. Commit message (draft)

```
fix(gateway/config): close GW-2 bug hunt batch (11 in-scope items)

Config hardening on security-critical parsing + defaults + validation.
All 11 findings below pre-dated the GW-2 rewrite — the rewrite is the
audit that surfaced them. See BUG-REPORT-GW-2.md for full analysis.

P0 (3):
- P0-1: STOA_* env vars for nested structs (mtls, dpop, sender_constraint,
        llm_router, api_proxy) now work via double-underscore split
        (Env::prefixed("STOA_").split("__")). Single-underscore stays
        no-op (backward compat). SECURITY: fixes silent auth bypass
        where operators thought mTLS was enabled via STOA_MTLS_ENABLED
        but the env var was ignored. k8s/deployment.yaml migration to
        double-underscore deferred to follow-up (activates API Proxy
        in prod for the first time, needs Council).
- P0-2: SNAPSHOT_EXTRA_PII_PATTERNS + mtls.{trusted_proxies,
        allowed_issuers, required_routes} accept both CSV and JSON
        array via custom deserializer (deserialize_string_list).
        Doc-compliant. Avoids startup crash on comma-separated input.
- P0-3: REWRITE-BUGS.md retrospective doc closes debt from
        REWRITE-PLAN.md §7.4/§10/§11. Cross-refs BUG-REPORT-GW-2.md.

P1 (4):
- P1-4: Align 4 fields between Config::default() and #[serde(default)]:
        rate_limit_default, rate_limit_window_seconds, log_level,
        log_format (all now #[serde(default = "fn")] returning Some).
- P1-5: Custom Debug impl for Config redacts 10 secret fields
        (jwt_secret, keycloak_client_secret, github_token, etc.).
        Redacted<T> wrapper applied to FederationUpstreamConfig.auth_token
        and UpstreamMcpConfig.auth_token. CI lock test asserts no
        sentinel secret leaks through {:?}.
- P1-6: Config::validate() now returns Result<(), ConfigError> and
        enforces: port > 0, mtls.enabled ⇒ trusted_proxies non-empty,
        federation_enabled ⇒ upstreams non-empty, sender_constraint
        ⇒ mtls||dpop, tcp_rate_limit finite+positive (absorbs P2-10).
        main.rs propagates via ?.
- P1-7: Roundtrip test + production fixture YAMLs (tests/fixtures/)
        + empty-yaml-default divergence test.

P2 (5 — 4 fixed, 1 deferred):
- P2-8: default_true centralisé via
        crate::config::defaults::default_true path for
        ProxyBackendConfig.circuit_breaker_enabled.
- P2-9: String → enum migration (git_provider, log_level, log_format,
        environment, shadow_capture_source, supervision_default_tier,
        llm_proxy_provider) DEFERRED to new Linear ticket
        "GW-3: Type config strings to enums" (estimated ~7 micro-PRs).
- P2-10: tcp_rate_limit_per_ip finite check absorbed into P1-6.
- P2-11: policy_path + ip_blocklist_file + prompt_cache_watch_dir
        soft allow-list via STOA_CONFIG_ALLOWED_PATHS (defense-in-depth,
        no-op when env unset).
- P2-12: ExpansionMode alias "per_operation" now tracked with
        TODO(CAB-XXXX) deadline post-2026-05-15.

Regression guards: 19 new tests covering env var split, CSV parsing,
defaults alignment, Debug redact, 6 validator invariants, roundtrip,
production fixture load.

Module GW-2 CLOSED: 11/13 findings handled in-commit (3 P0 + 4 P1 +
4 P2), 1 P2 deferred to GW-3 ticket, 2 P3 backlog.

Closes: P0-1, P0-2, P0-3, P1-4, P1-5, P1-6, P1-7, P2-8, P2-10, P2-11,
        P2-12 (see BUG-REPORT-GW-2.md)
Deferred to GW-3: P2-9
Backlog: P3-13, P3-14
```

---

## F. Phase 3 validation checklist

1. ☐ `cargo check` → zéro warning
2. ☐ `cargo clippy --all-targets -- -D warnings` → zéro issue
3. ☐ `cargo fmt --check` → propre
4. ☐ `cargo test` → tous tests passent (existants + 19 nouveaux)
5. ☐ Tests critiques nommément exécutés :
   - `cargo test test_env_var_nested_mtls_double_underscore`
   - `cargo test test_env_var_single_underscore_stays_flat`
   - `cargo test test_debug_does_not_leak_secrets`
   - `cargo test test_validate_rejects_mtls_without_trusted_proxies`
   - `cargo test test_config_roundtrip_default`
   - `cargo test test_validate_accepts_production_fixture`
6. ☐ Snapshot `insta` baseline figée (ou changements justifiés liés à P1-4 — vérif humaine).
7. ☐ Smoke test manuel (optionnel) :
   ```bash
   STOA_MTLS__ENABLED=true STOA_MTLS__TRUSTED_PROXIES="10.0.0.0/8" cargo run
   # verify logs : "mTLS enabled" + trusted_proxies: ["10.0.0.0/8"]
   ```
8. ☐ Mise à jour `BUG-REPORT-GW-2.md` section tête : "GW-2 CLOSED — 11/13 FIXED (commit <sha>), 1 DEFERRED (GW-3), 2 BACKLOG (P3-13/14)".
9. ☐ Ticket Linear créé : `GW-3: Type config strings to enums` avec liste 7 champs et reference à ce commit.
10. ☐ `REWRITE-BUGS.md` créé (~60 lignes) avec :
    - Résumé exécutif
    - Cross-ref vers `BUG-REPORT-GW-2.md`
    - Section "Known migration gaps" listant `k8s/deployment.yaml` + `stoa-signed-commits-policy/docs/CAB-864-MTLS-DESIGN.md` à migrer separately.
11. ☐ `CHANGELOG.md` : entrée sous `[Unreleased]` documentant double-underscore migration.
12. ☐ Commit SHA relevé et inscrit dans `handoff_session_2026_04_24_gw2_closed.md` (memory).

---

## G. Ce qui N'EST PAS fait dans ce commit

- **k8s/deployment.yaml** migration single→double underscore (active API Proxy en prod → Council requis).
- **stoa-signed-commits-policy cross-repo docs** migration (hors scope repo).
- **DpopConfig** (vit dans `src/auth/dpop.rs` pas `src/config/`) — tracer dans REWRITE-BUGS.md.
- **P2-9** String→enum (nouveau ticket GW-3).
- **P3-13, P3-14** (backlog).
- **Optional invariants** (hegemon_budget range, rate_limit > 0) — décalés dans GW-3 ou ticket séparé.

---

**STOP. Validation humaine avant Phase 2.**

Questions ouvertes pour l'utilisateur :

1. **k8s/deployment.yaml migration** : confirmes-tu qu'on NE PAS migre dans ce commit (garde l'API Proxy off en prod) ?
2. **P2-11 soft allow-list** : on implémente (extra ~20 LOC), ou on déferre aussi ?
3. **CAB ticket pour P2-12** : tu crées le ticket Linear en amont, ou je laisse `TODO(CAB-XXXX)` placeholder et toi tu renommes après ?
4. **Custom deserializer CSV** : on trim les espaces autour des éléments (`"a , b"` → `["a","b"]`) ou on préserve stricte (`["a "," b"]`) ? Reco : trim.
5. **Ticket GW-3 création** : je le crée via Linear MCP en Phase 3, ou tu préfères le créer toi-même ?
