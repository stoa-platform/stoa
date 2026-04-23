# GW-2 — REWRITE-PLAN: split `src/config.rs`

> **Statut** : Plan validé avec 4 amendements (cf. § Amendements). **Phase 2 autorisée.**
> Ce fichier remplace l'ancien plan GW-1 (livré, voir git log + `stoa-gateway/src/handlers/admin/`).

## Amendements (post-review)

1. **Façade conservée (S1 révisé).** On garde `src/config.rs` comme façade et on ajoute des enfants `src/config/*.rs` à côté. Rust 2018 autorise `foo.rs` + `foo/` simultanés ; seul `foo.rs` + `foo/mod.rs` est interdit. Pas de rename atomique initial. Réduit le churn Git et supprime un commit purement mécanique.
2. **Path fix : `super::defaults` est incorrect.** Dans `src/config.rs` (module courant), `super` désigne le **parent** de `config` (crate root), pas son enfant. Correct : `use self::defaults::*;` ou `use crate::config::defaults::*;`. Appliqué partout où le plan disait `super::defaults`.
3. **Visibilité module resserrée.** `mod defaults;` (pas `pub mod defaults;`) + `pub use defaults::Xxx;` pour exposer les types via chemin canonique public tout en gardant `defaults` privé. Même principe pour `loader`, `mtls`, etc. — seuls les **types** sont publics via re-export, pas les **modules** eux-mêmes.
4. **Snapshot serialized, pas `Debug`.** `Debug` dérivé n'est pas stable entre versions Rust (doc std explicite). On utilise `insta::assert_json_snapshot!(&Config::default())` ou `serde_json::to_string_pretty` + fichier figé. `insta` (features `json` + `redactions`) est déjà en dev-deps — zéro nouvelle dep.
5. **LOC target assoupli.** Plus de cible quasi-contractuelle `mod.rs ~500–550`. La règle : **nouveaux helpers < 400 LOC ; root config peut dépasser à cause du contrat flat**. On mesure après.

## 0. État actuel (numéros précis)

- **Fichier** : `src/config.rs` — **1973 LOC**.
- **Structs publiques** : 7 + 1 enum publique.
- **`fn default_*()`** : **79 fonctions** (intra-fichier uniquement).
- **Blocs `impl Default`** : 4 (`LlmRouterConfig`, `ApiProxyConfig`, `MtlsConfig`, `Config`).
- **Tests inline** : **29** (`#[test]`, pas de `#[tokio::test]`).
- **Feature gates (`#[cfg(feature = ...)]`) dans le fichier** : **0**.
- **Sections marquées `// === … ===`** : **50** domaines documentés (grain très fin).
- **Struct `Config` elle-même** : 793 LOC (lignes 21 → 814, ~140 champs flat).
- **`impl Default for Config`** : 157 LOC (lignes 1394 → 1551).
- **`impl Config`** : 75 LOC (lignes 1553 → 1627) — 3 méthodes : `keycloak_backend_url()`, `load()`, `validate()`.

## 1. Contraintes dures (non négociables)

### Contrat TOML/YAML flat — point clé
Le `Config` est aujourd'hui **flat** : ~140 champs au premier niveau (port, host, jwt_secret, …, snapshot_body_max_bytes). Seuls 6 champs sont nested :
- `mtls: MtlsConfig`
- `dpop: DpopConfig` (déjà hors-config.rs, dans `crate::auth::dpop`)
- `sender_constraint: SenderConstraintConfig`
- `api_proxy: ApiProxyConfig` (+ `ProxyBackendConfig` via `HashMap<String, ProxyBackendConfig>`)
- `llm_router: LlmRouterConfig`
- `federation_upstreams: Vec<FederationUpstreamConfig>`

Les 140 autres champs **doivent rester flat** (un YAML `port: 8080` au root doit continuer à parser). **On ne peut pas regrouper ces champs dans des sous-structs sans casser le contrat**. `#[serde(flatten)]` préserverait TOML mais casserait tous les callers (accès `config.mtls_enabled` → `config.auth_group.mtls_enabled`).

**Conséquence directe** : le découpage ne peut pas ramener `mod.rs` à 400 LOC. Il peut le ramener à ~500–550 LOC (struct seule, sans defaults, sans impls, sans tests). Les 400 LOC s'appliqueront pour les **nouveaux** sous-modules (mtls, api_proxy, …), pas pour `mod.rs`.

### Autres contraintes
- Aucun nouveau `Cargo.toml` dep.
- Toutes les env vars doc-commentées (`STOA_…`) restent valides (on ne touche ni aux noms de champs ni à Figment).
- Aucun fichier YAML fixture à modifier (on n'en trouve d'ailleurs pas dans le périmètre : pas de `config.yaml` ni `examples/` existants).
- Feature gates : 0 dans le fichier, rien à préserver côté `#[cfg(feature)]`.

## 2. Inventaire par domaine

| Domaine | Struct(s) / enum | Champs | Default fns | `impl Default` | Tests inline | LOC cible |
|---|---|---|---|---|---|---|
| **Root Config** (flat) | `Config` | ~140 | ~40 `fn default_*()` non-domaine (port, host, kafka, otel, quota, access_log, etc.) | 1 (`Default for Config`) | 24 | ~500 (struct) + 200 (defaults+impl Default) + 80 (loader) |
| **mTLS** (CAB-864) | `MtlsConfig` | 13 | 10 (8 headers + `default_require_binding` + `default_tenant_from_dn`) | 1 explicite | 2 | ~190 |
| **Sender-Constraint** (CAB-1607) | `SenderConstraintConfig` | 3 | 0 (uses `#[derive(Default)]`) | derive | 0 | ~35 |
| **API Proxy** (CAB-1722) | `ApiProxyConfig`, `ProxyBackendConfig` | 3 + 9 | 4 (`default_api_proxy_require_auth`, `default_proxy_backend_auth_type`, `default_proxy_backend_header`, `default_proxy_backend_timeout_secs`) + `default_true` partagé (cf. §7) | 1 explicite (ApiProxyConfig) | 3 | ~160 |
| **LLM Router** (CAB-1487) | `LlmRouterConfig` | 5 | 0 (défauts via `#[serde(default)]` sur sous-types) | 1 explicite | 0 | ~55 |
| **Federation upstreams** (CAB-1752) | `FederationUpstreamConfig` | 4 | 0 | 0 | 0 | ~25 |
| **Tool expansion** (CAB-2113) | `ExpansionMode` (enum, kebab-case + alias `per_operation`) | — | 0 | derive | 1 (`expansion_mode_accepts_kebab_and_snake_alias`) | ~50 |

### Dépendances externes citées dans `Config`
- `crate::mode::GatewayMode` (champ `gateway_mode`)
- `crate::auth::dpop::DpopConfig` (champ `dpop`) — **déjà dans son propre module**, pas de déplacement
- `crate::guardrails::PromptGuardAction` (champ `prompt_guard_action`)
- `crate::llm::{RoutingStrategy, ProviderConfig, SubscriptionMapping}` (utilisés dans `LlmRouterConfig`)

Aucune n'a besoin de bouger. `config/mod.rs` et les sous-modules les importent tels quels.

### Callers externes (à NE PAS toucher)
- `src/main.rs` : `stoa_gateway::config::{Config, ExpansionMode}`
- **30** `use crate::config::…` dans `src/` (hors `src/config.rs`) — types consommés : `Config` (majorité), `MtlsConfig`, `SenderConstraintConfig`, `LlmRouterConfig`, `ApiProxyConfig`, `ProxyBackendConfig`, `ExpansionMode`
- **8** `stoa_gateway::config::…` dans `tests/` — types consommés : `Config`, `LlmRouterConfig`

**Règle** : `config/mod.rs` **re-exporte** (`pub use`) ces 7 types → aucune édition de callers externes.

## 3. Découpage cible (amendement 1 : façade conservée)

```
src/
├── config.rs                # FAÇADE — struct Config (flat) + mod decls + pub use + #[cfg(test)] mod tests
└── config/
    ├── defaults.rs          # root-level fn default_*() + impl Default for Config
    ├── loader.rs            # impl Config { keycloak_backend_url, load, validate } + regression test
    ├── mtls.rs              # MtlsConfig + 10 default fns + impl Default + 2 tests
    ├── sender_constraint.rs # SenderConstraintConfig (derive Default)
    ├── api_proxy.rs         # ApiProxyConfig + ProxyBackendConfig + 4 default fns + impl Default + 3 tests
    ├── llm_router.rs        # LlmRouterConfig + impl Default
    ├── federation.rs        # FederationUpstreamConfig
    ├── expansion.rs         # ExpansionMode + 1 test
    └── tests.rs             # #[cfg(test)] — Config-level tests (~24)
```

Note Rust 2018 : `src/config.rs` + `src/config/*.rs` coexistent légalement. Pas de rename `config.rs → config/mod.rs`.

### Taille attendue après split (amendement 5 : targets indicatifs, pas contractuels)

| Fichier | LOC attendu | Remarque |
|---|---|---|
| `config.rs` (façade) | non-contraint | Struct `Config` + section headers + `mod` decls + `pub use`. Dépasse 400 LOC par design (140 champs flat). Mesure ex-post. |
| `config/defaults.rs` | ~200 | 40 fns + `impl Default for Config`. |
| `config/loader.rs` | ~90 | 3 méthodes + 1 test régression keycloak_backend_url. |
| `config/mtls.rs` | ~190 | Cohérent, autonome. |
| `config/sender_constraint.rs` | ~35 | |
| `config/api_proxy.rs` | ~160 | |
| `config/llm_router.rs` | ~55 | |
| `config/federation.rs` | ~25 | |
| `config/expansion.rs` | ~50 | |
| `config/tests.rs` | ~300 | 24 tests Config-level. Idiomatic Rust : `#[cfg(test)] mod tests;` + fichier frère. |

**Règle de merge (amendement 5)** : tous les **nouveaux** fichiers `config/*.rs` **< 400 LOC** ; `config.rs` (façade root) peut dépasser à cause du contrat flat. On audite ex-post.

### Justification de s'écarter du brief `{auth, mcp, telemetry, router, shadow}`
Le brief suggère un split par grand domaine fonctionnel. Mais le `Config` actuel n'a **que** quelques structs réellement nested (mtls, sender_constraint, api_proxy, llm_router, federation, expansion). Les ~140 autres champs sont **flat** et doivent le rester (cf. §1). Donc on ne peut pas créer `config/auth.rs` qui regroupe jwt_secret, keycloak_*, mtls, dpop, sender_constraint — ça exigerait de les déplacer dans une sub-struct auth, ce qui casserait le contrat TOML ET les callers.

→ **Le split se fait aux seules frontières structurelles actuelles** : 1 fichier par struct nested + 1 fichier pour les defaults root + 1 fichier pour le loader. Pas de regroupement thématique des champs flat. C'est l'équivalent exact de GW-1 (admin.rs → 17 fichiers selon la répartition des handlers existants).

## 4. Root Config (`src/config.rs` façade)

### Contenu cible
1. `//! Configuration with Figment` (docstring existant, conservé)
2. `use` statements :
   - `figment`, `serde::{Deserialize, Serialize}`, `crate::mode::GatewayMode`
   - `use self::defaults::*;` **← amendement 2** (pas `super::defaults::*`)
   - Les structs nested importées via `self::{mtls::MtlsConfig, api_proxy::ApiProxyConfig, …}` ou par re-export direct
3. **Module declarations privées (amendement 3)** :
   ```rust
   mod defaults;
   mod loader;
   mod mtls;
   mod sender_constraint;
   mod api_proxy;
   mod llm_router;
   mod federation;
   mod expansion;
   ```
   (`mod`, pas `pub mod` — les sous-modules sont des détails d'implémentation)
4. `pub use` re-exports (cf. §6) — c'est ÇA qui expose les types publiquement
5. `pub struct Config { … }` — la struct flat intacte, 140 champs, section headers préservés
6. `#[cfg(test)] mod tests;` (pointe vers `config/tests.rs`)

### Ce qui sort de `src/config.rs`
- Toutes les `fn default_*()` non-domaine → `config/defaults.rs`
- `impl Default for Config` → `config/defaults.rs` (co-located avec les fns qu'il appelle)
- `impl Config` (load, validate, keycloak_backend_url) → `config/loader.rs`
- Les 24 tests Config-level → `config/tests.rs`
- Tout ce qui concerne une struct nested → son fichier dédié

## 5. Visibilité (resserrage)

| Symbole | État actuel | Cible |
|---|---|---|
| Structs nested publiques re-exportées | `pub` | **`pub`** (stable API via re-export `mod.rs`) |
| Fns `default_*()` root-level appelées par `#[serde(default = "…")]` dans `Config` | `fn` privée | **`pub(super)` dans `defaults.rs`** (requises visibles depuis `mod.rs`) |
| Fns `default_mtls_*` (et autres domain-scoped) | `fn` privée | **restent privées dans leur fichier** — struct et fn co-locates, pas besoin d'exporter |
| `MtlsConfig`, `SenderConstraintConfig`, etc. | `pub` | **`pub`** (conservé, callers externes) |
| `ExpansionMode` | `pub` | **`pub`** (caller `main.rs`, `mcp/tools/api_bridge.rs`) |
| `FederationUpstreamConfig` | `pub` | **`pub`** (champ `federation_upstreams: Vec<FederationUpstreamConfig>` dans Config public) |
| `ProxyBackendConfig` | `pub` | **`pub`** (caller `src/proxy/api_proxy.rs`) |

**Règle** : tout ce qui est consommé hors du crate ou par d'autres modules reste `pub`. Tout ce qui devient cross-file intra-`config/` devient `pub(super)` au minimum. Pas d'API élargie, pas d'API resserrée sur les types publics (compat stricte).

## 6. Re-exports requis (`src/config.rs` façade)

```rust
pub use api_proxy::{ApiProxyConfig, ProxyBackendConfig};
pub use expansion::ExpansionMode;
pub use federation::FederationUpstreamConfig;
pub use llm_router::LlmRouterConfig;
pub use mtls::MtlsConfig;
pub use sender_constraint::SenderConstraintConfig;
```

Ne **PAS** re-exporter :
- Les `default_*()` (implementation detail)
- Les modules sous-jacents en tant que `pub use defaults::*` (explosion de surface)

Vérification après split :
```bash
# Doit retourner exactement le même compteur qu'avant (39 total)
grep -rn "crate::config::\|stoa_gateway::config::" src/ tests/ --include="*.rs" | grep -v "^src/config" | wc -l
```

## 7. Points délicats identifiés

### 7.1 `default_true()` est partagé
La fn `default_true()` (ligne 963 actuelle) est utilisée par :
- `Config::proxy_metrics_enabled` (mod.rs)
- `Config::proxy_tracing_enabled` (mod.rs)
- `ProxyBackendConfig::circuit_breaker_enabled` (api_proxy.rs)

Trois sites d'appel, deux fichiers cibles. **Décision** : garder `pub(super) fn default_true()` dans `defaults.rs` ; `api_proxy.rs` l'utilise via chemin qualifié. Sérialisation côté serde : `#[serde(default = "crate::config::defaults::default_true")]` dans `api_proxy.rs`. **Deux attributes serde différents, une seule fn source.** Évite la duplication.

### 7.2 `#[serde(default = "chemin")]` est un path string
Serde résout la chaîne comme un path Rust à l'expansion macro. Si on bouge `default_port()` hors de `src/config.rs`, le field `pub port: u16` avec `#[serde(default = "default_port")]` **doit** pouvoir résoudre `default_port` dans son scope. **Solution correcte (amendement 2)** :
```rust
use self::defaults::*;      // ou use crate::config::defaults::*;
// PAS `use super::defaults::*;` — super pointe vers le parent de config (crate root)
```

**Validation obligatoire** : `cargo check` après step S8 (extraction defaults) ; si échec résolution path, fallback = imports explicites listés un par un.

### 7.3 `impl Default for Config` co-location avec `defaults.rs`
Convention Rust traditionnelle : `impl Default for X` vit avec la struct `X`. Ici on le déplace dans `defaults.rs` parce que :
1. L'impl fait **157 LOC** d'affilée et appelle ~40 `default_*()` locaux.
2. Co-locater tous les defaults (fn + impl) dans un seul fichier simplifie l'entretien : chaque nouveau champ = 1 seule édition dans un seul fichier.
3. `mod.rs` devient une pure declaration de struct + re-exports.

**Risque** : convention surprenante. Mitigation : docstring en haut de `defaults.rs` expliquant la convention. Pas de problème orphan rule (Default est dans std, Config est local, impl est dans le même crate).

### 7.4 Env var nesting (hors scope — à documenter dans `REWRITE-BUGS.md`)
Les doc-comments de `MtlsConfig`, `SenderConstraintConfig` etc. affirment `STOA_MTLS_ENABLED`, `STOA_SENDER_CONSTRAINT_ENABLED`, etc. Mais Figment dans `loader.rs` utilise `Env::prefixed("STOA_")` **sans** `.split()`. Sans split, `STOA_MTLS_ENABLED` se résout en field flat `mtls_enabled` — qui **n'existe pas** au root de Config. Le Config attend plutôt la source YAML (`mtls: { enabled: true }`) ou `STOA_MTLS__ENABLED` avec double underscore (convention Figment).

→ **Comportement actuel conservé, documenté dans `REWRITE-BUGS.md`** comme divergence potentielle doc/code. **Pas fixé silencieusement** (risque incident prod si on active split env naïvement, impact middleware auth).

### 7.5 Tests de régression cross-file
- `regression_keycloak_backend_url_prefers_internal` (ligne 1929) teste `Config::keycloak_backend_url()` → va avec `loader.rs` (à co-locater avec la méthode testée).
- `expansion_mode_accepts_kebab_and_snake_alias` → va avec `expansion.rs`.
- `test_default_mtls_*` → `mtls.rs`.
- `test_default_api_proxy_*`, `test_api_proxy_*`, `test_proxy_backend_defaults` → `api_proxy.rs`.
- Tous les autres `test_default_*` → `tests.rs` (fichier frère de `mod.rs`).

### 7.6 `use crate::mode::GatewayMode` et `use crate::auth::dpop::DpopConfig`
Restent dans `mod.rs` (struct Config en a besoin). Pas de déplacement. Pas de cycle (ni `mode` ni `auth::dpop` n'importent de `config`).

### 7.7 `use std::collections::HashMap`
Utilisé uniquement pour `ApiProxyConfig.backends: HashMap<String, ProxyBackendConfig>`. Déplacer avec `api_proxy.rs`. Retirer de `mod.rs`.

## 8. Plan d'exécution (Phase 2) — **amendement 1 appliqué**

Ordre topologique, un commit par step, `cargo check && cargo test` vert entre chaque. **Façade `src/config.rs` conservée tout du long.**

1. **[S1 — expansion]** Créer `src/config/` (sous-dir). Extraire `ExpansionMode` enum + son test → `src/config/expansion.rs`. Ajouter `mod expansion; pub use expansion::ExpansionMode;` dans `src/config.rs`.
   - Commit : `refactor(gateway): extract ExpansionMode (GW-2 S1)`

2. **[S2 — federation]** Extraire `FederationUpstreamConfig` → `src/config/federation.rs`.
   - Commit : `refactor(gateway): extract FederationUpstreamConfig (GW-2 S2)`

3. **[S3 — sender_constraint]** Extraire `SenderConstraintConfig` → `src/config/sender_constraint.rs`.
   - Commit : `refactor(gateway): extract SenderConstraintConfig (GW-2 S3)`

4. **[S4 — llm_router]** Extraire `LlmRouterConfig` + son `impl Default` → `src/config/llm_router.rs`.
   - Commit : `refactor(gateway): extract LlmRouterConfig (GW-2 S4)`

5. **[S5 — api_proxy]** Extraire `ApiProxyConfig`, `ProxyBackendConfig`, leurs 4 default fns, leur `impl Default`, leurs 3 tests → `src/config/api_proxy.rs`. Adapter référence cross-file à `default_true` (cf. §7.1).
   - Commit : `refactor(gateway): extract ApiProxyConfig (GW-2 S5)`

6. **[S6 — mtls]** Extraire `MtlsConfig` + 10 default fns + `impl Default` + 2 tests → `src/config/mtls.rs`.
   - Commit : `refactor(gateway): extract MtlsConfig (GW-2 S6)`

7. **[S7 — loader]** Extraire `impl Config { keycloak_backend_url, load, validate }` + test `regression_keycloak_backend_url_prefers_internal` → `src/config/loader.rs`.
   - Commit : `refactor(gateway): split Config loader (GW-2 S7)`

8. **[S8 — defaults]** Extraire les ~40 `fn default_*()` root-level + `impl Default for Config` → `src/config/defaults.rs`. Ajouter `use self::defaults::*;` (**amendement 2**) dans `src/config.rs` pour résoudre les `#[serde(default = "default_foo")]`.
   - `cargo check` VITAL après cette étape. Si échec résolution path, fallback imports explicites.
   - Commit : `refactor(gateway): extract root config defaults (GW-2 S8)`

9. **[S9 — tests]** Déplacer les ~24 tests Config-level inline → `src/config/tests.rs` (fichier frère, `#[cfg(test)] mod tests;` dans `src/config.rs`).
   - Commit : `refactor(gateway): move Config tests to tests.rs (GW-2 S9)`

10. **[S10 — snapshot]** Ajouter snapshot **sérialisé** (**amendement 4**) : `insta::assert_json_snapshot!(&Config::default())`. Accepter le `.snap` initial (baseline). `insta` déjà en dev-deps avec feature `json`. Pas de nouvelle dep.
    - Commit : `refactor(gateway): add serialized snapshot for Config defaults (GW-2 S10)`

11. **[S11 — validation]** `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check`, `cargo doc --no-deps`, ajustements finaux.
    - Commit : `refactor(gateway): finalize config split (GW-2 S11)` (ou pas de commit si rien à ajuster)

**Points de réversion** : chaque step est un commit atomique. Revert d'un step = `git revert` propre (pas de cascade).

**Durée estimée** : 2–3h de mise en œuvre séquentielle (similaire cadence GO-2 S1–S10).

## 9. Snapshot test (critique — anti-drift de default, **amendement 4**)

`Debug` dérivé n'est **pas stable** entre versions Rust (std docs, `trait Debug`). On utilise un snapshot **sérialisé** via `serde`.

**Modalité retenue** (confirmé disponible, cf. Cargo.toml dev-deps) :
```rust
#[test]
fn snapshot_default_config() {
    insta::assert_json_snapshot!(&Config::default());
}
```

- `insta = { version = "1", features = ["json", "redactions"] }` déjà présent.
- Baseline capturée au step S10 (accepter `.snap` initial généré par `cargo insta review`).
- Un changement de champ/default = diff visible dans le `.snap` lors de la review.

Fallback si `insta` pose problème : `serde_json::to_string_pretty(&Config::default())` + fichier texte committed + `assert_eq!`. Pas d'ajout de dépendance.

## 10. Validation Phase 3 (critères de merge)

- [ ] `cargo check` : 0 warning nouveau
- [ ] `cargo clippy --all-targets -- -D warnings` : 0 issue (CI exact)
- [ ] `cargo fmt --check` : propre
- [ ] `cargo test` : tous tests verts, compteur ≥ avant (29 dans `config.rs`, doit rester 29 ou +1 avec snapshot test)
- [ ] `cargo doc --no-deps` : 0 nouveau warning
- [ ] Chaque fichier **nouveau** `src/config/*.rs` < 400 LOC (amendement 5). Façade `src/config.rs` sans cible contractuelle, mesurée ex-post.
- [ ] `tests.rs` ~300 LOC accepté (test code).
- [ ] Snapshot test `insta::assert_json_snapshot!(&Config::default())` identique à baseline pré-rewrite (amendement 4)
- [ ] `grep -rn "crate::config::\|stoa_gateway::config::"` même count qu'avant (~39 total)
- [ ] `cargo build --all-targets` passe **sans édit des callers externes**
- [ ] `REWRITE-BUGS.md` commit si bugs latents découverts (§7.4, §11)

## 11. Risques Rust identifiés

| Risque | Impact | Mitigation |
|---|---|---|
| `#[serde(default = "default_foo")]` path resolution après move des fns | Compile-fail `cannot find function` | `use self::defaults::*;` dans `src/config.rs` (**amendement 2** — pas `super`) ; `cargo check` après step S8 ; fallback imports explicites |
| `default_true()` utilisée par 3 sites dans 2 fichiers | Duplication ou import cyclique | Garder dans `defaults.rs`, référer par chemin qualifié dans `api_proxy.rs` (`#[serde(default = "crate::config::defaults::default_true")]`) |
| Orphan rule sur `impl Default for Config` co-located avec `defaults.rs` et non avec struct | Aucun (Default ∈ std, Config est local — orphan rule OK) | Documentation en-tête de `defaults.rs` pour expliquer la convention |
| Macro expansion de `#[derive(Deserialize)]` dépendante du path courant | Très rare, mais possible si path default est relatif | Préférer imports explicits `use super::defaults::…`, éviter glob problématique |
| Tests de config n'utilisent que defaults (pas de round-trip YAML) | Drift default silencieux non détecté par tests existants | Snapshot test §9 (obligatoire) + `REWRITE-BUGS.md` note coverage pauvre |
| `Figment` Env source : flat parsing (sans `.split()`) | Doc-comments STOA_MTLS_ENABLED trompeurs | Hors scope du rewrite, documenté dans `REWRITE-BUGS.md` |
| Import cyclique `config/mod.rs` ↔ sub-modules | Si sub-module importe `Config` et vice versa | Sub-modules n'importent **pas** `Config`. `Config` importe les struct nested. DAG acyclique. |
| `crate::auth::dpop::DpopConfig` import | Existant, rien ne change | Garder tel quel dans `mod.rs` |
| Docstring `///` sur les champs utilisé par serde/toml pour exposition schéma | Perte de doc si mal déplacé | Chaque struct bouge avec ses docstrings intactes ; audit après chaque step via `cargo doc --no-deps` |
| Trait `Serialize` implémenté sur `Config` mais pas utilisé en test | Risque drift de sérialisation si field order matters | Le test snapshot couvre `Debug` pas `Serialize`. Ajout d'un second snapshot `serde_yaml::to_string(&Config::default())` en step S11 si le coût est faible (une ligne de test) |

## 12. Ce qui ne sera **pas** fait dans cette PR (suivi séparé)

- **Fix doc/code des env vars nested** (`STOA_MTLS_ENABLED` vs `STOA_MTLS__ENABLED`) : risque incident prod, demande un plan dédié + Council (impact middleware auth).
- **Regrouper les 140 champs flat en sous-structs** : casse le TOML contract + tous les callers. Sujet stratégique = breaking change de config API, hors périmètre GW-2.
- **Validation runtime renforcée** : `Config::validate()` se contente de `tracing::warn!`. Ajouter `Result<(), ConfigError>` = changement comportemental, pas un rewrite.
- **Couverture tests Config** : 29 tests happy-path, 0 test parse YAML réel, 0 test serde round-trip. Noter dans `REWRITE-BUGS.md` pour Wave 2.

---

**Fin du plan. Validation humaine requise avant Phase 2.**
