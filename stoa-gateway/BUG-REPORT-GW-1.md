# BUG-REPORT-GW-1 — `stoa-gateway/src/handlers/admin/`

> **Rev 2 (post-review)** — reclassifications appliquées après review :
> P0-3 reclassé P1 (sécurité/hardening), P1-7 marqué "à vérifier / probablement non-bug" (matchit literal>param + MethodRouter 405), P1-8 reclassé P2 test-infra, P1-10 reclassé P2 (observabilité DORA-adjacent).
> Exploitability de P0-1 atténuée (sans mesure réelle d'infra, "~1h" était trop précis). P2-2 rattaché au batch contracts avec P1-1/P1-2.

**Scope** : 17 admin sub-modules + façade `admin.rs` + router wiring `src/lib.rs` (`admin_router`, lignes 93-263) + handler externe `src/proxy/api_proxy_handler.rs::list_api_proxy_backends` (orphelin sous `/admin/`).
**Méthode** : lecture exhaustive des 17 fichiers, scans greppés (unwrap/panic, locks, spawn, unsafe, secrets, validation, http-timeout, audit, rate-limit), confrontation au routeur prod `lib.rs`.
**Commit audité** : branche `fix/cp-1-p2-batch` @ `5a885b08a` (post-GW-1 merge `dc56524a`, post-CP-1 `b58bdca40`).
**Hors scope** : pas de fix dans ce pass ; documentation seulement, comme convenu.

---

## Executive summary (Rev 2)

| Sévérité | Count | Notes |
|---|---|---|
| **P0** | **2** | Timing-attack admin_auth, endpoint orphan sans auth |
| **P1** | **9** | Reload error leak (ex-P0), état transactionnel, validation manquante, memory growth, rate-limit, audit log |
| **P2** | **9** | Drift observabilité, UX CRUD, test-harness drift, fake deploy steps, routing à vérifier |
| **Hors scope** | 3 | Design / couverture tests (non comptés) |
| **TOTAL** | **20 bugs + 3 notes** | |

**Top 2 risques confirmés** :

1. **auth.rs:43** — comparaison non-timing-safe du bearer token admin ; la crate `subtle::ConstantTimeEq` est déjà présente (utilisée `src/auth/sender_constraint.rs:21`) mais pas ici. Sérieux surtout combiné à l'absence de rate-limit (P1-3).
2. **lib.rs:374** — `/admin/api-proxy/backends` est greffé **à l'extérieur** de l'`admin_router` ; il ne passe **pas** par le middleware `admin_auth`. Comportement confirmé par la doc Axum : `Router::layer()` n'applique qu'aux routes déclarées avant. Exposé anonymement en mode `EdgeMcp` en attendant vérif `curl`.

**Risque fonctionnel n°1 (P1-1/P1-2)** : `upsert_contract` écrit dans `contract_registry` **puis** tente `rest_binder.bind()` et `mcp_binder.bind()` ; un échec du binder n'est que `warn!` et la réponse HTTP reste 200/201. État inconsistant persisté + caller aveugle. Même pattern pour `delete_contract` (`unwrap_or(0)` côté unbind).

**Observations structurelles positives** :
- 0 `unsafe`, 0 `tokio::spawn`, 0 lock contention dans admin/* (concurrence déléguée aux registries/stores — bon découpage).
- 0 `unwrap`/`expect`/`panic!` en code prod (uniquement tests derrière `#[cfg(test)]`).
- 0 injection de commande shell, 0 accès fichier, 0 path-traversal possible via `Path<String>` (toutes utilisations = clés de registre).
- Le split GW-1 en 17 modules a bien isolé les surfaces par domaine ; le façade `admin.rs:1-81` est propre (80 LOC, re-exports seulement).

---

## Critical (P0)

### P0-1 — Timing attack sur `admin_auth`
- **Fichier** : `src/handlers/admin/auth.rs:43`
- **Code** :
  ```rust
  if auth_header == expected_header {
      Ok(next.run(request).await)
  } else { ... Err(UNAUTHORIZED) }
  ```
- **Problème** : `==` sur `&str` est un memcmp early-exit. La classe d'attaque (mesure de RTT par octet) est bien documentée (AWS SigV4 *timing-leak* 2020, Heartbleed-style probes). **Pas de chiffrage d'exploitabilité sans mesure sur l'infra réelle** — la faisabilité dépend du jitter WAN/LAN, du nombre de requêtes que l'attaquant peut faire (cf. P1-3 rate-limit absent = amplificateur direct), et de la stabilité de la latence côté serveur. Le bug reste sérieux, classe P0 au titre du principe défensif : *un secret long-lived ne se compare jamais avec `==`*.
- **Sévérité P0** : admin_api_token ouvre **tous** les endpoints admin (upsert routes/policies, reload, cache flush, credentials CRUD, etc.) — compromission totale du data plane.
- **Fix direction** :
  ```rust
  use subtle::ConstantTimeEq;
  // ct_eq sur deux slices de longueur identique ; construire expected_header comme slice
  // de la même longueur que auth_header quand c'est possible, sinon short-circuiter
  // sur la longueur (fuite d'info mineure sur la taille du token, acceptable).
  let ok = auth_header.len() == expected_header.len()
      && auth_header.as_bytes().ct_eq(expected_header.as_bytes()).unwrap_u8() == 1;
  ```
  La crate `subtle` documente `ct_eq` comme constant-time et renvoie un `Choice` via `unwrap_u8()`. Le pattern existe déjà dans `src/auth/sender_constraint.rs:303`.
- **Tests à ajouter** : test de régression unit `test_admin_auth_wrong_length` + `test_admin_auth_same_length_wrong_byte`.

### P0-2 — Endpoint orphelin `/admin/api-proxy/backends` sans auth
- **Fichier** : `src/lib.rs:374` (+ `src/proxy/api_proxy_handler.rs:451-489`)
- **Code** :
  ```rust
  // lib.rs, dans edge_base (EdgeMcp mode)
  .route("/admin/api-proxy/backends", get(list_api_proxy_backends))
  ```
- **Problème** : cette route est ajoutée **sur `edge_base`**, après `.nest("/admin", admin_router)` à la ligne 264. L'`admin_router` applique `admin_auth` via `.layer(...)` à la ligne 253-257 — comportement confirmé par la doc Axum : *`Router::layer()` n'applique qu'aux routes présentes au moment où la layer est ajoutée*. Les routes greffées à `edge_base` ne récupèrent **pas** cette layer. En cas de collision de path, la route directe prend priorité → la route est **anonymement accessible** tant qu'un test ne prouve pas le contraire.
- **Surface leakée** (cf. `api_proxy_handler.rs:470-478`) :
  - `base_url` de chaque backend (URLs internes d'infra)
  - `rate_limit_rpm` (tunable réservé opé)
  - `circuit_breaker_open` (état runtime)
  - `fallback_direct` (bypass CB activé ou non)
- **Vérification requise** (à faire avant fix) :
  ```bash
  curl -sSI https://<gateway>/admin/api-proxy/backends  # SANS Authorization header
  # attendu après fix : 401 ; comportement actuel supposé : 200 + JSON des backends
  ```
- **Sévérité P0** : info disclosure cross-tenant, pré-requis typique à un mouvement latéral ; viole l'hypothèse "tout sous `/admin/` requiert bearer token" documentée dans `admin.rs:16`.
- **Fix direction** : déplacer cette route dans `admin_router` (dans le bloc `let admin_router = Router::new()...` de `src/lib.rs`). Ajouter un test `tokio::test` qui vérifie `401` sans bearer et `200` avec bearer. *NB* : seule la branche `EdgeMcp` enregistre la route (lignes 293-468) ; Sidecar/Proxy/Shadow ne sont pas concernés.

---

## High (P1)

### P1-0 — Fuite d'informations internes dans les erreurs de `/admin/routes/reload` *(ex-P0-3, reclassé P1 post-review)*
- **Fichier** : `src/handlers/admin/reload.rs:33-39, 53-79`
- **Code** :
  ```rust
  Err(e) => (
      StatusCode::INTERNAL_SERVER_ERROR,
      Json(json!({ "status": "error", "message": format!("Route reload failed: {}", e) })),
  ),
  // avec e ∈ { "HTTP request failed: {reqwest_err}", "CP returned status {code}",
  //           "Failed to parse response: {serde_err}", "STOA_CONTROL_PLANE_URL not configured" }
  ```
- **Problème** : l'erreur bubblée vers le client admin contient des détails internes (URL du control-plane, nom DNS, motif de parsing JSON, stack reqwest). Endpoint derrière admin_auth, donc la surface est limitée à un attaquant déjà compromis — **mais** : viole le principe "ne jamais renvoyer de stack d'erreur brute côté client" et sert de vecteur de reconnaissance post-compromission.
- **Reclass P1** : pas de bypass d'auth, pas d'exploit direct ; c'est un *hardening defense-in-depth*. Garde le 1er batch avec les P0 par opportunisme (petite PR, même reviewer, même test surface).
- **Reproduction** :
  ```bash
  STOA_CONTROL_PLANE_URL=http://10.0.5.42:8080 cargo run
  curl -H "Authorization: Bearer $TOKEN" -XPOST https://<gw>/admin/routes/reload
  # → "Route reload failed: HTTP request failed: error sending request ... tcp connect error: Connection refused (os error 111)"
  ```
- **Fix direction** :
  1. Log complet (tracing::error! avec request_id) pour l'observabilité.
  2. Réponse client générique : `"message": "Route reload failed"` + `request_id` (corrélation côté log).
  3. Mapping ciblé pour les erreurs connues-utiles : `404` si CP a répondu 404, `502` si CP down, `503` si `STOA_CONTROL_PLANE_URL` absent.

### P1-1 — État transactionnel cassé sur `upsert_contract`
- **Fichier** : `src/handlers/admin/contracts.rs:57-99`
- **Séquence** :
  1. `contract_registry.upsert(contract.clone())` → commit en mémoire (ligne 61).
  2. `rest_binder.bind(&contract).await` → peut échouer, `warn!` seulement (67-71).
  3. `mcp_binder.bind(&contract).await` → idem (75-81).
  4. Réponse `201 CREATED` / `200 OK` avec `routes_generated: 0` en cas d'échec.
- **Conséquence** : le contrat est persisté sans routes REST ni outils MCP associés ; `GET /admin/contracts/:key` le retournera mais `GET /apis` n'exposera rien. Dérive silencieuse de l'état. Aucun rollback, aucun code d'erreur côté client.
- **Sévérité P1** : bug de cohérence avec impact UX + audit DORA (action admin réputée réussie alors que l'effet est partiel).
- **Fix direction** : séquence bind-first → puis upsert, ou deux-phase commit (bind dans une struct temporaire → swap atomique) ; **a minima** retourner `207 Multi-Status` / `500` avec `binders_failed: [...]` dans le body quand une des opérations bind échoue.

### P1-2 — Erreur d'unbind silencieusement écrasée sur `delete_contract`
- **Fichier** : `src/handlers/admin/contracts.rs:128, 132`
- **Code** :
  ```rust
  let routes_removed = rest_binder.unbind(&key).await.unwrap_or(0);
  let tools_removed  = mcp_binder.unbind(&key).await.unwrap_or(0);
  ```
- **Problème** : en cas d'erreur (ex : lock empoisonné, registry absent), on répond `200 OK {routes_removed: 0}`. Le contrat est supprimé mais les routes/tools orphelines restent. Client impossible à alerter.
- **Sévérité P1** : miroir inverse de P1-1.
- **Fix direction** : propager l'erreur — `unbind().await.map_err(...)?` ou `match` explicite avec `500` + log.

### P1-3 — Pas de rate-limit sur le routeur admin → amplifie P0-1
- **Fichier** : `src/lib.rs:93-264` (admin_router + nest)
- **Problème** : le routeur admin applique `admin_auth` mais aucune couche de rate-limit/back-off. Combiné au timing-attack (P0-1), un attaquant peut déclencher des millions de comparaisons de token sans être ralenti. `state.rate_limiter` existe (`src/state.rs:59`) mais n'est pas branché ici.
- **Sévérité P1** : propre (rate-limit absent = bug d'ops même sans timing-attack).
- **Fix direction** : ajouter une layer `tower_governor` ou impl maison à 60 req/min/IP avant `admin_auth`. Distinguer les endpoints read-only (tolérance large) des endpoints mutatifs (quelques req/min). **Candidat à inclure dans le batch P0** si la layer est simple (~40 LOC) — renforce directement P0-1.

### P1-4 — Pas d'audit log pour les actions admin mutantes
- **Fichiers concernés** : `apis.rs` (upsert/delete), `policies.rs` (upsert/delete), `contracts.rs` (upsert/delete), `credentials.rs` (4 endpoints mutants), `skills.rs` (upsert/update/delete/sync/reset/health_reset), `reload.rs`, `federation.rs` (cache_invalidate), `quotas.rs` (reset), `circuit_breaker.rs` (reset).
- **Problème** : aucune de ces routes n'émet un événement d'audit structuré (actor, action, resource_key, outcome, timestamp). Les seuls signaux sont des `tracing::warn!` sur rejection (apis.rs:41, 49, 61). Insuffisant pour DORA (exige "auditabilité complète des opérations admin"), ISO 27001 A.12.4.1.
- **Sévérité P1** : bloquant pour certification bancaire (cf. démo juin multi-client).
- **Fix direction** : trait `AdminAuditSink` → topic Kafka dédié / log structuré filtré par appender. Wrapper middleware sur `admin_router` qui capture méthode, path, status, actor, durée. Alternative tactique : crate `tracing` avec champ `audit=true` filtré par un layer dédié. **PR la plus grosse du lot** (~200 LOC + design) — isoler.

### P1-5 — `skills_health` fait croître la mémoire sans borne + fake-positive
- **Fichier** : `src/handlers/admin/skills.rs:255-259` ; délégué à `src/skills/health.rs:90-114`
- **Code** :
  ```rust
  pub fn stats(&self, skill_key: &str) -> SkillHealthStats {
      let counters = self.get_counters(skill_key);                // insère si absent
      ...
      let cb = self.circuit_breakers.get_or_create(skill_key);    // insère si absent
      ...
      SkillHealthStats { ..., success_rate: if total > 0 { .. } else { 1.0 }, circuit_state: state.to_string() }
  }
  ```
- **Problème** : `GET /admin/skills/<id>/health` crée un bucket counters + un CB même si le skill n'existe pas. Admin attaquant ou client naïf → spam `UUID.v4()` → growth non borné. Effet bonus : renvoie `success_rate=1.0`, `circuit_state="closed"` → **fake-positive** sur un skill inexistant (les dashboards d'observabilité mentent).
- **Sévérité P1** : DoS ressource + observabilité mensongère. Admin auth requis mais les défenses en profondeur n'existent pas (pas de rate-limit, cf. P1-3).
- **Fix direction** : dans `skills.rs:255`, vérifier d'abord `state.skill_resolver.get(&id).is_none()` → `404`. Puis `stats` ne doit lire que via une route `get` pure (pas `get_or_create`). Séparer un chemin `get_or_create_for_record()` (usage interne quand on **enregistre** un call) d'un chemin `peek()` read-only pour l'endpoint admin.

### P1-6 — Validation manquante sur 5 endpoints upsert
- **`policies.rs:13-25`** — `PolicyEntry.id`, `name`, `policy_type`, `config`, `api_id` tous acceptés vides. Policy avec id="" stockée sous clé `""`, collision avec autres policy sans id.
- **`credentials.rs:68-69`** (upsert_backend_credential) — `route_id`, `header_name`, `header_value` non vérifiés vides. Clé `""` en store crée conflits ; credential à valeur vide = injection de `Authorization: Bearer ` vide en aval.
- **`credentials.rs:109-126`** (upsert_consumer_credential) — zéro validation : pas de check SSRF même si OAuth2, pas de check presence champs.
- **`skills.rs:82-118, 148-183`** (upsert / sync) — `key`, `name`, `tenant_id` empty-ok. `scope` validé ✓, mais c'est le seul.
- **`apis.rs:40-55`** (upsert_api) — `name` et `backend_url` ✓ (+ SSRF check sur backend_url), mais `id`, `tenant_id`, `path_prefix`, `methods` non vérifiés.
- **Sévérité P1** : admin authentifié peut corrompre l'état silencieusement ; pas exploitable sans accès admin, mais multiplie la surface d'incident op.
- **Fix direction** : un helper `validate_admin_input!(route.id, route.tenant_id, ...)` qui renvoie `400 BAD_REQUEST` listant les champs en défaut. Les `validate()` ad-hoc existants (ex : `UacContractSpec::validate` couvre déjà bien, `src/uac/schema.rs:169-185`) peuvent servir de modèle.

### P1-7 — ~~Conflit de matching `/skills/status` vs `/skills/:id`~~ **À vérifier / probablement non-bug**
- **Fichier** : `src/lib.rs:162-181`
- **Statut post-review** : le finding initial supposait un fallthrough méthode sur `MethodRouter` Axum. Revue faite :
  - `matchit` donne priorité aux segments statiques sur les segments dynamiques → `/skills/status` match le literal avant `/skills/:id`.
  - Axum `MethodRouter` renvoie par défaut `405 Method Not Allowed` + header `Allow` lorsqu'un path matche mais que la méthode n'existe pas. Pas de fallback path-level.
  - Donc `DELETE /skills/status` devrait renvoyer **405**, pas tomber sur `/skills/:id`.
- **Action** : **ne pas fixer** avant preuve. Ajouter un test de régression tactique pour verrouiller le comportement :
  ```rust
  #[tokio::test]
  async fn test_delete_skills_status_returns_405_not_delete_by_id() {
      // pré-seed skill id="status" pour détecter un fallthrough accidentel
      // DELETE /skills/status doit renvoyer 405 et NE PAS supprimer "status"
  }
  ```
- **Sévérité** : désormais hors bug prod. Reste comme "test à écrire" (tag P2-test-regression).

### P1-8 — ~~Drift `build_full_admin_router`~~ **Reclassé P2 test-infra**
- *(Section déplacée vers Medium / P2 — voir P2-test-1)*

### P1-9 — HTTPS check case-sensitive + pas de normalisation URL sur OAuth2 token_url
- **Fichier** : `src/handlers/admin/credentials.rs:44`
- **Code** : `if !oauth2.token_url.starts_with("https://") { return 400; }`
- **Problème** : `HTTPS://...` est rejeté (faux positif sur URL valide), `https://foo\nHost: evil` accepté (pas de parsing URL propre). La chaîne brute est passée plus tard à `is_blocked_url` (ligne 54) qui fait sans doute un parse ; mais la validation initiale est naïve.
- **Sévérité P1 security-adjacent** : vrai bug de validation, pas de bypass connu mais fragile.
- **Fix direction** : parser via `url::Url::parse(&oauth2.token_url)`, vérifier `scheme() == "https"`, `host()` existe, pas de CRLF injection.

---

## Medium (P2)

### P2-1 — `health.rs` toujours `"ok"` — endpoint admin_health sans liveness/readiness
- **Fichier** : `src/handlers/admin/health.rs:17-25`
- **Problème** : `/admin/health` renvoie toujours `status: "ok"`, même si route_registry / policy_registry sont vides mais fonctionnels. Pas de signal de readiness (ex : CP atteignable, KC atteignable). Utilisé comme endpoint admin, pas comme liveness probe K8s — MAIS confusion possible si un opérateur s'y réfère.
- **Fix direction** : ajouter un mode `?readiness=true` qui vérifie CP reachability + KC JWKS cache âge ; ou laisser `/admin/health` purement statique (version + compteurs) et déléguer liveness/readiness à `/ready` + `/health/ready` déjà présents (`src/lib.rs:260-263`) — documenter dans le doc-comment de `admin_health`.

### P2-2 — `routes_count` / `tools_count` couplés à `contract.endpoints.len()` *(rattaché au batch P1-1/P1-2)*
- **Fichier** : `src/handlers/admin/contracts.rs:66, 76`
- **Problème** : on fait confiance à la taille de `contract.endpoints` comme proxy de "nombre de routes/tools générés". Aujourd'hui `RestBinder::generate_routes` est 1-pour-1 (cf. `src/uac/binders/rest.rs:26-68`) mais c'est un couplage implicite. Un futur skip/filtre rendra la métrique fausse sans casser de test.
- **Fix direction** : `rest_binder.bind(...)` renvoie déjà `BindingOutput::Routes(Vec<_>)` ; utiliser `.len()` sur le retour. Idem côté MCP. **À inclure dans la PR "Contract consistency"** avec P1-1 et P1-2.

### P2-3 — `skills_delete` legacy (?key=) coexiste avec `skills_delete_by_id` (:id)
- **Fichier** : `src/handlers/admin/skills.rs:186-195, 243-252`
- **Problème** : deux endpoints DELETE fonctionnellement redondants. Tech-debt, risque de drift comportemental (audit/observabilité inégale).
- **Fix direction** : documenter le legacy comme deprecated + header `Deprecation:` ; planifier suppression CAB.

### P2-4 — `skills_upsert` retourne toujours `200 OK` jamais `201 CREATED`
- **Fichier** : `src/handlers/admin/skills.rs:113-117`
- **Problème** : tous les autres upsert admin (`apis.rs`, `policies.rs`, `credentials.rs`, `contracts.rs`) respectent la convention `OK (update) / CREATED (new)`. Skills casse le contrat.
- **Fix direction** : `let existed = state.skill_resolver.upsert(skill).is_some();` si l'API le permet, sinon probe préalable. Aligner sur le reste.

### P2-5 — `federation_cache_invalidate` renvoie 200 aveuglément
- **Fichier** : `src/handlers/admin/federation.rs:41-53`
- **Problème** : aucune indication si la clé existait. Admin ne peut pas distinguer "cache invalidé" vs "sub_account_id typé n'avait rien en cache" vs "typo dans l'ID".
- **Fix direction** : retourner `{ "invalidated": true|false, "entries_removed": N }` selon l'API du cache.

### P2-6 — `circuit_breaker_reset` ne remonte pas l'état précédent
- **Fichier** : `src/handlers/admin/circuit_breaker.rs:44-51`
- **Problème** : retourne 200 OK même si le CB était déjà `closed`. Admin ne peut pas voir si l'action a eu un effet.
- **Fix direction** : réponse `{ "previous_state": "...", "new_state": "closed" }`.

### P2-7 — `prometheus::gather()` plein-scan à chaque `/admin/llm/costs`
- **Fichier** : `src/handlers/admin/llm.rs:124`
- **Problème** : `prometheus::gather()` itère toutes les MetricFamilies du registry global (peut être centaines de milliers de lignes dans une instance prod chargée). Endpoint admin, appelé rarement, donc pas un P0/P1 — mais inutile ; on peut exposer un `CounterVec` dédié et le lire directement.
- **Fix direction** : stocker une référence aux counters `gateway_llm_cost_total_*` dans `state.cost_calculator` et les lire ciblément.

### P2-8 — `upsert_api` émet des steps de progression fictifs *(ex-P1-10, reclassé P2)*
- **Fichier** : `src/handlers/admin/apis.rs:108-147`
- **Problème** : les steps `ApplyingPolicies` et `Activating` sont émis `step_started`/`step_completed` sans exécuter de travail (`// no-op for direct route upsert`, ligne 108). La route est en fait activée en un seul appel `route_registry.upsert` ligne 95. Les événements télémétriques sont donc mensongers : un consommateur de `state.deploy_progress` (ex : portal UI) affiche une chronologie synthétique qui ne reflète pas la réalité.
- **Sévérité P2 (DORA-adjacent)** : observabilité mensongère. Pour un audit DORA post-incident, un opérateur regardant la timeline peut mal attribuer la cause racine. Downgradé sous P1-4 (audit log) qui est le vrai mécanisme d'auditabilité.
- **Fix direction** : soit émettre ces steps pour de vraies phases (brancher une vraie logique "apply policies" une fois que `upsert_api` les gère), soit les supprimer et laisser `Validating` → `ApplyingRoutes` → `Done` (3 steps honnêtes).

### P2-test-1 — Drift `build_full_admin_router` *(ex-P1-8, reclassé test-infra)*
- **Fichier** : `src/handlers/admin/test_helpers.rs:48-112` vs prod `src/lib.rs:93-263`
- **Problème** : le helper `build_full_admin_router` utilisé par les tests n'inclut **pas** les endpoints suivants (présents en prod) : `skills_*` (11 routes), `reload_routes`, `llm_*` (3), `diagnostic_*` (3), `snapshot_*` (3), `ebpf_*`, `a2a/agents/*`, `hegemon/*`. Conséquence : aucune des rewrite-GW1 tests ne couvre ces handlers à travers le middleware `admin_auth`. Pire : la couverture varie en fonction du test harness — drift silencieux possible.
- **Sévérité P2 test-infra** : dette structurelle. Pas de bug runtime directement exploitable, mais sous-estime la couverture réelle et rate des régressions d'auth middleware sur ~25 routes prod.
- **Fix direction** : remplacer `test_helpers::build_*` par un re-use direct de la factory prod (`lib::build_admin_router(state)` si extraite), ou garder un seul router en prod + harnais qui appelle la même factory.

---

## Hors scope / design notes (non comptés comme bugs)

### N-1 — Couverture tests absente sur 3 modules
- **`skills.rs`** (314 LOC, 12 handlers) → 0 test inline.
- **`llm.rs`** (152 LOC, 3 handlers) → 0 test.
- **`reload.rs`** (79 LOC, 2 fonctions dont celle réutilisée hors handler) → 0 test.
- `contracts.rs` a 16 tests déportés dans `contracts/tests.rs` (OK).
- **Recommandation** : exiger dans le prochain plan que toute addition d'endpoint admin s'accompagne d'un test `#[tokio::test]` via `test_helpers::build_full_admin_router` (ou sa version unifiée prod — cf. P2-test-1). Le split GW-1 a bien isolé les domaines ; il reste à uniformiser la discipline de tests.

### N-2 — `/admin/api-proxy/backends` devrait de toute façon redacter ou tier-gater
- Même après fix de P0-2 (le mettre derrière `admin_auth`), l'endpoint expose `base_url` internes d'infra. Pour une mission bancaire/régulée, ce genre d'info devrait être redacté sauf pour un rôle `cpi-admin` (tier supérieur). Pas un bug, mais un choix de design à challenger.

### N-3 — Audit DORA : logs structurés vs tracing warn!
- L'audit log P1-4 est une **exigence**. `tracing::warn!` sans traitement downstream (append-only, immutable, horodaté, signé) ne répond pas. Le design d'un vrai pipeline audit (Kafka topic `audit.admin` + sink S3/ClickHouse) est hors scope de cet audit mais doit figurer dans le plan de fix post-revue.

---

## Priorité de fix (Rev 2, validée post-review)

### Batch P0 — micro-PRs, à shipper d'abord
1. **`admin_auth` constant-time** (P0-1) — ~15 LOC, `subtle::ConstantTimeEq`. Attention au cas longueurs différentes : check longueur puis `ct_eq` (fuite de taille acceptable) ou pad explicite. Tests inline.
2. **Déplacement `/admin/api-proxy/backends` dans `admin_router`** (P0-2) — ~10 LOC lib.rs + 2 tests `tokio::test` (401 sans token, 200 avec token).
3. **Sanitization `/admin/routes/reload`** (P1-0, ex-P0-3) — ~30 LOC + log structuré + mapping 502/503/500. Opportuniste : même PR ou batch, même reviewer.
4. **[Optionnel P0]** Rate-limit admin (P1-3) — si layer simple (`tower_governor` ~40 LOC), incluse dans le batch P0 pour renforcer P0-1.

### Batch P1 — 4-5 PRs cohérentes
1. **Contract consistency** (P1-1 + P1-2 + P2-2) — ordonnancement bind-first, propagation unbind error, longueur issue du `BindingOutput`. ~80 LOC + test d'échec binder.
2. **Admin input validation** (P1-6 + P1-9) — helpers de validation communs, tests par type d'upsert, parse URL OAuth2. ~150 LOC.
3. **Skills safety** (P1-5) — `peek` read-only sur `SkillHealthTracker`, `skills_health` + `skills_health_reset`, 404 si skill inexistant. ~50 LOC + test memory-growth.
4. **Admin rate-limit** (P1-3) — si pas fait dans batch P0. ~40 LOC.
5. **Admin audit log** (P1-4) — la plus grosse, isolée. Middleware + sink structuré. ~200 LOC + design.

### Batch P2 — cleanup groupé
- **Observability cleanup** (P2-1 health signal + P2-8 deploy steps fictifs) — ~30 LOC.
- **Admin UX consistency** (P2-3 + P2-4 + P2-5 + P2-6) — changements mécaniques. ~60 LOC.
- **LLM metrics optimization** (P2-7) — à côté d'autres évolutions LLM, pas d'urgence. ~30 LOC.
- **Test harness parity** (P2-test-1) — unification `build_admin_router` prod↔test. ~80 LOC.
- **Skills routing regression test** (P1-7) — test `DELETE /skills/status` → 405, sans fix code. ~20 LOC test only.

---

## Cluster par sous-module (vue synthèse Rev 2)

| Module | Bugs (sévérité Rev 2) | Tests inline | Notes |
|---|---|---|---|
| **`admin.rs` (façade)** | — | — | 80 LOC, re-exports propres, rien à signaler. |
| **`auth.rs`** | P0-1 | 5 | Le module le plus critique — comparaison timing-unsafe est le seul bug ici mais P0. |
| **`apis.rs`** | P1-6, P2-8 | 5 | Bonne validation de name/backend_url, mais deploy steps mensongers + id/tenant non validés. |
| **`cache.rs`** | — | 7 | RAS (le module est probablement le plus propre). |
| **`circuit_breaker.rs`** | P2-6 | 4 | État précédent non retourné, sinon propre. |
| **`contracts.rs`** | P1-1, P1-2, P2-2 | 0+16 (déportés) | Le gros trou : ordonnancement upsert/bind + silent unbind failure. |
| **`credentials.rs`** | P1-6, P1-9 | 4 | HTTPS check naïf + validation absente sur consumer_credentials. |
| **`federation.rs`** | P2-5 | 5 | RAS hors UX d'invalidation. |
| **`health.rs`** | P2-1 | 2 | Statut toujours ok. |
| **`llm.rs`** | P2-7, N-1 | 0 | Pas de tests, prometheus::gather plein-scan ; pas de bug exploitable. |
| **`mtls.rs`** | — | 2 | Délègue à `auth::mtls` — RAS dans l'admin. |
| **`policies.rs`** | P1-6 | 2 | Aucune validation entrée. |
| **`quotas.rs`** | — | 3 | RAS. |
| **`reload.rs`** | P1-0, N-1 | 0 | Endpoint critique sans tests + leak d'erreur (reclassé P1). |
| **`sessions.rs`** | — | 1 | RAS. |
| **`skills.rs`** | P1-5, P1-6, P2-3, P2-4, N-1, (P1-7 test-only) | 0 | Le module le plus dense en findings : 314 LOC, 12 handlers, 0 test. |
| **`tracing.rs`** | — | 1 | RAS. |
| **`test_helpers.rs`** | P2-test-1 | (test-only) | Drift harness test ↔ prod (reclassé P2). |
| **Wiring `lib.rs`** | P0-2, P1-3, P1-4, (P1-7 à vérifier) | — | Le *couplage* admin_router ↔ edge_base est la source du P0-2 ; rate-limit + audit log sont des manques structurels à ce niveau. |

---

## Méthode & reproductibilité

- **Greps appliqués** : unwrap/expect/panic/unreachable (hors tests), `tokio::spawn`, `std::sync::Mutex`, `unsafe {`, `danger_accept_invalid*`, `Command::new`, logs contenant token/secret/password, `Path<String>`, `starts_with("https`, validate(), audit/Audit, rate_limit, constant_time/subtle, csrf, http_client.
- **Réf calibrage** : CP-1 a donné 21 findings / 1973 LOC (≈ 1 finding / 94 LOC) ; GW-1 avec 3163 LOC "admin" sous audit donne 20 findings (≈ 1 / 158 LOC), cohérent avec la densité plus faible d'un code Rust strict + split récent (moins de pattern à cleaner que Python CP). GO-1 avait 17 / ~1400 LOC (≈ 1/82) — code en fort churn.
- **Pas d'exploit poussé jusqu'à la preuve** : P0-2 à vérifier par un simple `curl` sans token ; P0-1 théorique mais basé sur une primitive connue (exploitability dépendant de rate-limit + jitter, non chiffrée).

### Corrections apportées en Rev 2 (post-review)

| Finding | Rev 1 | Rev 2 | Raison |
|---|---|---|---|
| P0-3 → P1-0 | P0 | **P1** | Endpoint derrière admin_auth, pas de bypass direct ; hardening defense-in-depth. Reste dans le 1er batch par opportunisme. |
| P1-7 | P1 | **P2 test-only** | Comportement Axum/matchit : literal>param + MethodRouter 405 par défaut. Test de régression suffit, pas de fix code. |
| P1-8 → P2-test-1 | P1 | **P2 test-infra** | Dette test-harness, pas bug runtime. |
| P1-10 → P2-8 | P1 | **P2 (DORA-adjacent)** | Observabilité mensongère, couverte par l'audit log (P1-4). |
| P2-2 | P2 isolé | **P2 rattaché au batch contracts (P1-1/P1-2)** | Même fichier, même PR logique. |
| P0-1 formulation | "exploitable ~1h" | **"faisabilité dépendante de rate-limit+jitter, non chiffrée"** | Sans mesure infra réelle, chiffrage précis non justifié. |

---

**STOP** — phase audit terminée, Rev 2 intègre les corrections de review. Arbitrage final attendu sur : inclusion ou non de P1-3 (rate-limit) dans le batch P0, et bande passante pour P1-4 (audit log) qui demande un design dédié.
