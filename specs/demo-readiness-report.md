# STOA Demo — Readiness Report

> **Date**: 2026-04-24
> **Scope**: Évaluation du chemin démo minimal (`demo-scope.md` §2) versus état réel du monorepo.
> **Méthode**: inspection statique repo + revue `REWRITE-PLAN.md` actifs (GW-2, GO-2) + mapping endpoints cp-api et gateway.
> **Script de référence**: `scripts/demo-smoke-test.sh`

## 1. Résumé exécutif (10 lignes)

1. Les briques démo existent toutes en code : cp-api (routes apis/apps/subs/deployments présentes), stoa-gateway (`/apis/{api_name}/{*path}`, `/health`, `/metrics`), stoactl (apply/get/subscription).
2. Il n'y a **aucun test bout-en-bout** qui exerce les 5 étapes dans l'ordre sur la même instance. Le rewrite a recertifié chaque brique isolément.
3. Les rewrites actifs (GW-1 closed, GW-2 open, GO-2 validated) respectent leurs contrats internes mais aucun garde-fou démo ne protège le chemin vertical.
4. La route proxy gateway canonique est figée pour la démo : `GET /apis/{api_name}/get`. Le smoke ne probe plus plusieurs shapes.
5. Le seed existe (`make seed-dev`), mais un tenant `demo` minimal dédié smoke n'est pas garanti reproductible.
6. La métrique Prometheus attendue (`proxy_requests_total` ou `mcp_tool_calls_total`) est présente en code gateway mais son nom exact + labels ne sont pas figés dans un contrat testé ; OTEL/Grafana/Console/Portal sont maintenant cadrés en AT-5b nice-to-have.
7. L'auth API key (header `X-Api-Key`) existe gateway-side ; B1 borne maintenant le retour `api_key` cleartext au mode explicite `X-Demo-Mode: true`.
8. La stack docker-compose pré-existe (`deploy/docker-compose/docker-compose.yml`) mais son suffisance pour le smoke n'est pas validée (mock-backend non-confirmé).
9. Les specs `/specs/*.md` créés + `scripts/demo-smoke-test.sh` donnent un contrat exécutable avec verdicts non ambigus (`REAL_PASS`, `CONTRACT_DRY_RUN`, `MOCK_PASS`, `FAIL`). **Aucun run réel n'a encore été tenté**.
10. Verdict préliminaire : **FAIL attendu en premier run** sur AT-2/AT-3/AT-4. Plan "démo-first" actionnable immédiat ci-dessous.

## 2. Ce qui marche déjà (inspection statique)

### 2.1 Côté cp-api
- `POST /v1/tenants/{tid}/apis` — endpoint + tests unitaires présents (`control-plane-api/src/routers/apis.py`)
- `POST /v1/tenants/{tid}/applications` + `POST /applications/{id}/subscribe/{api_id}` — endpoint + tests
- `POST /v1/subscriptions` + logique clé API (`generate_key`, prefix) — fichier `subscriptions.py` complet
- `POST /v1/tenants/{tid}/deployments` — endpoint + schéma `DeploymentResponse`
- `GET /v1/internal/gateways/routes?gateway_name=X` — endpoint polling disponible
- `/health` sur cp-api — reconnu par scripts existants (smoke-test.sh)

### 2.2 Côté gateway
- `Router::new()` dans `src/lib.rs` :
  - `/health`, `/health/ready`, `/health/live`, `/ready`, `/metrics`
  - `/apis/{api_name}/{*path}` — fallback dynamique gateway via `RouteRegistry`
  - Mode edge-mcp par défaut (ADR-024)
- Instrumentation `tracing-subscriber` JSON par ligne (via CLAUDE.md gateway)
- Prometheus metrics registry (`src/metrics.rs`)
- Stack observabilité compose existante : Grafana, Prometheus, Loki, Data Prepper, OpenSearch, Tempo. Les datasources `OpenSearch Traces` et `Tempo` sont requises pour rendre OTEL visible dans Grafana.
- SIGHUP handler pour hot-reload routes depuis cp-api

### 2.3 Côté stoactl
- Commandes requises démo disponibles : `auth login`, `apply`, `get`, `subscription`, `gateway`, `deploy`
- Client HTTP `pkg/client/client.go` avec sous-clients catalog, audit, quota

### 2.4 Outils périphériques
- `Makefile` racine : `run-api`, `run-gateway`, `seed-dev`, `lint-*`, `test-*`
- `scripts/smoke-test.sh` (CAB-1043) — gate smoke niveau 1 basé sur URLs publiques (portal.gostoa.dev etc.) ; **pas adapté au chemin démo local** mais bon template
- `deploy/docker-compose/docker-compose.yml` — stack locale pré-existante

## 3. Ce qui manque (gap analysis)

### 3.0 Démo client/prospect séparée du smoke provider

Le parcours client/prospect n'était pas couvert par le contrat initial. Il est
maintenant cadré dans `specs/client-prospect-demo-scope.md` avec CPD-0..CPD-10.
Ce parcours couvre signup, Portal onboarding, catalogue, subscription, premier
appel, usage client, monitoring opérateur et dashboard prospects.

Il reste non bloquant pour `demo-smoke-test.sh` tant que les blockers provider
P0 ne sont pas fermés, mais il devient la référence pour toute PR touchant
Portal, signup, prospects, subscriptions UX ou usage client.

### 3.1 Contrats figés non documentés
- `architecture-rules.md` §2.2 affirme que `/apis/{api_name}/{*path}` est la surface démo officielle.
- `demo-smoke-test.sh` utilise un seul chemin canonique: `/apis/${DEMO_API_NAME}/get`.
- Format Prometheus attendu (`proxy_requests_total`) pas testé en intégration — probable drift silencieux si renommé

### 3.2 Seed démo reproductible
- `make seed-dev` seed un profile plus large que démo minimale. Besoin d'un profile `demo-smoke` qui seed UNIQUEMENT :
  - tenant `demo` avec UUID déterministe
  - gateway instance `gateway-demo` enregistrée
  - clé admin jetable `DEMO_ADMIN_TOKEN`

### 3.3 Accès clé API en cleartext (B1 traité)
Le smoke envoie `X-Demo-Mode: true`. Dans ce mode borné, `POST /v1/tenants/{tenant_id}/applications/{app_id}/subscribe/{api_id}` crée une subscription active avec hash stocké et retourne `api_key` cleartext une seule fois dans la réponse. Sans ce header, le comportement historique reste inchangé.

### 3.4 Mock backend stable dans la stack démo
`MOCK_BACKEND_URL=http://localhost:9090` est fourni par le service compose
`mock-backend`, qui expose `/ping` et `/get` en JSON stable avec `ok:true`.
Le smoke sépare cette URL de probe locale de `MOCK_BACKEND_UPSTREAM_URL`,
qui vaut `http://mock-backend:9090` en compose pour que la gateway ne cible
pas `localhost` depuis son propre conteneur.
Ce point ferme B2 pour AT-0. AT-4 peut maintenant cibler un backend local
déterministe dès que la stack locale dépasse AT-0/AT-2
exploitable.

### 3.5 Chemin proxy gateway figé
Le chemin gateway démo est canonique : `{GATEWAY_URL}/apis/{api_name}/get`.
`api_name` désigne le slug retourné par `POST /v1/tenants/{tid}/apis`
(`demo-api-smoke` par défaut). Le smoke utilise ce chemin unique.

### 3.6 Auth bypass dev non documenté
Le script smoke autorise `DEMO_ADMIN_TOKEN=""` en fallback, mais aucune variable `STOA_DISABLE_AUTH` ou flag équivalent n'est documenté côté cp-api. Probable que la démo échoue silencieusement en 401/403 sur AT-1 sans JWT Keycloak valide.

### 3.7 Route-sync latence
Polling 30s par défaut dans stoa-connect → AT-2 peut timeout. Mitigation dans script : `ROUTE_SYNC_GRACE_SECS=30` + probe explicite de `GET /v1/internal/gateways/routes`. En prod démo, ajouter un `POST /internal/gateways/{id}/trigger-sync` dédié ferait gagner du temps.

## 4. Blockers réels (à résoudre avant smoke `REAL_PASS`)

| # | Blocker | Sévérité | Étape impactée | Owner suggéré |
|---|---------|----------|----------------|---------------|
| B1 | Clé API cleartext exposée une seule fois en mode `X-Demo-Mode: true` | DONE | AT-3 → AT-4 | cp-api PR B1 |
| B2 | Mock backend non seedé dans docker-compose | P0 | AT-0, AT-4 | **DONE** — `mock-backend` compose |
| B3 | Mapping `api_name → proxy path` flou côté gateway | P0 | AT-4 | **DONE** — `/apis/{api_name}/get` |
| B4 | Auth dev-bypass cp-api non documenté | DONE | AT-1, AT-2, AT-3 | `STOA_DISABLE_AUTH=true` dev-only + `X-Demo-Mode: true` |
| B5 | Payload/seed démo non aligné modèle réel | DONE | AT-2, AT-3 | `DEMO_DEPLOY_ENV=dev` + `display_name` application |
| B6 | Métriques Prometheus noms non figés par test | P2 | AT-5 | gateway (test regression) |
| B7 | Route-sync 30s est lent pour une démo live | P2 | AT-2 | stoa-connect (trigger endpoint) |
| B8 | OTEL visible en UI non prouvé automatiquement | P3 | AT-5b | observability/ui (nice-to-have) |
| C-B1 | Démo client/prospect non automatisée (seed + UI + conversion) | P1 | CPD-0..CPD-10 | portal/console/cp-api |

## 5. Contournements acceptables pendant le rewrite

Pour débloquer rapidement la validation du contrat sans confondre script OK et démo prête :

| Contournement | Cible | Durée | Risque |
|---------------|-------|-------|--------|
| `./scripts/demo-smoke-test.sh --dry-run-contract` | Tous | permanent | Valide le contrat/script, verdict `CONTRACT_DRY_RUN`, jamais `DEMO READY` |
| `MOCK_MODE=all ./scripts/demo-smoke-test.sh` | stack absente | usage local | Valide le chemin mocké, verdict `MOCK_PASS`, jamais `DEMO READY` |
| Démarrer `mock-backend` via compose seul (`docker compose ... up -d mock-backend`) | B2 | jusqu'à stack complète | Service sous profil `demo`; ne pas exposer Prometheus sur le même port pendant ce smoke |
| `DEMO_GATEWAY_PATH` override local | B3 | debug uniquement | Toute démo officielle doit revenir à `/apis/{api_name}/get` |
| `STOA_DISABLE_AUTH=true` + `X-Demo-Mode: true` | B4 | jusqu'à auth Keycloak démo stable | Refusé en `ENVIRONMENT=production`; ne jamais présenter comme auth réelle |
| Script seed inline dans `demo-smoke-test.sh` qui crée tenant + gateway si absent | Seed futur | 1 jour | Pas idempotent si collisions |
| Check "au moins un counter `*_total`" sans figer nom | B6 | jusqu'à B6 | Drift silencieux toléré |

Ces contournements **sont figés dans le script**, mais ils ne produisent jamais
`REAL_PASS`. À chaque blocker fermé, on resserre la vérification.

## 6. Prochaine PR prioritaire

**PR `chore(demo): add demo-first scaffolding`** — PR de cadrage demo-first :

1. Commit 1 — specs+script : ce batch de fichiers `/specs/*.md` + `/scripts/demo-smoke-test.sh` (créé dans cette session)
2. Commit 2 — `deploy/docker-compose/docker-compose.demo.yml` : extension de `docker-compose.yml` qui ajoute `mock-backend` (httpbin) sur port 9090 + `.env.demo` avec defaults documentés
3. Commit 3 — `Makefile` targets : `demo-up`, `demo-down`, `demo-smoke` (le dernier wrappe `./scripts/demo-smoke-test.sh`)

La PR de cadrage posait le contrat sans code applicatif. B1 est maintenant traité par une PR ciblée cp-api + smoke, sans refonte sécurité ni lifecycle complet.

## 7. Verdict GO / NO-GO rewrite

**GO** sur la poursuite du rewrite actuel, **sous les 4 conditions**:

1. La PR prioritaire §6 est mergée dans la semaine (contrat démo actif en repo)
2. Chaque PR rewrite en cours (GW-2, GO-2, CP-*) ajoute la section "Demo impact" dans sa description (cf. `rewrite-guardrails.md` §4)
3. Dès le 1er run smoke `REAL_PASS` localement, `scripts/demo-smoke-test.sh` est ajouté en CI (workflow `.github/workflows/demo-smoke.yml`) avec `docker-compose.demo.yml` comme stack de test
4. Le parcours client/prospect a au minimum un seed idempotent + une checklist CPD-0..CPD-10 exécutable manuellement avant toute démo commerciale

**NO-GO** si :

- Aucune PR rewrite ne documente son "demo impact" dans les 7 jours → les rewrites avancent hors radar démo
- Un nouveau blocker P0 sur AT-3/AT-4 reste ouvert > 10 jours → indiquerait que la démo n'est pas priorité réelle
- Une régression AT-1..AT-5 est observée sans rollback immédiat
- Un `MOCK_PASS` ou `CONTRACT_DRY_RUN` est présenté comme `DEMO READY`

**Recommandation opérationnelle** : **GO conditionnel**. Le rewrite est qualitatif (plans GW-2/GO-2 rigoureux), mais il s'exécute sans contrat démo vérifiable. Les fichiers `/specs/` + `scripts/demo-smoke-test.sh` posés aujourd'hui sont le minimum pour transformer le rewrite en livraison démo-first.

## 8. Historique

| Date | Version | Auteur | Delta |
|------|---------|--------|-------|
| 2026-04-24 | v1.0 | Claude (session `/demo-scope`) | Création initiale, 7 blockers identifiés, verdict GO conditionnel |
