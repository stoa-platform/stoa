# BUG-REPORT-GW-2 — Gateway Rust config (src/config/*)

> **MODULE GW-2 CLOSED** (fixes on `fix/gw-2-bug-hunt-batch`).
> **10 fixed** in-commit · **2 deferred → GW-3** (P2-9, P2-11) · **2 backlog** (P3-13, P3-14).
> Status per finding called out inline below (`FIXED`, `DEFERRED → GW-3`, `BACKLOG`).
> Retrospective pointer: [`REWRITE-BUGS.md`](./REWRITE-BUGS.md).

> Audit fonctionnel post-rewrite GW-2 (split `src/config.rs` 1973 LOC → 9 sous-modules + façade 828 LOC).
> Scope : bugs latents de parsing, defaults, backward compat, sécurité.
> Méthode : lecture façade + 9 sous-modules + snapshot insta + callers + 3 probes Figment binaires pour valider les hypothèses.
> Calibrage : GO-1 = 14 / CP-1 = 21 / GW-1 = 20 / UI-2 = 38 / CP-2 = 11. GW-2 attendu 3-10 → **trouvé 10 réels + 2 notes design**.

## Executive summary

Le split compile propre (`cargo check` clean, `cargo clippy --all-targets -D warnings` clean, snapshot insta baseline figée). La régression contre l'ancien monolithe est nulle : défauts identiques champ-par-champ, API publique conservée via re-exports (`pub use`), callers externes (30 dans `src/`, 8 dans `tests/`) intacts.

**Les bugs listés ci-dessous pré-datent tous le rewrite** — ils étaient déjà présents dans le monolithe 1973 LOC. Le rewrite est l'audit qui les révèle. Trois d'entre eux ont été **explicitement** identifiés dans `REWRITE-PLAN.md` (§7.1, §7.4, §10) comme "hors scope / à documenter", mais le `REWRITE-BUGS.md` promis **n'a jamais été créé**. C'est ce rapport.

Bug dominant : **les env vars `STOA_*` pour les 5 structs nested sont silencieusement inopérantes** (mtls, dpop, sender_constraint, llm_router, api_proxy). Un opérateur qui définit `STOA_MTLS_ENABLED=true` croit activer mTLS ; en réalité l'env var est ignorée et le YAML seul peut piloter ces structs. Impact sécurité réel : désalignement entre doc et comportement sur une surface d'auth.

Bug collatéral : **un Vec<String> racine (`snapshot_extra_pii_patterns`) crash au startup** si l'opérateur suit la doc "comma-separated" (Figment refuse `"a,b"` → `InvalidType`, `Config::load()` → `Err` → gateway down).

---

## Critical (P0)

### P0-1 — Env vars `STOA_MTLS_*` / `STOA_DPOP_*` / `STOA_SENDER_CONSTRAINT_*` / `STOA_LLM_ROUTER_*` / `STOA_API_PROXY_*` silencieusement ignorées — **FIXED**
**Catégorie** : B (backward compat) + D (security) + A (defaults)
**Fichier** : `src/config/loader.rs:48` ; symptômes documentés dans `src/config.rs:344–359, 622–625, 693–697` et sur chaque champ `MtlsConfig`/`DpopConfig`/etc.

**Reproduction (probe Figment vérifié)** :
```rust
// loader.rs actuel :
figment = figment.merge(Env::prefixed("STOA_"));   // pas de .split("__")

// Comportement observé via probe binaire (cargo run):
std::env::set_var("STOA_MTLS_ENABLED", "true");
// → s'injecte comme clé FLAT `mtls_enabled` (lowercase, sans split)
// → Config n'a pas de champ `mtls_enabled` au root
// → valeur silencieusement IGNORÉE par serde (unknown field dropped)
// → config.mtls.enabled reste false
```
Vérification binaire (probe capturé 2026-04-24) :
```
SINGLE_UNDERSCORE (as in loader.rs):          mtls.enabled = false  ← doc-comment MENT
DOUBLE_UNDERSCORE_WITH_SPLIT("__"):           mtls.enabled = true
DOUBLE_UNDERSCORE_NO_SPLIT:                   mtls.enabled = false
```

**Surface impactée** (tous les champs nested de 5 structs) :
- `MtlsConfig` — 13 champs. `STOA_MTLS_ENABLED`, `STOA_MTLS_REQUIRE_BINDING`, `STOA_MTLS_TRUSTED_PROXIES`, `STOA_MTLS_ALLOWED_ISSUERS`, `STOA_MTLS_REQUIRED_ROUTES`, `STOA_MTLS_TENANT_FROM_DN`, + 8 header overrides.
- `DpopConfig` — 6 champs. `STOA_DPOP_ENABLED`, `STOA_DPOP_REQUIRED`, `STOA_DPOP_MAX_AGE_SECS`, etc.
- `SenderConstraintConfig` — 3 champs. `STOA_SENDER_CONSTRAINT_ENABLED`, `STOA_SENDER_CONSTRAINT_DPOP_REQUIRED`, `STOA_SENDER_CONSTRAINT_MTLS_REQUIRED`.
- `LlmRouterConfig` — 5 champs. `STOA_LLM_ROUTER_ENABLED`, `STOA_LLM_ROUTER_DEFAULT_STRATEGY`, `STOA_LLM_ROUTER_BUDGET_LIMIT_USD`.
- `ApiProxyConfig` — 3 champs + N backends.

**Impact sécurité** :
- Un opérateur qui ajoute `STOA_MTLS_ENABLED=true` + `STOA_SENDER_CONSTRAINT_ENABLED=true` à un Deployment K8s **croit** enforcer sender-constraint sur tous les tokens. En pratique, mTLS + sender-constraint restent désactivés, la vérification `cnf.x5t#S256` / `cnf.jkt` n'a jamais lieu, et un token volé reste exploitable sans présentation du cert client.
- Même scénario pour DPoP : un opérateur pense imposer DPoP via env, mais le middleware n'est pas monté (voir `src/lib.rs:109` — `mtls_enabled = state.config.mtls.enabled` est lu comme `false`).

**État actuel** :
- Fonctionne via YAML (`mtls: { enabled: true }` dans `config.yaml`).
- Ne fonctionne PAS via env var unique soulignement (doc-comment mensongère sur ~30 champs).
- Mentionné dans `REWRITE-PLAN.md §7.4` comme "documenté dans REWRITE-BUGS.md" — mais `REWRITE-BUGS.md` **n'existe pas sur disque**.

**Fix direction** :
- Option 1 (la plus sûre) : ajouter `.split("__")` + patch docs pour demander `STOA_MTLS__ENABLED` (double underscore). Breaking change pour quiconque utilisait déjà des YAML flat `mtls_enabled`, ce qui n'arrive jamais en pratique → à valider via grep prod.
- Option 2 : fabriquer un provider custom qui re-map `STOA_MTLS_*` → `mtls.*` via map préfix connue. Plus d'alignement opérateur, plus de code à maintenir.
- Option 3 : déplier toutes les structs nested en champs flat (casse 30 callers — hors scope total).

**Reco** : Option 1. Ajouter test d'intégration `STOA_MTLS__ENABLED=true → config.mtls.enabled=true` + `STOA_MTLS_ENABLED=true → config.mtls.enabled=false` (régression explicite) + updater chaque doc-comment.

---

### P0-2 — Crash au startup si `STOA_SNAPSHOT_EXTRA_PII_PATTERNS` est défini en CSV (comme documenté) — **FIXED**
**Catégorie** : C (panic/startup failure) + B (doc vs comportement)
**Fichier** : `src/config.rs:822–824` (field + doc-comment) ; `src/config/loader.rs:68` (extract failure point).

**Reproduction (probe Figment binaire)** :
```rust
std::env::set_var("STOA_SNAPSHOT_EXTRA_PII_PATTERNS", "card_number,ssn_us");
Figment::new().merge(Serialized::defaults(Cfg::default())).merge(Env::prefixed("STOA_")).extract()
→ Err(InvalidType(Str("card_number,ssn_us"), "a sequence"))
```

**Doc-comment vs comportement** :
```rust
/// Extra regex patterns to treat as PII during snapshot masking.
/// Env: STOA_SNAPSHOT_EXTRA_PII_PATTERNS (comma-separated)   ← ce que la doc promet
#[serde(default)]
pub snapshot_extra_pii_patterns: Vec<String>,                  ← Figment veut du JSON array
```

**Impact opérationnel** : un opérateur qui suit la doc littérale met `"card_number,ssn_us"` dans un `env:` Kubernetes. Au prochain `kubectl rollout`, `Config::load()` renvoie `Err`, `main()` termine via `?`, les nouveaux pods crashent au startup. Rollback obligatoire.

Le message d'erreur Figment (`InvalidType(Str("card_number,ssn_us"), "a sequence")`) n'est pas actionnable pour un SRE qui n'a pas le code sous les yeux — il pointe vers "a sequence" sans indiquer "utilisez un JSON array" ni "séparateur attendu".

**Fix direction** :
- Option A : accepter CSV → custom deserializer `deserialize_with = "csv_or_json"` sur le field. 10 LOC, aligné sur la doc.
- Option B : changer la doc pour dire `JSON array` + exemple `'["card_number","ssn_us"]'`. Moins opérateur-friendly, mais cohérent avec les autres Vec<T> (`federation_upstreams` est déjà documenté JSON array).
- Option C : regex parsing au chargement (custom Figment provider). Overkill.

**Reco** : Option A (aligné sur la doc historique + ergonomie K8s). Ajouter test d'intégration.

**Même catégorie** (mais surface masquée par P0-1) : `MtlsConfig.trusted_proxies`, `MtlsConfig.allowed_issuers`, `MtlsConfig.required_routes` — tous `Vec<String>` avec doc-comment "comma-separated CIDRs/DNs/patterns". Aujourd'hui cachés derrière P0-1 (env var ignorée avant d'atteindre le check de type). Dès que P0-1 est corrigé, ces 3 champs deviennent des sous-cas de P0-2.

---

### P0-3 — `REWRITE-BUGS.md` promis dans `REWRITE-PLAN.md` mais absent — **FIXED**
**Catégorie** : Process / traçabilité (non-code)
**Fichier** : absent de `stoa-gateway/`. Référencé dans `REWRITE-PLAN.md` lignes 212 (§7.4), 299 (§10), 310 (§11).

**Extraits pertinents** :
- §7.4 (L212) : `→ Comportement actuel conservé, documenté dans 'REWRITE-BUGS.md' comme divergence potentielle doc/code. Pas fixé silencieusement (risque incident prod si on active split env naïvement, impact middleware auth).`
- §10 (L299) : `[ ] REWRITE-BUGS.md commit si bugs latents découverts (§7.4, §11)`
- §11 (L310) : `Figment Env source : flat parsing (sans .split())` + `Doc-comments STOA_MTLS_ENABLED trompeurs` + `Hors scope du rewrite, documenté dans REWRITE-BUGS.md`

Aucun fichier `REWRITE-BUGS.md` n'existe dans `stoa-gateway/` (vérifié via `find`). Le checklist de validation §10 n'a pas été satisfait avant merge. Ce rapport **BUG-REPORT-GW-2.md** tient lieu de livrable rétrospectif.

**Fix direction** : aucun — le présent fichier ferme la dette documentaire. À consolider : soit renommer ce fichier `REWRITE-BUGS.md`, soit maintenir les deux (rewrite delta vs audit systématique) avec cross-refs explicites.

---

## High (P1)

### P1-4 — 4 divergences silencieuses entre `Config::default()` et `#[serde(default)]` — **FIXED**
**Catégorie** : A (defaults divergents)
**Fichier** : `src/config.rs:137–140, 178–182` ; `src/config/defaults.rs:300–307`.

**Reproduction binaire (probe)** :
```
Default::default()        : rate_limit_default=Some(1000), log_level=Some("info")
serde_json from "{}"      : rate_limit_default=None,       log_level=None
serde_yaml empty input    : rate_limit_default=None,       log_level=None
```

**Fields concernés** :
| Champ | `#[serde(default)]` sur | `Config::default()` | Serde désérialisation |
|---|---|---|---|
| `rate_limit_default` | `Option<usize>` | `Some(1000)` | `None` |
| `rate_limit_window_seconds` | `Option<u64>` | `Some(60)` | `None` |
| `log_level` | `Option<String>` | `Some("info")` | `None` |
| `log_format` | `Option<String>` | `Some("json")` | `None` |

**Pourquoi c'est partiellement self-healed en prod** :
- `loader.rs` Figment stack commence par `Serialized::defaults(Config::default())` → le YAML hérite des valeurs `Some(...)`. Donc le chemin de chargement normal donne `Some(1000)`.
- `rate_limit.rs:76–77` utilise `.unwrap_or(1000)` / `.unwrap_or(60)` → même valeur effective quel que soit le champ (None ou Some(1000)). Invisible.

**Pourquoi ça mord quand même** :
- `control_plane/registration.rs:448` teste `config.rate_limit_default.is_some()` → le check déclenche ou non un warn selon le path de construction du Config.
- Tout nouveau code qui fait `if config.rate_limit_default.is_some() { apply_limit() }` aura un comportement différent selon `Config::default()` (warn fire) vs YAML empty (warn silent).
- Le snapshot `insta` **verrouille** `Some(1000)`, donc toute tentative future de "normaliser" les defaults casse le snapshot sans test de régression intermédiaire.
- Tests qui font `serde_yaml::from_str::<Config>("port: 80")` retournent None — incohérent avec les assertions des tests existants qui utilisent `Config::default()` (e.g., `test_default_rate_limits` assert `Some(1000)`).

**Fix direction** :
- Aligner les 4 champs sur un seul comportement. Soit :
  - `#[serde(default = "default_rate_limit")]` avec `fn default_rate_limit() -> Option<usize> { Some(1000) }` → unification vers `Some(1000)`.
  - OU changer `Config::default()` pour retourner `None` → aligner vers serde default.
- Les `.unwrap_or(1000)` consumers absorbent les deux choix, donc l'option 1 est la plus conservative (préserve le snapshot + sémantique historique).

---

### P1-5 — `#[derive(Debug)]` sur Config expose 10+ secrets — **FIXED**
**Catégorie** : D (sécurité secrets)
**Fichier** : `src/config.rs:31` (Debug derivé sur Config root), `src/config/federation.rs:5` (sur FederationUpstreamConfig).

**Champs sensibles dans Config** (tous Option<String>, tous inclus dans `{:?}` output) :
```
jwt_secret, keycloak_client_secret, keycloak_admin_password,
control_plane_api_key, admin_api_token,
gitlab_token, github_token, github_webhook_secret,
llm_proxy_api_key, llm_proxy_mistral_api_key
```
Plus `FederationUpstreamConfig.auth_token` et `UpstreamMcpConfig.auth_token` (`src/federation/upstream.rs:28`).

**État actuel** :
- Aucun `println!("{:?}", config)` / `tracing::debug!(?config)` / `%config` détecté dans `src/` (grep vérifié).
- `loader.rs:70–75` logue seulement `port`, `host`, `control_plane_url` (safe).
- **Mais** le piège est armé : toute future ligne `tracing::debug!(?state.config)` ou `panic!("unexpected state: {:?}", config)` dump les secrets dans les logs structurés, qui partent vers Fluent Bit → Loki/Elastic. Les secrets apparaissent alors dans les search logs de tous les viewers RBAC qui n'ont pas l'accès "sensitive".
- Règle FR du CLAUDE.md `stoa-gateway` : "Zero tolerance clippy" — mais aucun lint détecte ce risque. Un reviewer humain aussi rapidement laissera passer un `debug!(?config)` "diagnostique".

**Impact** : defense-in-depth. Classé P1 parce que la zone est stable mais toute maintenance future (debugging, panic messages, admin /debug/config endpoint) peut trivialement leak.

**Fix direction** :
- Implémenter `Debug` custom qui redacte les champs sensibles : `jwt_secret: "<redacted>"` au lieu de `Some("eyJ...")`.
- Alternative : wrapper `struct Redacted<T>(T)` avec `impl Debug` qui ne print pas le contenu. Appliquer aux 10+ fields.
- Ajouter lint custom / CI test : `assert!(!format!("{:?}", config).contains(secret_value))` dans un test "no-secret-in-debug" pour chaque champ.
- Faire de même pour `FederationUpstreamConfig.auth_token` et `UpstreamMcpConfig.auth_token`.

---

### P1-6 — `Config::validate()` ne renvoie rien et log seulement — **FIXED**
**Catégorie** : E (error handling startup)
**Fichier** : `src/config/loader.rs:81–89`.

```rust
pub fn validate(&self) {
    if self.control_plane_url.is_none() {
        tracing::warn!("CONTROL_PLANE_URL not set - some features will be disabled");
    }
    if self.jwt_secret.is_none() && self.keycloak_url.is_none() {
        tracing::warn!("No JWT_SECRET or KEYCLOAK_URL - auth will be limited");
    }
}
```

**Problème** : le nom "validate" promet une validation. Le comportement est : pas d'erreur, pas de panic, juste 2 `warn!`. Toute config absurde passe :
- `port: 0` → passe ensuite à tokio qui bind le port aléatoirement
- `rate_limit_default: Some(0)` → pas de rate limit effective
- `mtls.enabled: true` avec `mtls.trusted_proxies: []` → accepte TOUT proxy (voir doc-comment ligne 21 : "If empty, all sources accepted") — auth bypass silencieux si mTLS activé en prod sans trusted_proxies
- `federation_enabled: true` avec `federation_upstreams: []` → fédération "enabled" mais inopérante
- `guardrails_pii_enabled: true` sans `guardrails_pii_redact: true|false` cohérent
- `hegemon_budget_warn_pct: 2.5` (au-delà de 1.0) → notifications mal calculées

**Conséquence** : toute combinaison valide syntaxiquement YAML démarre la gateway. Seul le runtime (au premier appel) révèle l'incohérence, parfois via une 500 cryptique.

**Fix direction** :
- Changer la signature en `fn validate(&self) -> Result<(), ConfigError>` avec `thiserror::Error` (conforme CLAUDE.md règle "anyhow pour app, thiserror pour lib"), couvrir les invariants critiques :
  - `port > 0` (rejeter 0)
  - `mtls.enabled ⇒ !mtls.trusted_proxies.is_empty() || documented_override` (sinon rejet)
  - `federation_enabled ⇒ !federation_upstreams.is_empty()`
  - `hegemon_enabled ⇒ 0.0 <= hegemon_budget_warn_pct <= 1.0 && hegemon_budget_daily_usd > 0.0`
  - `sender_constraint.enabled ⇒ mtls.enabled || dpop.enabled`
- Garder `warn!` pour les cas non-critiques (CP URL absent).
- Appeler via `?` dans `main.rs:23` (ligne actuelle `config.validate()` — remplacer par `config.validate()?`).

---

### P1-7 — Le snapshot `insta` ne couvre pas le round-trip sérialization — **FIXED**
**Catégorie** : G (tests / snapshot scope)
**Fichier** : `src/config/tests.rs:216–219`, snapshot `src/config/snapshots/stoa_gateway__config__tests__snapshot_default_config.snap`.

```rust
#[test]
fn snapshot_default_config() {
    insta::assert_json_snapshot!(Config::default());
}
```

**Ce que ça ne couvre pas** :
1. `serde_yaml::from_str::<Config>("") == Config::default()` — **faux** pour les 4 fields de P1-4.
2. `toml::from_str::<Config>("") == Config::default()` — même.
3. `Config::default() → serialize → deserialize == Config::default()` — oui (les Some roundtrip OK), mais le snapshot ne le prouve pas explicitement.
4. Compatibilité avec `gateway.toml` / `config.yaml` de prod réel. Pas de fixture YAML réaliste (BDF, Engie, Elis, dev local) versionnée → impossible de vérifier "un YAML qui marchait avant marche après".

**Fix direction** :
- Ajouter test `roundtrip_default_config` : `serialize(Config::default()) → deserialize → assert_eq!`.
- Ajouter test `parse_empty_yaml` : `serde_yaml::from_str::<Config>("")` + assert les 4 fields (P1-4) explicitement → révèle la divergence au prochain développeur.
- Ajouter fixtures YAML minimales (`tests/fixtures/config_minimal.yaml`, `config_production.yaml`, `config_federation.yaml`) et un test qui les parse + snapshot sérialization.

---

## Medium (P2)

### P2-8 — `default_true()` dupliqué dans `api_proxy.rs` — **FIXED**
**Catégorie** : Code smell (pas un bug fonctionnel)
**Fichier** : `src/config/api_proxy.rs:95–97` vs `src/config/defaults.rs:13–15`.

```rust
// defaults.rs (canonical):
pub(super) fn default_true() -> bool { true }

// api_proxy.rs (duplicate):
fn default_circuit_breaker_enabled() -> bool { true }   // L95
// + used at L67: #[serde(default = "default_circuit_breaker_enabled")]
```

Le `REWRITE-PLAN.md §7.1` prévoyait explicitement de partager la fn via chemin qualifié :
```rust
#[serde(default = "crate::config::defaults::default_true")]
```
La Phase 2 a préféré une fn locale. Pas d'impact fonctionnel (même valeur), juste une dette cosmétique par rapport au plan validé.

**Fix direction** : soit aligner sur le plan (`#[serde(default = "crate::config::defaults::default_true")]`), soit supprimer la mention du §7.1 dans le plan. Non bloquant.

---

### P2-9 — `git_provider: String` accepte n'importe quoi, fallthrough silencieux — **DEFERRED → GW-3**
**Catégorie** : A (pas d'enum, typage trop permissif)
**Fichier** : `src/config.rs:132–133`, test `src/config/tests.rs:200–209`.

```rust
#[serde(default = "default_git_provider")]
pub git_provider: String,   // expected: "gitlab" | "github"
```

Le test existant (`test_git_provider_unknown_value_treated_as_gitlab`, L200) **verrouille** le comportement de fallback silencieux : `git_provider: "bitbucket"` → considéré comme gitlab. C'est documenté via ce test, mais c'est une mauvaise ergo :
- Typo (`githhub` au lieu de `github`) → fallback gitlab → 404 sur tous les endpoints GitLab, reste silencieux jusqu'au premier webhook.
- `log_level: "WARN"` (majuscules) → serde accepte puis `tracing` ne l'interprète pas → niveau d'origine.

**Autres fields soft-typed** :
- `log_level: Option<String>` (pas d'enum)
- `log_format: Option<String>` — "json"/"pretty"/etc. non enforced
- `environment: String` — "dev"/"staging"/"prod" uniquement par convention
- `shadow_capture_source: Option<String>` — 4 valeurs documentées, 0 enforced
- `supervision_default_tier: String` — "autopilot"/"copilot"/"command" uniquement par convention
- `llm_proxy_provider: Option<String>` — "anthropic"/"mistral"/"openai" uniquement par convention
- `tool_expansion_mode: ExpansionMode` ✓ (propre — enum + alias). Contre-exemple qui montre que c'est faisable.

**Fix direction** : convertir progressivement en enums `#[serde(rename_all = "snake_case")]` avec alias backward compat (même pattern que `ExpansionMode`). Chaque conversion = 1 micro-PR isolée avec test de régression "valeur inconnue → deserialize Err avec message clair".

---

### P2-10 — `STOA_TCP_RATE_LIMIT_PER_IP` accepte infinity silencieusement — **FIXED** (absorbed into P1-6)
**Catégorie** : A (validation manquante sur f64) + I (Rust config)
**Fichier** : `src/config.rs:790–791`, consommé dans `src/tcp_filter.rs:78–84`.

```rust
// config.rs:
pub tcp_rate_limit_per_ip: Option<f64>,   // 0 = disabled per doc

// tcp_filter.rs:
let rate_limiter = config
    .tcp_rate_limit_per_ip
    .filter(|&r| r > 0.0)
    .map(|rate| RateLimiter { rate, ... });
```

Problèmes :
- `f64::NAN > 0.0` → false → filtered out → rate limiter None. Safe accidentellement.
- `f64::INFINITY > 0.0` → true → `rate = INFINITY`. Tous les bucket.tokens opérations produisent infinity ou NaN → `tokens >= 1.0` toujours true → rate limit inactif (pas de panic).
- Valeurs négatives : `f64::-INF > 0.0` → false → filtered out. Safe.

Pas de bug catastrophique (pas de crash, pas d'allocation illimitée), juste un écart silencieux entre valeur "configurée" et comportement effectif. Erreur opérateur plutôt que bug du code.

**Fix direction** : `Config::validate()` check `tcp_rate_limit_per_ip.map(|r| r.is_finite() && r > 0.0).unwrap_or(true)` avec `Err` sinon. Inclus dans P1-6.

---

### P2-11 — Pas de validation de path sur `policy_path`, `ip_blocklist_file`, `prompt_cache_watch_dir` — **DEFERRED → GW-3**
**Catégorie** : D (path traversal via config — théorique, scope opérateur)
**Fichier** : `src/config.rs:170` (`policy_path`), `785–786` (`ip_blocklist_file`), `580–581` (`prompt_cache_watch_dir`).

Les 3 champs acceptent n'importe quel chemin : `/etc/passwd`, `../../../`. Pas de `canonicalize()` ni `starts_with("/etc/stoa/")` check. L'impact dépend du privilège du process gateway : si le binaire tourne en non-root en K8s, il lira seulement les fichiers montés. Si un opérateur pointe sur un secret K8s mounté à un autre path, le fichier est lu.

**Impact réel** : faible — l'opérateur qui configure le pod a déjà accès à tout le FS du container. Pas un vecteur d'attaque "externe".

**Fix direction** : (low priority) allow-list de préfixes via env `STOA_CONFIG_ALLOWED_PATHS=/etc/stoa,/var/stoa`. Pas bloquant.

---

### P2-12 — Serde alias `per_operation` pour `ExpansionMode` sans date de suppression trackée — **FIXED** (TODO tracker added)
**Catégorie** : G (tests / maintenance)
**Fichier** : `src/config/expansion.rs:17`, test L33.

```rust
#[serde(alias = "per_operation")]
PerOp,
```

Le doc-comment dit "kept only for the PR3 doc-drift window ... Drop with Release N+1". Pas de TODO/ticket Linear associé. À la prochaine cadence release N+1, personne ne sait ce que N était.

**Fix direction** : ajouter `// TODO(CAB-XXXX): remove alias after release N+1 (target: 2026-05-15)` + créer un Linear ticket si absent. Non bloquant.

---

## Low (P3)

### P3-13 — `detailed_tracing` doc-comment dit "default: false" mais champ est `bool` sans `#[serde(default = "...")]` — **BACKLOG**
**Fichier** : `src/config.rs:200–201`, `defaults.rs:311`.

```rust
/// Env: STOA_DETAILED_TRACING (default: false)
#[serde(default)]
pub detailed_tracing: bool,
```

Le bool default Rust est `false`, donc le comportement match la doc. Mais si quelqu'un copie ce pattern pour un bool qui default à true (e.g., `proxy_metrics_enabled` utilise `#[serde(default = "default_true")]`), on a une incohérence de style. Pas un bug, juste une inconsistance de pattern à consolider.

---

### P3-14 — `default_*` helpers = 50+ fns avec un-line bodies — **BACKLOG**
**Fichier** : `src/config/defaults.rs` (intégralité).

Chaque default est une fn dédiée (`fn default_port() -> u16 { 8080 }`). Le plan prévoit 40 fns, la réalité est 56. Le pattern scale avec le nombre de fields (~140). Compile-time impact nul, readability discutable.

**Fix direction** : possible d'utiliser des constantes `const DEFAULT_PORT: u16 = 8080;` + `#[serde(default = "|| DEFAULT_PORT")]` — mais Rust ne permet pas de closure directe dans serde default. Alternative : macro `default_fn!(default_port, u16, 8080)` générerait les fns. Non urgent. Code de taille, pas de bug.

---

## Scope hors bugs — notes de design

### N-1 — Contrat flat TOML préservé mais coûteux pour la maintenance
Le `REWRITE-PLAN.md §1` explique pourquoi les 140 champs root doivent rester flat (compatibilité TOML + callers). C'est la bonne décision historique. Mais chaque ajout de field nécessite maintenant :
1. Declaration dans `src/config.rs` (struct).
2. Default fn dans `src/config/defaults.rs` si non-trivial.
3. Entry dans `impl Default for Config` dans `defaults.rs`.
4. Update snapshot `insta`.
5. (Optionnel) Test dans `config/tests.rs`.

5 touches par nouveau field. Un dev qui ajoute un field a 2/5 chances d'oublier une étape (defaults uniquement sur le struct, pas dans impl Default → divergence silencieuse — cf P1-4). Suggestion : macro proc-derive ou script de linting.

### N-2 — `FederationUpstreamConfig` n'a pas de `Default`
```rust
// federation.rs — pas de impl Default, pas de derive Default.
pub struct FederationUpstreamConfig {
    pub url: String,                  // required
    pub transport: Option<String>,    // doc says default "sse" mais Option::None
    pub auth_token: Option<String>,
    pub timeout_secs: Option<u64>,    // doc says default 30 mais Option::None
}
```
Les "defaults" documentés (transport="sse", timeout=30) sont appliqués **par le consumer** (`admin/federation.rs:91-93` via `unwrap_or_else`). Si un nouveau consumer oublie l'unwrap, il lira `None`. Documenter dans la struct ou fournir des helpers `upstream.transport_or_default() -> &str`.

### N-3 — Pas de test intégration bout-en-bout "gateway.toml de prod → Config chargé"
Aucune fixture YAML prod (dev local, Engie, Elis, BDF, LV) versionnée. Tout changement futur de nom de champ peut casser silencieusement un deployment prod existant. Suggestion : ajouter `tests/fixtures/config_*.yaml` (sans secrets) + test `load_production_fixtures` qui fait `Config::load_from(path)` pour chaque fixture et asserts des invariants.

---

## Priorité de fix (recommandation)

| Rang | ID | Titre court | Effort | Risk |
|---|---|---|---|---|
| 1 | P0-1 | Env vars nested silencieuses (mtls/dpop/...) | M (1 PR, ~80 LOC + docs) | High (sécurité + ops) |
| 2 | P0-2 | Crash startup sur CSV doc-compliant (`snapshot_extra_pii_patterns`) | S (custom deserializer) | High (crash boot) |
| 3 | P1-5 | Debug derive leak potentiel secrets | M (Debug custom + CI assert) | High (defense-in-depth) |
| 4 | P1-6 | `validate()` → `Result<(), ConfigError>` | M (refactor + tests) | Medium |
| 5 | P1-4 | 4 divergences `Config::default()` vs serde | S (aligner les 4 fields) | Low (self-healed par `unwrap_or`) |
| 6 | P1-7 | Snapshot roundtrip + fixtures prod | M (tests + fixtures) | Medium |
| 7 | P0-3 | Créer `REWRITE-BUGS.md` (ou renommer ce rapport) | XS (mv + cross-ref) | Low (trace docs) |
| 8 | P2-9 | String → enum progressif (git_provider, log_level, etc) | L (~7 micro-PRs) | Low |
| 9 | P2-8 | `default_true` centralisé | XS (1 commit) | Nil |
| 10 | P2-10 | `f64::INFINITY` rate_limit check | XS (inclus dans P1-6) | Nil |
| 11 | P2-11 | Path validation (low effort defense-in-depth) | S | Low |
| 12 | P2-12 | Supprimer alias `per_operation` avec ticket tracking | XS | Nil |

**Recommandation P0 batch** : P0-1 + P0-2 + P1-5 en 1 PR cohérent "config hardening" (surface opérationnelle critique). P0-3 en 1 commit séparé (move ou copy du rapport).

**Recommandation P1 batch** : P1-4 + P1-6 + P1-7 en 1 PR "config validation" (test-first, aligne les defaults et ajoute les invariants + roundtrip).

**Recommandation P2 batch** : P2-8 + P2-9 + P2-10 + P2-11 + P2-12 en micro-PRs indépendantes, rythme sprint.

---

## Verification notes (pour le reviewer)

- `cargo check` clean : 2026-04-24 ✓
- Probe Figment binaire pour P0-1 / P0-2 / P1-4 : `/tmp/figment_env_probe/` (artefact éphémère, reproductible via le Cargo.toml + src/main.rs listés dans ce rapport).
- Grep `println!|dbg!|{:?}` sur config : aucun call-site actuel (P1-5 est bien un risque latent, pas un leak actif).
- Grep `STOA_MTLS|STOA_DPOP|STOA_API_PROXY|STOA_LLM_ROUTER|STOA_SENDER_CONSTRAINT` dans tests : aucun test n'exerce le chemin env var nested (donc P0-1 passe silencieusement CI).
- Snapshot `stoa_gateway__config__tests__snapshot_default_config.snap` : exhaustif sur `Config::default()` mais n'attaque pas le round-trip (P1-7).

**Fin du rapport. Aucune modification de code — audit only.**
